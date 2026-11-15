"""Stage 62: the analysis pages for a Collector-like folder (a Caddy JSON access log and a JSON application log, with and without a
request ID) and the Containers page; the S3 numbers stay as they are (tests/test_api.py, tests/test_http_cards.py)."""
import dataclasses, datetime, json, os

import pytest

import logs_mini
from monishield.domain import analysis as an, log_formats as lf
from monishield.infrastructure import config, db, ingest
from monishield.infrastructure.metrics_store import MetricsStore
from monishield.infrastructure.queries import (availability as q_av, business as q_biz, containers as q_ctr, rootcause as q_rc, tracing as q_tr, analysis as q_an)

FOLDER = '2026-10-11'
UTC = datetime.timezone.utc
RULES = '''\
[[service]]
match = "web-1"
format = "caddy-json"
kind = "http"

[[service]]
match = "app-1"
format = "json"
kind = "app"

[[service]]
match = "*"
format = "plain"
kind = "app"
'''


def epoch(h, m, s=0): return datetime.datetime(2026, 10, 11, h, m, s, tzinfo=UTC).timestamp()


def caddy(h, m, method, uri, status, dur, rid=None, upstream=None):
    d = {'level': 'info', 'ts': epoch(h, m), 'logger': 'http.log.access.log0', 'msg': 'handled request', 'duration': dur, 'size': 10, 'status': status,
         'request': {'client_ip': '203.0.113.5', 'method': method, 'uri': uri, 'headers': {'User-Agent': ['curl/8']}}}
    if rid: d['request_id'] = rid
    if upstream: d['upstream'] = upstream
    return json.dumps(d)


def app(h, m, level, msg, rid=None):
    d = {'time': datetime.datetime.fromtimestamp(epoch(h, m), UTC).strftime('%Y-%m-%dT%H:%M:%SZ'), 'level': level, 'msg': msg}
    if rid: d['request_id'] = rid
    return json.dumps(d)


def lines(with_ids):
    r = lambda i: f'req-{i}' if with_ids else None
    web = [caddy(10, 0, 'GET', '/api/servers', 200, 0.05), caddy(10, 1, 'GET', '/api/servers', 200, 0.4), caddy(10, 2, 'POST', '/api/orders', 201, 0.1, r(1)),
           caddy(10, 3, 'POST', '/api/orders', 201, 0.1, r(2)), caddy(10, 4, 'POST', '/api/login', 401, 0.02), caddy(11, 0, 'GET', '/api/slow', 502, 2.5, r(3)),
           caddy(13, 0, 'GET', '/api/slow', 504, 3.0, r(4)), caddy(13, 5, 'GET', '/missing', 404, 0.01), caddy(13, 6, 'GET', '/api/orders/17', 200, 0.2),
           '{"level":"info","ts":%s,"msg":"certificate obtained"}' % epoch(9, 0)]
    web[5] = web[5][:-1] + ',"upstream":"app:8000"}' if False else web[5]
    app_ = [app(10, 2, 'info', 'order saved', r(1)), app(10, 3, 'info', 'order saved', r(2)), app(11, 0, 'error', 'Timeout after 30 ms reading /api/slow', r(3)),
            app(13, 0, 'error', 'Timeout after 45 ms reading /api/slow', r(4)), app(13, 1, 'error', 'S3 sync failed (code 7)'), app(13, 2, 'warn', 'cache miss'),
            app(10, 4, 'info', 'Payment received for order 5')]
    return '\n'.join(web) + '\n', '\n'.join(app_) + '\n'


def build(tmp_path, with_ids):
    root = str(tmp_path / 'logs')
    web, app_ = lines(with_ids)
    logs_mini.write(logs_mini.log_path(root, FOLDER, 'host1', 'web-1', 'p1'), web)
    logs_mini.write(logs_mini.log_path(root, FOLDER, 'host1', 'app-1', 'p1'), app_)
    logs_mini.write(logs_mini.log_path(root, FOLDER, 'host1', 'idle-1', 'p1'), '')
    toml = tmp_path / 'log-formats.toml'
    toml.write_text(RULES)
    cfg = dataclasses.replace(config.Config(), log_dir=root, data_dir=str(tmp_path / 'data'), inbox_dir=str(tmp_path / 'inbox'), state_dir=str(tmp_path / 'data'),
                              cache_dir=str(tmp_path / 'cache'), offline=True, log_formats_file=str(toml))
    con = db.open(cfg.db_path)
    before, was = lf.current(), an.all_current()
    lf.use(config.log_format_rules(cfg))
    an.use(None)
    ingest.run(cfg, con, workers=0)
    return cfg, con, before, was


class Site:
    def __init__(self, cur, cfg, with_ids): self.cur, self.cfg, self.with_ids = cur, cfg, with_ids


@pytest.fixture(params=[True, False], ids=['with-ids', 'without-ids'])
def site(request, tmp_path):
    cfg, con, before, was = build(tmp_path, request.param)
    cur = con.cursor()
    yield Site(cur, cfg, request.param)
    cur.close(); con.close(); lf.use(before); an.use(was)


def test_availability_reads_the_access_log(site):
    cur, cfg = site.cur, site.cfg
    d = q_av.availability(cur, FOLDER, cfg)
    assert d['available'] and d['mode'] == 'access' and d['access'] == dict(service='web-1', format='caddy-json', chosen=False)
    k = d['kpi']
    assert (k['requests'], k['n4xx'], k['n5xx']) == (9, 2, 2) and k['slowest_ms'] == pytest.approx(3000) and k['slowest_path'] == '/api/slow'
    assert k['p95_ms'] == pytest.approx(3000) and k['p50_ms'] == pytest.approx(100)
    assert dict(d['status_classes']) == {'2xx': 5, '3xx': 0, '4xx': 2, '5xx': 2}
    assert [n for _, n in d['n5xx_by_hour']] == [1, 1] and d['n5xx_by_hour'][0][0].endswith(' 18')          # 11:00 UTC is 18:00 local (+7 h)
    assert [(e['path'], e['n5xx']) for e in d['endpoints']][:2] == [('/api/slow', 2), ('/api/login', 0)]
    slow = d['endpoints'][0]
    assert slow['requests'] == 2 and slow['slowest_ms'] == pytest.approx(3000) and slow['p95_ms'] == pytest.approx(3000)
    assert '/api/servers' not in [e['path'] for e in d['endpoints']]                                            # no errors, fast


def test_availability_names_what_is_missing_without_an_access_log(site):
    cur, cfg = site.cur, site.cfg
    an.use(an.parse({'s3': {'access_log': 'app-1'}}))
    assert q_av.availability(cur, FOLDER, cfg) == {'available': False, 'reason': 'no_nginx'}
    an.use(an.parse({'s3': {'access_log': 'nothing-1'}}))
    assert q_av.availability(cur, FOLDER, cfg) == {'available': False, 'reason': 'no_nginx'}


def test_root_causes_lists_the_error_messages_and_upstream_errors(site):
    cur, cfg = site.cur, site.cfg
    d = q_rc.rootcause(cur, FOLDER, cfg)['generic']
    assert d['access']['service'] == 'web-1' and d['app_logs'] == ['app-1']
    assert (d['error_lines'], d['distinct'], d['error_services']) == (3, 2, 1)
    top = d['messages'][0]
    assert (top['service'], top['n'], top['key']) == ('app-1', 2, 'ERROR | Timeout after # ms reading /api/slow') and top['first'] == '2026-10-11 18:00' and top['last'] == '2026-10-11 20:00'
    assert top['search'].startswith('Timeout after 30 ms') and d['messages'][1]['n'] == 1
    assert d['busiest'] == dict(hour='2026-10-11 20', n=2)
    up = d['upstream']
    assert up['legacy'] is False and up['total'] == 2 and up['rows'] == [dict(backend='', n502=1, n503=0, n504=1, last='2026-10-11 20:00')]


def test_request_tracing_follows_ids_or_explains_the_setup(site):
    cur, cfg = site.cur, site.cfg
    d = q_tr.tracing(cur, FOLDER, cfg)
    assert d['available'] and d['mode'] == 'generic' and d['access']['service'] == 'web-1' and d['app_logs'] == ['app-1'] and 'request_id' in d['id_fields']
    if not site.with_ids:
        assert d['matched'] == 0 and d['traced'] == [] and d['ids']['access'] == [0, 9] and d['ids']['app'] == {'app-1': [0, 7]}
        return
    assert d['ids']['access'] == [4, 9] and d['ids']['app'] == {'app-1': [4, 7]}
    assert (d['matched'], d['kpi']) == (4, dict(with_id=4, traced=4, failed=2))
    first = d['traced'][0]
    assert (first['id'], first['status'], first['path'], first['services'], first['errors']) == ('req-4', 504, '/api/slow', ['app-1'], 1)
    ok = next(t for t in d['traced'] if t['id'] == 'req-1')
    assert (ok['status'], ok['method'], ok['errors']) == (201, 'POST', 0) and ok['ms'] == pytest.approx(100)


def test_a_configured_request_id_field_is_read_for_new_lines(tmp_path):
    root = str(tmp_path / 'logs')
    web, _ = lines(False)
    logs_mini.write(logs_mini.log_path(root, FOLDER, 'host1', 'web-1', 'p1'), web.replace('"msg": "handled request"', '"corr": "c-1", "msg": "handled request"', 1))
    cfg = dataclasses.replace(config.Config(), log_dir=root, data_dir=str(tmp_path / 'data'), inbox_dir=str(tmp_path / 'inbox'), state_dir=str(tmp_path / 'data'),
                              cache_dir=str(tmp_path / 'cache'), offline=True, log_formats_file=str(tmp_path / 'none.toml'))
    con = db.open(cfg.db_path)
    before, was = lf.current(), an.all_current()
    try:
        lf.use(lf.rules_from(dict(service=[dict(match='web-1', format='caddy-json'), dict(match='*', format='plain')])))
        an.use(an.parse({'s3': {'request_id': 'corr'}}))
        ingest.run(cfg, con, workers=0)
        assert con.execute("SELECT request_id FROM http_access WHERE request_id IS NOT NULL").fetchall() == [('c-1',)]
    finally:
        con.close(); lf.use(before); an.use(was)


def test_business_rules_count_requests_and_log_lines(site):
    cur, cfg = site.cur, site.cfg
    assert q_biz.business(cur, FOLDER, cfg)['custom'] == dict(rules=[], prev_folder=None, access='web-1', suggestions=[dict(rule=dict(
        name='Orders', service='web-1', match='request', method='POST', path='/api/orders', status='2xx', text=''), count=2)])
    an.use(an.parse({'s3': {'business': [
        dict(name='Orders', service='web-1', match='request', method='POST', path='/api/orders', status='2xx'),
        dict(name='Failed Logins', service='web-1', match='request', path='/api/login', status='4xx'),
        dict(name='Order Pages', service='web-1', match='request', path='/api/orders/*'),
        dict(name='Payments', service='app-1', match='log_line', text='payment received')]}}))
    c = q_biz.business(cur, FOLDER, cfg)['custom']
    assert {r['name']: r['n'] for r in c['rules']} == {'Orders': 2, 'Failed Logins': 1, 'Order Pages': 1, 'Payments': 1} and c['suggestions'] == []
    assert all(r['prev'] is None and not r['comparable'] for r in c['rules'])


def test_the_sql_and_python_rules_agree(site):
    cur, cfg = site.cur, site.cfg
    rows = cur.execute('SELECT method, path_key, status FROM http_access WHERE folder = ? AND service = ?', [FOLDER, 'web-1']).fetchall()
    for m in (an.metric_from(dict(name='a', service='web-1', match='request', method='GET', status='5xx'), 'x'), an.metric_from(dict(name='b', service='web-1', match='request', path='/api/*'), 'x'),
              an.metric_from(dict(name='c', service='web-1', match='request', status='404'), 'x')):
        assert q_an.count_rule(cur, FOLDER, m) == sum(an.request_matches(m, 'web-1', *r) for r in rows), m.name


def test_pages_say_nothing_for_a_folder_without_an_access_log(tmp_path):
    root = str(tmp_path / 'logs')
    logs_mini.write(logs_mini.log_path(root, FOLDER, 'host1', 'app-1', 'p1'), lines(True)[1])
    cfg = dataclasses.replace(config.Config(), log_dir=root, data_dir=str(tmp_path / 'data'), inbox_dir=str(tmp_path / 'inbox'), state_dir=str(tmp_path / 'data'),
                              cache_dir=str(tmp_path / 'cache'), offline=True, log_formats_file=str(tmp_path / 'none.toml'))
    con = db.open(cfg.db_path)
    before = lf.current()
    try:
        lf.use(lf.rules_from(dict(service=[dict(match='app-1', format='json'), dict(match='*', format='plain')])))
        ingest.run(cfg, con, workers=0)
        cur = con.cursor()
        assert q_av.availability(cur, FOLDER, cfg) == {'available': False, 'reason': 'no_nginx'}
        assert q_tr.tracing(cur, FOLDER, cfg) == {'available': False, 'reason': 'no_events_service'}
        g = q_rc.rootcause(cur, FOLDER, cfg)['generic']
        assert g['access'] is None and g['error_lines'] == 3 and g['upstream'] == dict(legacy=False, total=0, rows=[])
        assert q_biz.business(cur, FOLDER, cfg)['custom']['suggestions'] == []
    finally:
        con.close(); lf.use(before)


def test_containers_join_the_metrics_with_the_log_lines(site, tmp_path):
    cur, cfg = site.cur, site.cfg
    now = datetime.datetime(2026, 10, 12, 4, 0, tzinfo=UTC)
    store = MetricsStore(str(tmp_path / 'metrics.duckdb'))
    try:
        t = lambda **kw: now - datetime.timedelta(**kw)
        pts = [('docker-host-01', ctr, 'restarts', '', t(hours=h), v) for ctr, vals in (('app-1', (0, 0)), ('web-1', (1, 3))) for h, v in zip((10, 0), vals)]
        store.add(1, pts, {('docker-host-01', ''): dict(os='Ubuntu'), ('docker-host-01', 'app-1'): dict(image='app:2.0'), ('docker-host-01', 'web-1'): dict(image='caddy:2'),
                           ('docker-host-01', 'idle-1'): dict(image='nginx:1.29')}, now)
        collectors = [dict(id=1, name='dock', platform='docker', status='online'), dict(id=2, name='k8s', platform='kubernetes', status='online')]
        mcur = store.cursor()
        d = q_ctr.containers(cur, mcur, collectors, FOLDER, now)
        assert d['available'] and [h['host'] for h in d['hosts']] == ['docker-host-01']
        rows = {r['container']: r for r in d['hosts'][0]['rows']}
        assert [r['container'] for r in d['hosts'][0]['rows']] == ['app-1', 'idle-1', 'web-1']
        assert (rows['app-1']['lines'], rows['app-1']['err'], rows['app-1']['warn'], rows['app-1']['image']) == (7, 3, 1, 'app:2.0') and rows['web-1']['restarts'] == 2
        assert d['kpi'] == dict(containers=3, running=3, with_logs=2, without_logs=['idle-1'], err=5, err_containers=2, restarts=2)   # a 5xx of the access log is an error line too (agg_service.err)
        assert q_ctr.containers(cur, mcur, collectors[1:], FOLDER, now) == dict(available=False, reason='no_docker_hosts')
        mcur.close()
    finally: store.close()
