"""Account rules (TRD §8.2–§8.3): roles, username and password format, salted scrypt hash, machine token. Pure; account/session
storage is in monishield/infrastructure/auth.py."""
import hashlib, hmac, re, secrets

from monishield.domain.errors import Fail

ROLES = ('admin', 'user')


USERNAME = re.compile(r'[a-z0-9._-]{3,32}')


PASSWORD_MIN, PASSWORD_MAX = 12, 128


SCRYPT = (15, 8, 1)          # n = 2^15, r, p: ±76 ms on the developer laptop (docs/04a-measurements.md); stored per account


# ------------------------------------------------------------------ helpers
class AuthError(Fail):
    """Error that may be shown to the user. code = API error code, status = HTTP status."""


def hash_password(password, salt=None, params=None):
    """(hash, salt). params is read at call time, so what is stored in hash_params is always what was actually used."""
    salt = salt or secrets.token_bytes(16)
    n, r, p = params or SCRYPT
    return hashlib.scrypt(password.encode('utf-8'), salt=salt, n=2 ** n, r=r, p=p, maxmem=2 ** 30, dklen=32), salt


def check_username(username):
    if not isinstance(username, str) or not USERNAME.fullmatch(username):
        raise AuthError('invalid_username', 'Username must be 3–32 characters: lowercase letters, digits, dot, underscore, or hyphen.')
    return username


def check_password(password, username=''):
    if not isinstance(password, str) or not PASSWORD_MIN <= len(password) <= PASSWORD_MAX:
        raise AuthError('invalid_password', f'Password must be {PASSWORD_MIN}–{PASSWORD_MAX} characters.')
    if username and password.lower() == username.lower():
        raise AuthError('invalid_password', 'Password must not be the same as the username.')
    return password


def job_token_ok(configured, presented):
    """Machine token (ingest job, S3 link sender): constant-time comparison; empty = feature off."""
    return bool(configured) and isinstance(presented, str) and hmac.compare_digest(configured.encode(), presented.encode())
