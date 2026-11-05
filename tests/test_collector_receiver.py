"""Collector receiver (docs/12-collector.md, step 3): POST /api/v1/collector/logs on the sample payloads in fixtures/otlp."""
import asyncio, collections, dataclasses, gzip, json, os, shutil, threading, time, zlib

import pytest
from fastapi.testclient import TestClient

from monishield.domain import accounts
from monishield.interfaces.api import app as appmod, collector_logs, wire
from monishield.interfaces.api.common import FailureLimiter, RateWindow
from test_api import X, admin, cfg, error_code   # noqa: F401  (fixtures and helpers of the API tests)
from test_collectors import add, enroll, shift

FIX = os.path.join(os.path.dirname(__file__), 'fixtures', 'otlp')
URL = '/api/v1/collector/logs'
JSON = {'Content-Type': 'application/json'}
K8S = {
    '2026-11-05/ingress-nginx/nginx-ingress-controller/log_nginx-ingress-controller_ingress-nginx-controller-7d9c5b6f4-x2k8p_2026-11-05-16-00.log':
        ['203.0.113.5 - - [04/Nov/2026:16:55:36 +0700] "GET /api/orders HTTP/1.1" 200 512 "-" "curl/8.5.0" 80 0.012'],
    '2026-11-05/shop/orders-api/log_orders-api_orders-api-5f7c8d9b6-abcde_2026-11-05-16-00.log': ['{"level":"info","msg":"order created"}']}
HOST = {
    '2026-11-05/web-01/payments/log_payments_web-01_2026-11-05-16-00.log': ['ts=2026-11-04T09:55:36Z level=info msg=charged'],
    '2026-11-05/web-01/app/log_app_web-01_2026-11-05-16-00.log': ['GET / 200', 'no file name'],
    '2026-11-05/web-01/access/log_access_web-01_2026-11-05-16-00.log': ['rotated line'],
    '2026-11-05/web-01/access-log/log_access-log_web-01_2026-11-05-16-00.log': ['plain bytes line']}


def sample(name):
    with open(os.path.join(FIX, name + '.json'), 'rb') as fh: return fh.read()


@pytest.fixture
def make(cfg, auth_url, tmp_path, monkeypatch):
    """make(**settings) -> (admin client, collector key, inbox folder). Small limits keep the limit tests fast."""
    monkeypatch.setattr(accounts, 'SCRYPT', (10, 8, 1))
    clients = []

    def build(**over):
        small = dict(collector_max_body_mb=1, collector_max_raw_mb=1, collector_rate_per_min=1000, collector_min_free_mb=0, collector_max_age_hours=0)
        c = dataclasses.replace(cfg, auth_database_url=auth_url, inbox_dir=str(tmp_path / 'inbox'), **{**small, **over})
        tc = TestClient(appmod.create_app(c)); tc.__enter__(); clients.append(tc)
        admin(tc)
        body = add(tc)
        key = enroll(TestClient(tc.app), body['enroll_token']).json()['key']
        return tc, key, os.path.join(str(tmp_path / 'inbox'), 'collector')

    yield build
    for tc in clients: tc.__exit__(None, None, None)


def post(tc, key, data, headers=None, **kw):
    h = {**JSON, **({'Authorization': f'Bearer {key}'} if key else {}), **(headers or {})}
    return TestClient(tc.app).post(URL, content=data, headers=h, **kw)   # a client without the admin's session cookie


def files(root):
    out = {}
    for d, _, names in os.walk(root):
        for n in names:
            with open(os.path.join(d, n), encoding='utf-8', newline='') as fh: out[os.path.relpath(os.path.join(d, n), root).replace(os.sep, '/')] = fh.read()
    return out


def lines_of(root): return {k: v.rstrip('\n').split('\n') for k, v in files(root).items()}


def otlp(lines, host='web-01', svc='big'):
    recs = [{'timeUnixNano': '1793786136000000000', 'body': {'stringValue': line}} for line in lines]
    res = {'attributes': [{'key': 'host.name', 'value': {'stringValue': host}}, {'key': 'service.name', 'value': {'stringValue': svc}}]}
    return json.dumps({'resourceLogs': [{'resource': res, 'scopeLogs': [{'logRecords': recs}]}]}).encode()


# Accepted batches
@pytest.mark.parametrize('zipped', [False, True])
def test_batches_are_written_to_the_expected_files(make, zipped):
    tc, key, root = make()
    for name, expected in (('k8s', K8S), ('host_file', HOST)):
        data = sample(name)
        r = post(tc, key, gzip.compress(data) if zipped else data, {'Content-Encoding': 'gzip'} if zipped else None)
        assert (r.status_code, r.json()) == (200, {}), r.text
    assert lines_of(root) == {**K8S, **HOST}
    assert all(t.endswith('\n') and not t.endswith('\n\n') for t in files(root).values())


def test_rejected_records_are_reported_but_the_rest_is_kept(make):
    tc, key, root = make()
    r = post(tc, key, sample('bad'))
    ps = r.json()['partialSuccess']
    assert r.status_code == 200 and ps['rejectedLogRecords'] == '8' and 'empty line (1)' in ps['errorMessage']
    assert sorted(v for lines in lines_of(root).values() for v in lines) == ['from the future', 'good line']
    s = tc.app.state.collector_feed.status()
    only = next(iter(s['collectors'].values()))
    assert (only['received'], only['written'], only['rejected']['empty line']) == (10, 2, 1) and only['last_reject']['text'].startswith('8 log records rejected')
    assert only['last_batch_at'] and '2026-11-05' in s['pending']      # the future-dated record is kept at the receive time, so its folder depends on the clock


def at(hours_ago, line, svc='old'):
    nano = int((time.time() - hours_ago * 3600) * 1e9)
    res = {'attributes': [{'key': 'host.name', 'value': {'stringValue': 'web-01'}}, {'key': 'service.name', 'value': {'stringValue': svc}}]}
    rec = {'timeUnixNano': str(nano), 'body': {'stringValue': line}}
    return {'resource': res, 'scopeLogs': [{'logRecords': [rec]}]}


def test_records_older_than_the_limit_are_rejected_once_and_not_stored(make):
    tc, key, root = make(collector_max_age_hours=24)
    body = json.dumps({'resourceLogs': [at(48, 'history'), at(25, 'older'), at(23, 'recent'), at(0.1, 'new')]}).encode()
    r = post(tc, key, body)
    ps = r.json()['partialSuccess']                                       # 200: the collector must not retry what is too old
    assert r.status_code == 200 and ps['rejectedLogRecords'] == '2' and 'too old (2)' in ps['errorMessage']
    assert sorted(v for lines in lines_of(root).values() for v in lines) == ['new', 'recent']
    only = next(iter(tc.app.state.collector_feed.status()['collectors'].values()))
    assert (only['received'], only['written'], only['rejected']) == (4, 2, {'too old': 2})


def test_no_limit_keeps_every_record(make):
    tc, key, root = make(collector_max_age_hours=0)
    r = post(tc, key, json.dumps({'resourceLogs': [at(24 * 400, 'ancient'), at(1, 'new')]}).encode())
    assert (r.status_code, r.json()) == (200, {})
    assert sorted(v for lines in lines_of(root).values() for v in lines) == ['ancient', 'new']


def test_multi_line_entries_are_written_as_they_are(make):
    tc, key, root = make()
    assert post(tc, key, otlp(['Traceback (most recent call last):\n  File "x.py", line 1\nValueError: no'], svc='py')).status_code == 200
    (text,) = files(root).values()
    assert text == 'Traceback (most recent call last):\n  File "x.py", line 1\nValueError: no\n'


def test_no_session_no_csrf_header_no_audit_and_last_seen(make, monkeypatch):
    tc, key, root = make()
    before = tc.get('/api/v1/admin/audit?limit=500').json()['rows']
    seen = tc.get('/api/v1/admin/collectors').json()['rows'][0]['last_seen']          # set by enrollment
    anon = TestClient(tc.app)
    assert not anon.cookies and 'X-Requested-With' not in JSON
    shift(monkeypatch, minutes=10)                                                    # last_seen is written once a minute at most
    for _ in range(3): assert anon.post(URL, content=sample('k8s'), headers={**JSON, 'Authorization': f'Bearer {key}'}).status_code == 200
    assert tc.get('/api/v1/admin/audit?limit=500').json()['rows'] == before
    assert tc.get('/api/v1/admin/collectors').json()['rows'][0]['last_seen'] > seen


def test_the_middleware_leaves_a_request_without_x_ms_enc_alone(make):
    tc, key, root = make()
    assert tc.app.state.cfg.api_encryption
    r = post(tc, key, gzip.compress(sample('k8s')), {'Content-Encoding': 'gzip'})
    assert (r.status_code, r.headers['content-type'], r.json()) == (200, 'application/json', {}) and 'x-ms-enc' not in r.headers

    seen = {}

    async def inner(scope, receive, send): seen.update(scope=scope, receive=receive, send=send)
    mw = wire.PayloadCrypto(inner, tc.app.state)
    scope = dict(type='http', method='POST', path=URL, headers=[(b'authorization', b'Bearer x'), (b'content-encoding', b'gzip')])
    receive, send = object(), object()
    asyncio.run(mw(scope, receive, send))
    assert seen['scope'] is scope and seen['receive'] is receive and seen['send'] is send   # not read, not wrapped


# Keys
def test_missing_wrong_and_revoked_keys_are_refused(make):
    tc, key, root = make()
    other = key[:-1] + ('A' if key[-1] != 'A' else 'B')
    for bad in (None, '', 'nonsense', other, 'mse_1_' + 'A' * 43):
        r = post(tc, bad, sample('k8s'))
        assert (r.status_code, error_code(r)) == (401, 'invalid_collector_key'), bad
        assert r.json()['error']['message'] == 'Collector key is not valid.'
    r = TestClient(tc.app).post(URL, content=sample('k8s'), headers={**JSON, 'Authorization': f'Basic {key}'})
    assert r.status_code == 401
    assert not os.path.exists(root)
    cid = tc.get('/api/v1/admin/collectors').json()['rows'][0]['id']
    assert post(tc, key, sample('k8s')).status_code == 200
    assert tc.post(f'/api/v1/admin/collectors/{cid}/revoke', headers=X).status_code == 200
    r = post(tc, key, sample('k8s'))
    assert (r.status_code, error_code(r)) == (401, 'invalid_collector_key')


def test_a_rotated_keys_previous_key_still_works(make):
    tc, key, root = make()
    cid = tc.get('/api/v1/admin/collectors').json()['rows'][0]['id']
    new = tc.post(f'/api/v1/admin/collectors/{cid}/rotate', headers=X).json()['key']
    assert new != key and post(tc, key, sample('k8s')).status_code == 200 and post(tc, new, sample('k8s')).status_code == 200


def test_too_many_wrong_keys_block_the_address_but_not_sign_in(make):
    tc, key, root = make()
    for _ in range(60): assert post(tc, 'msk_1_' + 'A' * 43, b'{}').status_code == 401
    r = post(tc, 'msk_1_' + 'A' * 43, b'{}')
    assert (r.status_code, error_code(r), r.headers['retry-after']) == (429, 'too_many_attempts', '300')
    r = post(tc, key, sample('k8s'))                                                  # blocked: even the right key waits
    assert (r.status_code, r.headers['retry-after'] != '') == (429, True)
    assert TestClient(tc.app).post('/api/v1/auth/login', json=dict(username='admin', password='admin-password-after-change'), headers=X).status_code == 200


def test_failure_limiter_window_and_block_end():
    now = [0.0]; lim = FailureLimiter(limit=3, window=60, block=300, clock=lambda: now[0])
    assert [lim.failed('a') for _ in range(3)] == [False] * 3
    now[0] = 61                                                                       # the old failures left the window
    assert [lim.failed('a') for _ in range(3)] == [False] * 3 and lim.failed('a') is True
    assert lim.retry_after('a') == 301 and lim.retry_after('b') == 0
    now[0] = 61 + 301
    assert lim.retry_after('a') == 0 and lim.failed('a') is False


# What is refused
def test_content_type_and_encoding(make):
    tc, key, root = make()
    r = post(tc, key, b'{}', {'Content-Type': 'application/x-protobuf'})
    assert (r.status_code, error_code(r), r.json()['error']['message']) == (415, 'unsupported_media_type', 'Send OTLP as JSON (exporter setting encoding: json).')
    for ctype in ('text/plain', 'application/xml'): assert post(tc, key, b'{}', {'Content-Type': ctype}).status_code == 415
    assert post(tc, key, sample('k8s'), {'Content-Type': 'application/json; charset=utf-8'}).status_code == 200
    for enc in ('br', 'deflate', 'zstd'):
        r = post(tc, key, b'{}', {'Content-Encoding': enc})
        assert (r.status_code, error_code(r)) == (415, 'unsupported_media_type'), enc
    assert post(tc, key, sample('k8s'), {'Content-Encoding': 'identity'}).status_code == 200


def test_body_over_the_limit_is_refused_by_length_and_while_streaming(make):
    tc, key, root = make()
    r = post(tc, key, b' ' * (1024 * 1024 + 1))
    assert (r.status_code, error_code(r)) == (413, 'body_too_large')
    assert post(tc, key, sample('k8s'), {'Content-Length': str(10 * 1024 * 1024)}).status_code in (413, 400)   # claimed size over the limit
    sent = []

    def chunks():                                                                     # no Content-Length: chunked transfer
        for _ in range(40): sent.append(1); yield b' ' * 65536
    r = TestClient(tc.app).post(URL, content=chunks(), headers={**JSON, 'Authorization': f'Bearer {key}'})
    assert (r.status_code, error_code(r)) == (413, 'body_too_large')
    assert not os.path.exists(root)


def test_a_gzip_bomb_is_stopped_while_unpacking(make, monkeypatch):
    tc, key, root = make()
    z, out = zlib.compressobj(9, zlib.DEFLATED, 31), []
    for _ in range(200): out.append(z.compress(bytes(1024 * 1024)))                   # 200 MB of zeros
    bomb = b''.join(out) + z.flush()
    assert len(bomb) < 1024 * 1024
    made = []
    real = zlib.decompressobj

    class Spy:
        def __init__(self, *a): self.d = real(*a)
        def __getattr__(self, name): return getattr(self.d, name)
        def decompress(self, data, n=0):
            piece = self.d.decompress(data, n); made.append(len(piece)); return piece
    monkeypatch.setattr(collector_logs.zlib, 'decompressobj', Spy)
    r = post(tc, key, bomb, {'Content-Encoding': 'gzip'})
    assert (r.status_code, error_code(r)) == (413, 'body_too_large')
    assert sum(made) <= 1024 * 1024 + collector_logs.PIECE                           # never the 200 MB
    r = post(tc, key, bytes(1024 * 1024 + 5), {'Content-Encoding': 'identity'})       # identity is bounded by the same raw limit
    assert r.status_code in (400, 413) and not os.path.exists(root)


def test_unreadable_bodies_are_400(make):
    tc, key, root = make()
    good = gzip.compress(sample('k8s'))
    cases = [(b'not gzip at all', {'Content-Encoding': 'gzip'}), (good[:-10], {'Content-Encoding': 'gzip'}), (good + b'tail', {'Content-Encoding': 'gzip'}),
             (b'', {'Content-Encoding': 'gzip'}), (b'{"resourceLogs": [', None), (b'', None), (b'[]', None), (b'"text"', None), (b'null', None),
             (b'\xff\xfe\x00', None), (b'{"a": ' * 100000, None)]
    for data, h in cases:
        r = post(tc, key, data, h)
        assert (r.status_code, error_code(r)) == (400, 'invalid_body'), data[:20]
    assert not os.path.exists(root)


# Protection of the server
def test_rate_limit_per_collector(make):
    tc, key, root = make(collector_rate_per_min=3)
    assert [post(tc, key, sample('k8s')).status_code for _ in range(3)] == [200] * 3
    r = post(tc, key, sample('k8s'))
    assert (r.status_code, error_code(r), r.headers['retry-after']) == (429, 'rate_limited', '30')
    second = tc.post('/api/v1/admin/collectors', json=dict(name='web-02', platform='linux'), headers=X).json()
    key2 = enroll(TestClient(tc.app), second['enroll_token']).json()['key']
    assert post(tc, key2, sample('k8s')).status_code == 200                           # each collector has its own allowance


def test_low_disk_answers_503_and_keeps_the_data_with_the_collector(make, monkeypatch):
    tc, key, root = make(collector_min_free_mb=1024)
    Usage = collections.namedtuple('Usage', 'total used free')
    monkeypatch.setattr(shutil, 'disk_usage', lambda p: Usage(10**12, 10**12 - 1023 * 1024 * 1024, 1023 * 1024 * 1024))
    r = post(tc, key, sample('k8s'))
    assert (r.status_code, error_code(r), r.headers['retry-after']) == (503, 'disk_full', '60') and not os.path.exists(root)
    monkeypatch.setattr(shutil, 'disk_usage', lambda p: Usage(10**12, 0, 1024 * 1024 * 1024))
    assert post(tc, key, sample('k8s')).status_code == 200


def test_a_write_error_is_a_retryable_503(make, monkeypatch):
    tc, key, root = make()
    def broken(records): raise OSError('disk gone')
    monkeypatch.setattr(tc.app.state.collector_inbox, 'append', broken)
    r = post(tc, key, sample('k8s'))
    assert (r.status_code, error_code(r), r.headers['retry-after']) == (503, 'storage_error', '60')


def test_parallel_requests_never_interleave_lines_of_one_file(make):
    tc, key, root = make(collector_max_concurrent=8)
    n, threads = 40, 8
    wanted = {f't{t}-{i}-' + 'x' * 3000 for t in range(threads) for i in range(n)}
    results = []

    def work(t):
        data = otlp([f't{t}-{i}-' + 'x' * 3000 for i in range(n)])
        results.append(post(tc, key, data).status_code)
    ts = [threading.Thread(target=work, args=(t,)) for t in range(threads)]
    for t in ts: t.start()
    for t in ts: t.join()
    assert results == [200] * threads
    (rel, lines), = lines_of(root).items()
    assert rel == '2026-11-05/web-01/big/log_big_web-01_2026-11-05-16-00.log'
    assert len(lines) == threads * n and set(lines) == wanted


# Adapter
def test_inbox_refuses_paths_outside_its_root(tmp_path):
    from monishield.infrastructure.collector_inbox import CollectorInbox, UnsafePath
    inbox = CollectorInbox(str(tmp_path / 'in'))
    for rel in ('../escape.log', 'a/../../escape.log', str(tmp_path / 'abs.log'), '.', ''):
        with pytest.raises(UnsafePath): inbox.append([dict(relpath=rel, line='x')])
    (tmp_path / 'in').mkdir(exist_ok=True); (tmp_path / 'out').mkdir()
    os.symlink(tmp_path / 'out', tmp_path / 'in' / 'link')
    with pytest.raises(UnsafePath): inbox.append([dict(relpath='link/x.log', line='x')])
    assert os.listdir(tmp_path / 'out') == [] and not (tmp_path / 'escape.log').exists()
    assert inbox.append([dict(relpath='d/n/s/f.log', line='a'), dict(relpath='d/n/s/f.log', line='b')]) == {'d': 2}
    assert (tmp_path / 'in' / 'd' / 'n' / 's' / 'f.log').read_text() == 'a\nb\n'
    assert inbox.free_bytes() > 0


# Memory: requests at a time
def test_busy_server_answers_503_and_slots_are_always_released(make, monkeypatch):
    tc, key, root = make(collector_max_concurrent=1)
    feed = tc.app.state.collector_feed
    real, inside, gate = feed.receive, threading.Event(), threading.Event()

    def slow(*a):
        inside.set(); gate.wait(10)
        return real(*a)
    monkeypatch.setattr(feed, 'receive', slow)
    first = []
    t = threading.Thread(target=lambda: first.append(post(tc, key, sample('k8s'))))
    t.start()
    assert inside.wait(10)
    r = post(tc, key, sample('k8s'))
    assert (r.status_code, error_code(r), r.headers['retry-after']) == (503, 'busy', '5')
    gate.set(); t.join()
    assert first[0].status_code == 200
    assert post(tc, key, sample('k8s')).status_code == 200                            # the slot came back
    for data, code in ((b'[]', 400), (b' ' * (1024 * 1024 + 1), 413)):               # failing requests release it too
        assert post(tc, key, data).status_code == code
        assert post(tc, key, sample('k8s')).status_code == 200
