"""Notification settings (monishield/application/alert_service.py), admin only. Stored in the .env file.
  GET  /api/admin/alerts        settings (credentials only "set") + history of the latest sends
  PUT  /api/admin/alerts        write to .env; empty credential field = unchanged, `clear` = remove
  POST /api/admin/alerts/test   send a test message to one channel (using the SAVED settings)
  POST /api/admin/alerts/report daily report of one folder now (again if it already went out), or every report not sent yet
"""
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from monishield.application import alert_service
from monishield.domain.errors import Fail
from .admin import _audit
from .common import require_admin

router = APIRouter(prefix='/api/admin/alerts')


@router.get('')
def get_alerts(request: Request, admin=Depends(require_admin)):
    return alert_service.view(request.app.state)


class AlertsBody(BaseModel):
    channels: dict = {}
    events: dict = {}
    lang: str | None = None
    dashboard_url: str | None = None
    missing_hour: int | None = None
    summary_hour: int | None = None
    spike: dict | None = None            # {number: {factor, min} | null (off)}
    service_spike: dict | None = None    # {default: {factor, min} | null, services: {service: {factor, min} | null}}
    clear: list = []


@router.put('')
def put_alerts(body: AlertsBody, request: Request, admin=Depends(require_admin)):
    cfg = alert_service.update(request.app.state, {k: v for k, v in body.model_dump().items() if v is not None})
    on = [n for n, c in cfg['channels'].items() if c['enabled']]
    _audit(request, admin, 'alerts.update', f"active channels: {', '.join(on) or 'none'}")   # no credentials
    return alert_service.view(request.app.state)


class TestBody(BaseModel):
    channel: str


@router.post('/test')
def test_alert(body: TestBody, request: Request, admin=Depends(require_admin)):
    try: r = alert_service.send_test(request.app.state, body.channel)
    except Fail as e:
        if e.code == 'alert_send_failed': _audit(request, admin, 'alerts.test', f'{body.channel}: failed')
        raise
    _audit(request, admin, 'alerts.test', f'{body.channel}: succeeded')
    return r


class ReportBody(BaseModel):
    folder: str | None = None
    source: str = 's3'
    pending: bool = False   # true = every report among the latest folders that has not gone out yet


@router.post('/report')
def send_report(body: ReportBody, request: Request, admin=Depends(require_admin)):
    r = alert_service.send_report(request.app.state, body.folder, body.source, body.pending)
    what = 'reports not sent yet' if body.pending else f'{body.folder} ({body.source})'
    _audit(request, admin, 'alerts.report', f"{what}: {len(r['sent'])} sent, {len(r['failed'])} failed")
    return r
