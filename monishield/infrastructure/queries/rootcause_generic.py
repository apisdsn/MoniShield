"""Root Causes for any source (stage 62): the most frequent error messages of the application logs and the upstream errors of the
access log. Added to the answer of the Root Causes page next to the sections that exist for the ingress and the events service."""
from monishield.domain import analysis
from monishield.infrastructure.queries import analysis as q_analysis
from monishield.infrastructure.queries.sql import H, local, local_time
from .tables import NG

MESSAGES = 25
UPSTREAM_CODES = (502, 503, 504)


def generic(cur, folder, cfg=None):
    st = analysis.of(cfg)
    a = q_analysis.access(cur, folder, st)
    access_svc = a['service'] if a else None
    apps = q_analysis.app_services(cur, folder, st, access_svc)
    marks = ', '.join('?' * len(apps)) or "''"
    # error lines of the common-format application logs (app_line), with their times; messages are grouped by the normalised key
    rows = cur.execute(f"""SELECT service, msg_key, count(*), min(ts_utc), max(ts_utc), arg_min(message, coalesce(ts_utc, TIMESTAMP '9999-01-01'))
                           FROM app_line WHERE folder = ? AND level = 'ERROR' AND service IN ({marks}) GROUP BY service, msg_key""", [folder, *apps]).fetchall() if apps else []
    seen = {r[0] for r in rows}
    messages = [dict(service=s, key=k, n=n, first=local_time(f), last=local_time(l), search=(m or k).split('\n', 1)[0][:120]) for s, k, n, f, l, m in rows]
    # services read by a legacy parser (Spring Boot, ...) have no app_line rows: their error messages come from the message aggregate, without times
    left = [s for s in apps if s not in seen]
    if left:
        for s, k, n, sample in cur.execute(f"SELECT service, msg_key, n, sample_raw FROM agg_message WHERE folder = ? AND level = 'ERROR' AND service IN ({', '.join('?' * len(left))})", [folder, *left]).fetchall():
            messages.append(dict(service=s, key=k, n=n, first=None, last=None, search=(sample or k.split(' | ', 1)[-1]).split('\n', 1)[0][:120]))
    messages.sort(key=lambda m: (-m['n'], m['service'], m['key']))
    hour = H.format("date_trunc('hour', " + local('ts_utc') + ')')
    busiest = cur.execute(f"""SELECT {hour} AS h, count(*) FROM app_line WHERE folder = ? AND level = 'ERROR' AND ts_utc IS NOT NULL AND service IN ({marks})
                              GROUP BY h ORDER BY 2 DESC, 1 LIMIT 1""", [folder, *apps]).fetchone() if apps else None
    up = dict(legacy=access_svc == NG, total=0, rows=[])
    if a and not up['legacy']:
        up['total'] = cur.execute('SELECT count(*) FROM http_access WHERE folder = ? AND service = ? AND status IN (502, 503, 504)', [folder, access_svc]).fetchone()[0]
        up['rows'] = [dict(backend=b or '', n502=x, n503=y, n504=z, last=local_time(t)) for b, x, y, z, t in cur.execute(
            """SELECT coalesce(upstream, ''), count(*) FILTER (WHERE status = 502), count(*) FILTER (WHERE status = 503), count(*) FILTER (WHERE status = 504), max(ts_utc)
               FROM http_access WHERE folder = ? AND service = ? AND status IN (502, 503, 504) GROUP BY 1 ORDER BY 2 + 3 + 4 DESC, 1 LIMIT 25""", [folder, access_svc]).fetchall()]
    return dict(access=dict(service=access_svc, format=a['format'], chosen=a['chosen']) if a else None, app_logs=apps,
                error_lines=sum(m['n'] for m in messages), distinct=len(messages), error_services=len({m['service'] for m in messages}),
                busiest=dict(hour=busiest[0], n=busiest[1]) if busiest else None, messages=messages[:MESSAGES], upstream=up)
