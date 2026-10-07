"""Setelan notifikasi (monishield/alerts.py), admin saja.
  GET  /api/admin/alerts        setelan (kredensial hanya "sudah diisi") + riwayat kiriman terakhir
  PUT  /api/admin/alerts        simpan; kolom kredensial kosong = tidak diubah, `clear` = hapus
  POST /api/admin/alerts/test   kirim pesan uji ke satu saluran (memakai setelan TERSIMPAN)
"""
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from .. import alerts
from .admin import _audit
from .common import ApiError, require_admin

router = APIRouter(prefix='/api/admin/alerts')


def _view(request):
    auth = request.app.state.auth
    return dict(alerts.public(alerts.load(auth)), events_all=list(alerts.EVENTS), history=auth.alert_list(30))


@router.get('')
def get_alerts(request: Request, admin=Depends(require_admin)):
    return _view(request)


class AlertsBody(BaseModel):
    channels: dict = {}
    events: dict = {}
    lang: str | None = None
    dashboard_url: str | None = None
    missing_hour: int | None = None
    clear: list = []


@router.put('')
def put_alerts(body: AlertsBody, request: Request, admin=Depends(require_admin)):
    auth = request.app.state.auth
    data = {k: v for k, v in body.model_dump().items() if v is not None}
    try: cfg = alerts.merge(alerts.load(auth), data)
    except alerts.AlertFail as e: raise ApiError(400, 'invalid_alerts', str(e)) from None
    except (TypeError, ValueError): raise ApiError(400, 'invalid_parameter', 'Isian notifikasi tidak sah.') from None
    auth.setting_set('alerts', cfg, admin['username'])
    on = [n for n, c in cfg['channels'].items() if c['enabled']]
    _audit(request, admin, 'alerts.update', f"saluran aktif: {', '.join(on) or 'tidak ada'}")   # tanpa kredensial
    return _view(request)


class TestBody(BaseModel):
    channel: str


@router.post('/test')
def test_alert(body: TestBody, request: Request, admin=Depends(require_admin)):
    if body.channel not in alerts.SENDERS: raise ApiError(400, 'invalid_parameter', 'Saluran tidak dikenal.')
    auth = request.app.state.auth
    cfg = alerts.load(auth)
    ch = cfg['channels'][body.channel]
    try: alerts.validate(cfg)
    except alerts.AlertFail as e: raise ApiError(400, 'invalid_alerts', str(e)) from None
    need = dict(telegram=('bot_token', 'chat_id'), discord=('webhook_url',), email=('host', 'sender', 'to'))[body.channel]
    if not all(ch[k] for k in need): raise ApiError(400, 'alert_not_configured', 'Lengkapi dan simpan isian saluran ini dulu.')
    import time
    r = alerts.deliver(auth, cfg, f'test:{body.channel}:{time.time()}', 'test', alerts._t(cfg, 'test'), alerts._t(cfg, 'test_text'),
                       channels=[body.channel], force=True)
    _audit(request, admin, 'alerts.test', f"{body.channel}: {'berhasil' if r.get(body.channel) is None else 'gagal'}")
    if r.get(body.channel): raise ApiError(502, 'alert_send_failed', f'Gagal mengirim ke {body.channel}: {r[body.channel]}.')
    return dict(sent=True, channel=body.channel)
