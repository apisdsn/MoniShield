"""Impor dari awalan S3 (TRD §3.8, §9.6) terhadap S3 TIRUAN lokal: tanpa AWS, tanpa internet."""
import dataclasses, gzip, os, time

import pytest
from fastapi.testclient import TestClient

import logs_mini
from s3_tiruan import KEY_OK, S3Tiruan
from simpel4 import auth, config, db, importer, ingest
from simpel4.api import app as appmod
from conftest import JWT_SECRET

D = '2026-01-05'
PRE = f'k8s-logs/{D}/'
SECRET = 'rahasiaTiruanUjiYangTidakBolehBocor0001'
URL = f's3://simpel4-backup/{PRE}'
X = {'X-Requested-With': 'uji'}
TOKEN = 'token-mesin-untuk-uji-impor'
PW, PW2 = 'sandi-admin-pertama', 'sandi-admin-sesudah-diganti'


def obj(service, pod, ns='ombudsman', ext='.log', folder=D):
    return f'k8s-logs/{folder}/{ns}/{service}/log_{service}_{pod}_{folder}-00-00{ext}'


APPS = logs_mini.lines('om-be-appsmanager').encode()
ISI = {
    obj('om-be-appsmanager', 'pod-a'): APPS,
    obj('om-be-appsmanager', 'pod-a', ext='.log.gz'): gzip.compress(APPS),          # berpasangan: hanya .log yang diambil
    obj('om-fe-inhouse', 'pod-f', ns='ombudsman', ext='.log.gz'): gzip.compress(logs_mini.lines('om-fe-inhouse').encode()),   # .gz saja: diambil
    f'{PRE}.DS_Store': b'x',                                                          # bukan file log
    f'{PRE}catatan.txt': b'bukan log',
    f'{PRE}lepas.log': b'kurang dari 3 komponen path',
}


@pytest.fixture
def s3(monkeypatch):
    t = S3Tiruan({'simpel4-backup': dict(ISI), 'bucket-lain': dict(ISI)})
    monkeypatch.setattr(importer, 'ENDPOINT', t.url)
    yield t
    t.close()


@pytest.fixture
def cfg(tmp_path):
    return dataclasses.replace(config.Config(), log_dir=logs_mini.build(tmp_path / 'logs'), data_dir=str(tmp_path / 'data'), state_dir=str(tmp_path / 'state'),
                               inbox_dir=str(tmp_path / 'inbox'), cache_dir=str(tmp_path / 'cache'), offline=True, ingest_on_start=False, cookie_secure=False,
                               admin_user='admin', admin_password=PW, job_token=TOKEN, jwt_secret=JWT_SECRET,
                               import_buckets={'simpel4-backup': ['k8s-logs/']}, aws_access_key_id=KEY_OK, aws_secret_access_key=SECRET)


def kosong(cfg): return not os.path.exists(cfg.inbox_dir) or not os.listdir(cfg.inbox_dir)


def gagal(cfg, url, code, **kw):
    with pytest.raises(importer.ImportFail) as e: importer.run(cfg, url, importer.Credentials(cfg), **kw)
    assert e.value.code == code, (e.value.code, e.value.message)
    assert e.value.message and SECRET not in e.value.message
    return e.value


# ------------------------------------------------------------------ tautan: ditolak sebelum menghubungi S3
@pytest.mark.parametrize('url, code', [
    ('https://simpel4-backup.s3.amazonaws.com/k8s-logs/2026-01-05/', 'invalid_url'),
    ('s3://bucket-lain/k8s-logs/2026-01-05/', 'bucket_not_allowed'),
    ('s3://simpel4-backup/lain/2026-01-05/', 'prefix_not_allowed'),
    ('s3://simpel4-backup/k8s-logs/bukan-tanggal/', 'invalid_date'),
    ('s3://simpel4-backup/k8s-logs/2026-02-30/', 'invalid_date'),
    ('s3://simpel4-backup/k8s-logs/../2026-01-05/', 'invalid_url'),
    ('s3://simpel4-backup/k8s-logs//2026-01-05/', 'invalid_url'),
    ('s3://simpel4-backup/k8s-logs/\x00/2026-01-05/', 'invalid_url'),
    ('s3://SIMPEL4-BACKUP/k8s-logs/2026-01-05/', 'invalid_url'),
])
def test_tautan_ditolak_tanpa_menghubungi_s3(cfg, s3, url, code):
    gagal(cfg, url, code)
    assert s3.log == [] and kosong(cfg)


def test_impor_mati_tanpa_daftar_izin(cfg, s3):
    e = gagal(dataclasses.replace(cfg, import_buckets={}), URL, 'import_disabled')
    assert 'tidak diaktifkan' in e.message and s3.log == []


def test_tanpa_kredensial_pesan_cara_memberi(cfg, s3):
    e = gagal(dataclasses.replace(cfg, aws_access_key_id='', aws_secret_access_key=''), URL, 'no_credentials')
    assert 'AWS_ACCESS_KEY_ID' in e.message and 'tempel' in e.message and s3.log == [] and kosong(cfg)


def test_kredensial_ditolak_s3(cfg, s3):
    c = dataclasses.replace(cfg, aws_access_key_id='AKIASALAHSALAHSALAH1')
    gagal(c, URL, 's3_denied')
    assert kosong(cfg)


def test_awalan_kosong(cfg, s3):
    gagal(cfg, 's3://simpel4-backup/k8s-logs/2026-01-09/', 'empty_prefix')


# ------------------------------------------------------------------ objek
def test_kunci_berisi_dua_titik_membatalkan_impor(cfg, s3):
    s3.buckets['simpel4-backup'][f'{PRE}ombudsman/../../x/log_a_b_{D}.log'] = b'x'
    gagal(cfg, URL, 'unsafe_key')
    assert kosong(cfg) and s3.gets() == []


@pytest.mark.parametrize('ubah, code', [(dict(import_max_objects=1), 'too_many_objects'), (dict(import_max_object_mb=0), 'object_too_large'),
                                        (dict(import_max_total_mb=0), 'too_large')])
def test_melebihi_batas(cfg, s3, ubah, code):
    gagal(dataclasses.replace(cfg, **ubah), URL, code)
    assert kosong(cfg) and s3.gets() == []


def test_mode_coba_tidak_menulis_apa_pun(cfg, s3):
    r = importer.run(cfg, URL, importer.Credentials(cfg), dry_run=True)
    aksi = {o['rel']: (o['action'], o['reason']) for o in r['objects']}
    assert aksi[obj('om-be-appsmanager', 'pod-a')[len(PRE):]] == ('ambil', '')
    assert aksi[obj('om-be-appsmanager', 'pod-a', ext='.log.gz')[len(PRE):]] == ('lewati', '.gz berpasangan dengan .log')
    assert aksi[obj('om-fe-inhouse', 'pod-f', ext='.log.gz')[len(PRE):]] == ('ambil', '')
    assert aksi['.DS_Store'] == aksi['catatan.txt'] == aksi['lepas.log'] == ('lewati', 'bukan file log')
    assert (r['take'], r['skipped'], r['downloaded'], r['credentials']) == (2, 4, 0, 'lingkungan')
    assert kosong(cfg) and s3.gets() == [] and not os.path.exists(os.path.join(cfg.data_dir, 'tmp'))


def test_impor_lalu_ingest_dan_ulang_tanpa_unduh(cfg, s3):
    r = importer.run(cfg, URL, importer.Credentials(cfg))
    assert (r['take'], r['downloaded'], r['downloaded_bytes']) == (2, 2, len(APPS) + len(ISI[obj('om-fe-inhouse', 'pod-f', ext='.log.gz')]))
    got = sorted(p.split('/', 2)[2] for p in s3.gets())
    assert got == sorted([obj('om-be-appsmanager', 'pod-a'), obj('om-fe-inhouse', 'pod-f', ext='.log.gz')])      # .gz berpasangan tidak diunduh
    folder = os.path.join(cfg.inbox_dir, D)
    assert open(os.path.join(folder, 'ombudsman', 'om-be-appsmanager', f'log_om-be-appsmanager_pod-a_{D}-00-00.log'), 'rb').read() == APPS
    assert os.path.isfile(os.path.join(folder, importer.MANIFEST)) and os.listdir(os.path.join(cfg.data_dir, 'tmp')) == []
    con = db.open(cfg.db_path)
    try:
        g = ingest.run(cfg, con, folder=D, workers=0)
        assert g['files_failed'] == 0 and g['files_changed'] == 2
        rows = con.execute('SELECT service, lines FROM ingest_file WHERE folder = ? ORDER BY service', [D]).fetchall()
        assert [x[0] for x in rows] == ['om-be-appsmanager', 'om-fe-inhouse'] and all(n > 0 for _, n in rows)
        # tautan sama lagi: 0 objek diunduh, ingest tidak berubah, tidak ada data ganda
        n0 = len(s3.gets())
        r2 = importer.run(cfg, URL, importer.Credentials(cfg))
        assert (r2['take'], r2['downloaded']) == (0, 0) and len(s3.gets()) == n0
        assert {o['reason'] for o in r2['objects'] if o['action'] == 'lewati'} >= {'sama dengan unduhan sebelumnya'}
        assert ingest.run(cfg, con, folder=D, workers=0)['files_changed'] == 0
        assert con.execute('SELECT count(*) FROM ingest_file WHERE folder = ?', [D]).fetchone()[0] == 2
        # objek di S3 berubah: hanya objek itu yang diunduh ulang
        s3.buckets['simpel4-backup'][obj('om-be-appsmanager', 'pod-a')] = APPS + APPS
        r3 = importer.run(cfg, URL, importer.Credentials(cfg))
        assert (r3['take'], r3['downloaded']) == (1, 1)
    finally:
        con.close()


def test_folder_yang_sama_di_folder_log_lokal_diberi_peringatan(cfg, s3):
    s3.buckets['simpel4-backup'][obj('om-be-appsmanager', 'pod-z', folder='2026-01-01')] = APPS
    r = importer.run(cfg, 's3://simpel4-backup/k8s-logs/2026-01-01/', importer.Credentials(cfg), dry_run=True)
    assert any('folder log lokal' in w for w in r['warnings'])


# ------------------------------------------------------------------ kredensial
def test_kredensial_sementara_di_memori(cfg):
    c = importer.Credentials(dataclasses.replace(cfg, aws_access_key_id='', aws_secret_access_key=''))
    assert c.get() == (None, None) and c.status()['available'] is False
    with pytest.raises(importer.ImportFail): c.set('bukan kunci', 'x')
    c.set('AKIATEMPELUJI0000002', SECRET, 'token-sesi')
    kw, src = c.get()
    assert src == 'tempel' and kw['aws_session_token'] == 'token-sesi'
    assert SECRET not in repr(c) and SECRET not in str(c.status()) and c.status()['pasted_at']
    c.clear()
    assert c.get() == (None, None)
    # urutan: tempel lalu lingkungan
    c2 = importer.Credentials(cfg)
    assert c2.get()[1] == 'lingkungan'
    c2.set('AKIATEMPELUJI0000002', SECRET)
    assert c2.get()[1] == 'tempel'


# ------------------------------------------------------------------ API
@pytest.fixture
def client(cfg, auth_url, monkeypatch, s3):
    monkeypatch.setattr(auth, 'SCRYPT', (10, 8, 1))
    c = dataclasses.replace(cfg, auth_database_url=auth_url)
    con = db.open(c.db_path); ingest.run(c, con, workers=0); con.close()
    with TestClient(appmod.create_app(c)) as tc:
        assert tc.post('/api/auth/login', json=dict(username='admin', password=PW), headers=X).status_code == 200
        assert tc.post('/api/me/password', json=dict(old_password=PW, new_password=PW2), headers=X).status_code == 200
        yield tc


def tunggu(tc, job, h=X):
    for _ in range(300):
        j = tc.get(f'/api/admin/import/{job}', headers=h).json()
        if not j['running'] and j['status'] != 'berjalan' and (j['result'] or j['status'] == 'gagal'): return j
        time.sleep(0.05)
    raise AssertionError('impor tidak selesai')


def test_api_coba_lalu_impor_lewat_token_mesin(client, cfg):
    r = client.post('/api/admin/import', json=dict(url=URL, dry_run=True), headers=X)
    assert r.status_code == 202
    j = tunggu(client, r.json()['job_id'])
    assert (j['status'], j['files'], j['skipped'], j['result']['downloaded']) == ('coba', 2, 4, 0) and kosong(cfg)
    mesin = TestClient(client.app)
    h = {**X, 'Authorization': f'Bearer {TOKEN}'}
    r = mesin.post('/api/admin/import', json=dict(url=URL), headers=h)
    assert r.status_code == 202
    j = tunggu(mesin, r.json()['job_id'], h)
    assert (j['status'], j['files'], j['folder'], j['requested_by']) == ('selesai', 2, D, '(token mesin)'), j
    assert j['result']['ingest']['files_changed'] == 2 and 'ingest #' in j['message']
    assert D in [f['folder'] for f in client.get('/api/meta').json()['folders']]               # folder muncul di dashboard
    ov = client.get('/api/admin/import').json()
    assert [x['status'] for x in ov['jobs']][:2] == ['selesai', 'coba'] and ov['enabled'] and ov['allowed'] == ['s3://simpel4-backup/k8s-logs/<YYYY-MM-DD>/']
    assert {'import.start'} <= {x['action'] for x in client.get('/api/admin/audit').json()['rows']}


@pytest.mark.parametrize('url, code', [('s3://bucket-lain/k8s-logs/2026-01-05/', 'bucket_not_allowed'), ('s3://simpel4-backup/k8s-logs/x/', 'invalid_date'), ('', 'invalid_url')])
def test_api_tautan_ditolak_400(client, s3, url, code):
    r = client.post('/api/admin/import', json=dict(url=url), headers=X)
    assert (r.status_code, r.json()['error']['code']) == (400, code) and s3.log == []
    assert client.get('/api/admin/import').json()['jobs'] == []


def test_api_kredensial_sementara(client, cfg, auth_url, s3):
    h = {**X, 'Authorization': f'Bearer {TOKEN}'}
    mesin = TestClient(client.app)
    assert mesin.post('/api/admin/import/credentials', json=dict(access_key_id=KEY_OK, secret_access_key=SECRET), headers=h).status_code == 401
    assert mesin.delete('/api/admin/import/credentials', headers=h).status_code == 401
    r = client.post('/api/admin/import/credentials', json=dict(access_key_id='AKIATEMPELUJI0000002', secret_access_key=SECRET), headers=X)
    assert r.status_code == 200 and r.json()['credentials']['source'] == 'tempel' and SECRET not in r.text and 'AKIATEMPEL' not in r.text
    meta = client.get('/api/meta').json()['imports']
    assert meta == dict(enabled=True, credentials=dict(available=True, source='tempel'))
    # kunci tempel tidak dikenal S3 tiruan -> impor gagal dengan sebab; kotak masuk tetap kosong
    j = tunggu(client, client.post('/api/admin/import', json=dict(url=URL), headers=X).json()['job_id'])
    assert j['status'] == 'gagal' and 'S3 menolak' in j['message'] and kosong(cfg)
    assert client.delete('/api/admin/import/credentials', headers=X).json()['credentials']['source'] == 'lingkungan'
    # rahasia tidak ada di respons, audit, maupun basis data akun
    semua = client.get('/api/admin/audit?limit=500').text + client.get('/api/admin/import').text + client.get(f'/api/admin/import/{j["job_id"]}').text
    assert SECRET not in semua and KEY_OK not in semua and 'AKIATEMPEL' not in semua
    assert {'import.credentials.set', 'import.credentials.clear'} <= {x['action'] for x in client.get('/api/admin/audit?limit=500').json()['rows']}
    if auth_url.startswith('sqlite:///'):
        isi = open(auth_url[len('sqlite:///'):], 'rb').read()
        assert SECRET.encode() not in isi and b'AKIATEMPEL' not in isi


def test_kredensial_tempel_hilang_setelah_mulai_ulang(cfg, auth_url, monkeypatch, s3):
    monkeypatch.setattr(auth, 'SCRYPT', (10, 8, 1))
    c = dataclasses.replace(cfg, auth_database_url=auth_url, aws_access_key_id='', aws_secret_access_key='')
    con = db.open(c.db_path); con.close()
    for i in range(2):
        with TestClient(appmod.create_app(c)) as tc:
            assert tc.post('/api/auth/login', json=dict(username='admin', password=PW if i == 0 else PW2), headers=X).status_code == 200
            if i == 0:
                assert tc.post('/api/me/password', json=dict(old_password=PW, new_password=PW2), headers=X).status_code == 200
                assert tc.post('/api/admin/import/credentials', json=dict(access_key_id=KEY_OK, secret_access_key=SECRET), headers=X).status_code == 200
                assert tc.get('/api/admin/import').json()['credentials']['available'] is True
            else:
                assert tc.get('/api/admin/import').json()['credentials']['available'] is False
                r = tc.post('/api/admin/import', json=dict(url=URL), headers=X)
                assert (r.status_code, r.json()['error']['code']) == (400, 'no_credentials')


def test_user_biasa_403(client):
    assert client.post('/api/admin/users', json=dict(username='rina', display_name='Rina', role='user', password='sandi-awal-rina-123'), headers=X).status_code == 201
    tc = TestClient(client.app)
    assert tc.post('/api/auth/login', json=dict(username='rina', password='sandi-awal-rina-123'), headers=X).status_code == 200
    assert tc.post('/api/me/password', json=dict(old_password='sandi-awal-rina-123', new_password='sandi-baru-rina-456'), headers=X).status_code == 200
    for m, p in (('get', '/api/admin/import'), ('post', '/api/admin/import'), ('get', '/api/admin/import/1'), ('post', '/api/admin/import/credentials'),
                 ('delete', '/api/admin/import/credentials')):
        r = getattr(tc, m)(p, headers=X) if m in ('get', 'delete') else getattr(tc, m)(p, json={}, headers=X)
        assert r.status_code == 403, p


def test_tanpa_boto3_ditolak_dengan_cara_memasang(client, monkeypatch):
    """Laporan pemilik 2026-10-07: impor gagal "No module named 'botocore'" (paket s3 belum terpasang). Kini ditolak di
    depan dengan pesan cara memasang, tanpa membuat job gagal; layar membaca `library` untuk menonaktifkan impor."""
    monkeypatch.setattr(importer, 'library_ok', lambda: False)
    sebelum = len(client.get('/api/admin/import').json()['jobs'])
    r = client.post('/api/admin/import', json=dict(url=URL), headers=X)
    assert r.status_code == 400 and r.json()['error']['code'] == 'no_s3_library' and 'pip install' in r.json()['error']['message']
    ov = client.get('/api/admin/import').json()
    assert ov['library'] is False and len(ov['jobs']) == sebelum
    monkeypatch.undo()
    assert importer.library_ok() is True and client.get('/api/admin/import').json()['library'] is True
