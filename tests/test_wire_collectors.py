"""The collector admin endpoints and the Servers endpoints under the web UI's encrypted bodies (web/src/api.js, interfaces/api/wire.py):
every answer has X-MS-Enc: 1, is application/octet-stream and decrypts to the expected JSON, and encrypted request bodies are accepted.
The machine endpoints (receiver, enroll, config, install scripts) are not part of this: otelcol-contrib and curl call them with the
collector key, over HTTPS on the ingest subdomain (docs/12-collector.md, docs/13-metrics.md)."""
import datetime

from fastapi.testclient import TestClient

from test_wire import PW, PW2, Browser, base, tc   # noqa: F401  (the browser stand-in and its fixtures)

NOW = datetime.datetime.now(datetime.timezone.utc)


def signed_in(tc):
    b = Browser(tc)
    assert b.call('POST', '/api/auth/login', dict(username='admin', password=PW)).status_code == 200
    assert b.call('POST', '/api/me/password', dict(old_password=PW, new_password=PW2)).status_code == 200
    return b


def ok(b, method, path, body=None, status=200):
    """Call it encrypted, check the answer is sealed, and return the decrypted JSON."""
    r = b.call(method, path, body)
    assert r.status_code == status, (method, path, r.status_code, r.content[:200])
    assert r.headers['x-ms-enc'] == '1' and r.headers['content-type'] == 'application/octet-stream', (method, path)
    for text in (b'web-01', b'Client A', b'enroll_token', b'"rows"', b'"hosts"'): assert text not in r.content, (path, text)    # ciphertext, not JSON
    return b.json(r, method, path)


def test_the_collector_admin_calls_are_encrypted_both_ways(tc):
    b = signed_in(tc)
    made = ok(b, 'POST', '/api/admin/collectors', dict(name='web-01', platform='linux', group='Client A', options=dict(files=[], journald=True, units=[], host_metrics=True)), 201)
    cid = made['collector']['id']
    assert made['collector']['group'] == 'Client A' and made['collector']['options']['host_metrics'] is True and made['enroll_token'].startswith('mse_')
    listed = ok(b, 'GET', '/api/admin/collectors')
    assert [(r['name'], r['group']) for r in listed['rows']] == [('web-01', 'Client A')] and listed['groups'] == ['Client A']
    # a waiting collector can get a new enrollment token
    assert ok(b, 'POST', f'/api/admin/collectors/{cid}/token')['enroll_token'].startswith('mse_')
    # the collector itself (a machine call, plain) enrolls with the token; then the key can be replaced
    token = ok(b, 'POST', f'/api/admin/collectors/{cid}/token')['enroll_token']
    enrolled = TestClient(tc.app).post('/api/collector/enroll', json=dict(token=token), headers={'X-Requested-With': 'monishield-collector'})
    assert enrolled.status_code == 200 and enrolled.headers['content-type'].startswith('application/json') and 'x-ms-enc' not in enrolled.headers
    assert ok(b, 'POST', f'/api/admin/collectors/{cid}/rotate')['key'].startswith('msk_')
    changed = ok(b, 'PUT', f'/api/admin/collectors/{cid}/options', dict(options=dict(files=[], journald=True, units=[], host_metrics=False), group='Client B'))
    assert changed['collector']['group'] == 'Client B' and changed['collector']['options']['host_metrics'] is False
    assert ok(b, 'PUT', f'/api/admin/collectors/{cid}/options', dict(group=''))['collector']['group'] == ''
    assert ok(b, 'POST', f'/api/admin/collectors/{cid}/revoke')['collector']['status'] == 'revoked'
    assert ok(b, 'DELETE', f'/api/admin/collectors/{cid}') == dict(ok=True)
    assert ok(b, 'GET', '/api/admin/collectors')['rows'] == []


def test_errors_of_the_collector_calls_are_encrypted_too(tc):
    b = signed_in(tc)
    r = b.call('POST', '/api/admin/collectors', dict(name='web-02', platform='linux', group='-bad'))
    assert r.status_code == 400 and b.json(r, 'POST', '/api/admin/collectors')['error']['code'] == 'invalid_group'


def test_the_servers_endpoints_are_encrypted(tc):
    b = signed_in(tc)
    made = ok(b, 'POST', '/api/admin/collectors', dict(name='web-01', platform='linux', group='Client A'), 201)
    cid = made['collector']['id']
    TestClient(tc.app).post('/api/collector/enroll', json=dict(token=made['enroll_token']), headers={'X-Requested-With': 'monishield-collector'})
    pts = [('web-01', '', n, '', NOW - datetime.timedelta(minutes=m), v) for m in (3, 2, 1) for n, v in (('cpu', 12.0), ('mem_used', 2.0e9), ('mem_total', 8.0e9))]
    tc.app.state.metrics.add(cid, pts, {('web-01', ''): dict(os='Ubuntu 24.04', image=None)}, NOW)
    over = ok(b, 'GET', '/api/servers?range=24h')
    assert [(h['host'], h['group'], h['cpu']) for h in over['hosts']] == [('web-01', 'Client A', 12.0)]
    one = ok(b, 'GET', f'/api/servers/host?cid={cid}&host=web-01&range=1h')
    assert one['host'] == 'web-01' and one['group'] == 'Client A' and len(one['series']['cpu']) == 3
    r = b.call('GET', '/api/servers/host?cid=9999&host=web-01')
    assert r.status_code == 404 and b.json(r, 'GET', '/api/servers/host?cid=9999&host=web-01')['error']['code'] == 'not_found'


def test_a_wrong_key_is_a_plain_error_and_the_page_agrees_on_a_new_one(tc):
    b = signed_in(tc)
    r = b.call('GET', '/api/servers', kid='ffffffffffffffff')
    assert r.status_code == 400 and r.headers['content-type'].startswith('application/json') and r.json()['error']['code'] == 'enc_key_unknown'
