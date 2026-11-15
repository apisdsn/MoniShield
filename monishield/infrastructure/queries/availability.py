"""Availability page (TRD §5.3)."""

from monishield.domain import analysis
from monishield.infrastructure.queries import analysis as q_analysis
from monishield.infrastructure.queries.sql import H, _all, _one, _no, _has, local
from .tables import NG, first, services

SLOW_MS = 1000   # an endpoint whose P95 reaches this is listed even without errors


def availability(cur, folder, cfg=None):
    """nginx-ingress-controller is the access log (Auto with its lines, or chosen): the ingress numbers as before. Any other access log
    (the busiest one, or the one Analysis Settings name): requests, 5xx, response time and the endpoints that fail or are slow."""
    st = analysis.of(cfg)
    a = q_analysis.access(cur, folder, st)
    if q_analysis.generic_access(a): return _generic(cur, folder, a)
    if not a and st.access_log not in (analysis.AUTO, NG): return _no('no_nginx')   # the chosen access log has no requests in this folder
    if not _has(services(cur, folder), NG): return _no('no_nginx')
    req, n5 = cur.execute('SELECT requests, n5xx FROM agg_service WHERE folder = ? AND service = ?', [folder, NG]).fetchone()
    uk = _all(cur, f"SELECT {H.format('hour_wib')}, n, fail FROM agg_uk_hour WHERE folder = ? ORDER BY hour_wib", folder)
    # ponytail: 5xx per hour is read from the raw table (agg_hour.err also includes error-log lines, item 2); one folder = one contiguous
    # range, so only that folder's block is read. Add an n5xx column to agg_hour if this query measures slow.
    return dict(
        available=True,
        kpi=dict(requests=req, n5xx=n5, incidents=_one(cur, 'SELECT count(*) FROM agg_incident WHERE folder = ?', folder),
                 retries=_one(cur, 'SELECT coalesce(sum(n), 0) FROM agg_retry WHERE folder = ?', folder),
                 upstream_errors=_one(cur, 'SELECT count(*) FROM v_upstream_error WHERE folder = ?', folder),
                 uptime_checks=sum(r[1] for r in uk), uptime_failed=sum(r[2] for r in uk)),
        n5xx_by_hour=_all(cur, f"""SELECT {H.format(f"date_trunc('hour', {local('ts_utc')})")} AS h, count(*) FROM nginx_access
                                   WHERE folder = ? AND status BETWEEN 500 AND 599 GROUP BY h ORDER BY h""", folder),
        hours=[r[0] for r in _all(cur, f"SELECT {H.format('hour_wib')} FROM agg_hour WHERE folder = ? AND service = ? AND total > 0 ORDER BY hour_wib", folder, NG)],
        n5xx_by_upstream=_all(cur, 'SELECT upstream, n5xx FROM agg_upstream WHERE folder = ? AND n5xx > 0 ORDER BY n5xx DESC, upstream', folder),
        uptime_by_hour=uk,
        tables={t: first(cur, t, folder) for t in ('upstreams', 'incidents', 'upstream-errors', 'uptime-targets')})


def _generic(cur, folder, a):
    """Availability read from the access log of any service (the rows of http_access, or of the service's own table)."""
    svc = a['service']
    sql, pairs = q_analysis.requests_sql(svc)
    args = q_analysis._args(folder, svc, pairs)
    req, n4, n5 = a['requests'], a['n4xx'], a['n5xx']
    p50, p95, slowest = cur.execute(f'SELECT quantile_disc(duration_ms, 0.5), quantile_disc(duration_ms, 0.95), max(duration_ms) FROM ({sql}) WHERE duration_ms IS NOT NULL', args).fetchone()
    slow_path = cur.execute(f'SELECT path_key FROM ({sql}) WHERE duration_ms IS NOT NULL ORDER BY duration_ms DESC, path_key LIMIT 1', args).fetchone()
    classes = {c: 0 for c in (2, 3, 4, 5)}
    for st, n in cur.execute('SELECT status, n FROM agg_status WHERE folder = ? AND service = ?', [folder, svc]).fetchall():
        if st // 100 in classes: classes[st // 100] += n
    hour = H.format("date_trunc('hour', " + local('ts_utc') + ')')
    by_hour = _all(cur, f'SELECT {hour} AS h, count(*) FROM ({sql}) WHERE status BETWEEN 500 AND 599 AND ts_utc IS NOT NULL GROUP BY h ORDER BY h', *args)
    rows = _all(cur, f"""SELECT path_key, count(*) AS requests, count(*) FILTER (WHERE status BETWEEN 400 AND 499) AS n4xx, count(*) FILTER (WHERE status BETWEEN 500 AND 599) AS n5xx,
                                quantile_disc(duration_ms, 0.95) AS p95, max(duration_ms) AS slowest
                         FROM ({sql}) WHERE path_key IS NOT NULL GROUP BY path_key
                         HAVING n4xx + n5xx > 0 OR p95 >= {SLOW_MS} ORDER BY n5xx DESC, n4xx DESC, p95 DESC NULLS LAST, requests DESC, path_key LIMIT 25""", *args)
    return dict(
        available=True, mode='access', access=dict(service=svc, format=a['format'], chosen=a['chosen']),
        kpi=dict(requests=req, n4xx=n4, n5xx=n5, p50_ms=p50, p95_ms=p95, slowest_ms=slowest, slowest_path=slow_path[0] if slow_path else None),
        hours=[r[0] for r in _all(cur, f"SELECT {H.format('hour_wib')} FROM agg_hour WHERE folder = ? AND service = ? AND total > 0 ORDER BY hour_wib", folder, svc)],
        n5xx_by_hour=by_hour, status_classes=[[f'{c}xx', n] for c, n in classes.items()],
        endpoints=[dict(path=r[0], requests=r[1], n4xx=r[2], n5xx=r[3], p95_ms=r[4], slowest_ms=r[5]) for r in rows])
