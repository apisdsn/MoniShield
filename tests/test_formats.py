"""Common log formats (domain/formats.py, step 1b of docs/11-log-formats.md) on public sample lines in fixtures/formats."""
import dataclasses, datetime, glob, os, re

import logs_mini
from monishield.domain import formats as F, log_formats as lf, parse
from monishield.infrastructure import config, db, ingest

FIX = os.path.join(os.path.dirname(__file__), 'fixtures', 'formats')
UTC = datetime.timezone.utc
RULES = lf.rules_from({'service': [
    {'match': 'web-*', 'format': 'nginx-combined'},
    {'match': 'apache', 'format': 'apache-combined'},
    {'match': 'orders-api', 'format': 'json', 'features': ['tracing'],
     'fields': {'request_id': 'req.id', 'ip': 'req.remoteAddress', 'status': 'res.statusCode', 'duration_ms': 'responseTime'}},
    {'match': 'payments', 'format': 'logfmt'},
    {'match': 'hosts', 'format': 'syslog'},
    {'match': 'legacy-erp', 'format': 'regex', 'pattern': r'^\[(?P<time>[^\]]+)\] (?P<level>\w+) (?P<message>.*)$',
     'time_format': '%d/%m/%Y %H:%M:%S', 'multiline': r'^\[', 'levels': {'SEVERE': 'ERROR', 'WARNING': 'WARN'}},
    {'match': 'worker-*', 'format': 'auto'},
    {'match': '*', 'format': 'plain'},
]})


def read(name, service):
    o = parse.Out(service, namespace='shop', format_rules=RULES)
    with open(os.path.join(FIX, name), encoding='utf-8') as fh: s = parse.parse_lines(fh, o)
    return s, o.data


def test_nginx_combined():
    s, d = read('nginx-combined.log', 'web-shop')
    rows = d['http_access']
    assert (s['lines'], s['unmatched_lines'], s['err'], len(rows)) == (4, 1, 1, 3)    # the 502 is an error; one line is not a log line
    first = dict(zip(parse.TABLES['http_access'], rows[0]))
    assert (first['ts_utc'], first['ip'], first['method'], first['path'], first['status'], first['bytes']) == ('2026-10-10 13:55:36', '203.0.113.5', 'GET', '/api/orders?id=1', 200, 2326)
    assert (first['user_name'], first['duration_ms'], first['ua']) == ('alice', 123.0, 'Mozilla/5.0 (X11; Linux x86_64)')
    assert first['path_key'] == '/api/orders' and s['known_service']


def test_apache_combined_with_offset_and_no_bytes():
    s, d = read('apache-combined.log', 'apache')
    rows = [dict(zip(parse.TABLES['http_access'], r)) for r in d['http_access']]
    assert s['unmatched_lines'] == 0 and rows[0]['ts_utc'] == '2026-10-10 20:55:36'     # -0700 -> UTC
    assert (rows[1]['status'], rows[1]['bytes'], rows[1]['user_name']) == (401, None, None)


def test_json_lines_pino():
    s, d = read('pino.json.log', 'orders-api')
    rows = [dict(zip(parse.TABLES['app_line'], r)) for r in d['app_line']]
    assert (s['lines'], s['unmatched_lines'], s['err'], s['warn'], len(rows)) == (4, 1, 1, 1, 3)
    assert (rows[0]['level'], rows[0]['request_id'], rows[0]['method'], rows[0]['path_key'], rows[0]['status'], rows[0]['duration_ms']) == ('INFO', 'r-1', 'GET', '/api/items', 200, 12.5)
    assert rows[0]['ts_utc'] == '2026-10-10 13:55:36'                                     # epoch milliseconds
    assert (rows[1]['level'], rows[1]['message']) == ('ERROR', 'payment provider timeout') and rows[2]['ts_utc'] == '2026-10-10 13:55:38'
    assert ['level', 'ERROR', 1] in s['counters'] and d['log_message'][0][2] == 'ERROR'   # error messages feed the Messages table


def test_logfmt():
    s, d = read('logfmt.log', 'payments')
    rows = [dict(zip(parse.TABLES['app_line'], r)) for r in d['app_line']]
    assert (s['unmatched_lines'], [r['level'] for r in rows]) == (1, ['INFO', 'WARN', 'ERROR'])
    assert (rows[1]['request_id'], rows[1]['duration_ms'], rows[2]['logger']) == ('abc123', 1520.0, 'db.pool')


def test_syslog_both_rfcs():
    now = datetime.datetime(2026, 10, 20, tzinfo=UTC)
    r3164 = F.read_syslog("<34>Oct 11 22:14:15 mymachine su: 'su root' failed", lf.Rule('h', 'syslog', 'app'), now)
    assert (r3164['time'], r3164['level'], r3164['logger']) == ('2026-10-11 15:14:15', 'ERROR', 'su')   # no zone: local +7 -> UTC
    r5424 = F.read_syslog('<165>1 2026-10-11T22:14:15.003Z h evntslog - ID47 [x@1 a="1"] An event', lf.Rule('h', 'syslog', 'app'), now)
    assert (r5424['time'], r5424['level'], r5424['message']) == ('2026-10-11 22:14:15', 'INFO', 'An event')
    s, _ = read('syslog.log', 'hosts')
    assert (s['lines'], s['unmatched_lines']) == (3, 0)


def test_regex_with_multiline_stack_trace_and_own_levels():
    s, d = read('legacy-erp.log', 'legacy-erp')
    rows = [dict(zip(parse.TABLES['app_line'], r)) for r in d['app_line']]
    assert (s['lines'], len(rows), s['unmatched_lines']) == (6, 3, 0)                    # the stack trace joins its entry
    assert [r['level'] for r in rows] == ['INFO', 'ERROR', 'WARN'] and rows[1]['line_no'] == 2
    assert 'SocketException' in rows[1]['message'] and rows[0]['ts_utc'] == '2026-10-10 06:55:36'


def test_plain_and_auto_until_detection():
    s, d = read('plain.log', 'anything')
    assert [r[3] for r in d['app_line']] == ['INFO', 'ERROR', 'WARN'] and s['unmatched_lines'] == 0
    s, d = read('plain.log', 'worker-mail')                                              # auto = plain until step 1d
    assert len(d['app_line']) == 3


def test_time_formats_and_levels():
    assert F.parse_time('2026-10-10T13:55:36+07:00') == '2026-10-10 06:55:36'
    assert F.parse_time('2026-10-10 13:55:36,123') == '2026-10-10 06:55:36'               # no zone: the site's local time
    assert F.parse_time(1791640536, 'epoch') == F.parse_time('1791640536000', 'epoch_ms') == '2026-10-10 13:55:36'
    assert F.parse_time('10/Oct/2026:13:55:36 +0000', 'clf') == '2026-10-10 13:55:36'
    assert F.parse_time('yesterday') is None and F.parse_time('99/99/9999', '%d/%m/%Y') is None
    assert [F.level_of(x) for x in ('warning', 'E', 50, '30', 'notice', 'FATAL', 'weird')] == ['WARN', 'ERROR', 'ERROR', 'INFO', 'INFO', 'ERROR', None]
    assert F.level_of('SEVERE', {'SEVERE': 'ERROR'}) == 'ERROR' and F.guess_level('all fine') == 'INFO'


def test_entries_without_and_with_multiline():
    assert list(F.entries(['a\n', 'b\n'])) == [(1, 'a'), (2, 'b')]
    assert list(F.entries(['  orphan', '[1] x', '  more', '[2] y'], re.compile(r'^\['))) == [(1, '  orphan'), (2, '[1] x\n  more'), (4, '[2] y')]


def test_built_in_rules_read_exactly_as_before(tmp_path):
    """No rules file: every legacy service is read by today's parser; the tables and counters do not change."""
    root = logs_mini.build(tmp_path / 'logs')
    rules = lf.default_rules(parse.services.current())
    for path in sorted(p for p in glob.glob(os.path.join(root, '**', '*.log'), recursive=True)):
        svc = os.path.basename(os.path.dirname(path))
        a, b = parse.Out(svc), parse.Out(svc, namespace='tenant', format_rules=rules)
        lines = open(path, encoding='utf-8', errors='replace').readlines()
        sa, sb = parse.parse_lines(iter(lines), a), parse.parse_lines(iter(lines), b)
        assert sa == sb and a.data == b.data, path


def test_ingest_fills_the_common_tables(tmp_path):
    root = tmp_path / 'logs'
    day = root / '2026-10-11' / 'shop'
    for svc, name in (('web-shop', 'nginx-combined.log'), ('orders-api', 'pino.json.log'), ('legacy-erp', 'legacy-erp.log')):
        (day / svc).mkdir(parents=True)
        (day / svc / f'log_{svc}_pod-1_2026-10-11-00-00.log').write_text(open(os.path.join(FIX, name), encoding='utf-8').read())
    cfg = dataclasses.replace(config.Config(), log_dir=str(root), data_dir=str(tmp_path / 'data'), inbox_dir=str(tmp_path / 'inbox'), offline=True)
    con = db.open(cfg.db_path)
    before = lf.current()
    lf.use(RULES)
    try: res = ingest.run(cfg, con, workers=0)
    finally: lf.use(before)
    assert not [w for w in res['warnings'] if 'unknown service' in w]                    # the rules file names them
    q = lambda sql: con.execute(sql).fetchall()
    assert q("SELECT service, count(*) FROM http_access GROUP BY 1") == [('web-shop', 3)]
    assert sorted(q("SELECT service, count(*) FROM app_line GROUP BY 1")) == [('legacy-erp', 3), ('orders-api', 3)]
    assert dict(q("SELECT service, lines_unmatched FROM ingest_file")) == {'web-shop': 1, 'orders-api': 1, 'legacy-erp': 0}
    assert dict(q("SELECT service, err FROM ingest_file")) == {'web-shop': 1, 'orders-api': 1, 'legacy-erp': 1}
