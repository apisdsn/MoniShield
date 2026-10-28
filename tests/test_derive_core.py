"""Core aggregates (TRD §3.4, §4.3): logs_mini, values computed by hand from lines in fixtures/lines,
computed without top-N truncation."""
import collections, dataclasses, os

import pytest

import logs_mini
from monishield.infrastructure import config, db, ingest

A, B = '2026-01-01', '2026-01-02'
NG, FE, SL, AM = 'nginx-ingress-controller', 'web-frontend', 'event-api', 'auth-service'
C = collections.Counter


def make(tmp_path, log_dir, **kw):
    cfg = dataclasses.replace(config.Config(), log_dir=str(log_dir), data_dir=str(tmp_path / 'data'), inbox_dir=str(tmp_path / 'inbox'),
                              state_dir=str(tmp_path / 'data'), cache_dir=str(tmp_path / 'cache'), offline=True)
    con = db.open(cfg.db_path)
    ingest.run(cfg, con, **kw)
    return cfg, con


@pytest.fixture
def mini(tmp_path):
    cfg, con = make(tmp_path, logs_mini.build(tmp_path / 'logs'), workers=0)
    yield con
    con.close()


def q(con, sql, *p): return con.execute(sql, list(p)).fetchall()
def H(ts): return f'{ts:%Y-%m-%d %H}'
def M(ts): return f'{ts:%Y-%m-%d %H:%M}'


# ------------------------------------------------------------------ (a) computed by hand
def test_service(mini):
    rows = {r[1]: r[2:] for r in q(mini, 'SELECT * FROM agg_service WHERE folder = ?', B)}
    #            lines err warn err_http err_log files empty corrupt requests n4xx n5xx ip_unique users_ok
    assert rows[NG] == (11, 2, 1, 0, 2, 1, 0, 0, 7, 2, 0, 7, 0)
    assert rows[SL] == (9, 0, 2, 0, 0, 1, 0, 0, 4, 1, 0, 2, 0)          # 2 non-5xx failed events = warning
    assert rows['coredns'] == (3, 1, 0, 0, 1, 1, 0, 0, 0, 0, 0, 0, 0)
    assert rows['reference-service'] == (1, 0, 0, 0, 0, 1, 0, 1, 0, 0, 0, 0, 0)  # corrupt file: 1 row, 0 content
    assert rows[AM] == (0, 0, 0, 0, 0, 1, 1, 0, 0, 0, 0, 0, 0)                  # empty file still has a service row
    assert rows['unknown-service'][:3] == (10, 1, 4) and rows['unknown-service'][-1] == 1
    a = {r[1]: r[2:] for r in q(mini, 'SELECT * FROM agg_service WHERE folder = ?', A)}
    assert a[FE] == (5, 1, 0, 0, 1, 1, 0, 0, 2, 1, 0, 2, 0) and a[AM] == (10, 1, 4, 0, 1, 1, 0, 0, 0, 0, 0, 0, 1)


def test_hour_wib_and_error_logs_count_per_hour(mini):
    h = lambda svc, f: {H(r[0]): r[1:] for r in q(mini, 'SELECT hour_wib, total, err FROM agg_hour WHERE folder = ? AND service = ?', f, svc)}
    # nginx access: 17:03, 17:02, 17:10, 17:22 UTC 27 Sep -> 00 WIB 28 Sep; 21:54 -> 04; 02:05 (28) -> 09; 16:15 (28) -> 23
    # error log: [error] 18:45 UTC 27 Sep -> 01 WIB; [crit] 16:31 UTC 29 Sep -> 23 WIB 29 Sep; [warn] not counted
    assert h(NG, B) == {'2026-09-28 00': (4, 0), '2026-09-28 01': (0, 1), '2026-09-28 04': (1, 0), '2026-09-28 09': (1, 0),
                        '2026-09-28 23': (1, 0), '2026-09-29 23': (0, 1)}
    assert h(FE, A) == {'2026-09-28 00': (1, 0), '2026-09-28 06': (1, 1)}       # 404 is not an error; [error] line 23:29 UTC -> 06 WIB
    assert h(AM, A) == {'2026-09-25 23': (2, 0), '2026-09-28 00': (1, 1), '2026-09-28 05': (1, 0), '2026-09-28 06': (3, 0)}
    assert h('report-service', B) == {'2026-09-28 02': (3, 0), '2026-09-28 09': (1, 0)}
    assert h(SL, B) == {} and h('coredns', B) == {}                              # no timestamp
    for svc, f in ((NG, B), (FE, A), (AM, A)):                                   # errors per hour sum = Error KPI
        assert sum(v[1] for v in h(svc, f).values()) == q(mini, 'SELECT err FROM agg_service WHERE folder = ? AND service = ?', f, svc)[0][0]


def test_status_upstream_ua(mini):
    assert dict(q(mini, 'SELECT status, n FROM agg_status WHERE folder = ? AND service = ?', B, NG)) == {200: 4, 403: 1, 401: 1, 101: 1}
    assert dict(q(mini, 'SELECT status, n FROM agg_status WHERE folder = ? AND service = ?', B, SL)) == {200: 3, 401: 1}
    assert {r[0]: r[1:] for r in q(mini, 'SELECT upstream, requests, n5xx FROM agg_upstream WHERE folder = ?', B)} == {
        'web-frontend-3000': (2, 0), 'event-api-3000': (1, 0), '-': (1, 0), 'auth-service-3000': (1, 0), 'cattle-system-rancher-80': (2, 0)}
    ua = dict(q(mini, 'SELECT ua90, n FROM agg_ua WHERE folder = ?', B))
    assert sum(ua.values()) == 7 and ua['Uptime-Kuma/2.0.2'] == 1 and ua['Go-http-client/1.1'] == 1 and max(map(len, ua)) <= 90


def test_endpoint_and_percentiles(mini):
    e = {r[0]: r[1:] for r in q(mini, 'SELECT key, requests, n4xx, n5xx, dur_n, dur_max, p50, p95, p99 FROM agg_endpoint WHERE folder = ? AND service = ?', B, NG)}
    assert e['GET /reports/count'] == (1, 0, 0, 1, 117.933, 117.933, 117.933, 117.933)     # query stripped from the key
    assert e['GET /forum/core/css.php'] == (1, 1, 0, 1, 0.0, 0.0, 0.0, 0.0) and e['GET /v1/user/select'][:3] == (1, 1, 0)
    assert e['GET /v3/projects/local:p-24lsk/subscribe'] == (1, 0, 0, 0, None, None, None, None)  # 101 websocket: no duration
    assert len(e) == 7
    s = {r[0]: r[1:] for r in q(mini, 'SELECT key, requests, n4xx, dur_n, p50 FROM agg_endpoint WHERE folder = ? AND service = ?', B, SL)}
    assert s == {'GET /uploads': (1, 0, 1, 0.048), 'PATCH /regenerate-document': (1, 0, 1, 3.243), 'GET /reports/count': (1, 1, 1, 0.001), 'POST /files': (1, 0, 1, 0.088)}
    assert q(mini, "SELECT key, requests FROM agg_endpoint WHERE service = 'coredns'") == [('backup-example-volume.s3.ap-southeast-3.amazonaws.com.', 1)]
    assert q(mini, 'SELECT domain, n FROM v_dns') == [('backup-example-volume.s3.ap-southeast-3.amazonaws.com.', 1)]
    assert {r[0] for r in q(mini, 'SELECT key FROM agg_endpoint WHERE service = ?', FE)} == {'GET /submit-report', 'GET /apple-touch-icon-precomposed.png'}


def test_endpoint_error(mini):
    assert q(mini, 'SELECT status, key, n FROM agg_endpoint_error WHERE service = ? ORDER BY 1', NG) == [(401, 'GET /v1/user/select', 1), (403, 'GET /forum/core/css.php', 1)]
    assert q(mini, 'SELECT status, key, n FROM agg_endpoint_error WHERE service = ?', FE) == [(404, '/apple-touch-icon-precomposed.png', 1)]  # no method
    assert q(mini, 'SELECT status, key, n FROM agg_endpoint_error WHERE service = ? ORDER BY 1', SL) == [(200, 'POST /files', 1), (401, 'GET /reports/count', 1)]  # failed events only


def test_ip(mini):
    ip = {r[0]: r[1:] for r in q(mini, 'SELECT ip, requests, n4xx, ua_first_4xx FROM agg_ip WHERE folder = ? AND service = ?', B, NG)}
    assert len(ip) == 7 and ip['66.66.66.107'] == (1, 1, 'Go-http-client/1.1') and ip['66.66.66.100'] == (1, 0, None)
    assert ip['66.66.66.221'][:2] == (1, 1) and ip['66.66.66.221'][2].startswith('Mozilla/5.0 (Linux; Android 10; K)') and len(ip['66.66.66.221'][2]) == 100
    assert dict(q(mini, 'SELECT ip, requests FROM agg_ip WHERE service = ?', SL)) == {'66.66.66.213': 1, '66.66.66.126': 1}  # failed event without ipAddress
    assert dict(q(mini, 'SELECT ip, n4xx FROM agg_ip WHERE service = ?', FE)) == {'66.66.66.213': 0, '66.66.66.209': 1}


def test_effective_level_events_service(mini):
    assert dict(q(mini, 'SELECT level, n FROM agg_level WHERE folder = ? AND service = ?', B, SL)) == {'INFO': 4, 'PERFORMANCE': 1, 'WARN': 2}  # original tag: ERROR 2
    assert dict(q(mini, 'SELECT level, n FROM agg_level WHERE folder = ? AND service = ?', A, AM)) == {'ERROR': 1, 'INFO': 2, 'WARN': 4, 'Hibernate SQL': 1}


def test_messages_and_first_sample(mini, tmp_path):
    m = {r[0]: r[1:] for r in q(mini, 'SELECT msg_key, level, n, sample_raw FROM agg_message WHERE folder = ? AND service = ?', B, NG)}
    assert set(m) == {'ERROR | recv() failed (#: Connection reset by peer) while reading response header from upstream',
                      'WARN | a client request body is buffered to a temporary file /tmp/client-body/#',
                      'CRIT | connect() to #.#:# failed (#: Invalid argument) while connecting to upstream'}
    assert all(v[1] == 1 and v[2].startswith('2026/09/') for v in m.values())
    # two files, same key: the sample is taken from the file that comes first by relpath
    root = logs_mini.build(tmp_path / 'dua')
    err = logs_mini.lines(NG).splitlines()[7]
    logs_mini.write(logs_mini.log_path(root, B, 'ingress-nginx', NG, 'pod-a'), err.replace('*90237038', '*111') + '\n')
    logs_mini.write(logs_mini.log_path(root, B, 'ingress-nginx', NG, 'pod-z'), err.replace('*90237038', '*999') + '\n')
    _, con = make(tmp_path / 'x', root, workers=0)
    n, raw = q(con, "SELECT n, sample_raw FROM agg_message WHERE service = ? AND msg_key LIKE 'ERROR | recv%'", NG)[0]
    assert n == 3 and '*111 ' in raw
    con.close()


def test_slow_flow_pod_retry(mini):
    assert q(mini, 'SELECT seq, duration_ms, key, status FROM agg_slow') == [(1, 3243.0, 'PATCH /regenerate-document', 200)]
    flow = {r[:3]: r[3] for r in q(mini, 'SELECT ip, upstream, pod, n FROM agg_flow')}
    assert len(flow) == 7 and flow['66.66.66.81', 'event-api-3000', '10.42.191.163:3000'] == 1 and flow['66.66.66.107', '-', '-'] == 1  # last pod = the one that answered
    assert {r[:2]: r[2:] for r in q(mini, 'SELECT upstream, addr, attempts, n5xx FROM agg_pod')} == {
        ('event-api-3000', '10.42.191.169:3000'): (1, 1), ('event-api-3000', '10.42.191.163:3000'): (1, 0),
        ('web-frontend-3000', '10.42.245.161:3000'): (1, 0), ('web-frontend-3000', '10.42.233.139:3000'): (1, 0),
        ('auth-service-3000', '10.42.233.151:3000'): (1, 0), ('cattle-system-rancher-80', '10.42.191.133:80'): (2, 0)}
    assert q(mini, 'SELECT upstream, addr_first, status_first, n FROM agg_retry') == [('event-api-3000', '10.42.191.169:3000', '502', 1)]
    assert q(mini, 'SELECT count(*) FROM v_upstream_error WHERE folder = ?', B) == [(2,)] and q(mini, 'SELECT count(*) FROM v_upstream_error WHERE folder = ?', A) == [(0,)]
    assert q(mini, 'SELECT service, pod, restart_app, restart_seconds FROM v_restart ORDER BY 1') == [(AM, 'pod-a', 'AuthApplication', 17.163), ('unknown-service', 'pod-u', 'AuthApplication', 17.163)]


def test_c401_and_uptime_kuma(mini, tmp_path):
    r = q(mini, 'SELECT ip, key, n, peak_per_min, first_wib, last_wib FROM agg_c401')
    assert [(x[0], x[1], x[2], x[3], M(x[4]), M(x[5])) for x in r] == [('66.66.66.221', 'GET /v1/user/select', 1, 1, '2026-09-28 00:10', '2026-09-28 00:10')]
    assert [(H(x[0]), x[1], x[2]) for x in q(mini, 'SELECT hour_wib, n, fail FROM agg_uk_hour')] == [('2026-09-28 00', 1, 0)]
    assert q(mini, 'SELECT target, n FROM agg_uk_target') == [('GET / → web-frontend-3000', 1)]
    # per-minute peak: 3 times in the same minute + 1 in another minute; failed Uptime-Kuma check (503)
    root = str(tmp_path / 'p'); l401 = logs_mini.lines(NG).splitlines()[4]; uk = logs_mini.lines(NG).splitlines()[1]
    logs_mini.write(logs_mini.log_path(root, B, 'ingress-nginx', NG, 'pod-n'), '\n'.join(
        [l401, l401.replace('17:10:16', '17:10:59'), l401.replace('17:10:16', '17:10:00'), l401.replace('17:10:16', '18:30:00'), uk.replace('" 200 6599', '" 503 6599')]) + '\n')
    _, con = make(tmp_path / 'y', root, workers=0)
    x = q(con, 'SELECT n, peak_per_min, first_wib, last_wib FROM agg_c401')[0]
    assert (x[0], x[1], M(x[2]), M(x[3])) == (4, 3, '2026-09-28 00:10', '2026-09-28 01:30')
    assert q(con, 'SELECT n, fail FROM agg_uk_hour') == [(1, 1)]
    con.close()


def test_derive_again_is_the_same_and_folder_state(mini):
    before = ingest.checksums(mini)
    assert ingest.derive_all(mini) == [A, B] and ingest.checksums(mini) == before
    assert ingest.derive_all(mini, B) == [B] and ingest.checksums(mini) == before
    assert q(mini, 'SELECT folder::VARCHAR, lines, files, files_empty, files_corrupt FROM folder_state ORDER BY 1') == [(A, 15, 2, 0, 0), (B, 38, 7, 1, 1)]


def test_deleting_a_file_rederives_the_aggregates(tmp_path):
    root = logs_mini.build(tmp_path / 'logs'); cfg, con = make(tmp_path, root, workers=0)
    os.remove(logs_mini.log_path(root, B, 'ingress-nginx', NG, 'pod-n')); ingest.run(cfg, con, workers=0)
    for t in ('agg_flow', 'agg_pod', 'agg_retry', 'agg_c401', 'agg_uk_hour', 'agg_upstream', 'agg_ua'):
        assert q(con, f'SELECT count(*) FROM {t}') == [(0,)], t
    assert q(con, 'SELECT count(*) FROM agg_service WHERE service = ?', NG) == [(0,)] and q(con, 'SELECT count(*) FROM agg_service WHERE folder = ?', B)[0][0] == 6
    assert ingest.forget(con, A) == 2 and q(con, 'SELECT count(*) FROM agg_service WHERE folder = ?', A) == [(0,)] and q(con, 'SELECT count(*) FROM agg_hour WHERE folder = ?', A) == [(0,)]
    con.close()


# ------------------------------------------------------------------ (b) real folders vs the old parser's raw statistics


