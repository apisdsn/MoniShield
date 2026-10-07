"""Dokumentasi API interaktif (permintaan pemilik 2026-10-07): Swagger UI di /api/docs dan skema di /api/openapi.json.
Hanya untuk user yang sudah masuk lewat halaman login yang sama (cookie sesi) dan sudah mengganti sandi awal; belum
masuk -> diarahkan ke halaman login lalu kembali ke sini. "Try it out" memakai sesi itu, jadi setiap rute tetap tunduk
pada perannya (user biasa melihat rute admin tetapi mendapat 403). Aset Swagger UI dari server sendiri (CSP 'self')."""
from fastapi import APIRouter, Depends, Request
from fastapi.openapi.utils import get_openapi
from fastapi.responses import HTMLResponse, RedirectResponse

from monishield import __version__
from .common import ApiError, public, require_user, require_user_ready

router = APIRouter(prefix='/api')

DESCRIPTION = """Dashboard log dan keamanan MoniShield. Semua waktu UTC kecuali disebut lain; folder log = tanggal WIB (YYYY-MM-DD).

**Masuk**: buka halaman login MoniShield dengan akun yang sama; cookie sesi dipakai otomatis oleh halaman ini.
Permintaan yang mengubah data (POST/PUT/PATCH/DELETE) wajib membawa header `X-Requested-With` (ditambahkan otomatis
di sini). **Token mesin** (`S4_JOB_TOKEN`) hanya berlaku untuk rute ingest dan impor: tombol *Authorize* → `jobToken`.

Peran: `admin` untuk rute `/api/admin/*`, selain itu user yang sudah masuk. Galat selalu berbentuk
`{"error": {"code": "...", "message": "..."}}`.

*EN*: sign in on the MoniShield login page with the same account; this page uses that session cookie. Requests that
change data need the `X-Requested-With` header (added here automatically). The machine token (`S4_JOB_TOKEN`) only works
for ingest/import routes (*Authorize* → `jobToken`). `/api/admin/*` needs the admin role."""

# Kelompok di Swagger menurut awalan jalur utuh per segmen (yang pertama cocok; /api/me bukan /api/meta); urutan = urutan tampil
TAGS = [('/api/auth', 'Masuk & sesi / Session'), ('/api/me', 'Masuk & sesi / Session'), ('/api/admin/users', 'User (admin)'),
        ('/api/admin/import', 'Impor & sinkron S3 / S3 import & sync (admin)'), ('/api/admin/upload', 'Unggah folder / Folder upload (admin)'),
        ('/api/admin/kafka', 'Kafka (admin)'), ('/api/live', 'Realtime (Kafka)'),
        ('/api/admin', 'Ingest, folder & audit (admin)'), ('/api/folders/{folder}/tables', 'Tabel / Tables'),
        ('/api/folders', 'Halaman per folder / Folder pages'), ('/api', 'Umum / General')]

PAGE = """<!doctype html>
<html lang="id"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>API · MoniShield</title><link rel="icon" href="/favicon.svg"><link rel="stylesheet" href="/swagger/swagger-ui.css">
<style>body{margin:0}.topbar{display:none}.mshead{display:flex;align-items:center;gap:12px;padding:12px 20px;background:#0b1015;color:#e6edf3;font:600 15px system-ui,sans-serif}
.mshead a{color:#2dd4bf;margin-left:auto;font-weight:500;text-decoration:none}</style></head>
<body><div class="mshead"><svg width="26" height="26" viewBox="0 0 32 32" aria-hidden="true"><path d="M16 2l12 4.5v8.2c0 7.3-5 13.4-12 15.3C9 28.1 4 22 4 14.7V6.5z" fill="#2dd4bf"/>
<path d="M10 21V11l6 6 6-6v10" fill="none" stroke="#04201c" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/></svg>MoniShield API<a href="/">&larr; Dashboard</a></div><div id="swagger-ui"></div>
<script src="/swagger/swagger-ui-bundle.js"></script><script src="/swagger/init.js"></script></body></html>"""


def schema(app):
    """Skema OpenAPI dengan cara masuk yang dipakai MoniShield (dibuat sekali, disimpan di app)."""
    if not getattr(app.state, 'openapi', None):
        s = get_openapi(title='MoniShield API', version=__version__, description=DESCRIPTION, routes=app.routes)
        s.setdefault('components', {})['securitySchemes'] = {
            'session': {'type': 'apiKey', 'in': 'cookie', 'name': 's4_session', 'description': 'Cookie dari halaman login (otomatis).'},
            'jobToken': {'type': 'http', 'scheme': 'bearer', 'description': 'S4_JOB_TOKEN, hanya untuk rute ingest/impor.'}}
        s['security'] = [{'session': []}]
        for path, ops in s.get('paths', {}).items():
            for op in ops.values():
                if isinstance(op, dict): op['tags'] = [next(t for pre, t in TAGS if path == pre or path.startswith(pre + '/'))]
        s['tags'] = [dict(name=t) for t in dict.fromkeys(t for _, t in TAGS)]
        app.state.openapi = s
    return app.state.openapi


@router.get('/docs', include_in_schema=False, dependencies=[Depends(public)])
def docs(request: Request):
    """Belum masuk / belum ganti sandi -> halaman login dengan ?next=/api/docs (SPA kembali ke sini sesudahnya)."""
    try: require_user_ready(require_user(request))
    except ApiError: return RedirectResponse('/?next=/api/docs', status_code=303)
    return HTMLResponse(PAGE, headers={'Cache-Control': 'no-store'})


@router.get('/openapi.json', include_in_schema=False)
def openapi(request: Request, user=Depends(require_user_ready)):
    return schema(request.app)
