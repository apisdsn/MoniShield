"""Collector registry (docs/12-collector.md, step 2): domain rules, enrollment, keys, rotation, revoke, API roles and audit."""
import datetime

import pytest
from fastapi.testclient import TestClient

from monishield.domain import collectors as dom
from monishield.domain.errors import Fail
from monishield.infrastructure import auth as authmod
from test_api import X, as_user, admin, cfg, client, error_code, make_user   # noqa: F401  (fixtures and helpers of the API tests)

ENROLL_H = {'X-Requested-With': 'monishield-collector'}
SECRET = 'A' * 43


# Domain
def test_names():
    for ok in ('a', 'web-01', '0x', 'a' * 63): assert dom.check_name(ok) == ok
    for bad in ('', 'Web', '-a', 'a_b', 'a b', 'a' * 64, None, 5, 'é'):
        with pytest.raises(Fail) as e: dom.check_name(bad)
        assert e.value.code == 'invalid_name'


def test_platforms():
    for p in ('linux', 'windows', 'kubernetes', 'docker'): assert dom.check_platform(p) == p
    for bad in ('', 'Linux', 'mac', None):
        with pytest.raises(Fail) as e: dom.check_platform(bad)
        assert e.value.code == 'invalid_platform'


def test_secret_parse():
    text, secret = dom.new_secret('enroll', 7)
    assert text == f'mse_7_{secret}' and len(secret) == 43 and dom.parse_secret(text, 'enroll') == (7, secret)
    key, secret = dom.new_secret('key', 12)
    assert key.startswith('msk_12_') and dom.parse_secret(key, 'key') == (12, secret)
    assert dom.parse_secret(key, 'enroll') is None                                   # wrong prefix for the kind
    for bad in (f'mse_x_{SECRET}', f'mse_-1_{SECRET}', f'mse_0_{SECRET}', f'mse__{SECRET}', f'mse_1_{SECRET[:-1]}', f'mse_1_{SECRET}A',
                f'mse_1_{"A" * 42}!', f'mse_1_{"A" * 42} ', f'mse_1_{"A" * 42}é', f'xxx_1_{SECRET}', f'mse_1{SECRET}', '', None, 5, 'mse_' + '1' * 80 + '_' + SECRET):
        assert dom.parse_secret(bad, 'enroll') is None, bad


def test_secret_hash_is_sha256_hex():
    h = dom.secret_hash(SECRET)
    assert len(h) == 64 and h == dom.secret_hash(SECRET) and h != dom.secret_hash('B' * 43)


def test_status_boundaries():
    t, m = datetime.datetime(2026, 1, 1, 12, 0), datetime.timedelta(minutes=1)
    assert dom.status(t, t, t, t) == 'revoked'
    assert dom.status(t, None, None, None) == 'waiting'
    assert dom.status(t, t - 10 * m, t - 5 * m, None) == 'online'
    assert dom.status(t, t - 10 * m, t - 5 * m - datetime.timedelta(seconds=1), None) == 'late'
    assert dom.status(t, t - 90 * m, t - 60 * m, None) == 'late'
    assert dom.status(t, t - 90 * m, t - 60 * m - datetime.timedelta(seconds=1), None) == 'offline'
    assert dom.status(t, t - 2 * m, None, None) == 'online'                          # enrolled, not heard from yet: counts from enrollment


# Store and API
def add(tc, name='web-01', platform='linux'):
    r = tc.post('/api/admin/collectors', json=dict(name=name, platform=platform), headers=X)
    assert r.status_code == 201, r.text
    return r.json()


def enroll(tc, token, **kw):
    return tc.post('/api/collector/enroll', json=dict(token=token), headers={**ENROLL_H, **kw.get('headers', {})})


def shift(monkeypatch, **delta):
    real = authmod.now
    monkeypatch.setattr(authmod, 'now', lambda: real() + datetime.timedelta(**delta))


def audit_rows(tc): return tc.get('/api/admin/audit?limit=500').json()['rows']


def test_create_enroll_once(client):
    admin(client)
    r = client.post('/api/admin/collectors', json=dict(name='web-01', platform='linux'), headers=X)
    body = r.json()
    assert r.headers['cache-control'] == 'no-store' and body['collector']['status'] == 'waiting' and body['enroll_token'].startswith('mse_')
    assert body['expires'] == body['collector']['enroll_expires'] and not any('hash' in k for k in body['collector'])
    anon = TestClient(client.app)
    e = enroll(anon, body['enroll_token'], headers={'User-Agent': 'otelcol-contrib/0.1 ' + 'x' * 100})
    assert e.status_code == 200 and e.headers['cache-control'] == 'no-store'
    got = e.json()
    assert got['key'].startswith('msk_') and got['collector'] == dict(id=body['collector']['id'], name='web-01', platform='linux')
    second = enroll(anon, body['enroll_token'])
    assert (second.status_code, error_code(second)) == (401, 'invalid_enrollment_token')
    assert second.json()['error']['message'] == 'Enrollment token is not valid.'
    row = client.get('/api/admin/collectors').json()['rows'][0]
    assert row['status'] == 'online' and row['enroll_expires'] is None and row['enrolled_at'] and len(row['version']) == 80
    assert client.app.state.auth.collector_check(got['key'])['name'] == 'web-01'


def test_create_validation_and_unique_name(client):
    admin(client)
    add(client)
    r = client.post('/api/admin/collectors', json=dict(name='web-01', platform='docker'), headers=X)
    assert (r.status_code, error_code(r)) == (409, 'name_taken')
    assert error_code(client.post('/api/admin/collectors', json=dict(name='Bad Name', platform='linux'), headers=X)) == 'invalid_name'
    assert error_code(client.post('/api/admin/collectors', json=dict(name='ok', platform='mac'), headers=X)) == 'invalid_platform'


def test_expired_token_fails(client, monkeypatch):
    admin(client)
    token = add(client)['enroll_token']
    shift(monkeypatch, hours=dom.ENROLL_HOURS, seconds=1)
    r = enroll(TestClient(client.app), token)
    assert (r.status_code, error_code(r)) == (401, 'invalid_enrollment_token')


def test_new_token_replaces_old_and_only_before_enrolling(client):
    admin(client)
    c = add(client)
    cid, old = c['collector']['id'], c['enroll_token']
    r = client.post(f'/api/admin/collectors/{cid}/token', headers=X)
    assert r.status_code == 200 and r.headers['cache-control'] == 'no-store' and set(r.json()) == {'enroll_token', 'expires'}
    anon = TestClient(client.app)
    assert enroll(anon, old).status_code == 401                                      # the first token no longer works
    assert enroll(anon, r.json()['enroll_token']).status_code == 200
    r = client.post(f'/api/admin/collectors/{cid}/token', headers=X)
    assert (r.status_code, error_code(r)) == (409, 'collector_enrolled')
    assert client.post('/api/admin/collectors/999/token', headers=X).status_code == 404


def test_wrong_tokens_share_one_error_and_count_toward_the_ip_limit(client):
    admin(client)
    good = add(client)['enroll_token']
    anon = TestClient(client.app)
    _, secret = dom.new_secret('enroll', 1)
    answers = {enroll(anon, t).text for t in ('garbage', f'mse_1_{secret}', f'mse_999_{secret}', '')}
    assert len(answers) == 1 and 'Enrollment token is not valid.' in answers.pop()
    for _ in range(authmod.IP_MAX_FAILED - 4): assert enroll(anon, 'garbage').status_code == 401
    r = enroll(anon, good)                                                           # the valid token is refused for this IP now
    assert (r.status_code, error_code(r)) == (429, 'too_many_attempts')
    assert client.get('/api/admin/collectors').json()['rows'][0]['status'] == 'waiting'


def test_throttle_is_shared_with_login(client):
    admin(client)
    good = add(client)['enroll_token']
    anon = TestClient(client.app)
    for _ in range(authmod.IP_MAX_FAILED):
        anon.post('/api/auth/login', json=dict(username='nobody', password='wrong-password'), headers=X)
    assert error_code(enroll(anon, good)) == 'too_many_attempts'


def test_check_rotate_and_grace(client, monkeypatch):
    admin(client)
    c = add(client)
    cid = c['collector']['id']
    key1 = enroll(TestClient(client.app), c['enroll_token']).json()['key']
    store = client.app.state.auth
    assert store.collector_check(key1)['id'] == cid
    assert store.collector_check(key1[:-1] + ('A' if key1[-1] != 'A' else 'B')) is None and store.collector_check('junk') is None
    r = client.post(f'/api/admin/collectors/{cid}/rotate', headers=X)
    assert r.status_code == 200 and r.headers['cache-control'] == 'no-store'
    key2, until = r.json()['key'], r.json()['previous_valid_until']
    assert key2 != key1 and until
    assert store.collector_check(key2) and store.collector_check(key1)               # the old key works during the grace period
    shift(monkeypatch, hours=dom.ROTATE_GRACE_HOURS, seconds=1)
    assert store.collector_check(key2) and store.collector_check(key1) is None
    assert store.collector_get(cid)['previous_valid_until'] is None                  # (the admin session is over too after 24 h)


def test_rotate_needs_an_enrolled_collector(client):
    admin(client)
    cid = add(client)['collector']['id']
    assert error_code(client.post(f'/api/admin/collectors/{cid}/rotate', headers=X)) == 'collector_not_enrolled'
    client.post(f'/api/admin/collectors/{cid}/revoke', headers=X)
    assert error_code(client.post(f'/api/admin/collectors/{cid}/rotate', headers=X)) == 'collector_revoked'
    assert error_code(client.post(f'/api/admin/collectors/{cid}/token', headers=X)) == 'collector_revoked'
    assert error_code(client.post(f'/api/admin/collectors/{cid}/revoke', headers=X)) == 'collector_revoked'


def test_revoke_refuses_both_keys_and_the_token(client):
    admin(client)
    c = add(client)
    cid = c['collector']['id']
    key1 = enroll(TestClient(client.app), c['enroll_token']).json()['key']
    key2 = client.post(f'/api/admin/collectors/{cid}/rotate', headers=X).json()['key']
    r = client.post(f'/api/admin/collectors/{cid}/revoke', headers=X)
    assert r.status_code == 200 and r.json()['collector']['status'] == 'revoked' and r.json()['collector']['revoked_by'] == 'admin'
    store = client.app.state.auth
    assert store.collector_check(key1) is None and store.collector_check(key2) is None
    other = add(client, 'web-02')
    client.post(f"/api/admin/collectors/{other['collector']['id']}/revoke", headers=X)
    assert enroll(TestClient(client.app), other['enroll_token']).status_code == 401  # a revoked collector cannot enroll


def test_delete_only_after_revoke_or_before_enrolling(client):
    admin(client)
    c = add(client)
    cid = c['collector']['id']
    enroll(TestClient(client.app), c['enroll_token'])
    r = client.delete(f'/api/admin/collectors/{cid}', headers=X)
    assert (r.status_code, error_code(r)) == (409, 'collector_active')
    client.post(f'/api/admin/collectors/{cid}/revoke', headers=X)
    assert client.delete(f'/api/admin/collectors/{cid}', headers=X).json() == {'ok': True}
    assert client.get('/api/admin/collectors').json()['rows'] == []
    assert client.delete(f'/api/admin/collectors/{cid}', headers=X).status_code == 404
    never = add(client, 'never')                                                     # never enrolled: may be deleted right away
    assert client.delete(f"/api/admin/collectors/{never['collector']['id']}", headers=X).status_code == 200


def test_roles_and_csrf(client):
    admin(client); make_user(client)
    user = as_user(client, 'rina', 'rina-initial-password-123')
    anon = TestClient(client.app)
    for method, path in (('get', '/api/admin/collectors'), ('post', '/api/admin/collectors'), ('post', '/api/admin/collectors/1/token'),
                         ('post', '/api/admin/collectors/1/rotate'), ('post', '/api/admin/collectors/1/revoke'), ('delete', '/api/admin/collectors/1')):
        for tc, status, code in ((user, 403, 'forbidden'), (anon, 401, 'unauthenticated')):
            r = getattr(tc, method)(path, headers=X, **({} if method in ('get', 'delete') else dict(json={})))
            assert (r.status_code, error_code(r)) == (status, code), (method, path)
    token = add(client)['enroll_token']
    r = anon.post('/api/collector/enroll', json=dict(token=token))                   # no X-Requested-With
    assert (r.status_code, error_code(r)) == (403, 'csrf')
    assert enroll(anon, token).status_code == 200                                    # the refused call did not use the token


def test_audit_has_the_actions_and_never_a_secret(client):
    admin(client)
    secrets_seen = []
    c = add(client)
    cid = c['collector']['id']
    secrets_seen.append(c['enroll_token'])
    t2 = client.post(f'/api/admin/collectors/{cid}/token', headers=X).json()['enroll_token']
    secrets_seen.append(t2)
    e = enroll(TestClient(client.app), t2, headers={'User-Agent': 'otelcol/1.0'}).json()
    secrets_seen.append(e['key'])
    secrets_seen.append(client.post(f'/api/admin/collectors/{cid}/rotate', headers=X).json()['key'])
    enroll(TestClient(client.app), c['enroll_token'])                                # a failed attempt with a real-looking token
    client.post(f'/api/admin/collectors/{cid}/revoke', headers=X)
    client.delete(f'/api/admin/collectors/{cid}', headers=X)
    rows = audit_rows(client)
    actions = {r['action'] for r in rows}
    assert {'collector.add', 'collector.token', 'collector.enroll', 'collector.enroll_fail', 'collector.rotate', 'collector.revoke', 'collector.delete'} <= actions
    dump = repr(rows)
    for text in secrets_seen:
        assert text not in dump and text.split('_', 2)[2] not in dump
    enrolled = next(r for r in rows if r['action'] == 'collector.enroll')
    assert enrolled['detail'] == 'web-01 otelcol/1.0'


def test_seen_is_written_at_most_once_a_minute(client, monkeypatch):
    admin(client)
    c = add(client)
    cid = c['collector']['id']
    key = enroll(TestClient(client.app), c['enroll_token']).json()['key']
    svc, store = client.app.state.collectors, client.app.state.auth
    base = authmod.now()
    clock = {'t': base}
    monkeypatch.setattr(authmod, 'now', lambda: clock['t'])
    clock['t'] = base + datetime.timedelta(seconds=100)
    assert svc.authenticate(key, '10.0.0.1', 'otelcol/2')['id'] == cid
    first = store.collector_get(cid)
    assert first['last_ip'] == '10.0.0.1' and first['version'] == 'otelcol/2'
    clock['t'] = base + datetime.timedelta(seconds=130)
    svc.authenticate(key, '10.0.0.2', 'otelcol/3')
    assert store.collector_get(cid)['last_ip'] == '10.0.0.1'                         # 30 s later: not written
    clock['t'] = base + datetime.timedelta(seconds=161)
    svc.authenticate(key, '10.0.0.2', 'otelcol/3')
    assert store.collector_get(cid)['last_ip'] == '10.0.0.2'                         # 61 s after the last write
    assert svc.authenticate('msk_1_' + SECRET, '10.0.0.3', None) is None             # a bad key records nothing
    assert store.collector_get(cid)['last_ip'] == '10.0.0.2'
