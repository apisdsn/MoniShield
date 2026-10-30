"""Configuration page -> .env file (owner request 2026-10-07): AWS/MaxMind credentials, blocklist exclusions,
automatic S3 folders, and notifications are written to .env, take effect without a restart, and are read again at server start.
Secrets never go back out to the browser."""
import dataclasses, json, os, stat, urllib.error

import pytest
from fastapi.testclient import TestClient

import logs_mini
from fake_s3 import KEY_OK, FakeS3
from monishield.domain import accounts
from monishield.infrastructure import auth, config, envfile, importer, refdata
from monishield.domain import alerts, settings
from monishield.interfaces.api import app as appmod
from conftest import JWT_SECRET

X = {'X-Requested-With': 'test'}
PW, PW2 = 'first-admin-password', 'admin-password-after-change'
SECRET_ENV = 'envTestSecretThatMustNeverLeak0001'
KEY_UI, SECRET_UI = 'AKIAPAGETEST00000002', 'pageTestSecretThatMustNeverLeak02'
MM_ID, MM_KEY = '123456', 'SecretMaxMindLicense_0001'
SAMPLE_ENV = """# sample .env
S4_JWT_SECRET=left-as-is
# [OPTIONAL] region
# S4_IMPORT_REGION=ap-southeast-3
MAXMIND_ACCOUNT_ID=
MAXMIND_LICENSE_KEY=
"""


# ------------------------------------------------------------------ .env writer
def test_envfile_writes_in_place_and_keeps_comments(tmp_path):
    p = tmp_path / '.env'
    p.write_text(SAMPLE_ENV); os.chmod(p, 0o640)
    ino = os.stat(p).st_ino
    envfile.update(str(p), {'MAXMIND_ACCOUNT_ID': MM_ID, 'S4_IMPORT_REGION': 'ap-southeast-1', 'S4_BLOCKLIST_EXCLUDE_ORG': 'A B#C',
                            'S4_SMTP_FROM': 'Team "Ops" <ops@x.id>', 'S4_NEW_KEY': ''})
    t = p.read_text()
    assert os.stat(p).st_ino == ino and stat.S_IMODE(os.stat(p).st_mode) == 0o640       # the same file (Docker bind mount)
    assert '# sample .env\nS4_JWT_SECRET=left-as-is\n# [OPTIONAL] region\nS4_IMPORT_REGION=ap-southeast-1\nMAXMIND_ACCOUNT_ID=123456\n' in t
    assert envfile.MARK in t
    v = config.read_dotenv(str(p))
    assert (v['S4_BLOCKLIST_EXCLUDE_ORG'], v['S4_SMTP_FROM'], v['S4_NEW_KEY']) == ('A B#C', 'Team "Ops" <ops@x.id>', '')
    # delete = line disabled without the old value (secrets are not left in a comment)
    envfile.update(str(p), {'MAXMIND_ACCOUNT_ID': None})
    assert '# MAXMIND_ACCOUNT_ID=\n' in p.read_text() and MM_ID not in p.read_text() and 'MAXMIND_ACCOUNT_ID' not in config.read_dotenv(str(p))
    for bad in ('a\nS4_JAHAT=1', 'kutip \' dan "'):
        with pytest.raises(envfile.EnvFileFail): envfile.update(str(p), {'S4_X': bad})
    assert 'S4_JAHAT' not in p.read_text()
    q = tmp_path / 'new.env'
    envfile.update(str(q), {'AWS_ACCESS_KEY_ID': KEY_UI})
    assert stat.S_IMODE(os.stat(q).st_mode) == 0o600


# ------------------------------------------------------------------ API
@pytest.fixture
def s3(monkeypatch):
    t = FakeS3({'example-log-bucket': {'k8s-logs/2026-01-05/ns/svc/a.log': b'x'}}, keys=(KEY_OK, KEY_UI))
    monkeypatch.setattr(importer, 'ENDPOINT', t.url)
    yield t
    t.close()


@pytest.fixture
def cfg(tmp_path, auth_url):
    return dataclasses.replace(config.Config(), log_dir=logs_mini.build(tmp_path / 'logs'), data_dir=str(tmp_path / 'data'), state_dir=str(tmp_path / 'state'),
                               inbox_dir=str(tmp_path / 'inbox'), cache_dir=str(tmp_path / 'cache'), offline=False, ingest_on_start=False, cookie_secure=False,
                               admin_user='admin', admin_password=PW, jwt_secret=JWT_SECRET, auth_database_url=auth_url,
                               import_buckets={'example-log-bucket': ['k8s-logs/']}, aws_access_key_id=KEY_OK, aws_secret_access_key=SECRET_ENV)


@pytest.fixture
def envp(tmp_path):
    p = tmp_path / 'v2.env'
    p.write_text(SAMPLE_ENV + f'AWS_ACCESS_KEY_ID={KEY_OK}\nAWS_SECRET_ACCESS_KEY={SECRET_ENV}\n')
    return str(p)


@pytest.fixture
def client(cfg, envp, monkeypatch, s3):
    monkeypatch.setattr(accounts, 'SCRYPT', (10, 8, 1))
    for k in ('AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'AWS_SESSION_TOKEN', 'MAXMIND_ACCOUNT_ID', 'MAXMIND_LICENSE_KEY'): monkeypatch.delenv(k, raising=False)
    with TestClient(appmod.create_app(cfg, env_path=envp)) as tc:
        assert tc.post('/api/auth/login', json=dict(username='admin', password=PW), headers=X).status_code == 200
        assert tc.post('/api/me/password', json=dict(old_password=PW, new_password=PW2), headers=X).status_code == 200
        yield tc


def clean(text):
    for s in (SECRET_ENV, SECRET_UI, MM_KEY, KEY_UI, KEY_OK): assert s not in text


def test_initial_view_without_secrets(client, envp):
    r = client.get('/api/admin/config', headers=X)
    assert r.status_code == 200
    v = r.json()
    a = v['aws']
    assert a['aws_access_key_id'] == dict(set=True, source='file', env='AWS_ACCESS_KEY_ID', masked=f'{KEY_OK[:4]}…{KEY_OK[-4:]}')
    assert a['aws_secret_access_key'] == dict(set=True, source='file', env='AWS_SECRET_ACCESS_KEY')
    assert a['aws_session_token'] == dict(set=False, source=None, env='AWS_SESSION_TOKEN')
    assert a['import_region'] == dict(value='', source=None, env='S4_IMPORT_REGION')   # no built-in region: free text
    assert v['maxmind']['maxmind_license_key'] == dict(set=False, source='file', env='MAXMIND_LICENSE_KEY')
    assert v['blocklist']['blocklist_exclude_org']['value'] == ''
    assert v['server']['jwt_secret'] is True and v['server']['job_token'] is False
    assert v['file'] == dict(path=envp, exists=True, writable=True, environment_override=[], pending=[])
    clean(r.text)


def test_save_to_env_applies_at_once(client, envp):
    cfg = client.app.state.cfg
    r = client.put('/api/admin/config', json=dict(aws_access_key_id=KEY_UI, aws_secret_access_key=SECRET_UI, maxmind_account_id=MM_ID,
                                                  maxmind_license_key=MM_KEY, blocklist_exclude='36.66.1.0/24, 198.51.100.7'), headers=X)
    assert r.status_code == 200, r.text
    clean(r.text)
    f = config.read_dotenv(envp)
    assert (f['AWS_ACCESS_KEY_ID'], f['AWS_SECRET_ACCESS_KEY'], f['MAXMIND_ACCOUNT_ID'], f['MAXMIND_LICENSE_KEY']) == (KEY_UI, SECRET_UI, MM_ID, MM_KEY)
    assert f['S4_BLOCKLIST_EXCLUDE'] == '36.66.1.0/24, 198.51.100.7' and f['S4_JWT_SECRET'] == 'left-as-is'
    assert (cfg.aws_access_key_id, cfg.aws_secret_access_key, cfg.maxmind_license_key) == (KEY_UI, SECRET_UI, MM_KEY)
    assert client.app.state.imports.creds.get()[0]['aws_access_key_id'] == KEY_UI
    assert client.app.state.auth.setting_get('config') is None                          # no longer in the database
    # empty secret = unchanged; ordinary fields can be replaced (commented example line enabled in place)
    r = client.put('/api/admin/config', json=dict(aws_access_key_id=KEY_UI, aws_secret_access_key='', import_region='ap-southeast-1'), headers=X)
    assert r.status_code == 200, r.text
    assert (cfg.aws_secret_access_key, cfg.import_region) == (SECRET_UI, 'ap-southeast-1')
    assert '# [OPTIONAL] region\nS4_IMPORT_REGION=ap-southeast-1\n' in open(envp).read()
    log = json.dumps(client.app.state.auth.audit_list(50), default=str)
    assert 'config.update' in log
    clean(log)
    # delete -> line disabled, default value
    r = client.put('/api/admin/config', json=dict(clear=['aws_session_token', 'import_region', 'maxmind_account_id', 'maxmind_license_key']), headers=X)
    assert r.status_code == 200
    assert cfg.import_region == '' and cfg.maxmind_license_key == ''
    t = open(envp).read()
    assert '# S4_IMPORT_REGION=\n' in t and MM_KEY not in t


def test_read_again_on_restart(client, envp):
    assert client.put('/api/admin/config', json=dict(maxmind_account_id=MM_ID, maxmind_license_key=MM_KEY, blocklist_exclude_org='KOMINFO'), headers=X).status_code == 200
    c = config.load(env={}, dotenv=envp)
    assert (c.maxmind_account_id, c.maxmind_license_key, c.blocklist_exclude_org, c.aws_access_key_id) == (MM_ID, MM_KEY, 'KOMINFO', KEY_OK)


def test_environment_variables_beat_env_and_are_marked(client, monkeypatch):
    monkeypatch.setenv('AWS_ACCESS_KEY_ID', 'AKIADARILINGKUNGAN01')
    v = client.get('/api/admin/config', headers=X).json()
    assert v['aws']['aws_access_key_id']['source'] == 'environment' and v['file']['environment_override'] == ['AWS_ACCESS_KEY_ID']


@pytest.mark.parametrize('body', [
    dict(aws_access_key_id='akia-kecil', aws_secret_access_key=SECRET_UI),
    dict(aws_access_key_id=KEY_UI, aws_secret_access_key='pendek'),
    dict(aws_access_key_id='', clear=['aws_secret_access_key']),                       # incomplete pair
    dict(import_region='ap southeast 3'),                                         # free text, but no spaces
    dict(maxmind_account_id='abc', maxmind_license_key=MM_KEY),
    dict(maxmind_license_key=MM_KEY),
    dict(blocklist_exclude='10.0.0.0/8, not-an-ip'),
    dict(blocklist_exclude_org='(unclosed'),
])
def test_invalid_fields_are_refused_without_writing(client, envp, body):
    before = open(envp).read()
    r = client.put('/api/admin/config', json=body, headers=X)
    assert r.status_code == 400 and r.json()['error']['code'] == 'invalid_config', r.text
    clean(r.text)
    assert open(envp).read() == before and client.app.state.cfg.aws_access_key_id == KEY_OK


def test_env_not_writable(client, envp, monkeypatch):
    monkeypatch.setattr(envfile, 'writable', lambda p: False)   # (tests run as root: file permissions do not apply)
    before = open(envp).read()
    assert client.get('/api/admin/config', headers=X).json()['file']['writable'] is False
    r = client.put('/api/admin/config', json=dict(import_region='ap-southeast-1'), headers=X)
    assert r.status_code == 400 and r.json()['error']['code'] == 'env_not_writable' and open(envp).read() == before
    assert client.app.state.cfg.import_region == ''


def test_move_from_the_database_to_env(cfg, envp, monkeypatch, s3):
    """Old settings (before .env) in app_setting are moved once to .env at server start, then removed from the database."""
    monkeypatch.setattr(accounts, 'SCRYPT', (10, 8, 1))
    a = auth.Auth(cfg.auth_url)
    a.setting_set('config', dict(maxmind_account_id=MM_ID, maxmind_license_key=MM_KEY, aws_access_key_id=''), 'admin')
    a.setting_set('s3_watch', dict(url='s3://example-log-bucket/k8s-logs/', minutes=15, enabled=True), 'admin')
    a.setting_set('alerts', dict(channels=dict(discord=dict(enabled=True, webhook_url='https://discord.com/api/webhooks/1/abc')), lang='en'), 'admin')
    a.close()
    with TestClient(appmod.create_app(cfg, env_path=envp)) as tc:
        c = tc.app.state.cfg
        assert (c.maxmind_license_key, c.s3_watch, c.s3_watch_minutes, c.alert_discord, c.alert_lang) == (MM_KEY, 's3://example-log-bucket/k8s-logs/', 15, True, 'en')
        assert c.aws_access_key_id == KEY_OK                                            # old empty value does not overwrite
        assert all(tc.app.state.auth.setting_get(k) is None for k in ('config', 's3_watch', 'alerts'))
    f = config.read_dotenv(envp)
    assert (f['MAXMIND_LICENSE_KEY'], f['S4_S3_WATCH_MINUTES'], f['S4_ALERT_DISCORD'], f['DISCORD_WEBHOOK_URL']) == \
        (MM_KEY, '15', 'true', 'https://discord.com/api/webhooks/1/abc')


def test_blocklist_exclusions_from_the_page(client):
    from monishield.infrastructure.queries import ips
    assert client.put('/api/admin/config', json=dict(blocklist_exclude='36.66.1.0/24', blocklist_exclude_org='TELKOM'), headers=X).status_code == 200
    c = client.app.state.cfg
    assert ips._excluded(c, '36.66.1.9', False, '') == 'list' and ips._excluded(c, '8.8.8.8', False, 'PT TELKOM INDONESIA') == 'org'
    assert ips._excluded(c, '8.8.8.8', False, 'EXAMPLE ORG') is None


def test_check_aws(client):
    r = client.post('/api/admin/config/test', json=dict(kind='aws'), headers=X)
    assert r.status_code == 200, r.text
    assert r.json() == dict(ok=True, kind='aws', target='s3://example-log-bucket/k8s-logs/', source='environment')
    assert client.put('/api/admin/config', json=dict(aws_access_key_id='AKIASALAHSALAHSALAH1', aws_secret_access_key=SECRET_UI), headers=X).status_code == 200
    r = client.post('/api/admin/config/test', json=dict(kind='aws'), headers=X)
    assert r.status_code == 424 and r.json()['error']['code'] == 's3_denied'
    clean(r.text)
    assert client.post('/api/admin/config/test', json=dict(kind='other'), headers=X).status_code == 400


def test_check_maxmind(client, monkeypatch):
    r = client.post('/api/admin/config/test', json=dict(kind='maxmind'), headers=X)
    assert r.status_code == 400 and r.json()['error']['code'] == 'maxmind_missing'
    assert client.put('/api/admin/config', json=dict(maxmind_account_id=MM_ID, maxmind_license_key=MM_KEY), headers=X).status_code == 200
    seen = []

    class Opener:
        def __init__(self, code): self.code = code
        def open(self, req, timeout=None):
            seen.append((req.get_method(), req.full_url, req.get_header('Authorization')))
            raise urllib.error.HTTPError(req.full_url, self.code, 'x', {}, None)
    for code, status, err in ((302, 200, None), (401, 424, 'maxmind_denied'), (500, 424, 'maxmind_error')):
        monkeypatch.setattr(refdata.urllib.request, 'build_opener', lambda *a, c=code: Opener(c))
        r = client.post('/api/admin/config/test', json=dict(kind='maxmind'), headers=X)
        assert r.status_code == status, (code, r.text)
        if err: assert r.json()['error']['code'] == err
        clean(r.text)
    assert seen[0][0] == 'HEAD' and seen[0][1] == config.Config().url_maxmind.format('GeoLite2-City-CSV') and seen[0][2].startswith('Basic ')
    client.app.state.cfg.offline = True
    assert client.post('/api/admin/config/test', json=dict(kind='maxmind'), headers=X).json()['error']['code'] == 'offline'


def test_without_session_rejected(cfg, envp, monkeypatch, s3):
    monkeypatch.setattr(accounts, 'SCRYPT', (10, 8, 1))
    with TestClient(appmod.create_app(cfg, env_path=envp)) as tc:
        assert tc.get('/api/admin/config', headers=X).status_code == 401
        assert tc.put('/api/admin/config', json={}, headers=X).status_code == 401
        assert tc.post('/api/admin/config/test', json=dict(kind='aws'), headers=X).status_code == 401


def test_addresses_and_limits_from_env():
    """Download source URLs, the Telegram API, and limits that used to be hard-coded now come from .env."""
    c = config.load(env={'S4_URL_IP2ASN': 'https://mirror.corp.example.com/ip2asn-v4.tsv.gz', 'S4_TELEGRAM_API': 'https://tg-proxy.corp.example.com',
                         'S4_URL_MAXMIND': 'https://mm.corp.example.com/{}.zip', 'S4_GEO_MAX_AGE_DAYS': '14', 'S4_UPLOAD_SESSION_HOURS': '2'}, dotenv=False)
    assert (c.url_ip2asn, c.telegram_api, c.url_maxmind, c.geo_max_age_days, c.upload_session_hours) == \
        ('https://mirror.corp.example.com/ip2asn-v4.tsv.gz', 'https://tg-proxy.corp.example.com', 'https://mm.corp.example.com/{}.zip', 14, 2)
    assert alerts.load(c)['channels']['telegram']['api'] == 'https://tg-proxy.corp.example.com'
    for env in ({'S4_GEO_MAX_AGE_DAYS': '60'}, {'S4_URL_MAXMIND': 'https://x/tanpa-edisi'}, {'S4_URL_LAND': 'ftp://x'}):
        with pytest.raises(SystemExit): config.load(env=env, dotenv=False)
    assert settings.GROUPS['alerts'][0] == 'alert_telegram'


def test_kafka_fields_from_the_page_are_saved_to_env(client, envp):
    """The Kafka card in Configuration sends kafka_* to PUT /api/admin/config (same body as AdminConfig.svelte kfBody):
    must be written to .env and take effect immediately; the SASL password is never returned."""
    body = dict(kafka_enabled=True, kafka_brokers='127.0.0.1:9, 127.0.0.2:9', kafka_topic='k8s-logs', kafka_group='monishield',
                kafka_security='sasl_plaintext', kafka_sasl_mechanism='SCRAM-SHA-512', kafka_username='monishield', kafka_password='secretKafkaPassword1',
                kafka_offset_reset='latest', kafka_ingest_minutes='15')
    r = client.put('/api/admin/config', json=body, headers=X)
    assert r.status_code == 200, r.text
    assert 'secretKafkaPassword1' not in r.text and r.json()['kafka']['kafka_password'] == dict(set=True, source='file', env='KAFKA_PASSWORD')
    text = open(envp).read()
    for line in ('S4_KAFKA_TOPIC=k8s-logs', 'S4_KAFKA_SECURITY=sasl_plaintext', 'S4_KAFKA_INGEST_MINUTES=15', 'KAFKA_PASSWORD='): assert line in text, line
    c = client.app.state.cfg
    assert (c.kafka_enabled, c.kafka_brokers, c.kafka_sasl_mechanism, c.kafka_password, c.kafka_ingest_minutes) == \
        (True, '127.0.0.1:9, 127.0.0.2:9', 'SCRAM-SHA-512', 'secretKafkaPassword1', 15)
    r = client.put('/api/admin/config', json=dict(kafka_security='sasl_ssl', kafka_password=''), headers=X)   # empty password = unchanged
    assert r.status_code == 200 and client.app.state.cfg.kafka_password == 'secretKafkaPassword1'
    r = client.put('/api/admin/config', json=dict(kafka_brokers='not a broker'), headers=X)
    assert r.status_code == 400 and 'host:port' in r.json()['error']['message']
    r = client.put('/api/admin/config', json=dict(kafka_enabled=False), headers=X)   # switch from the UI (JSON bool)
    assert r.status_code == 200 and client.app.state.cfg.kafka_enabled is False and 'S4_KAFKA_ENABLED=false' in open(envp).read()


def test_bad_value_elsewhere_does_not_block_other_sections(client, envp):
    """An invalid AWS key in the running settings (for example from the process environment) only blocks saving the AWS
    section, not unrelated sections such as the block list or the mail server."""
    object.__setattr__(client.app.state.cfg, 'aws_access_key_id', 'placeholder-key')
    r = client.put('/api/admin/config', json=dict(blocklist_exclude_org='KOMINFO', smtp_port='587'), headers=X)
    assert r.status_code == 200, r.text
    assert config.read_dotenv(envp)['S4_BLOCKLIST_EXCLUDE_ORG'] == 'KOMINFO'
    r = client.put('/api/admin/config', json=dict(aws_secret_access_key=SECRET_UI), headers=X)   # the pair rule reads the bad key
    assert r.status_code == 400 and r.json()['error']['code'] == 'invalid_config'
    assert 'Access Key ID' in r.json()['error']['message']
    clean(r.text)


def test_object_storage_provider_from_the_page(client, envp):
    """Sidebar → Object storage: another provider with its endpoint and its own key format, then Azure."""
    r = client.put('/api/admin/config', json=dict(storage_provider='r2', aws_access_key_id='3f2a9c0e7b6d4a1f8e5c2b9a7d4e1f0a',
                                                  aws_secret_access_key='c0ffee1234567890abcdef0123456789', import_region='auto'), headers=X)
    assert r.status_code == 400 and 'endpoint' in r.json()['error']['message']   # R2 needs its endpoint
    r = client.put('/api/admin/config', json=dict(storage_provider='r2', storage_endpoint='https://acc.r2.cloudflarestorage.com',
                                                  aws_access_key_id='3f2a9c0e7b6d4a1f8e5c2b9a7d4e1f0a',
                                                  aws_secret_access_key='c0ffee1234567890abcdef0123456789', import_region='auto'), headers=X)
    assert r.status_code == 200, r.text
    f = config.read_dotenv(envp)
    assert (f['S4_STORAGE_PROVIDER'], f['S4_STORAGE_ENDPOINT'], f['S4_IMPORT_REGION']) == ('r2', 'https://acc.r2.cloudflarestorage.com', 'auto')
    v = client.get('/api/admin/config', headers=X).json()['aws']
    assert v['storage_provider']['value'] == 'r2' and v['azure_storage_key'] == dict(set=False, source=None, env='AZURE_STORAGE_KEY')
    key = 'bm90LWEtcmVhbC1rZXktanVzdC1hLXRlc3Q=' * 2
    r = client.put('/api/admin/config', json=dict(storage_provider='azure', azure_storage_account='monishieldlogs', azure_storage_key=key), headers=X)
    assert r.status_code == 200, r.text
    assert key not in r.text and client.app.state.s3.creds.get()[0] == dict(account='monishieldlogs', key=key)
