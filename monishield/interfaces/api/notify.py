"""Setelan notifikasi (monishield/application/alert_service.py), admin saja. Disimpan di file .env.
  GET  /api/admin/alerts        setelan (kredensial hanya "sudah diisi") + riwayat kiriman terakhir
  PUT  /api/admin/alerts        tulis ke .env; kolom kredensial kosong = tidak diubah, `clear` = hapus
  POST /api/admin/alerts/test   kirim pesan uji ke satu saluran (memakai setelan TERSIMPAN)
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
    clear: list = []


@router.put('')
def put_alerts(body: AlertsBody, request: Request, admin=Depends(require_admin)):
    cfg = alert_service.update(request.app.state, {k: v for k, v in body.model_dump().items() if v is not None})
    on = [n for n, c in cfg['channels'].items() if c['enabled']]
    _audit(request, admin, 'alerts.update', f"saluran aktif: {', '.join(on) or 'tidak ada'}")   # tanpa kredensial
    return alert_service.view(request.app.state)


class TestBody(BaseModel):
    channel: str


@router.post('/test')
def test_alert(body: TestBody, request: Request, admin=Depends(require_admin)):
    try: r = alert_service.send_test(request.app.state, body.channel)
    except Fail as e:
        if e.code == 'alert_send_failed': _audit(request, admin, 'alerts.test', f'{body.channel}: gagal')
        raise
    _audit(request, admin, 'alerts.test', f'{body.channel}: berhasil')
    return r
