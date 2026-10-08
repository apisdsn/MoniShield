"""Configuration: all credentials and settings that may be filled in from the UI, in one place, admin only. Everything is
WRITTEN TO THE .env FILE (monishield/application/settings_service.py) and takes effect immediately.
  GET  /api/admin/config        status of each group (secrets only "set" + source) + .env file status + keys only settable via .env
  PUT  /api/admin/config        write to .env; empty secret field = unchanged, `clear` = line disabled (default value)
  POST /api/admin/config/test   test the connection with the SAVED settings: {kind: 'aws'} (list 1 object in S3) or
                                {kind: 'maxmind'} (request a GeoLite2 download link; authorization only, no download)
                                {kind: 'smtp', to?} (send the test letter; default recipient: the admin's own email)
The automatic S3 parent folder and notifications have their own APIs (/api/admin/import/watch, /api/admin/alerts); the
Configuration page uses both.
"""
import threading

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from monishield.application import settings_service
from monishield.domain.errors import Fail
from .admin import _audit
from .common import require_admin

router = APIRouter(prefix='/api/admin/config')


@router.get('')
def get_config(request: Request, admin=Depends(require_admin)):
    return settings_service.view(request.app.state)


class ConfigBody(BaseModel):
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None
    aws_session_token: str | None = None
    import_region: str | None = None
    maxmind_account_id: str | None = None
    maxmind_license_key: str | None = None
    blocklist_exclude: str | None = None
    blocklist_exclude_org: str | None = None
    # Kafka card (Rancher cluster logging -> Kafka); fields not listed here are silently dropped by pydantic
    kafka_enabled: bool | None = None
    kafka_brokers: str | None = None
    kafka_topic: str | None = None
    kafka_group: str | None = None
    kafka_security: str | None = None
    kafka_sasl_mechanism: str | None = None
    kafka_username: str | None = None
    kafka_password: str | None = None
    kafka_offset_reset: str | None = None
    kafka_ingest_minutes: str | int | None = None
    smtp_host: str | None = None
    smtp_port: str | int | None = None
    smtp_security: str | None = None
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from: str | None = None
    retention_days: str | int | None = None
    retention_inbox_days: str | int | None = None
    clear: list[str] = []


@router.put('')
def put_config(body: ConfigBody, request: Request, admin=Depends(require_admin)):
    groups = settings_service.update(request.app.state, {k: v for k, v in body.model_dump().items() if v is not None})
    _audit(request, admin, 'config.update', f"groups: {', '.join(groups) or 'none'} (.env)")   # no values
    if 'kafka' in groups:   # consumer restarted with the new settings (in the background: waits for the running poll to finish)
        threading.Thread(target=request.app.state.kafka.restart, name='kafka-restart', daemon=True).start()
    return settings_service.view(request.app.state)


class TestBody(BaseModel):
    kind: str
    to: str | None = None     # smtp: recipient of the test email (default: the admin's own email)
    lang: str | None = None   # smtp: language of the test email (the page language)


@router.post('/test')
def test_config(body: TestBody, request: Request, admin=Depends(require_admin)):
    try: r = settings_service.test_connection(request.app.state, body.kind, to=body.to or admin.get('email'), lang=body.lang if body.lang in ('id', 'en') else None)
    except Fail as e:
        _audit(request, admin, 'config.test', f'{body.kind}: failed ({e.code})'); raise
    _audit(request, admin, 'config.test', f'{body.kind}: succeeded')
    return r
