"""Halaman Overview (TRD §5.3)."""
from fastapi import APIRouter, Depends

from .common import cursor, folder_param, require_user_ready, H, _all
from .tables import first

router = APIRouter(prefix='/api', dependencies=[Depends(require_user_ready)])


@router.get('/folders/{folder}/overview')
def overview(folder: str = Depends(folder_param), cur=Depends(cursor)):
    a, b = cur.execute(f"SELECT {H.format('min(hour_wib)')}, {H.format('max(hour_wib)')} FROM agg_hour WHERE folder = ? AND total > 0", [folder]).fetchone()
    err = {}
    for s, h, n in _all(cur, f"SELECT service, {H.format('hour_wib')}, err FROM agg_hour WHERE folder = ? AND err > 0 ORDER BY service, hour_wib", folder):
        err.setdefault(s, []).append([h, n])
    return dict(available=True, period=dict(start=a, end=b), err_by_hour=err, tables=dict(messages=first(cur, 'messages', folder, limit=25)))
