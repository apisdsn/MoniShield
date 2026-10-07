"""Halaman Ketersediaan (TRD §5.3)."""
from fastapi import APIRouter, Depends

from .common import cursor, folder_param, require_user_ready, H, _all, _one, _no, _has
from .tables import NG, first, services

router = APIRouter(prefix='/api', dependencies=[Depends(require_user_ready)])


@router.get('/folders/{folder}/availability')
def availability(folder: str = Depends(folder_param), cur=Depends(cursor)):
    if not _has(services(cur, folder), NG): return _no('no_nginx')
    req, n5 = cur.execute('SELECT requests, n5xx FROM agg_service WHERE folder = ? AND service = ?', [folder, NG]).fetchone()
    uk = _all(cur, f"SELECT {H.format('hour_wib')}, n, fail FROM agg_uk_hour WHERE folder = ? ORDER BY hour_wib", folder)
    # ponytail: 5xx per jam dibaca dari tabel mentah (agg_hour.err memuat juga baris error log, butir 2); satu folder = satu rentang
    # berurutan, jadi hanya blok folder itu yang dibaca. Tambah kolom n5xx di agg_hour bila query ini terukur lambat.
    return dict(
        available=True,
        kpi=dict(requests=req, n5xx=n5, incidents=_one(cur, 'SELECT count(*) FROM agg_incident WHERE folder = ?', folder),
                 retries=_one(cur, 'SELECT coalesce(sum(n), 0) FROM agg_retry WHERE folder = ?', folder),
                 upstream_errors=_one(cur, 'SELECT count(*) FROM v_upstream_error WHERE folder = ?', folder),
                 uptime_checks=sum(r[1] for r in uk), uptime_failed=sum(r[2] for r in uk)),
        n5xx_by_hour=_all(cur, f"""SELECT {H.format("date_trunc('hour', ts_utc + INTERVAL 7 HOUR)")} AS h, count(*) FROM nginx_access
                                   WHERE folder = ? AND status BETWEEN 500 AND 599 GROUP BY h ORDER BY h""", folder),
        hours=[r[0] for r in _all(cur, f"SELECT {H.format('hour_wib')} FROM agg_hour WHERE folder = ? AND service = ? AND total > 0 ORDER BY hour_wib", folder, NG)],
        n5xx_by_upstream=_all(cur, 'SELECT upstream, n5xx FROM agg_upstream WHERE folder = ? AND n5xx > 0 ORDER BY n5xx DESC, upstream', folder),
        uptime_by_hour=uk,
        tables={t: first(cur, t, folder) for t in ('upstreams', 'incidents', 'upstream-errors', 'uptime-targets')})
