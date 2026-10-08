"""Read-side query helpers: cell format, WIB hours, short execution, rejection (domain error -> HTTP in the interface)."""
import datetime

from monishield.domain.errors import Fail


def reject(status, code, message):
    """Rejection from a query (invalid parameter, not found): the interface layer translates it to HTTP."""
    return Fail(code, message, status)


# ------------------------------------------------------------------ format
def wib(ts, n=16):
    """UTC TIMESTAMP -> WIB text 'YYYY-MM-DD HH:MM' (n=13: up to the hour), same format as the old system's data."""
    return None if ts is None else (ts + datetime.timedelta(hours=7)).strftime('%Y-%m-%d %H:%M')[:n]


def ip_cell(ip, asn=None, cc=None, org=None):
    """IP cell + network owner (TRD §5.1): only {'ip'} when the owner is unknown."""
    return dict(ip=ip) if org is None else dict(ip=ip, asn=asn, cc=cc, org=org)


# ------------------------------------------------------------------ used by the page modules (TRD §5.3)
# All page numbers are read from the full aggregate tables (TRD K4), not from already-truncated lists.
# When the needed logs are missing: 200 with available=false + reason, not an error.
SL, AM, RP = 'om-be-simpel-loop', 'om-be-appsmanager', 'om-be-report'
H = "strftime({}, '%Y-%m-%d %H')"   # WIB hour, old format


def _all(cur, sql, *p): return [list(r) for r in cur.execute(sql, list(p)).fetchall()]
def _one(cur, sql, *p): return cur.execute(sql, list(p)).fetchone()[0]
def _no(reason): return dict(available=False, reason=reason)
def _has(svc, name): return bool(svc.get(name))   # service exists AND has lines
