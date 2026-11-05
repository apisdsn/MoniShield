"""Collector options, configuration and install scripts through the API (docs/12-collector.md, step 5)."""
import dataclasses, re

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from monishield.domain import collector_config as cc
from monishield.domain.config_model import Config
from monishield.infrastructure import auth as authmod
from test_api import X, admin, client, cfg, error_code, make_user, as_user   # noqa: F401
from test_collectors import ENROLL_H, add, audit_rows, enroll

FILES = [dict(path='/var/log/app/*.log', service='app')]


def new(tc, name='web-01', platform='linux', options=None):
    body = dict(name=name, platform=platform)
    if options is not None: body['options'] = options
    return tc.post('/api/admin/collectors', json=body, headers=X)


def test_options_on_create_and_defaults(client):
    admin(client)
    r = new(client, options=dict(files=FILES, journald=False))
    assert r.status_code == 201 and r.json()['collector']['options'] == dict(files=FILES, journald=False, units=[], host_metrics=False)
    r = new(client, 'web-02')                                                       # nothing chosen: the defaults of the platform
    assert r.json()['collector']['options'] == cc.default_options('linux')
    assert new(client, 'win-01', 'windows').json()['collector']['options']['channels'] == ['application', 'system']
    assert new(client, 'k8s', 'kubernetes').json()['collector']['options'] == dict(host_metrics=True)
    rows = {c['name']: c for c in client.get('/api/admin/collectors').json()['rows']}
    assert rows['web-01']['options']['files'] == FILES and all('stats' in c for c in rows.values())


@pytest.mark.parametrize('options,code', [
    (dict(files=[dict(path='relative.log', service='a')]), 'invalid_path'),
    (dict(files=[dict(path='/a.log', service='bad name')]), 'invalid_service'),
    (dict(journald=False), 'no_inputs'),
    (dict(channels=['system']), 'invalid_options'),
])
def test_bad_options_are_refused_and_nothing_is_created(client, options, code):
    admin(client)
    r = new(client, options=options)
    assert (r.status_code, error_code(r)) == (400, code)
    assert client.get('/api/admin/collectors').json()['rows'] == []


def test_update_options_audit_and_roles(client):
    admin(client); make_user(client)
    cid = new(client).json()['collector']['id']
    r = client.put(f'/api/admin/collectors/{cid}/options', json=dict(options=dict(files=FILES, journald=True, units=['ssh.service'])), headers=X)
    assert r.status_code == 200 and r.json()['collector']['options']['units'] == ['ssh.service']
    assert client.get('/api/admin/collectors').json()['rows'][0]['options']['files'] == FILES
    assert any(a['action'] == 'collector.options' and a['detail'] == 'web-01' for a in audit_rows(client))
    assert error_code(client.put(f'/api/admin/collectors/{cid}/options', json=dict(options=dict(journald=False)), headers=X)) == 'no_inputs'
    assert client.put('/api/admin/collectors/999/options', json=dict(options={}), headers=X).status_code == 404
    user, anon = as_user(client, 'rina', 'rina-initial-password-123'), TestClient(client.app)
    assert user.put(f'/api/admin/collectors/{cid}/options', json=dict(options={}), headers=X).status_code == 403
    assert anon.put(f'/api/admin/collectors/{cid}/options', json=dict(options={}), headers=X).status_code == 401
    client.post(f'/api/admin/collectors/{cid}/revoke', headers=X)
    assert error_code(client.put(f'/api/admin/collectors/{cid}/options', json=dict(options=dict(journald=True)), headers=X)) == 'collector_revoked'


def test_enroll_returns_the_configuration_without_the_key(client):
    admin(client)
    c = new(client, options=dict(files=FILES, journald=False)).json()
    got = enroll(TestClient(client.app), c['enroll_token']).json()
    assert set(got) == {'collector', 'key', 'config'}
    assert got['key'] not in got['config'] and 'msk_' not in got['config'] and '${env:MONISHIELD_COLLECTOR_KEY}' in got['config']
    assert 'endpoint: "http://testserver/api/collector"' in got['config'] and '"/var/log/app/*.log"' in got['config']


def test_enroll_for_the_install_script_is_text_plus_headers(client):
    admin(client)
    c = new(client, 'edge-1', 'docker').json()
    r = TestClient(client.app).post('/api/collector/enroll?format=install', json=dict(token=c['enroll_token']), headers=ENROLL_H)
    assert r.status_code == 200 and r.headers['content-type'].startswith('text/plain') and r.headers['cache-control'] == 'no-store'
    assert r.headers['x-collector-platform'] == 'docker' and r.headers['x-collector-name'] == 'edge-1' and r.headers['x-collector-key'].startswith('msk_')
    assert r.headers['x-collector-key'] not in r.text and '/var/lib/otelcol-contrib/containers/*.log' in r.text and 'container.name' in r.text
    bad = TestClient(client.app).post('/api/collector/enroll?format=install', json=dict(token=c['enroll_token']), headers=ENROLL_H)
    assert bad.status_code == 401 and error_code(bad) == 'invalid_enrollment_token'


def test_get_config_needs_a_key_and_follows_the_options(client):
    admin(client)
    c = new(client, options=dict(files=FILES, journald=False)).json()
    anon = TestClient(client.app)
    key = enroll(anon, c['enroll_token']).json()['key']
    assert error_code(anon.get('/api/collector/config')) == 'invalid_collector_key'
    assert error_code(anon.get('/api/collector/config', headers={'Authorization': 'Bearer msk_1_' + 'A' * 43})) == 'invalid_collector_key'
    r = anon.get('/api/collector/config', headers={'Authorization': f'Bearer {key}'})
    assert r.status_code == 200 and r.headers['cache-control'] == 'no-store' and '"/var/log/app/*.log"' in r.text and key not in r.text
    client.put(f"/api/admin/collectors/{c['collector']['id']}/options", json=dict(options=dict(journald=True, units=[])), headers=X)
    r = anon.get('/api/collector/config', headers={'Authorization': f'Bearer {key}'})
    assert 'journald:' in r.text and 'file_log/1' not in r.text


def test_upgrade_reads_the_config_with_the_key_alone_and_docker_is_recognised(client):
    # install.sh --upgrade sends only the Bearer key (no X-Requested-With, no token) and tells a Docker collector by the link folder
    admin(client)
    c = new(client, 'dock-01', 'docker').json()
    anon = TestClient(client.app)
    key = enroll(anon, c['enroll_token']).json()['key']
    r = anon.get('/api/collector/config', headers={'Authorization': f'Bearer {key}'})
    assert r.status_code == 200 and 'otelcol-contrib/containers/' in r.text and key not in r.text
    lin = enroll(anon, new(client, 'lin-01').json()['enroll_token']).json()['key']
    assert 'otelcol-contrib/containers/' not in anon.get('/api/collector/config', headers={'Authorization': f'Bearer {lin}'}).text


def test_kubernetes_enroll_returns_helm_values(client):
    admin(client)
    c = new(client, 'prod', 'kubernetes').json()
    cfg_ = enroll(TestClient(client.app), c['enroll_token']).json()['config']
    assert 'mode: "daemonset"' in cfg_ and f'tag: "{Config().collector_otel_version}"' in cfg_


def test_public_url_setting_wins_over_the_request(cfg, auth_url, monkeypatch):
    from monishield.interfaces.api import app as appmod
    c = dataclasses.replace(cfg, auth_database_url=auth_url, collector_public_url='https://logs.example.org')
    with TestClient(appmod.create_app(c)) as tc:
        admin(tc)
        token = new(tc).json()['enroll_token']
        assert 'endpoint: "https://logs.example.org/api/collector"' in enroll(TestClient(tc.app), token).json()['config']
        assert 'https://logs.example.org' in tc.get('/collector/install.sh').text


def test_scripts_are_public_and_filled_in(client):
    version = Config().collector_otel_version
    for name, ctype in (('install.sh', 'text/x-shellscript'), ('install.ps1', 'text/plain')):
        r = client.get(f'/collector/{name}')                                         # no session
        assert r.status_code == 200 and r.headers['content-type'].startswith(ctype) and r.headers['cache-control'] == 'no-store'
        assert f"'{version}'" in r.text and 'http://testserver' in r.text and '@@' not in r.text
        assert not re.search(r'ms[ek]_\d+_[A-Za-z0-9_-]{43}', r.text)


def test_scripts_use_the_forwarded_scheme_only_behind_a_proxy(cfg, auth_url):
    from monishield.interfaces.api import app as appmod
    for trust, want in ((False, 'http://testserver'), (True, 'https://testserver')):
        c = dataclasses.replace(cfg, auth_database_url=auth_url, trust_proxy=trust)
        with TestClient(appmod.create_app(c)) as tc:
            assert want in tc.get('/collector/install.sh', headers={'X-Forwarded-Proto': 'https'}).text


def test_a_bad_host_header_is_refused(client):
    r = client.get('/collector/install.sh', headers={'Host': 'x.com"; id; "'})
    assert r.status_code == 400 and error_code(r) == 'invalid_host'


def test_old_database_gets_the_options_column(tmp_path):
    url = f'sqlite:///{tmp_path}/old.db'
    first = authmod.Auth(url, 'j' * 40)
    first.close()
    with create_engine(url).begin() as c:                                             # the table as it was before the options existed
        c.execute(text('ALTER TABLE collector DROP COLUMN options'))
    assert 'options' not in {r[1] for r in create_engine(url).connect().execute(text('PRAGMA table_info(collector)'))}
    again = authmod.Auth(url, 'j' * 40)
    info, _ = again.collector_create('old-1', 'linux', None, None, dict(journald=True))
    assert info['options'] == dict(journald=True) and again.collector_list()[0]['options'] == dict(journald=True)
    again.close()
    authmod.Auth(url, 'j' * 40).close()                                               # a second start does not try to add it again


def test_admin_lists_the_receiver_and_downloads_the_configuration(client):
    admin(client); make_user(client)
    cid = new(client, 'k8s', 'kubernetes').json()['collector']['id']
    rows = client.get('/api/admin/collectors').json()
    assert rows['receiver'] == 'http://testserver' and rows['otel_version'] == Config().collector_otel_version
    r = client.get(f'/api/admin/collectors/{cid}/config')
    assert r.status_code == 200 and 'values.yaml' in r.headers['content-disposition'] and r.headers['cache-control'] == 'no-store'
    assert 'mode: "daemonset"' in r.text and 'msk_' not in r.text and 'mse_' not in r.text
    assert 'config.yaml' in client.get(f"/api/admin/collectors/{new(client, 'web-9').json()['collector']['id']}/config").headers['content-disposition']
    assert client.get('/api/admin/collectors/999/config').status_code == 404
    user, anon = as_user(client, 'rina', 'rina-initial-password-123'), TestClient(client.app)
    assert user.get(f'/api/admin/collectors/{cid}/config').status_code == 403 and anon.get(f'/api/admin/collectors/{cid}/config').status_code == 401


def test_stats_name_the_hosts_the_collector_sent_for(client):
    admin(client)
    c = new(client, 'web-01').json()
    anon = TestClient(client.app)
    key = enroll(anon, c['enroll_token']).json()['key']
    def line(host, n):
        return {'resourceLogs': [{'resource': {'attributes': [{'key': 'host.name', 'value': {'stringValue': host}}]},
                                   'scopeLogs': [{'logRecords': [{'body': {'stringValue': f'line {n}'}}]}]}]}
    for i, host in enumerate(['h1', 'h2', 'h1', 'h3', 'h4', 'h5', 'h6']):
        r = anon.post('/api/collector/v1/logs', json=line(host, i), headers={'Authorization': f'Bearer {key}'})
        assert r.status_code == 200, r.text
    stats = client.get('/api/admin/collectors').json()['rows'][0]['stats']
    assert stats['hosts'] == ['h6', 'h5', 'h4', 'h3', 'h1'] and stats['received'] == 7 and stats['written'] == 7


def test_ingest_domain_is_the_receiver_when_no_public_url(cfg, auth_url):
    from monishield.interfaces.api import app as appmod
    c = dataclasses.replace(cfg, auth_database_url=auth_url, collector_public_url='https://ingest.example.org')   # what config.load makes of DOCKER_INGEST_DOMAIN
    with TestClient(appmod.create_app(c)) as tc:
        admin(tc)
        assert tc.get('/api/admin/collectors').json()['receiver'] == 'https://ingest.example.org'
        assert 'https://ingest.example.org' in tc.get('/collector/install.sh').text
