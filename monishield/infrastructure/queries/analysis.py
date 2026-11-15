"""Reads of the Analysis Settings page and of the pages that follow it (Availability, Root Causes, Request Tracing, Containers,
Business): which service is the access log of a folder, which are the application logs, how many lines carry a request ID, how
many requests or lines each business rule counts, and what could be suggested as a rule.

Rule zero of stage 62: for a source whose access log is nginx-ingress-controller (or whose events service writes the business
events), the older pages keep their own numbers; the functions here only add what those sources never had.
"""
from monishield.domain import analysis, log_formats, services as profile
from monishield.infrastructure.queries.tables import NG, http_service

LIKE = "ESCAPE '\\'"


def newest_folder(cur):
    r = cur.execute('SELECT max(folder)::VARCHAR FROM folder_state').fetchone()
    return r[0] if r else None


def _rules(): return log_formats.current() or log_formats.default_rules(profile.current())


def formats(cur, folder):
    """{service: preset} of the services of a folder, from the rule that reads each."""
    rules = _rules()
    out = {}
    for ns, svc in cur.execute('SELECT DISTINCT ns, service FROM ingest_file WHERE folder = ?', [folder]).fetchall():
        r = log_formats.match(rules, ns, svc)
        out.setdefault(svc, r.format if r else None)
    return out


def service_lines(cur, folder): return {s: n for s, n in cur.execute('SELECT service, lines FROM agg_service WHERE folder = ?', [folder]).fetchall()}


def access(cur, folder, settings):
    """The access-log service of the folder -> dict(service, lines, requests, n4xx, n5xx, format, chosen) or None.
    `chosen` is true when Analysis Settings name it; Auto is the HTTP cards' choice (nginx-ingress-controller, else the busiest)."""
    if not folder: return None
    row = http_service(cur, folder, settings.access_log)
    if not row: return None
    return dict(row, format=formats(cur, folder).get(row['service']), chosen=settings.access_log != analysis.AUTO)


def app_services(cur, folder, settings, access_service=None):
    """The application-log services of the folder: the listed ones, or Auto = every other service that has lines."""
    lines = service_lines(cur, folder)
    if settings.app_logs != analysis.AUTO: return [s for s in settings.app_logs if lines.get(s)]
    return sorted(s for s, n in lines.items() if n and s != access_service)


def requests_sql(service):
    """-> (SELECT of method, path_key, status for the requests of one service of a folder, 1 when it needs the folder only, 2 when it also filters by service)."""
    p = profile.current()
    if service == NG: return 'SELECT method, path_key, status FROM nginx_access WHERE folder = ?', 1
    if service == p.frontend: return 'SELECT method, path_key, status FROM fe_access WHERE folder = ?', 1
    if service == p.events: return 'SELECT method, path_key, status FROM sl_event WHERE folder = ?', 1
    return ('SELECT method, path_key, status FROM http_access WHERE folder = ? AND service = ? '
            'UNION ALL SELECT method, path_key, status FROM app_line WHERE folder = ? AND service = ? AND status IS NOT NULL AND path_key IS NOT NULL'), 2


def _args(folder, service, pairs): return [folder] if pairs == 1 else [folder, service, folder, service]


def count_rule(cur, folder, m):
    """How many requests or log lines of the folder count for one rule (domain/analysis.py has the same test in Python)."""
    if m.match == 'log_line':
        return cur.execute('SELECT count(*) FROM app_line WHERE folder = ? AND service = ? AND contains(lower(message), lower(?))', [folder, m.service, m.text]).fetchone()[0]
    sql, pairs = requests_sql(m.service)
    cond, args = [], _args(folder, m.service, pairs)
    if m.method: cond.append('method = ?'); args.append(m.method)
    if m.path: cond.append(f'path_key LIKE ? {LIKE}'); args.append(analysis.like_pattern(m.path))
    if m.status:
        lo, hi = analysis.status_bounds(m.status)
        cond.append('status BETWEEN ? AND ?'); args += [lo, hi]
    return cur.execute(f"SELECT count(*) FROM ({sql}) WHERE {' AND '.join(cond) or 'true'}", args).fetchone()[0]


def count_rules(cur, folder, metrics):
    """{name: count} for the rules over one folder (None folder: all zero)."""
    return {m.name: (count_rule(cur, folder, m) if folder else 0) for m in metrics}


def suggestions(cur, folder, settings, limit=8):
    """Successful POST endpoints of the access log with their count in the folder, not yet a rule -> [dict(rule, name, count)]."""
    a = access(cur, folder, settings)
    if not a: return []
    sql, pairs = requests_sql(a['service'])
    rows = cur.execute(f"SELECT path_key, count(*) FROM ({sql}) WHERE method = 'POST' AND status BETWEEN 200 AND 299 GROUP BY 1 ORDER BY 2 DESC, 1 LIMIT {int(limit) + len(settings.business)}",
                       _args(folder, a['service'], pairs)).fetchall()
    have = {(m.service, m.method, m.path) for m in settings.business if m.match == 'request'}
    out = [dict(rule=dict(name=analysis.suggest_name('POST', path), service=a['service'], match='request', method='POST', path=path, status='2xx', text=''), count=n)
           for path, n in rows if (a['service'], 'POST', path) not in have]
    return out[:limit]


def request_id_stats(cur, folder, access_service, app_list):
    """How many lines of the access log and of the application logs carry a request ID -> dict(access=(with, total), app={service: (with, total)})."""
    if not folder: return dict(access=(0, 0), app={})
    table = 'nginx_access' if access_service == NG else 'http_access' if access_service else None
    acc = (0, 0)
    if table:
        where = 'folder = ?' + ('' if table == 'nginx_access' else ' AND service = ?')
        total, withid = cur.execute(f'SELECT count(*), count(request_id) FROM {table} WHERE {where}', [folder] + ([] if table == 'nginx_access' else [access_service])).fetchone()
        acc = (withid, total)
    lines = service_lines(cur, folder)
    app = {}
    if app_list:
        got = {s: n for s, n in cur.execute(f"SELECT service, count(request_id) FROM app_line WHERE folder = ? AND service IN ({', '.join('?' * len(app_list))}) GROUP BY 1",
                                            [folder, *app_list]).fetchall()}
        app = {s: (got.get(s, 0), lines.get(s, 0)) for s in app_list}
    return dict(access=acc, app=app)


def overview(cur, settings):
    """What Auto picks for the newest folder of a source, and the services it holds."""
    folder = newest_folder(cur)
    a = access(cur, folder, settings) if folder else None
    apps = app_services(cur, folder, settings, a['service'] if a else None) if folder else []
    fmts = formats(cur, folder) if folder else {}
    lines = service_lines(cur, folder) if folder else {}
    ids = request_id_stats(cur, folder, a['service'] if a else None, apps)
    p = profile.current()
    return dict(folder=folder, access=dict(service=a['service'], format=a['format'], chosen=a['chosen'], requests=a['requests']) if a else None, app_logs=apps,
                services=[dict(service=s, lines=n, format=fmts.get(s)) for s, n in sorted(lines.items())],
                request_id=dict(access=list(ids['access']), app={s: list(v) for s, v in ids['app'].items()}),
                kubernetes=dict(names=p.names(), tag=p.event_tag, present=[r for r, s in p.names().items() if lines.get(s)] + ([NG] if lines.get(NG) else [])),
                counts=count_rules(cur, folder, settings.business))
