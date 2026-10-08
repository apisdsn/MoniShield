"""Import from an S3 prefix (TRD §3.8, §9.6) against a local FAKE S3: no AWS, no internet."""
import dataclasses, gzip, json, os, time

import pytest
from fastapi.testclient import TestClient

import logs_mini
from s3_tiruan import KEY_OK, S3Tiruan
from monishield.domain import accounts
from monishield.infrastructure import config, db, envfile, importer, ingest
from monishield.interfaces.api import app as appmod
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
    obj('om-be-appsmanager', 'pod-a', ext='.log.gz'): gzip.compress(APPS),          # paired: only the .log is fetched
    obj('om-fe-inhouse', 'pod-f', ns='ombudsman', ext='.log.gz'): gzip.compress(logs_mini.lines('om-fe-inhouse').encode()),   # .gz only: fetched
    f'{PRE}.DS_Store': b'x',                                                          # not a log file
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


# ------------------------------------------------------------------ links: rejected before contacting S3
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
    assert 'not enabled' in e.message and s3.log == []


def test_tanpa_kredensial_pesan_cara_memberi(cfg, s3):
    e = gagal(dataclasses.replace(cfg, aws_access_key_id='', aws_secret_access_key=''), URL, 'no_credentials')
    assert 'AWS_ACCESS_KEY_ID' in e.message and 'paste' in e.message and s3.log == [] and kosong(cfg)


def test_kredensial_ditolak_s3(cfg, s3):
    c = dataclasses.replace(cfg, aws_access_key_id='AKIASALAHSALAHSALAH1')
    gagal(c, URL, 's3_denied')
    assert kosong(cfg)


def test_awalan_kosong(cfg, s3):
    gagal(cfg, 's3://simpel4-backup/k8s-logs/2026-01-09/', 'empty_prefix')


# ------------------------------------------------------------------ objects
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
    assert aksi[obj('om-be-appsmanager', 'pod-a')[len(PRE):]] == ('fetch', '')
    assert aksi[obj('om-be-appsmanager', 'pod-a', ext='.log.gz')[len(PRE):]] == ('skip', '.gz paired with .log')
    assert aksi[obj('om-fe-inhouse', 'pod-f', ext='.log.gz')[len(PRE):]] == ('fetch', '')
    assert aksi['.DS_Store'] == aksi['catatan.txt'] == aksi['lepas.log'] == ('skip', 'not a log file')
    assert (r['take'], r['skipped'], r['downloaded'], r['credentials']) == (2, 4, 0, 'environment')
    assert kosong(cfg) and s3.gets() == [] and not os.path.exists(os.path.join(cfg.data_dir, 'tmp'))


def test_impor_lalu_ingest_dan_ulang_tanpa_unduh(cfg, s3):
    r = importer.run(cfg, URL, importer.Credentials(cfg))
    assert (r['take'], r['downloaded'], r['downloaded_bytes']) == (2, 2, len(APPS) + len(ISI[obj('om-fe-inhouse', 'pod-f', ext='.log.gz')]))
    got = sorted(p.split('/', 2)[2] for p in s3.gets())
    assert got == sorted([obj('om-be-appsmanager', 'pod-a'), obj('om-fe-inhouse', 'pod-f', ext='.log.gz')])      # paired .gz is not downloaded
    folder = os.path.join(cfg.inbox_dir, D)
    assert open(os.path.join(folder, 'ombudsman', 'om-be-appsmanager', f'log_om-be-appsmanager_pod-a_{D}-00-00.log'), 'rb').read() == APPS
    assert os.path.isfile(os.path.join(folder, importer.MANIFEST)) and os.listdir(os.path.join(cfg.data_dir, 'tmp')) == []
    con = db.open(cfg.db_path)
    try:
        g = ingest.run(cfg, con, folder=D, workers=0)
        assert g['files_failed'] == 0 and g['files_changed'] == 2
        rows = con.execute('SELECT service, lines FROM ingest_file WHERE folder = ? ORDER BY service', [D]).fetchall()
        assert [x[0] for x in rows] == ['om-be-appsmanager', 'om-fe-inhouse'] and all(n > 0 for _, n in rows)
        # same link again: 0 objects downloaded, ingest unchanged, no duplicate data
        n0 = len(s3.gets())
        r2 = importer.run(cfg, URL, importer.Credentials(cfg))
        assert (r2['take'], r2['downloaded']) == (0, 0) and len(s3.gets()) == n0
        assert {o['reason'] for o in r2['objects'] if o['action'] == 'skip'} >= {'same as the previous download'}
        assert ingest.run(cfg, con, folder=D, workers=0)['files_changed'] == 0
        assert con.execute('SELECT count(*) FROM ingest_file WHERE folder = ?', [D]).fetchone()[0] == 2
        # object in S3 changed: only that object is downloaded again
        s3.buckets['simpel4-backup'][obj('om-be-appsmanager', 'pod-a')] = APPS + APPS
        r3 = importer.run(cfg, URL, importer.Credentials(cfg))
        assert (r3['take'], r3['downloaded']) == (1, 1)
    finally:
        con.close()


def test_folder_yang_sama_di_folder_log_lokal_diberi_peringatan(cfg, s3):
    s3.buckets['simpel4-backup'][obj('om-be-appsmanager', 'pod-z', folder='2026-01-01')] = APPS
    r = importer.run(cfg, 's3://simpel4-backup/k8s-logs/2026-01-01/', importer.Credentials(cfg), dry_run=True)
    assert any('local log folder' in w for w in r['warnings'])


# ------------------------------------------------------------------ credentials
def test_kredensial_sementara_di_memori(cfg):
    c = importer.Credentials(dataclasses.replace(cfg, aws_access_key_id='', aws_secret_access_key=''))
    assert c.get() == (None, None) and c.status()['available'] is False
    with pytest.raises(importer.ImportFail): c.set('bukan kunci', 'x')
    c.set('AKIATEMPELUJI0000002', SECRET, 'token-sesi')
    kw, src = c.get()
    assert src == 'pasted' and kw['aws_session_token'] == 'token-sesi'
    assert SECRET not in repr(c) and SECRET not in str(c.status()) and c.status()['pasted_at']
    c.clear()
    assert c.get() == (None, None)
    # order: pasted then environment
    c2 = importer.Credentials(cfg)
    assert c2.get()[1] == 'environment'
    c2.set('AKIATEMPELUJI0000002', SECRET)
    assert c2.get()[1] == 'pasted'


# ------------------------------------------------------------------ API
@pytest.fixture
def client(cfg, auth_url, monkeypatch, s3):
    monkeypatch.setattr(accounts, 'SCRYPT', (10, 8, 1))
    c = dataclasses.replace(cfg, auth_database_url=auth_url)
    con = db.open(c.db_path); ingest.run(c, con, workers=0); con.close()
    with TestClient(appmod.create_app(c)) as tc:
        assert tc.post('/api/auth/login', json=dict(username='admin', password=PW), headers=X).status_code == 200
        assert tc.post('/api/me/password', json=dict(old_password=PW, new_password=PW2), headers=X).status_code == 200
        yield tc


def tunggu(tc, job, h=X):
    for _ in range(300):
        j = tc.get(f'/api/admin/import/{job}', headers=h).json()
        if not j['running'] and j['status'] != 'running' and (j['result'] or j['status'] == 'failed'): return j
        time.sleep(0.05)
    raise AssertionError('impor tidak selesai')


def test_api_coba_lalu_impor_lewat_token_mesin(client, cfg):
    r = client.post('/api/admin/import', json=dict(url=URL, dry_run=True), headers=X)
    assert r.status_code == 202
    j = tunggu(client, r.json()['job_id'])
    assert (j['status'], j['files'], j['skipped'], j['result']['downloaded']) == ('dry_run', 2, 4, 0) and kosong(cfg)
    mesin = TestClient(client.app)
    h = {**X, 'Authorization': f'Bearer {TOKEN}'}
    r = mesin.post('/api/admin/import', json=dict(url=URL), headers=h)
    assert r.status_code == 202
    j = tunggu(mesin, r.json()['job_id'], h)
    assert (j['status'], j['files'], j['folder'], j['requested_by']) == ('done', 2, D, '(machine token)'), j
    assert j['result']['ingest']['files_changed'] == 2 and 'ingest #' in j['message']
    assert D in [f['folder'] for f in client.get('/api/meta').json()['folders']]               # folder appears in the dashboard
    ov = client.get('/api/admin/import').json()
    assert [x['status'] for x in ov['jobs']][:2] == ['done', 'dry_run'] and ov['enabled'] and ov['allowed'] == ['s3://simpel4-backup/k8s-logs/<YYYY-MM-DD>/']
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
    assert r.status_code == 200 and r.json()['credentials']['source'] == 'pasted' and SECRET not in r.text and 'AKIATEMPEL' not in r.text
    meta = client.get('/api/meta').json()['imports']
    assert meta == dict(enabled=True, credentials=dict(available=True, source='pasted'))
    # pasted key unknown to the fake S3 -> import fails with a cause; inbox stays empty
    j = tunggu(client, client.post('/api/admin/import', json=dict(url=URL), headers=X).json()['job_id'])
    assert j['status'] == 'failed' and 'S3 denied' in j['message'] and kosong(cfg)
    assert client.delete('/api/admin/import/credentials', headers=X).json()['credentials']['source'] == 'environment'
    # secrets are not in the response, the audit, or the account database
    semua = client.get('/api/admin/audit?limit=500').text + client.get('/api/admin/import').text + client.get(f'/api/admin/import/{j["job_id"]}').text
    assert SECRET not in semua and KEY_OK not in semua and 'AKIATEMPEL' not in semua
    assert {'import.credentials.set', 'import.credentials.clear'} <= {x['action'] for x in client.get('/api/admin/audit?limit=500').json()['rows']}
    if auth_url.startswith('sqlite:///'):
        isi = open(auth_url[len('sqlite:///'):], 'rb').read()
        assert SECRET.encode() not in isi and b'AKIATEMPEL' not in isi


def test_kredensial_tempel_hilang_setelah_mulai_ulang(cfg, auth_url, monkeypatch, s3):
    monkeypatch.setattr(accounts, 'SCRYPT', (10, 8, 1))
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
    """Owner report 2026-10-07: import failed with "No module named 'botocore'" (s3 package not installed). Now rejected
    up front with a message on how to install it, without creating a failed job; the UI reads `library` to disable import."""
    monkeypatch.setattr(importer, 'library_ok', lambda: False)
    sebelum = len(client.get('/api/admin/import').json()['jobs'])
    r = client.post('/api/admin/import', json=dict(url=URL), headers=X)
    assert r.status_code == 400 and r.json()['error']['code'] == 'no_s3_library' and 'pip install' in r.json()['error']['message']
    ov = client.get('/api/admin/import').json()
    assert ov['library'] is False and len(ov['jobs']) == sebelum
    monkeypatch.undo()
    assert importer.library_ok() is True and client.get('/api/admin/import').json()['library'] is True


# ------------------------------------------------------------------ extract .log.gz -> .log (owner request 2026-10-07)
FE_GZ = obj('om-fe-inhouse', 'pod-f', ext='.log.gz')
FE_LOG = os.path.join('ombudsman', 'om-fe-inhouse', f'log_om-fe-inhouse_pod-f_{D}-00-00.log')


def test_gz_diekstrak_menjadi_log(cfg, s3):
    r = importer.run(cfg, URL, importer.Credentials(cfg))
    folder = os.path.join(cfg.inbox_dir, D)
    assert r['extracted'] == 1 and not os.path.exists(os.path.join(folder, FE_LOG + '.gz'))
    assert open(os.path.join(folder, FE_LOG), 'rb').read() == gzip.decompress(ISI[FE_GZ])
    man = json.load(open(os.path.join(folder, importer.MANIFEST)))
    assert man[FE_GZ[len(PRE):]]['stored'] == FE_GZ[len(PRE):-3] and man[FE_GZ[len(PRE):]]['size'] == len(ISI[FE_GZ])
    r2 = importer.run(cfg, URL, importer.Credentials(cfg))                  # again: no re-download and no re-extract
    assert (r2['downloaded'], r2['extracted']) == (0, 0)
    con = db.open(cfg.db_path)
    try: assert ingest.run(cfg, con, folder=D, workers=0)['files_failed'] == 0
    finally: con.close()


def test_tanpa_ekstrak_gz_disimpan_apa_adanya(cfg, s3):
    c = dataclasses.replace(cfg, import_extract=False)
    r = importer.run(c, URL, importer.Credentials(c))
    folder = os.path.join(cfg.inbox_dir, D)
    assert r['extracted'] == 0 and os.path.isfile(os.path.join(folder, FE_LOG + '.gz')) and not os.path.exists(os.path.join(folder, FE_LOG))


def test_gz_dari_impor_lama_diekstrak_tanpa_unduh_ulang(cfg, s3):
    importer.run(dataclasses.replace(cfg, import_extract=False), URL, importer.Credentials(cfg))   # like the owner's 2026-10-07 folder
    n0 = len(s3.gets())
    r = importer.run(cfg, URL, importer.Credentials(cfg))
    folder = os.path.join(cfg.inbox_dir, D)
    assert (r['downloaded'], r['extracted']) == (0, 1) and len(s3.gets()) == n0
    assert os.path.isfile(os.path.join(folder, FE_LOG)) and not os.path.exists(os.path.join(folder, FE_LOG + '.gz'))
    assert importer.run(cfg, URL, importer.Credentials(cfg))['extracted'] == 0
    assert importer.run(cfg, URL, importer.Credentials(cfg), dry_run=True)['extracted'] == 0


def test_gz_rusak_membatalkan_impor(cfg, s3):
    s3.buckets['simpel4-backup'][FE_GZ] = gzip.compress(b'baris log\n' * 100)[:-12]     # truncated
    gagal(cfg, URL, 'bad_gzip')
    assert kosong(cfg) and os.listdir(os.path.join(cfg.data_dir, 'tmp')) == []


def test_hasil_ekstrak_terlalu_besar_dibatalkan(cfg, s3, monkeypatch):
    monkeypatch.setattr(importer, 'EXTRACT_RATIO', 1e-8)        # ±10-byte limit: a fake "gzip bomb"
    gagal(cfg, URL, 'extract_too_large')
    assert kosong(cfg)


# ------------------------------------------------------------------ automatic sync from the parent prefix (S4_S3_WATCH)
WATCH = 's3://simpel4-backup/k8s-logs/'


def test_pilih_folder_baru_dan_periksa_ulang():
    import datetime as dt
    today = dt.date(2026, 10, 7)
    fs = ['2026-08-01', '2026-10-01', '2026-10-02', '2026-10-03', '2026-10-05', '2026-10-06', '2026-10-07']
    known = {'2026-10-02', '2026-10-06', '2026-10-07'}
    take, again, wait = importer.pick(fs, known, {'2026-10-06', '2026-10-07'}, today, days=30, recheck_days=1, max_new=2)
    assert (take, again, wait) == (['2026-10-03', '2026-10-05'], ['2026-10-06', '2026-10-07'], 1)   # 08-01 outside 30 days; 10-01 follows later
    assert importer.pick(fs, known, set(), today, days=0, recheck_days=1, max_new=10)[0] == ['2026-08-01', '2026-10-01', '2026-10-03', '2026-10-05']


@pytest.mark.parametrize('watch,code', [('s3://simpel4-backup/k8s-logs/', None), ('s3://bucket-lain/k8s-logs/', 'watch_not_allowed'),
                                        ('s3://simpel4-backup/lain/', 'watch_not_allowed'), ('https://x/y', 'invalid_watch'),
                                        ('s3://simpel4-backup/k8s-logs/../x/', 'invalid_watch')])
def test_awalan_pantau_diperiksa_terhadap_daftar_izin(cfg, watch, code):
    c = dataclasses.replace(cfg, s3_watch=watch)
    if code is None: assert importer.parse_watch(c) == [('simpel4-backup', 'k8s-logs/')]
    else:
        with pytest.raises(importer.ImportFail) as e: importer.parse_watch(c)
        assert e.value.code == code


@pytest.fixture
def wclient(cfg, auth_url, monkeypatch, s3):
    """S3 holds folders 2026-01-02 (already in the local log folder), 01-05, 01-06, 01-07, and a non-date prefix."""
    monkeypatch.setattr(accounts, 'SCRYPT', (10, 8, 1))
    b = s3.buckets['simpel4-backup']
    for f in ('2026-01-02', '2026-01-06', '2026-01-07'): b[obj('om-be-appsmanager', 'pod-a', folder=f)] = APPS
    b['k8s-logs/arsip-lama/x.log'] = b'x'
    c = dataclasses.replace(cfg, auth_database_url=auth_url, s3_watch=WATCH, s3_watch_days=0, s3_watch_max_folders=2, s3_watch_recheck_days=400, s3_watch_minutes=0)
    con = db.open(c.db_path); ingest.run(c, con, workers=0); con.close()
    with TestClient(appmod.create_app(c)) as tc:
        assert tc.post('/api/auth/login', json=dict(username='admin', password=PW), headers=X).status_code == 200
        assert tc.post('/api/me/password', json=dict(old_password=PW, new_password=PW2), headers=X).status_code == 200
        yield tc


def sinkron(tc, h=X, baca=None):
    assert tc.post('/api/admin/import/sync', headers=h).status_code == 202
    tc.app.state.imports.wait(60)
    return (baca or tc).get('/api/admin/import', headers=X).json()['watch']['last']


def test_sinkron_otomatis_mengambil_folder_baru_tanpa_tautan(wclient, cfg, s3):
    w = wclient.get('/api/admin/import').json()['watch']
    assert w['enabled'] and w['sources'] == [WATCH] and w['problem'] is None and w['last'] is None
    r = sinkron(wclient)
    assert (r['imported'], r['waiting'], r['errors'], r['failed']) == (['2026-01-06', '2026-01-07'], 1, [], []), r   # newest first, max. 2
    assert r['sources'] == [dict(source=WATCH, folders=4, new=3)]                    # 01-02 is in the local log folder: not fetched
    folders = [f['folder'] for f in wclient.get('/api/meta').json()['folders']]
    assert {'2026-01-06', '2026-01-07'} <= set(folders) and D not in folders
    jobs = wclient.get('/api/admin/import').json()['jobs']
    assert [(j['folder'], j['status']) for j in jobs[:2]] == [('2026-01-07', 'done'), ('2026-01-06', 'done')] and jobs[0]['requested_by'] == 'admin'
    # next round via machine token (cron): pending folders follow; existing ones are not downloaded again
    n0 = len(s3.gets())
    r = sinkron(TestClient(wclient.app), {**X, 'Authorization': f'Bearer {TOKEN}'}, wclient)
    assert (r['imported'], r['rechecked'], r['waiting']) == ([D], [], 0) and r['by'] == '(machine token)'
    assert len(s3.gets()) - n0 == 2                                                   # only the two objects of folder D
    # file arriving later in an already-synced folder: rechecked, only new objects are downloaded
    s3.buckets['simpel4-backup'][obj('om-fe-inhouse', 'pod-f', folder='2026-01-07')] = logs_mini.lines('om-fe-inhouse').encode()
    n0 = len(s3.gets())
    r = sinkron(wclient)
    assert (r['imported'], r['rechecked']) == ([], ['2026-01-07']) and len(s3.gets()) - n0 == 1
    assert {'import.sync'} <= {x['action'] for x in wclient.get('/api/admin/audit').json()['rows']}


def test_folder_yang_dihapus_admin_tidak_disinkron_lagi(wclient, cfg):
    sinkron(wclient)
    assert wclient.post('/api/admin/folders/2026-01-07/delete', json=dict(delete_inbox=True), headers=X).status_code == 200
    r = sinkron(wclient)
    assert '2026-01-07' not in r['imported'] + r['rechecked'] and r['imported'] == [D]
    assert not os.path.exists(os.path.join(cfg.inbox_dir, '2026-01-07'))


def test_sinkron_belum_diatur_dan_tanpa_kredensial(client, cfg):
    r = client.post('/api/admin/import/sync', headers=X)
    assert (r.status_code, r.json()['error']['code']) == (400, 'watch_disabled')
    assert client.get('/api/admin/import').json()['watch']['enabled'] is False


def test_penjadwal_memeriksa_sendiri(wclient):
    """Settings saved from the UI -> the scheduler is woken and checks ±5 seconds later, without a button."""
    m = wclient.app.state.imports
    r = wclient.put('/api/admin/import/watch', json=dict(url=WATCH, minutes=5, enabled=True), headers=X)
    assert r.status_code == 200 and r.json()['minutes'] == 5
    assert config.read_dotenv(os.path.join(wclient.app.state.cfg.state_dir, '.env'))['S4_S3_WATCH_MINUTES'] == '5'   # written to .env
    for _ in range(400):
        if m.watch['last'] and not m.state['running']: break
        time.sleep(0.05)
    assert m.watch['last']['by'] == '(automatic S3 sync)' and m.watch['last']['imported'] == ['2026-01-06', '2026-01-07']
    assert wclient.get('/api/admin/import').json()['watch']['next_check']


@pytest.fixture
def plain(cfg, auth_url, monkeypatch, s3):
    """Without S4_S3_WATCH in .env: sync only via the address the admin fills in on the UI."""
    monkeypatch.setattr(accounts, 'SCRYPT', (10, 8, 1))
    b = s3.buckets['simpel4-backup']
    b[obj('om-be-appsmanager', 'pod-a', folder='2026-01-06')] = APPS
    c = dataclasses.replace(cfg, auth_database_url=auth_url, s3_watch_days=0)
    con = db.open(c.db_path); ingest.run(c, con, workers=0); con.close()
    return c


def masuk_admin(tc):
    assert tc.post('/api/auth/login', json=dict(username='admin', password=PW), headers=X).status_code == 200
    assert tc.post('/api/me/password', json=dict(old_password=PW, new_password=PW2), headers=X).status_code == 200


@pytest.mark.parametrize('url,code', [('s3://simpel4-backup/k8s-logs/2026-01-06/', 'watch_is_date'), ('s3://bucket-lain/x/', 'watch_not_allowed'),
                                      ('simpel4-backup/k8s-logs', 'invalid_watch'), ('', 'invalid_watch')])
def test_alamat_dari_layar_diperiksa(plain, url, code):
    with TestClient(appmod.create_app(plain)) as tc:
        masuk_admin(tc)
        r = tc.put('/api/admin/import/watch', json=dict(url=url, minutes=60, enabled=True), headers=X)
        assert (r.status_code, r.json()['error']['code']) == (400, code)


def test_alamat_dari_layar_tersimpan_dan_dipakai(plain, s3):
    with TestClient(appmod.create_app(plain)) as tc:
        masuk_admin(tc)
        w = tc.get('/api/admin/import').json()['watch']
        assert (w['enabled'], w['source'], w['url']) == (False, None, '')
        assert tc.post('/api/admin/import/sync', headers=X).json()['error']['code'] == 'watch_disabled'
        r = tc.put('/api/admin/import/watch', json=dict(url='s3://simpel4-backup/k8s-logs', minutes=60, enabled=True), headers=X)   # without trailing "/"
        assert r.status_code == 200, r.text
        w = r.json()
        assert (w['enabled'], w['sources'], w['source'], w['minutes']) == (True, [WATCH], 'file', 60)
        env = config.read_dotenv(os.path.join(plain.state_dir, '.env'))
        assert env == {'S4_S3_WATCH': 's3://simpel4-backup/k8s-logs'}   # only values that differ from the current ones are written
        assert 'import.watch' in {x['action'] for x in tc.get('/api/admin/audit').json()['rows']}
        assert tc.put('/api/admin/import/watch', json=dict(url=WATCH, minutes=7, enabled=True), headers=X).status_code == 400   # interval outside the choices
    # settings persist after a server restart (read again from .env), then the check uses that address
    with TestClient(appmod.create_app(muat_ulang(plain))) as tc:
        assert tc.post('/api/auth/login', json=dict(username='admin', password=PW2), headers=X).status_code == 200   # password already changed above
        assert tc.get('/api/admin/import').json()['watch']['sources'] == [WATCH]
        assert tc.post('/api/admin/import/sync', headers=X).status_code == 202
        tc.app.state.imports.wait(60)
        assert tc.get('/api/admin/import').json()['watch']['last']['imported'] == [D, '2026-01-06']
        # turned off from the UI: S4_S3_WATCH_ENABLED=false, address kept; button rejected
        assert tc.put('/api/admin/import/watch', json=dict(url=WATCH, minutes=60, enabled=False), headers=X).json()['enabled'] is False
        assert tc.post('/api/admin/import/sync', headers=X).json()['error']['code'] == 'watch_disabled'
        assert tc.app.state.cfg.s3_watch == WATCH
        assert config.read_dotenv(os.path.join(plain.state_dir, '.env'))['S4_S3_WATCH_ENABLED'] == 'false'


def muat_ulang(c):
    """Like a server restart: all test values as environment, EXCEPT those in .env (read by config.load)."""
    path = os.path.join(c.state_dir, '.env')
    fv = config.read_dotenv(path)
    env = {config.env_name(f.name): envfile.fmt(getattr(c, f.name)) for f in dataclasses.fields(c)}
    return config.load(env={k: v for k, v in env.items() if k not in fv}, dotenv=path)


def test_user_biasa_tidak_boleh_mengatur_sinkron(plain):
    with TestClient(appmod.create_app(plain)) as tc:
        masuk_admin(tc)
        assert tc.post('/api/admin/users', json=dict(username='rina', display_name='Rina', role='user', password='sandi-awal-rina-123'), headers=X).status_code == 201
        u = TestClient(tc.app)
        u.post('/api/auth/login', json=dict(username='rina', password='sandi-awal-rina-123'), headers=X)
        u.post('/api/me/password', json=dict(old_password='sandi-awal-rina-123', new_password='sandi-baru-rina-123'), headers=X)
        assert u.put('/api/admin/import/watch', json=dict(url=WATCH, minutes=60, enabled=True), headers=X).status_code == 403
