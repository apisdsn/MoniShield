"""Collector rules (docs/12-collector.md, step 2): names, platforms, the secrets a collector holds, and its status.
Pure; the registry itself is in monishield/infrastructure/auth.py.

A collector gets a one-time enrollment token (`mse_<id>_<secret>`, valid ENROLL_HOURS) and exchanges it once for its
own long-lived key (`msk_<id>_<secret>`). <id> is the collector's row id, so the server finds the row without
scanning; <secret> is 256 random bits, so a plain SHA-256 is enough to store (no slow hash is needed for random values).
"""
import datetime, hashlib, re, secrets

from monishield.domain.errors import Fail

NAME = re.compile(r'[a-z0-9][a-z0-9-]{0,62}')
PLATFORMS = ('linux', 'windows', 'kubernetes', 'docker')
ENROLL_HOURS = 24
ROTATE_GRACE_HOURS = 24   # the previous key keeps working, so a running collector can be updated without losing data
ONLINE_MINUTES, LATE_MINUTES = 5, 60
KINDS = {'enroll': 'mse', 'key': 'msk'}
SECRET = re.compile(r'[A-Za-z0-9_-]{43}')   # secrets.token_urlsafe(32) is always 43 characters
ID_MAX = 10 ** 12


def check_name(name):
    if not isinstance(name, str) or not NAME.fullmatch(name):
        raise Fail('invalid_name', 'Collector name must be 1–63 characters: lowercase letters, digits and hyphen, starting with a letter or digit.')
    return name


def check_platform(platform):
    if platform not in PLATFORMS: raise Fail('invalid_platform', f"Platform must be one of: {', '.join(PLATFORMS)}.")
    return platform


def new_secret(kind, cid):
    """(text shown once, secret part to hash). kind = 'enroll' or 'key'."""
    secret = secrets.token_urlsafe(32)
    return f'{KINDS[kind]}_{cid}_{secret}', secret


def parse_secret(text, kind):
    """-> (collector id, secret) or None for anything that is not a well-formed token or key of this kind."""
    if not isinstance(text, str) or len(text) > 80: return None
    parts = text.split('_', 2)
    if len(parts) != 3 or parts[0] != KINDS[kind] or not (parts[1].isascii() and parts[1].isdigit()): return None
    cid = int(parts[1])
    if not 0 < cid < ID_MAX or not SECRET.fullmatch(parts[2]): return None
    return cid, parts[2]


def secret_hash(secret): return hashlib.sha256(secret.encode('ascii')).hexdigest()


def status(now, enrolled_at, last_seen, revoked_at):
    """'revoked' | 'waiting' (never enrolled) | 'online' | 'late' | 'offline'."""
    if revoked_at: return 'revoked'
    if not enrolled_at: return 'waiting'
    age = now - (last_seen or enrolled_at)
    if age <= datetime.timedelta(minutes=ONLINE_MINUTES): return 'online'
    return 'late' if age <= datetime.timedelta(minutes=LATE_MINUTES) else 'offline'
