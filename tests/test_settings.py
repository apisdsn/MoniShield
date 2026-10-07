"""Halaman Konfigurasi (permintaan pemilik 2026-10-07): kredensial AWS/MaxMind + pengecualian daftar blokir diisi dari layar,
disimpan di basis data akun, ditimpakan ke konfigurasi server tanpa mulai ulang. Rahasia tidak pernah keluar lagi."""
import dataclasses, json, urllib.error

import pytest
from fastapi.testclient import TestClient

import logs_mini
from s3_tiruan import KEY_OK, S3Tiruan
from monishield import auth, config, importer, settings
from monishield.api import app as appmod, config_api
from conftest import JWT_SECRET

X = {'X-Requested-With': 'uji'}
PW, PW2 = 'sandi-admin-pertama', 'sandi-admin-sesudah-diganti'
SECRET_ENV = 'rahasiaEnvUjiYangTidakBolehBocor0001'
KEY_UI, SECRET_UI = 'AKIALAYARUJI00000002', 'rahasiaLayarUjiYangTidakBolehBocor02'
MM_ID, MM_KEY = '123456', 'LisensiMaxMindRahasia_0001'


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


def start(c):
    tc = TestClient(appmod.create_app(c))
    tc.__enter__()
    return tc


def login(tc, pw):
    assert tc.post('/api/auth/login', json=dict(username='admin', password=pw), headers=X).status_code == 200


@pytest.fixture
def client(cfg, monkeypatch, s3):
    monkeypatch.setattr(auth, 'SCRYPT', (10, 8, 1))
    tc = start(cfg)
    login(tc, PW)
    assert tc.post('/api/me/password', json=dict(old_password=PW, new_password=PW2), headers=X).status_code == 200
    yield tc
    tc.__exit__(None, None, None)


def bersih(text):
    for s in (SECRET_ENV, SECRET_UI, MM_KEY, KEY_UI, KEY_OK): assert s not in text


def test_lihat_awal_dari_env_tanpa_rahasia(client):
    r = client.get('/api/admin/config', headers=X)
    assert r.status_code == 200
    v = r.json()
    a = v['aws']
    assert a['aws_access_key_id'] == dict(set=True, source='env', masked=f'{KEY_OK[:4]}…{KEY_OK[-4:]}')
    assert a['aws_secret_access_key'] == dict(set=True, source='env')
    assert a['aws_session_token'] == dict(set=False, source=None)
    assert a['import_region'] == dict(value='ap-southeast-3', source='env')
    assert v['maxmind']['maxmind_license_key'] == dict(set=False, source=None)
    assert v['blocklist']['blocklist_exclude_org']['value'] == 'OMBUDSMAN'
    assert v['server']['jwt_secret'] is True and v['server']['job_token'] is False
    assert v['server']['import_buckets'] == {'simpel4-backup': ['k8s-logs/']}
    bersih(r.text)


def test_simpan_langsung_berlaku_dan_kembali_ke_env(client):
    app = client.app
    r = client.put('/api/admin/config', json=dict(aws_access_key_id=KEY_UI, aws_secret_access_key=SECRET_UI, maxmind_account_id=MM_ID,
                                                  maxmind_license_key=MM_KEY, blocklist_exclude='203.0.113.0/24, 198.51.100.7'), headers=X)
    assert r.status_code == 200, r.text
    bersih(r.text)
    v = r.json()
    assert v['aws']['aws_access_key_id']['source'] == 'layar' and v['aws']['aws_secret_access_key'] == dict(set=True, source='layar')
    assert v['maxmind']['maxmind_account_id']['source'] == 'layar'
    cfg = app.state.cfg
    assert (cfg.aws_access_key_id, cfg.aws_secret_access_key, cfg.maxmind_license_key) == (KEY_UI, SECRET_UI, MM_KEY)
    assert cfg.blocklist_exclude == '203.0.113.0/24, 198.51.100.7'
    assert app.state.cfg_env.aws_access_key_id == KEY_OK                    # nilai .env asli tetap tersimpan
    st = client.get('/api/admin/import', headers=X).json()['credentials']
    assert (st['source'], st['saved']) == ('layar', True)
    assert app.state.imports.creds.get()[0]['aws_access_key_id'] == KEY_UI

    # rahasia kosong = tidak diubah; kolom biasa bisa diganti
    r = client.put('/api/admin/config', json=dict(aws_access_key_id=KEY_UI, aws_secret_access_key='', import_region='ap-southeast-1'), headers=X)
    assert r.status_code == 200, r.text
    assert (cfg.aws_secret_access_key, cfg.import_region) == (SECRET_UI, 'ap-southeast-1')

    # audit hanya nama kelompok
    log = json.dumps(app.state.auth.audit_list(50), default=str)
    assert 'config.update' in log
    bersih(log)

    # hapus -> kembali ke .env
    r = client.put('/api/admin/config', json=dict(clear=['aws_access_key_id', 'aws_secret_access_key', 'import_region']), headers=X)
    assert r.status_code == 200
    assert (cfg.aws_access_key_id, cfg.aws_secret_access_key, cfg.import_region) == (KEY_OK, SECRET_ENV, 'ap-southeast-3')
    assert r.json()['aws']['aws_access_key_id']['source'] == 'env'
    assert client.get('/api/admin/import', headers=X).json()['credentials']['source'] == 'lingkungan'


def test_tersimpan_berlaku_setelah_mulai_ulang_dan_di_cli(client, cfg):
    assert client.put('/api/admin/config', json=dict(maxmind_account_id=MM_ID, maxmind_license_key=MM_KEY), headers=X).status_code == 200
    client.__exit__(None, None, None)
    tc = start(cfg)
    try: assert tc.app.state.cfg.maxmind_license_key == MM_KEY and cfg.maxmind_license_key == ''   # objek pemanggil tidak diubah
    finally: tc.__exit__(None, None, None)
    c2 = settings.for_cli(cfg)
    assert (c2.maxmind_account_id, c2.maxmind_license_key, cfg.maxmind_license_key) == (MM_ID, MM_KEY, '')
    client.__enter__()


@pytest.mark.parametrize('body', [
    dict(aws_access_key_id='akia-kecil', aws_secret_access_key=SECRET_UI),
    dict(aws_access_key_id=KEY_UI),                                         # pasangan tidak lengkap
    dict(aws_access_key_id=KEY_UI, aws_secret_access_key='pendek'),
    dict(import_region='jakarta'),
    dict(maxmind_account_id='abc', maxmind_license_key=MM_KEY),
    dict(maxmind_license_key=MM_KEY),
    dict(blocklist_exclude='10.0.0.0/8, bukan-ip'),
    dict(blocklist_exclude_org='(tidak-tertutup'),
])
def test_isian_tidak_sah_ditolak_tanpa_menyimpan(client, body):
    r = client.put('/api/admin/config', json=body, headers=X)
    assert r.status_code == 400 and r.json()['error']['code'] == 'invalid_config'
    bersih(r.text)
    assert client.app.state.auth.setting_get('config') is None
    assert client.app.state.cfg.aws_access_key_id == KEY_OK


def test_pengecualian_daftar_blokir_dari_layar(client):
    from monishield.api import ips
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
    assert seen[0][0] == 'HEAD' and 'GeoLite2-City-CSV' in seen[0][1] and seen[0][2].startswith('Basic ')
    client.app.state.cfg.offline = True
    assert client.post('/api/admin/config/test', json=dict(kind='maxmind'), headers=X).json()['error']['code'] == 'offline'


def test_tanpa_sesi_ditolak(cfg, monkeypatch, s3):
    monkeypatch.setattr(auth, 'SCRYPT', (10, 8, 1))
    with TestClient(appmod.create_app(cfg)) as tc:
        assert tc.get('/api/admin/config', headers=X).status_code == 401
        assert tc.put('/api/admin/config', json={}, headers=X).status_code == 401
        assert tc.post('/api/admin/config/test', json=dict(kind='aws'), headers=X).status_code == 401
