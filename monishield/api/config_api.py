"""Konfigurasi: semua kredensial dan setelan yang boleh diisi dari layar, di satu tempat, admin saja. Semuanya DITULIS KE
FILE .env (monishield/settings.py, monishield/envfile.py) dan langsung berlaku.
  GET  /api/admin/config        status tiap kelompok (rahasia hanya "sudah diisi" + sumber) + status file .env + kunci yang hanya lewat .env
  PUT  /api/admin/config        tulis ke .env; kolom rahasia kosong = tidak diubah, `clear` = baris dinonaktifkan (nilai bawaan)
  POST /api/admin/config/test   uji koneksi memakai setelan TERSIMPAN: {kind: 'aws'} (daftar 1 objek di S3) atau
                                {kind: 'maxmind'} (minta tautan unduhan GeoLite2; hanya otorisasi, tanpa mengunduh)
Folder induk S3 otomatis dan notifikasi punya API sendiri (/api/admin/import/watch, /api/admin/alerts); halaman
Konfigurasi memakai keduanya.
"""
import base64, urllib.error, urllib.request

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from .. import importer, settings
from .admin import _audit
from .common import ApiError, require_admin

router = APIRouter(prefix='/api/admin/config')


@router.get('')
def get_config(request: Request, admin=Depends(require_admin)):
    return settings.view(request.app)


class ConfigBody(BaseModel):
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None
    aws_session_token: str | None = None
    import_region: str | None = None
    maxmind_account_id: str | None = None
    maxmind_license_key: str | None = None
    blocklist_exclude: str | None = None
    blocklist_exclude_org: str | None = None
    clear: list[str] = []


@router.put('')
def put_config(body: ConfigBody, request: Request, admin=Depends(require_admin)):
    data = {k: v for k, v in body.model_dump().items() if v is not None}
    try: groups = settings.update(request.app, data)
    except settings.SettingsFail as e: raise ApiError(400, e.code, str(e)) from None
    _audit(request, admin, 'config.update', f"kelompok: {', '.join(groups) or 'tidak ada'} (.env)")   # tanpa nilai
    return settings.view(request.app)


class TestBody(BaseModel):
    kind: str


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k): return None   # 302 = kunci diterima; tautan unduhan tidak diikuti


def _test_aws(app):
    cfg, imports = app.state.cfg, app.state.imports
    if not importer.library_ok(): raise ApiError(400, 'no_s3_library', importer.NO_LIBRARY)
    creds, source = imports.creds.get()
    if not creds: raise ApiError(400, 'no_credentials', importer.NO_CREDENTIALS)
    w = imports.watch_config()
    try: targets = importer.parse_watch(cfg, w['url']) if w['url'] else []
    except importer.ImportFail: targets = []
    targets = targets or [(b, p) for b, ps in sorted(cfg.import_buckets.items()) for p in ps][:1]
    if not targets: raise ApiError(400, 'import_disabled', 'Impor S3 tidak diaktifkan: daftar izin S4_IMPORT_BUCKETS di .env kosong.')
    bucket, prefix = targets[0]
    try: importer._client(cfg, creds).list_objects_v2(Bucket=bucket, Prefix=prefix, MaxKeys=1)
    except Exception as e:   # noqa: BLE001
        f = importer._s3_error(e)
        raise ApiError(f.status, f.code, f.message) from None
    return dict(ok=True, kind='aws', target=f's3://{bucket}/{prefix}', source=source)


def _test_maxmind(app):
    cfg = app.state.cfg
    if not (cfg.maxmind_account_id and cfg.maxmind_license_key):
        raise ApiError(400, 'maxmind_missing', 'Account ID dan License key MaxMind belum diisi.')
    if cfg.offline: raise ApiError(400, 'offline', 'Server dalam mode luring (S4_OFFLINE); uji koneksi tidak dijalankan.')
    auth = base64.b64encode(f'{cfg.maxmind_account_id}:{cfg.maxmind_license_key}'.encode()).decode()
    req = urllib.request.Request(cfg.url_maxmind.format('GeoLite2-City-CSV'), method='HEAD',
                                 headers={'Authorization': 'Basic ' + auth, 'User-Agent': 'monishield/2.0'})
    try:
        with urllib.request.build_opener(_NoRedirect).open(req, timeout=20) as r: code = r.status
    except urllib.error.HTTPError as e: code = e.code
    except OSError as e: raise ApiError(502, 'maxmind_unreachable', f'MaxMind tidak terjangkau dari server ({type(e).__name__}).') from None
    if code in (401, 403): raise ApiError(502, 'maxmind_denied', f'MaxMind menolak kunci ({code}): periksa Account ID dan License key.')
    if code not in (200, 302, 303, 307): raise ApiError(502, 'maxmind_error', f'MaxMind menjawab {code}.')
    return dict(ok=True, kind='maxmind')


@router.post('/test')
def test_config(body: TestBody, request: Request, admin=Depends(require_admin)):
    fn = dict(aws=_test_aws, maxmind=_test_maxmind).get(body.kind)
    if not fn: raise ApiError(400, 'invalid_parameter', 'Jenis uji tidak dikenal.')
    try: r = fn(request.app)
    except ApiError as e:
        _audit(request, admin, 'config.test', f"{body.kind}: gagal ({e.detail['code']})"); raise
    _audit(request, admin, 'config.test', f'{body.kind}: berhasil')
    return r
