"""Overview page (TRD §5.3)."""

from monishield.infrastructure.queries.sql import H, _all
from .tables import first


def overview(cur, folder):
    a, b = cur.execute(f"SELECT {H.format('min(hour_wib)')}, {H.format('max(hour_wib)')} FROM agg_hour WHERE folder = ? AND total > 0", [folder]).fetchone()
    err = {}
    for s, h, n in _all(cur, f"SELECT service, {H.format('hour_wib')}, err FROM agg_hour WHERE folder = ? AND err > 0 ORDER BY service, hour_wib", folder):
        err.setdefault(s, []).append([h, n])
    return dict(available=True, period=dict(start=a, end=b), err_by_hour=err, tables=dict(messages=first(cur, 'messages', folder, limit=25)))
