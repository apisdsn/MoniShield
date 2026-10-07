"""Yang dipakai semua router: galat, peran, validasi parameter (TRD §8.1), akses DuckDB."""
import datetime, re

from fastapi import Depends, HTTPException, Request, Response

from monishield.infrastructure import auth as authmod

COOKIE = 's4_session'
CSRF_HEADER = 'x-requested-with'      # wajib pada setiap permintaan yang mengubah data (TRD §8.2)
DATE = re.compile(r'\d{4}-\d\d-\d\d')


class ApiError(HTTPException):
    def __init__(self, status, code, message): super().__init__(status_code=status, detail=dict(code=code, message=message))


def client_ip(request: Request):
    cfg = request.app.state.cfg
    if cfg.trust_proxy and (xff := request.headers.get('x-forwarded-for')): return xff.split(',')[0].strip()[:64]
    return request.client.host if request.client else None


# ------------------------------------------------------------------ peran (TRD §8.3)
# Setiap rute /api WAJIB memakai salah satu dependensi di bawah (atau terdaftar publik); app.py menolak mulai bila tidak.
def public(): return None


def _session_user(request: Request):
    return request.app.state.auth.session_user(request.cookies.get(COOKIE))


def _check_csrf(request: Request):
    """Cookie SameSite=Strict + header khusus + Origin yang cocok untuk semua metode yang mengubah data."""
    if request.method in ('GET', 'HEAD', 'OPTIONS'): return
    if not request.headers.get(CSRF_HEADER): raise ApiError(403, 'csrf', 'Permintaan ditolak: header X-Requested-With tidak ada.')
    origin = request.headers.get('origin')
    if origin and origin.split('://', 1)[-1] != request.headers.get('host'):
        raise ApiError(403, 'csrf', 'Permintaan ditolak: asal (Origin) tidak cocok.')


def require_user(request: Request):
    user = _session_user(request)
    if not user: raise ApiError(401, 'unauthenticated', 'Belum masuk atau sesi sudah berakhir.')
    _check_csrf(request)
    request.state.user = user
    return user


def require_user_ready(user=Depends(require_user)):
    """User yang sudah mengganti sandi awalnya; sebelum itu hanya /api/me dan ganti sandi yang boleh."""
    if user['must_change_password']: raise ApiError(403, 'must_change_password', 'Ganti sandi dulu sebelum melanjutkan.')
    return user


def require_admin(user=Depends(require_user_ready)):
    if user['role'] != 'admin': raise ApiError(403, 'forbidden', 'Halaman ini hanya untuk admin.')
    return user


def require_admin_or_job(request: Request):
    """Admin, atau pemanggil mesin ber-token (tugas ingest, pengirim tautan S3). Token hanya berlaku di rute yang memakai dependensi ini."""
    bearer = request.headers.get('authorization', '')
    if bearer.lower().startswith('bearer '):
        if authmod.job_token_ok(request.app.state.cfg.job_token, bearer[7:].strip()):
            request.state.user = None
            return dict(user_id=None, username='(token mesin)', role='job')
        raise ApiError(401, 'unauthenticated', 'Token mesin tidak dikenal.')
    return require_admin(require_user_ready(require_user(request)))


ROLE_DEPS = (public, require_user, require_user_ready, require_admin, require_admin_or_job)


# ------------------------------------------------------------------ DuckDB
def cursor(request: Request):
    """Satu kursor per permintaan atas koneksi tunggal proses ini (TRD K1). Pembaca tidak terblokir oleh ingest."""
    cur = request.app.state.con.cursor()
    try: yield cur
    finally: cur.close()


def folder_param(folder: str, response: Response, cur=Depends(cursor)):
    """`folder` harus YYYY-MM-DD yang sah DAN sudah ter-ingest; selain itu 404 (TRD §8.1). Memasang ETag folder itu (TRD §5.1)."""
    if not DATE.fullmatch(folder): raise ApiError(404, 'not_found', 'Folder tidak ditemukan.')
    try: datetime.date.fromisoformat(folder)
    except ValueError: raise ApiError(404, 'not_found', 'Folder tidak ditemukan.') from None
    r = cur.execute('SELECT derived_at FROM folder_state WHERE folder = ?', [folder]).fetchone()
    if not r: raise ApiError(404, 'not_found', 'Folder tidak ditemukan.')
    # ponytail: ETag dikirim, 304 belum dijawab (respons tetap no-store); tambahkan bila halaman terukur lambat di jaringan.
    if r[0]: response.headers['ETag'] = f'"{folder}-{r[0]:%Y%m%d%H%M%S}"'
    return folder

