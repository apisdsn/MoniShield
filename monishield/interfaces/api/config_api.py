"""Konfigurasi: semua kredensial dan setelan yang boleh diisi dari layar, di satu tempat, admin saja. Semuanya DITULIS KE
FILE .env (monishield/application/settings_service.py) dan langsung berlaku.
  GET  /api/admin/config        status tiap kelompok (rahasia hanya "sudah diisi" + sumber) + status file .env + kunci yang hanya lewat .env
  PUT  /api/admin/config        tulis ke .env; kolom rahasia kosong = tidak diubah, `clear` = baris dinonaktifkan (nilai bawaan)
  POST /api/admin/config/test   uji koneksi memakai setelan TERSIMPAN: {kind: 'aws'} (daftar 1 objek di S3) atau
                                {kind: 'maxmind'} (minta tautan unduhan GeoLite2; hanya otorisasi, tanpa mengunduh)
Folder induk S3 otomatis dan notifikasi punya API sendiri (/api/admin/import/watch, /api/admin/alerts); halaman
Konfigurasi memakai keduanya.
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
    # kartu Kafka (Rancher cluster logging -> Kafka); kolom yang tidak disebut di sini dibuang diam-diam oleh pydantic
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
    clear: list[str] = []


@router.put('')
def put_config(body: ConfigBody, request: Request, admin=Depends(require_admin)):
    groups = settings_service.update(request.app.state, {k: v for k, v in body.model_dump().items() if v is not None})
    _audit(request, admin, 'config.update', f"kelompok: {', '.join(groups) or 'tidak ada'} (.env)")   # tanpa nilai
    if 'kafka' in groups:   # konsumen dimulai ulang dengan setelan baru (di latar: menunggu poll berjalan selesai)
        threading.Thread(target=request.app.state.kafka.restart, name='kafka-restart', daemon=True).start()
    return settings_service.view(request.app.state)


class TestBody(BaseModel):
    kind: str


@router.post('/test')
def test_config(body: TestBody, request: Request, admin=Depends(require_admin)):
    try: r = settings_service.test_connection(request.app.state, body.kind)
    except Fail as e:
        _audit(request, admin, 'config.test', f'{body.kind}: gagal ({e.code})'); raise
    _audit(request, admin, 'config.test', f'{body.kind}: berhasil')
    return r
