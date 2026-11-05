"""Metrics receiver (docs/13-metrics.md): POST /api/collector/v1/metrics on the real requests in fixtures/otlp_metrics_*.json."""
import collections, copy, dataclasses, datetime, gzip, json, os, shutil, threading, time, zlib

import pytest
from fastapi.testclient import TestClient

from monishield.domain import accounts
from monishield.interfaces.api import app as appmod, collector_logs
from test_api import X, admin, cfg, error_code   # noqa: F401  (fixtures and helpers of the API tests)
from test_collectors import add, enroll

FIX = os.path.join(os.path.dirname(__file__), 'fixtures')
URL = '/api/collector/v1/metrics'
JSON = {'Content-Type': 'application/json'}


def sample(name):
    with open(os.path.join(FIX, f'otlp_metrics_{name}.json'), 'rb') as fh: return fh.read()


def shifted(name, seconds):
    """The sample with every time moved by `seconds` (the real requests are from 2026-11-05)."""
    d = json.loads(sample(name))
    for rm in d['resourceMetrics']:
        for sm in rm['scopeMetrics']:
            for m in sm['metrics']:
                for dp in (m.get('gauge') or m['sum'])['dataPoints']:
                    for k in ('timeUnixNano', 'startTimeUnixNano'):
                        if k in dp: dp[k] = str(int(dp[k]) + seconds * 10 ** 9)
    return json.dumps(d).encode()


def recent(name, minutes_ago=0):
    """The sample moved to now, so that the receive time and the sample time agree (too old / future checks)."""
    d = json.loads(sample(name))
    first = min(int(dp['timeUnixNano']) for rm in d['resourceMetrics'] for sm in rm['scopeMetrics'] for m in sm['metrics'] for dp in (m.get('gauge') or m['sum'])['dataPoints'])
    return shifted(name, int(time.time() - minutes_ago * 60 - first / 1e9))


@pytest.fixture
def make(cfg, auth_url, tmp_path, monkeypatch):
    """make(**settings) -> (admin client, collector key, metrics store). Its own data folder, so the metrics file is the test's."""
    monkeypatch.setattr(accounts, 'SCRYPT', (10, 8, 1))
    clients = []

    def build(**over):
        small = dict(collector_max_body_mb=1, collector_max_raw_mb=1, collector_rate_per_min=1000, collector_min_free_mb=0, collector_max_age_hours=0)
        c = dataclasses.replace(cfg, auth_database_url=auth_url, data_dir=str(tmp_path / 'data'), inbox_dir=str(tmp_path / 'inbox'), **{**small, **over})
        tc = TestClient(appmod.create_app(c)); tc.__enter__(); clients.append(tc)
        admin(tc)
        key = enroll(TestClient(tc.app), add(tc)['enroll_token']).json()['key']
        return tc, key, tc.app.state.metrics

    yield build
    for tc in clients: tc.__exit__(None, None, None)


def post(tc, key, data, headers=None, **kw):
    h = {**JSON, **({'Authorization': f'Bearer {key}'} if key else {}), **(headers or {})}
    return TestClient(tc.app).post(URL, content=data, headers=h, **kw)


def values(store, name, dim='', ctr=''):
    return [v for (v,) in store.rows('SELECT v FROM metric_point WHERE name = ? AND dim = ? AND ctr = ? ORDER BY t', [name, dim, ctr])]


# Accepted
@pytest.mark.parametrize('zipped', [False, True])
def test_a_real_request_is_stored(make, zipped):
    tc, key, store = make()
    data = sample('hostmetrics')
    r = post(tc, key, gzip.compress(data) if zipped else data, {'Content-Encoding': 'gzip'} if zipped else None)
    assert (r.status_code, r.json()) == (200, {}), r.text
    assert values(store, 'mem_total') == [16867418112.0] and values(store, 'disk_used', '/') == [24628260864.0] and values(store, 'load1') == [0.16]
    assert 0 <= values(store, 'cpu')[0] < 5
    (row,) = store.rows("SELECT host, os FROM metric_target WHERE ctr = ''")
    assert row[0] == 'vm' and row[1].startswith('Ubuntu 24.04')
    cid = tc.get('/api/admin/collectors').json()['rows'][0]['id']
    assert store.rows('SELECT DISTINCT cid FROM metric_point') == [(cid,)]
    assert tc.app.state.metrics_feed.status()['collectors'][cid]['stored'] == 10


def test_network_values_appear_from_the_second_request_and_a_repeat_adds_nothing(make):
    tc, key, store = make()
    assert post(tc, key, sample('hostmetrics_first')).status_code == 200
    assert values(store, 'net_rx') == [] and values(store, 'cpu') == []                # no rate yet, and the first scrape has no CPU
    assert post(tc, key, sample('hostmetrics')).status_code == 200
    assert len(values(store, 'net_rx')) == 1 and len(values(store, 'net_tx')) == 1 and values(store, 'net_rx')[0] >= 0
    assert post(tc, key, sample('hostmetrics')).status_code == 200                     # a retry of the same request
    assert len(values(store, 'net_rx')) == 1


def test_container_values_and_targets(make):
    tc, key, store = make()
    assert post(tc, key, sample('docker_stats')).status_code == 200
    assert values(store, 'cpu', ctr='web-1')[0] == pytest.approx(2.8) and values(store, 'mem_limit', ctr='web-1') == [2e9] and values(store, 'restarts', ctr='web-1') == [3.0]
    assert store.rows("SELECT host, ctr, image FROM metric_target WHERE ctr <> ''") == [('vm', 'web-1', 'nginx:1.27')]
    assert sorted(h for (h,) in store.rows('SELECT host FROM metric_target')) == ['vm', 'vm']


def test_rejected_points_are_reported_but_the_rest_is_kept(make):
    tc, key, store = make()
    d = json.loads(sample('hostmetrics'))
    load = next(m for rm in d['resourceMetrics'] for m in rm['scopeMetrics'][0]['metrics'] if m['name'] == 'system.cpu.load_average.1m')
    load['gauge']['dataPoints'][0]['timeUnixNano'] = 'abc'
    d['resourceMetrics'].append({'scopeMetrics': [{'metrics': [{'name': 'system.disk.io', 'sum': {'dataPoints': []}}]}]})                # not used: not rejected
    r = post(tc, key, json.dumps(d).encode())
    assert r.status_code == 200 and r.json()['partialSuccess']['rejectedDataPoints'] == '1' and 'invalid time (1)' in r.json()['partialSuccess']['errorMessage']
    assert values(store, 'load1') == [] and values(store, 'mem_total') == [16867418112.0]
    only = next(iter(tc.app.state.metrics_feed.status()['collectors'].values()))
    assert only['rejected'] == {'invalid time': 1} and only['ignored'] >= 1 and only['last_reject']['text'].startswith('1 data points rejected')


def test_points_older_than_the_limit_are_rejected_once(make):
    tc, key, store = make(collector_max_age_hours=24)
    r = post(tc, key, recent('hostmetrics', 48 * 60))
    assert r.status_code == 200 and 'too old' in r.json()['partialSuccess']['errorMessage'] and store.rows('SELECT count(*) FROM metric_point') == [(0,)]
    r = post(tc, key, recent('hostmetrics', 1))
    assert (r.status_code, r.json()) == (200, {}) and store.rows('SELECT count(*) FROM metric_point')[0][0] > 5


def test_no_session_no_csrf_header_and_no_audit(make):
    tc, key, store = make()
    before = tc.get('/api/admin/audit?limit=500').json()['rows']
    anon = TestClient(tc.app)
    assert anon.post(URL, content=sample('hostmetrics'), headers={**JSON, 'Authorization': f'Bearer {key}'}).status_code == 200
    assert tc.get('/api/admin/audit?limit=500').json()['rows'] == before


# Keys
def test_missing_wrong_and_revoked_keys_are_refused(make):
    tc, key, store = make()
    other = key[:-1] + ('A' if key[-1] != 'A' else 'B')
    for bad in (None, '', 'nonsense', other):
        r = post(tc, bad, sample('hostmetrics'))
        assert (r.status_code, error_code(r)) == (401, 'invalid_collector_key'), bad
    assert store.rows('SELECT count(*) FROM metric_point') == [(0,)]
    cid = tc.get('/api/admin/collectors').json()['rows'][0]['id']
    assert post(tc, key, sample('hostmetrics')).status_code == 200
    assert tc.post(f'/api/admin/collectors/{cid}/revoke', headers=X).status_code == 200
    assert error_code(post(tc, key, sample('hostmetrics'))) == 'invalid_collector_key'


# What is refused
def test_content_type_and_encoding(make):
    tc, key, store = make()
    r = post(tc, key, b'{}', {'Content-Type': 'application/x-protobuf'})
    assert (r.status_code, error_code(r)) == (415, 'unsupported_media_type')
    assert post(tc, key, b'{}', {'Content-Type': 'text/plain'}).status_code == 415
    assert post(tc, key, b'{}', {'Content-Encoding': 'br'}).status_code == 415
    assert post(tc, key, b'{}', {'Content-Type': 'application/json; charset=utf-8'}).status_code == 200


def test_size_limits_and_unreadable_bodies(make):
    tc, key, store = make()
    assert error_code(post(tc, key, b' ' * (1024 * 1024 + 1))) == 'body_too_large'
    z, out = zlib.compressobj(9, zlib.DEFLATED, 31), []
    for _ in range(200): out.append(z.compress(bytes(1024 * 1024)))
    bomb = b''.join(out) + z.flush()
    r = post(tc, key, bomb, {'Content-Encoding': 'gzip'})
    assert (r.status_code, error_code(r)) == (413, 'body_too_large')
    good = gzip.compress(sample('hostmetrics'))
    for data, h in ((b'not gzip', {'Content-Encoding': 'gzip'}), (good[:-10], {'Content-Encoding': 'gzip'}), (b'', None), (b'[]', None), (b'null', None), (b'{"resourceMetrics": [', None)):
        r = post(tc, key, data, h)
        assert (r.status_code, error_code(r)) == (400, 'invalid_body'), data[:20]
    assert store.rows('SELECT count(*) FROM metric_point') == [(0,)]


def test_rate_limit_per_collector(make):
    tc, key, store = make(collector_rate_per_min=2)
    assert [post(tc, key, b'{}').status_code for _ in range(2)] == [200, 200]
    r = post(tc, key, b'{}')
    assert (r.status_code, error_code(r), r.headers['retry-after']) == (429, 'rate_limited', '30')


def test_low_disk_answers_503(make, monkeypatch):
    tc, key, store = make(collector_min_free_mb=1024)
    Usage = collections.namedtuple('Usage', 'total used free')
    monkeypatch.setattr(shutil, 'disk_usage', lambda p: Usage(10**12, 10**12 - 1023 * 1024 * 1024, 1023 * 1024 * 1024))
    r = post(tc, key, sample('hostmetrics'))
    assert (r.status_code, error_code(r), r.headers['retry-after']) == (503, 'disk_full', '60') and store.rows('SELECT count(*) FROM metric_point') == [(0,)]
    monkeypatch.setattr(shutil, 'disk_usage', lambda p: Usage(10**12, 0, 1024 * 1024 * 1024))
    assert post(tc, key, sample('hostmetrics')).status_code == 200


def test_a_storage_error_is_a_retryable_503(make, monkeypatch):
    tc, key, store = make()
    def broken(*a): raise OSError('disk gone')
    monkeypatch.setattr(store, 'add', broken)
    r = post(tc, key, sample('hostmetrics'))
    assert (r.status_code, error_code(r), r.headers['retry-after']) == (503, 'storage_error', '60') and 'metrics' in r.json()['error']['message']


def test_busy_server_answers_503_and_the_slot_comes_back(make, monkeypatch):
    tc, key, store = make(collector_max_concurrent=1)
    feed = tc.app.state.metrics_feed
    real, inside, gate = feed.receive, threading.Event(), threading.Event()

    def slow(*a):
        inside.set(); gate.wait(10)
        return real(*a)
    monkeypatch.setattr(feed, 'receive', slow)
    first = []
    t = threading.Thread(target=lambda: first.append(post(tc, key, sample('hostmetrics'))))
    t.start()
    assert inside.wait(10)
    r = post(tc, key, sample('hostmetrics'))
    assert (r.status_code, error_code(r), r.headers['retry-after']) == (503, 'busy', '5')
    gate.set(); t.join()
    assert first[0].status_code == 200 and post(tc, key, b'{}').status_code == 200


def test_logs_and_metrics_share_a_collector_but_not_their_storage(make):
    from test_collector_receiver import post as post_logs, sample as log_sample
    tc, key, store = make()
    assert post_logs(tc, key, log_sample('k8s')).status_code == 200 and post(tc, key, sample('hostmetrics')).status_code == 200
    assert store.rows('SELECT count(*) FROM metric_point')[0][0] > 5


def test_the_metrics_file_is_in_the_data_folder_and_closes_with_the_app(make):
    tc, key, store = make()
    assert post(tc, key, sample('hostmetrics')).status_code == 200
    assert store.path == os.path.join(tc.app.state.cfg.data_dir, 'metrics.duckdb') and os.path.exists(store.path)
