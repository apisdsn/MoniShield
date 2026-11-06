"""Collector groups (docs/12-collector.md): the name rules, the column on an old database, the API (set, change, clear, list, case reuse) and the audit."""
import pytest
from sqlalchemy import create_engine, inspect, text

from monishield.domain import collectors as dom
from monishield.domain.errors import Fail
from monishield.infrastructure import auth as authmod
from test_api import X, admin, as_user, cfg, client, error_code, make_user   # noqa: F401  (fixtures and helpers of the API tests)
from test_collectors import audit_rows


def new(tc, name, group=None, platform='linux'):
    body = dict(name=name, platform=platform, **({} if group is None else dict(group=group)))
    return tc.post('/api/v1/admin/collectors', json=body, headers=X)


def rows(tc): return {r['name']: r for r in tc.get('/api/v1/admin/collectors').json()['rows']}


# Domain
def test_group_names():
    for ok in ('Client A', 'a', '0', 'Team_1.north-2', 'x' * 40): assert dom.check_group(ok) == ok
    assert dom.check_group('  Client A  ') == 'Client A' and dom.check_group('') == '' and dom.check_group('   ') == '' and dom.check_group(None) == ''
    for bad in ('-a', '.a', '_a', 'a' * 41, 'a/b', 'a;b', 'é', 'a\nb', 'a<b', 5, ['a']):
        with pytest.raises(Fail) as e: dom.check_group(bad)
        assert e.value.code == 'invalid_group', bad


def test_a_group_takes_the_spelling_of_an_existing_one():
    assert dom.same_group('client a', ['Internal', 'Client A']) == 'Client A'
    assert dom.same_group('Client B', ['Client A']) == 'Client B' and dom.same_group('', ['Client A']) == ''


# Old databases
def test_the_column_is_added_to_an_old_collector_table(tmp_path):
    url = f'sqlite:///{tmp_path}/old.db'
    first = authmod.Auth(url)
    first.collector_create('web-01', 'linux')
    first.engine.dispose()
    eng = create_engine(url)
    with eng.begin() as c: c.execute(text('ALTER TABLE collector DROP COLUMN group_name'))      # the table as it was before groups
    assert 'group_name' not in {x['name'] for x in inspect(eng).get_columns('collector')}
    eng.dispose()
    second = authmod.Auth(url)
    assert 'group_name' in {x['name'] for x in inspect(second.engine).get_columns('collector')}
    (old,) = second.collector_list()
    assert old['name'] == 'web-01' and old['group'] == ''                                       # no group
    second.collector_set_group(old['id'], 'Client A')
    assert second.collector_groups() == ['Client A']


# API
def test_add_with_a_group_list_and_get(client):
    admin(client)
    assert new(client, 'web-01', 'Client A').status_code == 201 and new(client, 'web-02').status_code == 201
    out = client.get('/api/v1/admin/collectors').json()
    assert out['groups'] == ['Client A'] and [(r['name'], r['group']) for r in out['rows']] == [('web-01', 'Client A'), ('web-02', '')]


def test_the_group_is_trimmed_and_reuses_the_spelling_in_any_case(client):
    admin(client)
    new(client, 'a-1', 'Client A'); new(client, 'a-2', '  client a ')
    new(client, 'b-1', 'Client B'); new(client, 'b-2', 'CLIENT B')
    r = rows(client)
    assert (r['a-2']['group'], r['b-2']['group']) == ('Client A', 'Client B')
    assert client.get('/api/v1/admin/collectors').json()['groups'] == ['Client A', 'Client B']


def test_a_bad_group_is_refused(client):
    admin(client)
    r = new(client, 'web-01', '-x')
    assert r.status_code == 400 and error_code(r) == 'invalid_group'
    assert client.get('/api/v1/admin/collectors').json()['rows'] == []                              # nothing was created
    cid = new(client, 'web-02').json()['collector']['id']
    assert error_code(client.put(f'/api/v1/admin/collectors/{cid}/options', json=dict(group='a;b'), headers=X)) == 'invalid_group'


def test_set_change_and_clear_the_group_and_the_audit_entry_only_on_a_change(client):
    admin(client)
    cid = new(client, 'web-01').json()['collector']['id']
    put = lambda **body: client.put(f'/api/v1/admin/collectors/{cid}/options', json=body, headers=X)   # noqa: E731
    assert put(group='Internal').json()['collector']['group'] == 'Internal'
    assert put(group='internal').json()['collector']['group'] == 'Internal'                      # same group, no change
    assert put(group='Client A').json()['collector']['group'] == 'Client A'
    assert client.get('/api/v1/admin/collectors').json()['groups'] == ['Client A']                  # the old group is gone with its last member
    assert put(group='').json()['collector']['group'] == '' and put(group=None).json()['collector']['group'] == ''
    changes = [r['detail'] for r in audit_rows(client) if r['action'] == 'collector.group']
    assert sorted(changes) == sorted(['web-01: - -> Internal', 'web-01: Internal -> Client A', 'web-01: Client A -> -'])


def test_options_and_group_can_be_sent_together_or_alone(client):
    admin(client)
    cid = new(client, 'web-01', 'Client A').json()['collector']['id']
    r = client.put(f'/api/v1/admin/collectors/{cid}/options', json=dict(options=dict(files=[], journald=True, units=[], host_metrics=False)), headers=X).json()['collector']
    assert r['group'] == 'Client A' and r['options']['host_metrics'] is False                    # the group stays
    r = client.put(f'/api/v1/admin/collectors/{cid}/options', json=dict(options=dict(files=[], journald=True, units=[], host_metrics=True), group='Other'), headers=X).json()['collector']
    assert (r['group'], r['options']['host_metrics']) == ('Other', True)
    assert client.put(f'/api/v1/admin/collectors/{cid}/options', json={}, headers=X).status_code == 400


def test_only_an_admin_can_change_groups(client):
    admin(client)
    cid = new(client, 'web-01', 'Client A').json()['collector']['id']
    make_user(client, 'rina')
    user = as_user(client, 'rina', 'rina-initial-password-123')
    assert user.put(f'/api/v1/admin/collectors/{cid}/options', json=dict(group='X'), headers=X).status_code == 403
    assert user.post('/api/v1/admin/collectors', json=dict(name='x-1', platform='linux', group='X'), headers=X).status_code == 403
    assert rows(client)['web-01']['group'] == 'Client A'


def test_servers_carry_the_group_of_their_collector(client):
    admin(client)
    cid = new(client, 'web-01', 'Client A').json()['collector']['id']
    token = client.post(f'/api/v1/admin/collectors/{cid}/token', headers=X).json()['enroll_token']
    from test_collectors import enroll
    from fastapi.testclient import TestClient
    enroll(TestClient(client.app), token)
    import datetime
    now = datetime.datetime.now(datetime.timezone.utc)
    client.app.state.metrics.add(cid, [('h1', '', 'cpu', '', now, 5.0)], {('h1', ''): dict(os=None, image=None)}, now)
    assert client.post('/api/v1/servers', json={}, headers=X).json()['hosts'][0]['group'] == 'Client A'
    assert client.post('/api/v1/servers/host', json=dict(cid=cid, host='h1'), headers=X).json()['group'] == 'Client A'
