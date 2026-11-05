"""Step 1c of docs/11-log-formats.md: pages and attack detection read the common formats (http_access, app_line)."""
import json, os

import logs_mini
from test_derive_core import make

SNAPSHOT = os.path.join(os.path.dirname(__file__), 'fixtures', 'derive_snapshot.json')


def _cell(v):
    if isinstance(v, float): return round(v, 6)
    if isinstance(v, (list, tuple)): return [_cell(x) for x in v]
    if isinstance(v, dict): return {str(k): _cell(x) for k, x in sorted(v.items())}
    return v if v is None or isinstance(v, (int, str)) else str(v)


def dump_aggregates(con):
    """{table: sorted rows} of every agg_* table, as plain JSON values."""
    out = {}
    for (t,) in con.execute("SELECT table_name FROM information_schema.tables WHERE table_name LIKE 'agg\\_%' ESCAPE '\\' ORDER BY 1").fetchall():
        out[t] = sorted(json.dumps(_cell(list(r)), sort_keys=True) for r in con.execute(f'SELECT * FROM {t}').fetchall())
    return out


# The pages read the common formats
import dataclasses

import pytest

from monishield.domain import log_formats as lf, parse
from monishield.infrastructure import config, db, ingest
from monishield.infrastructure.derive import DERIVE_VERSION
from monishield.infrastructure.queries import ips as q_ips, search as q_search, service as q_service

FOLDER = '2026-10-11'
SHOP = '''\
203.0.113.5 - - [11/Oct/2026:10:00:01 +0000] "GET /api/orders?id=1 HTTP/1.1" 200 512 "-" "Mozilla/5.0" 0.120
203.0.113.5 - - [11/Oct/2026:10:00:02 +0000] "GET /api/orders?id=2 HTTP/1.1" 404 10 "-" "Mozilla/5.0" 0.020
198.51.100.7 - - [11/Oct/2026:10:30:00 +0000] "POST /api/orders HTTP/1.1" 502 157 "-" "curl/8.4.0" 2.500
192.0.2.10 - - [11/Oct/2026:11:05:00 +0000] "GET /?id=1%20UNION%20SELECT%20username,password%20FROM%20users-- HTTP/1.1" 200 100 "-" "Mozilla/5.0" 0.010
this is not an access log line
'''
RULES_TOML = '''\
[[service]]
match = "web-shop"
format = "nginx-combined"
kind = "http"

[[service]]
match = "orders-api"
format = "json"
kind = "app"
fields = { request_id = "req.id", ip = "req.remoteAddress", status = "res.statusCode", duration_ms = "responseTime" }
'''


@pytest.fixture
def site(tmp_path):
    """One folder with web-shop read as nginx-combined and orders-api as json, ingested and derived."""
    day = tmp_path / 'logs' / FOLDER / 'shop'
    for svc, text in (('web-shop', SHOP), ('orders-api', open(os.path.join(os.path.dirname(__file__), 'fixtures', 'formats', 'pino.json.log'), encoding='utf-8').read())):
        logs_mini.write(logs_mini.log_path(str(tmp_path / 'logs'), FOLDER, 'shop', svc, 'pod-1'), text)
    toml = tmp_path / 'log-formats.toml'
    toml.write_text(RULES_TOML)
    cfg = dataclasses.replace(config.Config(), log_dir=str(tmp_path / 'logs'), data_dir=str(tmp_path / 'data'), inbox_dir=str(tmp_path / 'inbox'),
                              state_dir=str(tmp_path / 'data'), cache_dir=str(tmp_path / 'cache'), offline=True, log_formats_file=str(toml))
    con = db.open(cfg.db_path)
    before = lf.current()
    lf.use(config.log_format_rules(cfg))
    ingest.run(cfg, con, workers=0)
    yield cfg, con
    lf.use(before)
    con.close()


def rows(con, sql, *p): return con.execute(sql, list(p)).fetchall()


def test_service_numbers(site):
    _, con = site
    got = {r[0]: r[1:] for r in rows(con, """SELECT service, lines, err, warn, err_http, err_log, requests, n4xx, n5xx, ip_unique
                                             FROM agg_service WHERE folder = ?""", FOLDER)}
    #                       lines err warn err_http err_log requests 4xx 5xx ip_unique
    assert got['web-shop'] == (5, 1, 0, 1, 0, 4, 1, 1, 3)       # the unread line is a line, not a request
    assert got['orders-api'] == (4, 1, 1, 0, 1, 2, 0, 1, 0)     # JSON request logs count as requests (app_line keeps no IP); their ERROR is a log error


def test_hour_status_endpoint_and_ip(site):
    _, con = site
    hour = lambda svc: [(f'{h:%d %H}', t, e) for h, t, e in rows(con, 'SELECT hour_wib, total, err FROM agg_hour WHERE service = ? ORDER BY 1', svc)]
    assert hour('web-shop') == [('11 17', 3, 1), ('11 18', 1, 0)]            # 10:00-10:30 and 11:05 UTC, shown in local time (+7 h)
    assert hour('orders-api') == [('10 20', 3, 1)]                           # the WARN line has its own time too
    status = lambda svc: rows(con, 'SELECT status, n FROM agg_status WHERE service = ? ORDER BY 1', svc)
    assert status('web-shop') == [(200, 2), (404, 1), (502, 1)] and status('orders-api') == [(200, 1), (500, 1)]
    ep = {(s, k): r for s, k, *r in rows(con, 'SELECT service, key, requests, n4xx, n5xx, dur_n, dur_max FROM agg_endpoint WHERE service IN (?, ?)', 'web-shop', 'orders-api')}
    assert ep['web-shop', 'GET /api/orders'] == [2, 1, 0, 2, 0.12] and ep['web-shop', 'POST /api/orders'] == [1, 0, 1, 1, 2.5]
    assert ep['web-shop', 'GET /'] == [1, 0, 0, 1, 0.01] and ep['orders-api', 'POST /api/pay'] == [1, 0, 1, 1, 2.005]
    assert rows(con, "SELECT status, key, n FROM agg_endpoint_error WHERE service = 'web-shop' ORDER BY 1") == [(404, 'GET /api/orders', 1), (502, 'POST /api/orders', 1)]
    assert rows(con, "SELECT status, key FROM agg_endpoint_error WHERE service = 'orders-api'") == [(500, 'POST /api/pay')]
    assert rows(con, "SELECT ip, requests, n4xx, ua_first_4xx FROM agg_ip WHERE service = 'web-shop' ORDER BY 1") == [
        ('192.0.2.10', 1, 0, None), ('198.51.100.7', 1, 0, None), ('203.0.113.5', 2, 1, 'Mozilla/5.0')]
    assert rows(con, "SELECT count(*) FROM agg_ip WHERE service = 'orders-api'") == [(0,)]       # app_line has no IP column


def test_levels_and_messages_are_not_counted_twice(site):
    """app_line feeds agg_level / agg_message through the parser's counters and log_message rows; derive adds no second branch."""
    _, con = site
    assert rows(con, "SELECT level, n FROM agg_level WHERE service = 'orders-api' ORDER BY 1") == [('ERROR', 1), ('INFO', 1), ('WARN', 1)]
    assert rows(con, "SELECT level, n, msg_key FROM agg_message WHERE service = 'orders-api' ORDER BY 1") == [
        ('ERROR', 1, 'ERROR | payment provider timeout'), ('WARN', 1, 'WARN | cache miss rate high')]
    assert rows(con, "SELECT count(*) FROM agg_level WHERE service = 'web-shop'") == [(0,)]     # an access log has no levels
    assert rows(con, "SELECT count(*) FROM app_line WHERE folder = ?", FOLDER) == [(3,)]         # one app_line row per entry, one level count each
    assert rows(con, "SELECT sum(n) FROM file_counter WHERE kind = 'level'") == [(3,)]


def test_attack_in_an_access_log_is_detected(site):
    _, con = site
    hit = rows(con, "SELECT ip, crs_attack, crs_score, capec FROM http_access WHERE crs_score IS NOT NULL")
    assert [h[0] for h in hit] == ['192.0.2.10'] and hit[0][1] == 'sqli' and hit[0][2] >= 5
    assert rows(con, "SELECT ip, hits FROM agg_crs_ip") == [('192.0.2.10', 1)]
    url = rows(con, "SELECT method_path, attack, hits, top_ip, upstreams FROM agg_crs_url")
    assert len(url) == 1 and url[0][0].startswith("GET /?id=1") and url[0][2:] == (1, '192.0.2.10', ['web-shop'])
    assert [(f'{h:%d %H}', n) for h, n in rows(con, "SELECT hour_wib, n FROM agg_crs_hour")] == [('11 18', 1)]
    assert rows(con, "SELECT count(*) FROM agg_attack_url") == [(0,)]            # the old rules stay ingress-only


def test_ip_profile_search_and_map(site):
    cfg, con = site
    p = q_ips.ip_profile(con, FOLDER, cfg, '192.0.2.10')
    assert (p['kpi']['requests'], p['kpi']['attacks']) == (1, 1) and p['folders'][0]['requests'] == 1 and p['folders'][0]['attacks'] == 1
    assert p['requests'][0]['path'].startswith('/?id=1 UNION SELECT') and p['requests'][0]['category'].endswith('/sqli') and p['requests'][0]['rules']
    p = q_ips.ip_profile(con, FOLDER, cfg, '203.0.113.5')
    assert (p['kpi']['requests'], p['kpi']['n4xx'], p['kpi']['attacks'], p['kpi']['endpoints']) == (2, 1, 0, 1)
    r = q_search.search(con, dict(q='198.51.100', folder=FOLDER))
    assert [(x['type'], x['label']) for x in r['results']] == [('ip', '198.51.100.7')]
    assert rows(con, "SELECT ip, upstream, pod, n FROM agg_flow ORDER BY 1") == [
        ('192.0.2.10', 'web-shop', '-', 1), ('198.51.100.7', 'web-shop', '-', 1), ('203.0.113.5', 'web-shop', '-', 2)]


def test_range_and_ip_sources(site):
    _, con = site
    a, b = rows(con, 'SELECT range_start_utc, range_end_utc FROM folder_state')[0]
    assert (str(a), str(b)) == ('2026-10-10 13:55:36', '2026-10-11 11:05:00')            # app_line and http_access both count
    from monishield.infrastructure import refdata
    ips = {r[0] for r in con.execute(refdata.IP_SOURCES).fetchall()}
    assert {'192.0.2.10', '198.51.100.7', '203.0.113.5'} <= ips


def test_service_page_shows_format_and_unread_rate(site):
    _, con = site
    shop = q_service.service_page(con, FOLDER, 'web-shop')
    assert shop['format'] == dict(preset='nginx-combined', kind='http', unread=0.2)         # 1 of 5 lines
    api = q_service.service_page(con, FOLDER, 'orders-api')
    assert api['format'] == dict(preset='json', kind='app', unread=0.25)                    # 1 of 4 lines
    assert api['kpi']['requests'] == 2 and dict(api['levels'])['ERROR'] == 1


def test_legacy_preset_has_no_unread_rate(tmp_path):
    root = logs_mini.build(tmp_path / 'logs')
    cfg = dataclasses.replace(config.Config(), log_dir=root, data_dir=str(tmp_path / 'data'), inbox_dir=str(tmp_path / 'inbox'), offline=True)
    con = db.open(cfg.db_path)
    before = lf.current()
    lf.use(lf.default_rules(parse.services.current()))
    try:
        ingest.run(cfg, con, workers=0)
        page = q_service.service_page(con, '2026-01-02', 'nginx-ingress-controller')
    finally: lf.use(before)
    assert page['format'] == dict(preset='ingress-nginx', kind='http', unread=None)


# Derive version and legacy numbers
def test_old_folders_are_derived_once_without_parsing(site):
    cfg, con = site
    good = dump_aggregates(con)
    assert rows(con, 'SELECT derive_version FROM folder_state') == [(DERIVE_VERSION,)]
    con.execute('UPDATE folder_state SET derive_version = NULL')                     # a folder derived before step 1c
    for t in ('agg_service', 'agg_hour', 'agg_status', 'agg_endpoint', 'agg_ip', 'agg_flow', 'agg_crs_url'): con.execute(f'DELETE FROM {t}')
    con.execute('UPDATE http_access SET crs_score = NULL, crs_rules = NULL')
    res = ingest.run(cfg, con, workers=0)
    assert res['folders_rederived'] == [FOLDER] and res['files_parsed'] == 0           # raw tables are enough: no re-parse
    assert dump_aggregates(con) == good
    assert ingest.run(cfg, con, workers=0)['folders_rederived'] == []                  # once only


def test_legacy_aggregates_are_unchanged(tmp_path):
    """Built-in rules, the legacy fixtures: every aggregate equals the snapshot taken from the code before step 1c."""
    cfg, con = make(tmp_path, logs_mini.build(tmp_path / 'logs'), workers=0)
    want = json.load(open(SNAPSHOT, encoding='utf-8'))
    got = dump_aggregates(con)
    assert sorted(want) == sorted(got)
    for t in want: assert got[t] == want[t], t
