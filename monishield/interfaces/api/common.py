"""Shared by all routers: errors, roles, parameter validation (TRD §8.1), DuckDB access."""
import datetime, re, threading, time

from fastapi import Depends, HTTPException, Request, Response

from monishield.application import sources
from monishield.domain import accounts, client_address

COOKIE = 's4_session'
CSRF_HEADER = 'x-requested-with'      # required on every request that changes data (TRD §8.2)
DATE = re.compile(r'\d{4}-\d\d-\d\d')


class ApiError(HTTPException):
    def __init__(self, status, code, message, headers=None): super().__init__(status_code=status, detail=dict(code=code, message=message), headers=headers)


def client_ip(request: Request):
    cfg = request.app.state.cfg
    # the LAST address is the one our proxy added; earlier ones were sent by the client and can be anything (security review)
    if cfg.trust_proxy and (xff := request.headers.get('x-forwarded-for')): peer = xff.split(',')[-1].strip()[:64]
    else: peer = request.client.host if request.client else None
    # behind Cloudflare: CF-Connecting-IP, believed only when the peer is a Cloudflare address (domain/client_address.py)
    return client_address.real_client(peer, request.headers.get('cf-connecting-ip'), cfg.trust_cloudflare, cfg.cloudflare_ips)


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
        if accounts.job_token_ok(request.app.state.cfg.job_token, bearer[7:].strip()):
            request.state.user = None
            return dict(user_id=None, username='(machine token)', role='job')
        raise ApiError(401, 'unauthenticated', 'Unknown machine token.')
    return require_admin(require_user_ready(require_user(request)))


class FailureLimiter:
    """Failed collector keys per IP: more than `limit` within `window` seconds blocks the IP for `block` seconds. Kept apart from
    the login's limit so bad keys of a collector never lock people out of sign-in. In memory, thread-safe."""

    def __init__(self, limit=60, window=60, block=300, clock=time.monotonic):
        self.limit, self.window, self.block, self.clock = limit, window, block, clock
        self._lock, self._fails, self._blocked = threading.Lock(), {}, {}

    def retry_after(self, ip):
        """Seconds the IP is still blocked, or 0."""
        with self._lock:
            until = self._blocked.get(ip, 0)
            if until > (t := self.clock()): return int(until - t) + 1
            self._blocked.pop(ip, None)
            return 0

    def failed(self, ip):
        """Record one failure. -> True when this one blocks the IP."""
        with self._lock:
            t = self.clock()
            recent = [x for x in self._fails.get(ip, ()) if t - x < self.window] + [t]
            if len(recent) > self.limit:
                self._fails.pop(ip, None); self._blocked[ip] = t + self.block
                return True
            self._fails[ip] = recent
            if len(self._fails) > 10000: self._prune(t)
            return False

    def _prune(self, t):
        for k in [k for k, v in self._fails.items() if t - v[-1] >= self.window]: del self._fails[k]
        for k in [k for k, v in self._blocked.items() if v <= t]: del self._blocked[k]


class RateWindow:
    """At most `limit` hits per key in each clock minute (a fixed window: simple, and good enough to stop a runaway client)."""

    def __init__(self, clock=time.time):
        self.clock, self._lock, self._count = clock, threading.Lock(), {}

    def hit(self, key, limit):
        """-> True when this hit is within the limit."""
        with self._lock:
            minute = int(self.clock() // 60)
            if len(self._count) > 10000: self._count = {k: v for k, v in self._count.items() if v[0] == minute}
            m, n = self._count.get(key, (minute, 0))
            n = n + 1 if m == minute else 1
            self._count[key] = (minute, n)
            return n <= limit


class Slots:
    """A fixed number of requests at a time, never waiting: `take()` is False when all are in use."""

    def __init__(self): self._lock, self._used = threading.Lock(), 0

    def take(self, limit):
        with self._lock:
            if self._used >= limit: return False
            self._used += 1
            return True

    def release(self):
        with self._lock: self._used = max(0, self._used - 1)


def _bearer(request: Request):
    h = request.headers.get('authorization', '')
    return h[7:].strip() if h[:7].lower() == 'bearer ' else ''


def require_collector(request: Request):
    """A collector with a valid key (`Authorization: Bearer msk_…`). A machine client: no session, no CSRF check, no audit.
    Wrong keys are counted per IP (not on the login's limit); the key is never logged or returned."""
    ip, limiter = client_ip(request), request.app.state.collector_failures
    if wait := limiter.retry_after(ip): raise ApiError(429, 'too_many_attempts', 'Too many wrong collector keys. Try again later.', {'Retry-After': str(wait)})
    info = request.app.state.collectors.authenticate(_bearer(request), ip, request.headers.get('user-agent'))
    if info: return info
    if limiter.failed(ip): raise ApiError(429, 'too_many_attempts', 'Too many wrong collector keys. Try again later.', {'Retry-After': str(limiter.block)})
    raise ApiError(401, 'invalid_collector_key', 'Collector key is not valid.', {'WWW-Authenticate': 'Bearer'})


ROLE_DEPS = (public, require_user, require_user_ready, require_admin, require_admin_or_job, require_collector)


# ------------------------------------------------------------------ DuckDB
def source_ctx(request: Request):
    """The data source of the request: `?source=s3` (default), `kafka` or `collector` (owner request 2026-10-23). Each source has
    its own database and folders; everything a page reads (and the admin folder tools) goes through the source's ctx."""
    name = request.query_params.get('source') or sources.S3
    if not sources.valid(name): raise ApiError(400, 'invalid_parameter', 'source must be s3, kafka or collector.')
    return request.app.state.sources[name]


def cursor(request: Request):
    """One cursor per request on the source's single connection (TRD K1). Readers are not blocked by ingest."""
    cur = source_ctx(request).con.cursor()
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

