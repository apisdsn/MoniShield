"""Halaman Konfigurasi -> file .env (permintaan pemilik 2026-10-07): kredensial AWS/MaxMind, pengecualian daftar blokir,
folder S3 otomatis, dan notifikasi ditulis ke .env, langsung berlaku tanpa mulai ulang, dan dibaca lagi saat server mulai.
Rahasia tidak pernah keluar lagi ke browser."""
import dataclasses, json, os, stat, urllib.error

import pytest
from fastapi.testclient import TestClient

import logs_mini
from s3_tiruan import KEY_OK, S3Tiruan
from monishield.infrastructure import auth, config, envfile, importer
from monishield.application import settings
from monishield.interfaces.api import app as appmod, config_api
from conftest import JWT_SECRET

X = {'X-Requested-With': 'uji'}
PW, PW2 = 'sandi-admin-pertama', 'sandi-admin-sesudah-diganti'
SECRET_ENV = 'rahasiaEnvUjiYangTidakBolehBocor0001'
KEY_UI, SECRET_UI = 'AKIALAYARUJI00000002', 'rahasiaLayarUjiYangTidakBolehBocor02'
MM_ID, MM_KEY = '123456', 'LisensiMaxMindRahasia_0001'
CONTOH = """# contoh .env
S4_JWT_SECRET=dibiarkan
# [OPSIONAL] wilayah
# S4_IMPORT_REGION=ap-southeast-3
MAXMIND_ACCOUNT_ID=
MAXMIND_LICENSE_KEY=
"""


# ------------------------------------------------------------------ penulis .env
def test_envfile_menulis_di_tempat_dan_menjaga_komentar(tmp_path):
    p = tmp_path / '.env'
    p.write_text(CONTOH); os.chmod(p, 0o640)
    ino = os.stat(p).st_ino
    envfile.update(str(p), {'MAXMIND_ACCOUNT_ID': MM_ID, 'S4_IMPORT_REGION': 'ap-southeast-1', 'S4_BLOCKLIST_EXCLUDE_ORG': 'A B#C',
                            'S4_SMTP_FROM': 'Tim "Ops" <ops@x.id>', 'S4_BARU': ''})
    t = p.read_text()
    assert os.stat(p).st_ino == ino and stat.S_IMODE(os.stat(p).st_mode) == 0o640       # file yang sama (bind mount Docker)
    assert '# contoh .env\nS4_JWT_SECRET=dibiarkan\n# [OPSIONAL] wilayah\nS4_IMPORT_REGION=ap-southeast-1\nMAXMIND_ACCOUNT_ID=123456\n' in t
    assert envfile.MARK in t
    v = config.read_dotenv(str(p))
    assert (v['S4_BLOCKLIST_EXCLUDE_ORG'], v['S4_SMTP_FROM'], v['S4_BARU']) == ('A B#C', 'Tim "Ops" <ops@x.id>', '')
    # hapus = baris dinonaktifkan tanpa nilai lama (rahasia tidak tertinggal di komentar)
    envfile.update(str(p), {'MAXMIND_ACCOUNT_ID': None})
    assert '# MAXMIND_ACCOUNT_ID=\n' in p.read_text() and MM_ID not in p.read_text() and 'MAXMIND_ACCOUNT_ID' not in config.read_dotenv(str(p))
    for bad in ('a\nS4_JAHAT=1', 'kutip \' dan "'):
        with pytest.raises(envfile.EnvFileFail): envfile.update(str(p), {'S4_X': bad})
    assert 'S4_JAHAT' not in p.read_text()
    q = tmp_path / 'baru.env'
    envfile.update(str(q), {'AWS_ACCESS_KEY_ID': KEY_UI})
    assert stat.S_IMODE(os.stat(q).st_mode) == 0o600


# ------------------------------------------------------------------ API
@pytest.fixture
def s3(monkeypatch):
    t = S3Tiruan({'simpel4-backup': {'k8s-logs/2026-01-05/ns/svc/a.log': b'x'}}, keys=(KEY_OK, KEY_UI))
    monkeypatch.setattr(importer, 'ENDPOINT', t.url)
    yield t
    t.close()


@pytest.fixture
def cfg(tmp_path, auth_url):
    return dataclasses.replace(config.Config(), log_dir=logs_mini.build(tmp_path / 'logs'), data_dir=str(tmp_path / 'data'), state_dir=str(tmp_path / 'state'),
                               inbox_dir=str(tmp_path / 'inbox'), cache_dir=str(tmp_path / 'cache'), offline=False, ingest_on_start=False, cookie_secure=False,
                               admin_user='admin', admin_password=PW, jwt_secret=JWT_SECRET, auth_database_url=auth_url,
                               import_buckets={'simpel4-backup': ['k8s-logs/']}, aws_access_key_id=KEY_OK, aws_secret_access_key=SECRET_ENV)


@pytest.fixture
def envp(tmp_path):
    p = tmp_path / 'v2.env'
    p.write_text(CONTOH + f'AWS_ACCESS_KEY_ID={KEY_OK}\nAWS_SECRET_ACCESS_KEY={SECRET_ENV}\n')
    return str(p)


@pytest.fixture
def client(cfg, envp, monkeypatch, s3):
    monkeypatch.setattr(auth, 'SCRYPT', (10, 8, 1))
    for k in ('AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'AWS_SESSION_TOKEN', 'MAXMIND_ACCOUNT_ID', 'MAXMIND_LICENSE_KEY'): monkeypatch.delenv(k, raising=False)
    with TestClient(appmod.create_app(cfg, env_path=envp)) as tc:
        assert tc.post('/api/auth/login', json=dict(username='admin', password=PW), headers=X).status_code == 200
        assert tc.post('/api/me/password', json=dict(old_password=PW, new_password=PW2), headers=X).status_code == 200
        yield tc


def bersih(text):
    for s in (SECRET_ENV, SECRET_UI, MM_KEY, KEY_UI, KEY_OK): assert s not in text


def test_lihat_awal_tanpa_rahasia(client, envp):
    r = client.get('/api/admin/config', headers=X)
    assert r.status_code == 200
    v = r.json()
    a = v['aws']
    assert a['aws_access_key_id'] == dict(set=True, source='file', env='AWS_ACCESS_KEY_ID', masked=f'{KEY_OK[:4]}…{KEY_OK[-4:]}')
    assert a['aws_secret_access_key'] == dict(set=True, source='file', env='AWS_SECRET_ACCESS_KEY')
    assert a['aws_session_token'] == dict(set=False, source=None, env='AWS_SESSION_TOKEN')
    assert a['import_region'] == dict(value='ap-southeast-3', source=None, env='S4_IMPORT_REGION')
    assert v['maxmind']['maxmind_license_key'] == dict(set=False, source='file', env='MAXMIND_LICENSE_KEY')
    assert v['blocklist']['blocklist_exclude_org']['value'] == 'OMBUDSMAN'
    assert v['server']['jwt_secret'] is True and v['server']['job_token'] is False
    assert v['file'] == dict(path=envp, exists=True, writable=True, environment_override=[], pending=[])
    bersih(r.text)


def test_simpan_ke_env_langsung_berlaku(client, envp):
    cfg = client.app.state.cfg
    r = client.put('/api/admin/config', json=dict(aws_access_key_id=KEY_UI, aws_secret_access_key=SECRET_UI, maxmind_account_id=MM_ID,
                                                  maxmind_license_key=MM_KEY, blocklist_exclude='36.66.1.0/24, 198.51.100.7'), headers=X)
    assert r.status_code == 200, r.text
    bersih(r.text)
    f = config.read_dotenv(envp)
    assert (f['AWS_ACCESS_KEY_ID'], f['AWS_SECRET_ACCESS_KEY'], f['MAXMIND_ACCOUNT_ID'], f['MAXMIND_LICENSE_KEY']) == (KEY_UI, SECRET_UI, MM_ID, MM_KEY)
    assert f['S4_BLOCKLIST_EXCLUDE'] == '36.66.1.0/24, 198.51.100.7' and f['S4_JWT_SECRET'] == 'dibiarkan'
    assert (cfg.aws_access_key_id, cfg.aws_secret_access_key, cfg.maxmind_license_key) == (KEY_UI, SECRET_UI, MM_KEY)
    assert client.app.state.imports.creds.get()[0]['aws_access_key_id'] == KEY_UI
    assert client.app.state.auth.setting_get('config') is None                          # tidak lagi di basis data
    # rahasia kosong = tidak diubah; kolom biasa bisa diganti (baris contoh berkomentar diaktifkan di tempatnya)
    r = client.put('/api/admin/config', json=dict(aws_access_key_id=KEY_UI, aws_secret_access_key='', import_region='ap-southeast-1'), headers=X)
    assert r.status_code == 200, r.text
    assert (cfg.aws_secret_access_key, cfg.import_region) == (SECRET_UI, 'ap-southeast-1')
    assert '# [OPSIONAL] wilayah\nS4_IMPORT_REGION=ap-southeast-1\n' in open(envp).read()
    log = json.dumps(client.app.state.auth.audit_list(50), default=str)
    assert 'config.update' in log
    bersih(log)
    # hapus -> baris dinonaktifkan, nilai bawaan
    r = client.put('/api/admin/config', json=dict(clear=['aws_session_token', 'import_region', 'maxmind_account_id', 'maxmind_license_key']), headers=X)
    assert r.status_code == 200
    assert cfg.import_region == 'ap-southeast-3' and cfg.maxmind_license_key == ''
    t = open(envp).read()
    assert '# S4_IMPORT_REGION=\n' in t and MM_KEY not in t


def test_dibaca_lagi_saat_mulai_ulang(client, envp):
    assert client.put('/api/admin/config', json=dict(maxmind_account_id=MM_ID, maxmind_license_key=MM_KEY, blocklist_exclude_org='KOMINFO'), headers=X).status_code == 200
    c = config.load(env={}, dotenv=envp)
    assert (c.maxmind_account_id, c.maxmind_license_key, c.blocklist_exclude_org, c.aws_access_key_id) == (MM_ID, MM_KEY, 'KOMINFO', KEY_OK)


def test_variabel_lingkungan_mengalahkan_env_ditandai(client, monkeypatch):
    monkeypatch.setenv('AWS_ACCESS_KEY_ID', 'AKIADARILINGKUNGAN01')
    v = client.get('/api/admin/config', headers=X).json()
    assert v['aws']['aws_access_key_id']['source'] == 'environment' and v['file']['environment_override'] == ['AWS_ACCESS_KEY_ID']


@pytest.mark.parametrize('body', [
    dict(aws_access_key_id='akia-kecil', aws_secret_access_key=SECRET_UI),
    dict(aws_access_key_id=KEY_UI, aws_secret_access_key='pendek'),
    dict(aws_access_key_id='', clear=['aws_secret_access_key']),                       # pasangan tidak lengkap
    dict(import_region='jakarta'),
    dict(maxmind_account_id='abc', maxmind_license_key=MM_KEY),
    dict(maxmind_license_key=MM_KEY),
    dict(blocklist_exclude='10.0.0.0/8, bukan-ip'),
    dict(blocklist_exclude_org='(tidak-tertutup'),
])
def test_isian_tidak_sah_ditolak_tanpa_menulis(client, envp, body):
    before = open(envp).read()
    r = client.put('/api/admin/config', json=body, headers=X)
    assert r.status_code == 400 and r.json()['error']['code'] == 'invalid_config', r.text
    bersih(r.text)
    assert open(envp).read() == before and client.app.state.cfg.aws_access_key_id == KEY_OK


def test_env_tidak_bisa_ditulis(client, envp, monkeypatch):
    monkeypatch.setattr(envfile, 'writable', lambda p: False)   # (uji berjalan sebagai root: izin file tidak berlaku)
    before = open(envp).read()
    assert client.get('/api/admin/config', headers=X).json()['file']['writable'] is False
    r = client.put('/api/admin/config', json=dict(import_region='ap-southeast-1'), headers=X)
    assert r.status_code == 400 and r.json()['error']['code'] == 'env_not_writable' and open(envp).read() == before
    assert client.app.state.cfg.import_region == 'ap-southeast-3'


def test_pindahan_dari_basis_data_ke_env(cfg, envp, monkeypatch, s3):
    """Setelan lama (sebelum .env) di app_setting dipindah sekali ke .env saat server mulai, lalu dihapus dari basis data."""
    monkeypatch.setattr(auth, 'SCRYPT', (10, 8, 1))
    a = auth.Auth(cfg.auth_url)
    a.setting_set('config', dict(maxmind_account_id=MM_ID, maxmind_license_key=MM_KEY, aws_access_key_id=''), 'admin')
    a.setting_set('s3_watch', dict(url='s3://simpel4-backup/k8s-logs/', minutes=15, enabled=True), 'admin')
    a.setting_set('alerts', dict(channels=dict(discord=dict(enabled=True, webhook_url='https://discord.com/api/webhooks/1/abc')), lang='en'), 'admin')
    a.close()
    with TestClient(appmod.create_app(cfg, env_path=envp)) as tc:
        c = tc.app.state.cfg
        assert (c.maxmind_license_key, c.s3_watch, c.s3_watch_minutes, c.alert_discord, c.alert_lang) == (MM_KEY, 's3://simpel4-backup/k8s-logs/', 15, True, 'en')
        assert c.aws_access_key_id == KEY_OK                                            # nilai kosong lama tidak menimpa
        assert all(tc.app.state.auth.setting_get(k) is None for k in ('config', 's3_watch', 'alerts'))
    f = config.read_dotenv(envp)
    assert (f['MAXMIND_LICENSE_KEY'], f['S4_S3_WATCH_MINUTES'], f['S4_ALERT_DISCORD'], f['DISCORD_WEBHOOK_URL']) == \
        (MM_KEY, '15', 'true', 'https://discord.com/api/webhooks/1/abc')


def test_pengecualian_daftar_blokir_dari_layar(client):
    from monishield.interfaces.api import ips
    assert client.put('/api/admin/config', json=dict(blocklist_exclude='36.66.1.0/24', blocklist_exclude_org='TELKOM'), headers=X).status_code == 200
    c = client.app.state.cfg
    assert ips._excluded(c, '36.66.1.9', False, '') == 'list' and ips._excluded(c, '8.8.8.8', False, 'PT TELKOM INDONESIA') == 'org'
    assert ips._excluded(c, '8.8.8.8', False, 'OMBUDSMAN RI') is None


def test_uji_aws(client):
    r = client.post('/api/admin/config/test', json=dict(kind='aws'), headers=X)
    assert r.status_code == 200, r.text
    assert r.json() == dict(ok=True, kind='aws', target='s3://simpel4-backup/k8s-logs/', source='lingkungan')
    assert client.put('/api/admin/config', json=dict(aws_access_key_id='AKIASALAHSALAHSALAH1', aws_secret_access_key=SECRET_UI), headers=X).status_code == 200
    r = client.post('/api/admin/config/test', json=dict(kind='aws'), headers=X)
    assert r.status_code == 502 and r.json()['error']['code'] == 's3_denied'
    bersih(r.text)
    assert client.post('/api/admin/config/test', json=dict(kind='lain'), headers=X).status_code == 400


def test_uji_maxmind(client, monkeypatch):
    r = client.post('/api/admin/config/test', json=dict(kind='maxmind'), headers=X)
    assert r.status_code == 400 and r.json()['error']['code'] == 'maxmind_missing'
    assert client.put('/api/admin/config', json=dict(maxmind_account_id=MM_ID, maxmind_license_key=MM_KEY), headers=X).status_code == 200
    seen = []

    class Opener:
        def __init__(self, code): self.code = code
        def open(self, req, timeout=None):
            seen.append((req.get_method(), req.full_url, req.get_header('Authorization')))
            raise urllib.error.HTTPError(req.full_url, self.code, 'x', {}, None)
    for code, status, err in ((302, 200, None), (401, 502, 'maxmind_denied'), (500, 502, 'maxmind_error')):
        monkeypatch.setattr(config_api.urllib.request, 'build_opener', lambda *a, c=code: Opener(c))
        r = client.post('/api/admin/config/test', json=dict(kind='maxmind'), headers=X)
        assert r.status_code == status, (code, r.text)
        if err: assert r.json()['error']['code'] == err
        bersih(r.text)
    assert seen[0][0] == 'HEAD' and seen[0][1] == config.Config().url_maxmind.format('GeoLite2-City-CSV') and seen[0][2].startswith('Basic ')
    client.app.state.cfg.offline = True
    assert client.post('/api/admin/config/test', json=dict(kind='maxmind'), headers=X).json()['error']['code'] == 'offline'


def test_tanpa_sesi_ditolak(cfg, envp, monkeypatch, s3):
    monkeypatch.setattr(auth, 'SCRYPT', (10, 8, 1))
    with TestClient(appmod.create_app(cfg, env_path=envp)) as tc:
        assert tc.get('/api/admin/config', headers=X).status_code == 401
        assert tc.put('/api/admin/config', json={}, headers=X).status_code == 401
        assert tc.post('/api/admin/config/test', json=dict(kind='aws'), headers=X).status_code == 401


def test_alamat_dan_batas_dari_env():
    """URL sumber unduhan, API Telegram, dan batas yang dulu tertulis di kode kini dari .env."""
    c = config.load(env={'S4_URL_IP2ASN': 'https://cermin.kantor.go.id/ip2asn-v4.tsv.gz', 'S4_TELEGRAM_API': 'https://tg-proxy.kantor.go.id',
                         'S4_URL_MAXMIND': 'https://mm.kantor.go.id/{}.zip', 'S4_GEO_MAX_AGE_DAYS': '14', 'S4_UPLOAD_SESSION_HOURS': '2'}, dotenv=False)
    assert (c.url_ip2asn, c.telegram_api, c.url_maxmind, c.geo_max_age_days, c.upload_session_hours) == \
        ('https://cermin.kantor.go.id/ip2asn-v4.tsv.gz', 'https://tg-proxy.kantor.go.id', 'https://mm.kantor.go.id/{}.zip', 14, 2)
    from monishield.application import alerts
    assert alerts.load(c)['channels']['telegram']['api'] == 'https://tg-proxy.kantor.go.id'
    for env in ({'S4_GEO_MAX_AGE_DAYS': '60'}, {'S4_URL_MAXMIND': 'https://x/tanpa-edisi'}, {'S4_URL_LAND': 'ftp://x'}):
        with pytest.raises(SystemExit): config.load(env=env, dotenv=False)
    assert settings.GROUPS['alerts'][0] == 'alert_telegram'
