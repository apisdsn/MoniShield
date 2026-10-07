"""Halaman Pelacakan Request (TRD §5.3)."""

from monishield.infrastructure.queries.sql import SL, _all, _one, _no
from .tables import cells, first, services


def tracing(cur, folder):
    corr = cur.execute('SELECT matched, total FROM agg_corr WHERE folder = ?', [folder]).fetchone()
    if not corr: return _no('no_simpel_loop' if SL not in services(cur, folder) else 'no_correlation')
    gagal = 'folder = ? AND status BETWEEN 400 AND 599'
    by_ip = cells(cur, [dict(ip=ip, n=n) for ip, n in _all(cur, f'SELECT ip, sum(n)::BIGINT FROM agg_trace WHERE {gagal} GROUP BY ip ORDER BY 2 DESC, 1 LIMIT 10', folder)], ('ip',))
    return dict(
        available=True, corr=dict(matched=corr[0], total=corr[1]),
        kpi=dict(failed_requests=_one(cur, f'SELECT coalesce(sum(n), 0) FROM agg_trace WHERE {gagal}', folder),
                 failed_ips=_one(cur, f'SELECT count(DISTINCT ip) FROM agg_trace WHERE {gagal}', folder),
                 # TRD §4.4 butir 9: semua jejak lambat yang tidak gagal, apa pun statusnya
                 slow_requests=_one(cur, "SELECT coalesce(sum(n), 0) FROM agg_trace WHERE folder = ? AND error LIKE 'Lambat%'", folder)),
        by_ip=[dict(**r['ip'], n=r['n']) for r in by_ip],
        by_error=_all(cur, f"SELECT status || ' ' || error, sum(n)::BIGINT FROM agg_trace WHERE {gagal} GROUP BY 1 ORDER BY 2 DESC, 1 LIMIT 10", folder),
        tables=dict(trace=first(cur, 'trace', folder)))
