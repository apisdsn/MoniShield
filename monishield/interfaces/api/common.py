"""Shared by all routers: errors, roles, parameter validation (TRD §8.1), DuckDB access."""
import datetime, re

from fastapi import Depends, HTTPException, Request, Response

from monishield.infrastructure import auth as authmod

COOKIE = 's4_session'
CSRF_HEADER = 'x-requested-with'      # required on every request that changes data (TRD §8.2)
DATE = re.compile(r'\d{4}-\d\d-\d\d')


class ApiError(HTTPException):
    def __init__(self, status, code, message): super().__init__(status_code=status, detail=dict(code=code, message=message))


def client_ip(request: Request):
    cfg = request.app.state.cfg
    if cfg.trust_proxy and (xff := request.headers.get('x-forwarded-for')): return xff.split(',')[0].strip()[:64]
    return request.client.host if request.client else None


# ------------------------------------------------------------------ roles (TRD §8.3)
# Every /api route MUST use one of the dependencies below (or be registered public); app.py refuses to start otherwise.
def public(): return None


def _session_user(request: Request):
    return request.app.state.auth.session_user(request.cookies.get(COOKIE))


def _check_csrf(request: Request):
    """SameSite=Strict cookie + custom header + matching Origin for every method that changes data."""
    if request.method in ('GET', 'HEAD', 'OPTIONS'): return
    if not request.headers.get(CSRF_HEADER): raise ApiError(403, 'csrf', 'Request rejected: X-Requested-With header missing.')
    origin = request.headers.get('origin')
    if origin and origin.split('://', 1)[-1] != request.headers.get('host'):
        raise ApiError(403, 'csrf', 'Request rejected: Origin does not match.')


def require_user(request: Request):
    user = _session_user(request)
    if not user: raise ApiError(401, 'unauthenticated', 'Not signed in or the session has expired.')
    _check_csrf(request)
    request.state.user = user
    return user


def require_user_ready(user=Depends(require_user)):
    """A user who has changed their initial password; before that only /api/me and changing the password are allowed."""
    if user['must_change_password']: raise ApiError(403, 'must_change_password', 'Change your password before continuing.')
    return user


def require_admin(user=Depends(require_user_ready)):
    if user['role'] != 'admin': raise ApiError(403, 'forbidden', 'This page is for admins only.')
    return user


def require_admin_or_job(request: Request):
    """Admin, or a machine caller with a token (ingest job, S3 link sender). The token only works on routes using this dependency."""
    bearer = request.headers.get('authorization', '')
    if bearer.lower().startswith('bearer '):
        if authmod.job_token_ok(request.app.state.cfg.job_token, bearer[7:].strip()):
            request.state.user = None
            return dict(user_id=None, username='(machine token)', role='job')
        raise ApiError(401, 'unauthenticated', 'Unknown machine token.')
    return require_admin(require_user_ready(require_user(request)))


ROLE_DEPS = (public, require_user, require_user_ready, require_admin, require_admin_or_job)


# ------------------------------------------------------------------ DuckDB
def cursor(request: Request):
    """One cursor per request on this process's single connection (TRD K1). Readers are not blocked by ingest."""
    cur = request.app.state.con.cursor()
    try: yield cur
    finally: cur.close()


def folder_param(folder: str, response: Response, cur=Depends(cursor)):
    """`folder` must be a valid YYYY-MM-DD AND already ingested; otherwise 404 (TRD §8.1). Sets that folder's ETag (TRD §5.1)."""
    if not DATE.fullmatch(folder): raise ApiError(404, 'not_found', 'Folder not found.')
    try: datetime.date.fromisoformat(folder)
    except ValueError: raise ApiError(404, 'not_found', 'Folder not found.') from None
    r = cur.execute('SELECT derived_at FROM folder_state WHERE folder = ?', [folder]).fetchone()
    if not r: raise ApiError(404, 'not_found', 'Folder not found.')
    # ponytail: ETag is sent, 304 is not answered yet (responses stay no-store); add it when pages measure slow on the network.
    if r[0]: response.headers['ETag'] = f'"{folder}-{r[0]:%Y%m%d%H%M%S}"'
    return folder

