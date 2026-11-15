"""Request Tracing page (TRD §5.3)."""

from monishield.domain import analysis, services as profile
from monishield.infrastructure.queries import analysis as q_analysis
from monishield.infrastructure.queries.sql import _all, _one, _no, local_time
from .tables import cells, first, services

TRACED = 200   # requests listed


def tracing(cur, folder, cfg=None):
    corr = cur.execute('SELECT matched, total FROM agg_corr WHERE folder = ?', [folder]).fetchone()
    if not corr:
        # no events service: follow a request by the ID that the access log and an application log both write (stage 62)
        st = analysis.of(cfg)
        a = q_analysis.access(cur, folder, st)
        if q_analysis.generic_access(a) and profile.current().events not in services(cur, folder): return _generic(cur, folder, st, a)
        return _no('no_events_service' if profile.current().events not in services(cur, folder) else 'no_correlation')
    failed = 'folder = ? AND status BETWEEN 400 AND 599'
    by_ip = cells(cur, [dict(ip=ip, n=n) for ip, n in _all(cur, f'SELECT ip, sum(n)::BIGINT FROM agg_trace WHERE {failed} GROUP BY ip ORDER BY 2 DESC, 1 LIMIT 10', folder)], ('ip',))
    return dict(
        available=True, corr=dict(matched=corr[0], total=corr[1]),
        kpi=dict(failed_requests=_one(cur, f'SELECT coalesce(sum(n), 0) FROM agg_trace WHERE {failed}', folder),
                 failed_ips=_one(cur, f'SELECT count(DISTINCT ip) FROM agg_trace WHERE {failed}', folder),
                 # TRD §4.4 item 9: all slow traces that did not fail, whatever their status
                 slow_requests=_one(cur, "SELECT coalesce(sum(n), 0) FROM agg_trace WHERE folder = ? AND error LIKE 'Lambat%'", folder)),
        by_ip=[dict(**r['ip'], n=r['n']) for r in by_ip],
        by_error=_all(cur, f"SELECT status || ' ' || error, sum(n)::BIGINT FROM agg_trace WHERE {failed} GROUP BY 1 ORDER BY 2 DESC, 1 LIMIT 10", folder),
        tables=dict(trace=first(cur, 'trace', folder)))


def _generic(cur, folder, st, a):
    """Requests of the access log whose request ID also stands in an application log of the source."""
    svc = a['service']
    apps = q_analysis.app_services(cur, folder, st, svc)
    ids = q_analysis.request_id_stats(cur, folder, svc, apps)
    out = dict(available=True, mode='generic', access=dict(service=svc, format=a['format'], chosen=a['chosen']), app_logs=apps, field=st.request_id,
               id_fields=list(analysis.ID_FIELDS), ids=dict(access=list(ids['access']), app={s: list(v) for s, v in ids['app'].items()}),
               matched=0, kpi=dict(with_id=ids['access'][0], traced=0, failed=0), traced=[])
    if not apps or not ids['access'][0] or not any(v[0] for v in ids['app'].values()): return out
    marks = ', '.join('?' * len(apps))
    table, extra = ('nginx_access', '') if svc == q_analysis.NG else ('http_access', ' AND service = ?')
    dur = 'request_time * 1000' if table == 'nginx_access' else 'duration_ms'
    rows = cur.execute(f"""WITH l AS (SELECT request_id, service, count(*) AS n, count(*) FILTER (WHERE level = 'ERROR') AS err, min(ts_utc) AS t
                                      FROM app_line WHERE folder = ? AND service IN ({marks}) AND request_id IS NOT NULL GROUP BY 1, 2),
                           a AS (SELECT request_id, any_value(method) AS method, any_value(path_key) AS path_key, max(status) AS status, max({dur}) AS ms, min(ts_utc) AS t
                                 FROM {table} WHERE folder = ?{extra} AND request_id IS NOT NULL GROUP BY 1)
                           SELECT a.request_id, a.method, a.path_key, a.status, a.ms, a.t, list(l.service ORDER BY l.service), sum(l.err)
                           FROM a JOIN l USING (request_id) GROUP BY a.request_id, a.method, a.path_key, a.status, a.ms, a.t
                           ORDER BY (coalesce(a.status, 0) >= 500 OR sum(l.err) > 0) DESC, a.ms DESC NULLS LAST, a.request_id""",
                       [folder, *apps, folder] + ([svc] if extra else [])).fetchall()
    out['matched'] = len(rows)
    out['kpi'] = dict(with_id=ids['access'][0], traced=len(rows), failed=sum(1 for r in rows if (r[3] or 0) >= 500 or (r[7] or 0) > 0))
    out['traced'] = [dict(id=r[0], method=r[1], path=r[2], status=r[3], ms=r[4], time=local_time(r[5]), services=r[6], errors=int(r[7] or 0)) for r in rows[:TRACED]]
    return out
