"""Read-side query helpers: cell format, local hours, short execution, rejection (domain error -> HTTP in the interface)."""
from monishield.domain import timezone
from monishield.domain.errors import Fail


def reject(status, code, message):
    """Rejection from a query (invalid parameter, not found): the interface layer translates it to HTTP."""
    return Fail(code, message, status)


# ------------------------------------------------------------------ format
def local_time(ts, n=16):
    """UTC TIMESTAMP -> local text 'YYYY-MM-DD HH:MM' (n=13: up to the hour; S4_TIMEZONE_OFFSET), the old system's format."""
    return None if ts is None else timezone.current().local(ts).strftime('%Y-%m-%d %H:%M')[:n]


def local(expr):
    """SQL: UTC column -> local TIMESTAMP (the offset is an integer from the configuration, never user input)."""
    return f'{expr} + to_minutes({int(timezone.current().minutes)})'


def ip_cell(ip, asn=None, cc=None, org=None):
    """IP cell + network owner (TRD §5.1): only {'ip'} when the owner is unknown."""
    return dict(ip=ip) if org is None else dict(ip=ip, asn=asn, cc=cc, org=org)


# ------------------------------------------------------------------ used by the page modules (TRD §5.3)
# All page numbers are read from the full aggregate tables (TRD K4), not from already-truncated lists.
# When the needed logs are missing: 200 with available=false + reason, not an error.
H = "strftime({}, '%Y-%m-%d %H')"   # local hour, old format


def _all(cur, sql, *p): return [list(r) for r in cur.execute(sql, list(p)).fetchall()]
def _one(cur, sql, *p): return cur.execute(sql, list(p)).fetchone()[0]
def _no(reason): return dict(available=False, reason=reason)
def _has(svc, name): return bool(svc.get(name))   # service exists AND has lines
