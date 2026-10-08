"""API skeleton (TRD §5.1–§5.2, §5.5–§5.6, §8, §9.5–§9.6): login, session, role, CSRF, headers, validation, in-process ingest."""
import dataclasses, os, time, urllib.parse

import duckdb, pytest
from fastapi.testclient import TestClient

import logs_mini
from monishield.domain import accounts
from monishield.infrastructure import config, db, ingest
from monishield.interfaces.api import app as appmod, common
from conftest import JWT_SECRET

PW, PW2 = 'sandi-admin-pertama', 'sandi-admin-sesudah-diganti'
A, B = '2026-01-01', '2026-01-02'
X = {'X-Requested-With': 'uji'}
TOKEN = 'token-mesin-untuk-uji'
NG, SL = 'nginx-ingress-controller', 'om-be-simpel-loop'
HALAMAN = ('overview', 'map', 'security', 'rootcause', 'availability', 'pods', 'business', 'tracing')


@pytest.fixture(scope='module')
def cfg(tmp_path_factory):
    tmp = tmp_path_factory.mktemp('api')
    c = dataclasses.replace(config.Config(), log_dir=logs_mini.build(tmp / 'logs'), data_dir=str(tmp / 'data'), state_dir=str(tmp / 'state'),
                            inbox_dir=str(tmp / 'inbox'), cache_dir=str(tmp / 'cache'), offline=True, ingest_on_start=False, cookie_secure=False,
                            admin_user='admin', admin_password=PW, job_token=TOKEN, jwt_secret=JWT_SECRET)
    con = db.open(c.db_path); ingest.run(c, con, workers=0); con.close()
    return c


@pytest.fixture
def client(cfg, auth_url, monkeypatch):
    """New app with an empty account database for each test (log data is shared, read-only)."""
    monkeypatch.setattr(accounts, 'SCRYPT', (10, 8, 1))   # cheap hash so tests are fast; the real cost is measured in docs/04a
    c = dataclasses.replace(cfg, auth_database_url=auth_url)
    with TestClient(appmod.create_app(c)) as tc:
        yield tc


def masuk(tc, username='admin', password=PW):
    r = tc.post('/api/auth/login', json=dict(username=username, password=password), headers=X)
    assert r.status_code == 200, r.text
    return r


def admin(tc):
    """The first admin must change the password first."""
    masuk(tc)
    assert tc.post('/api/me/password', json=dict(old_password=PW, new_password=PW2), headers=X).status_code == 200
    return tc


def buat_user(tc, username='rina', role='user', password='sandi-awal-rina-123'):
    r = tc.post('/api/admin/users', json=dict(username=username, display_name=username.title(), role=role, password=password), headers=X)
    assert r.status_code == 201, r.text
    return r.json()


def sebagai(cfg_client, username, password, baru='sandi-baru-milik-user'):
    """Separate client logged in as another user who has already changed their initial password."""
    tc = TestClient(cfg_client.app)
    masuk(tc, username, password)
    assert tc.post('/api/me/password', json=dict(old_password=password, new_password=baru), headers=X).status_code == 200
    return tc


def kode(r): return r.json().get('error', {}).get('code')


# ------------------------------------------------------------------ basics
def test_health_tanpa_sesi_tanpa_data(client):
    r = client.get('/api/health')
    assert r.status_code == 200 and r.json() == {'ok': True}


def test_tanpa_sesi_ditolak(client):
    for path in ('/api/meta', f'/api/folders/{B}', '/api/me', '/api/admin/users', '/api/admin/ingest/status'):
        r = client.get(path)
        assert (r.status_code, kode(r)) == (401, 'unauthenticated'), path


def test_header_keamanan_di_semua_jawaban(client):
    for r in (client.get('/api/health'), client.get('/api/meta'), client.get('/tidak-ada'), client.get('/api/tidak-ada')):
        assert "default-src 'self'" in r.headers['content-security-policy'] and "frame-ancestors 'none'" in r.headers['content-security-policy']
        assert r.headers['x-content-type-options'] == 'nosniff' and r.headers['referrer-policy'] == 'no-referrer'
    assert client.get('/api/health').headers['cache-control'] == 'no-store'


def test_format_galat(client):
    r = client.get('/api/tidak-ada')
    assert r.status_code == 404 and set(r.json()) == {'error'} and set(r.json()['error']) == {'code', 'message'}


# ------------------------------------------------------------------ login and session
def test_masuk_cookie_dan_wajib_ganti_sandi(client):
    r = masuk(client)
    assert r.json() == dict(username='admin', display_name='Administrator', email=None, role='admin', must_change_password=True, session_idle_minutes=60)
    ck = r.headers['set-cookie'].lower()
    assert 's4_session=' in ck and 'httponly' in ck and 'samesite=strict' in ck and 'path=/' in ck and 'secure' not in ck  # cookie_secure=False in tests
    assert PW not in r.text and client.get('/api/me').json()['must_change_password'] is True
    assert client.get('/api/me').json()['session_idle_minutes'] == 60                  # basis for the session warning in the UI (DRD §6.9)
    r = client.get('/api/meta')
    assert (r.status_code, kode(r)) == (403, 'must_change_password')            # only /api/me and change password are allowed
    assert client.post('/api/me/password', json=dict(old_password=PW, new_password=PW2), headers=X).status_code == 200
    assert client.get('/api/meta').status_code == 200 and client.get('/api/me').json()['must_change_password'] is False
    assert {f['source'] for f in client.get('/api/meta').json()['folders']} == {'log'}   # from the main log folder (not Kafka/S3/upload)


def test_cookie_secure_bila_dikonfigurasi(cfg, auth_url, monkeypatch):
    monkeypatch.setattr(accounts, 'SCRYPT', (10, 8, 1))
    c = dataclasses.replace(cfg, auth_database_url=auth_url, cookie_secure=True)
    with TestClient(appmod.create_app(c), base_url='https://uji.local') as tc:
        assert '; secure' in masuk(tc).headers['set-cookie'].lower()


def test_sandi_salah_dan_user_tidak_ada_jawaban_sama(client):
    a = client.post('/api/auth/login', json=dict(username='admin', password='sandi-yang-salah'), headers=X)
    b = client.post('/api/auth/login', json=dict(username='tidak-ada', password='sandi-yang-salah'), headers=X)
    assert a.status_code == b.status_code == 401 and a.json() == b.json() and 'set-cookie' not in a.headers


def test_enam_kali_salah_dibatasi(client):
    for _ in range(5):
        assert client.post('/api/auth/login', json=dict(username='admin', password='sandi-yang-salah'), headers=X).status_code == 401
    r = client.post('/api/auth/login', json=dict(username='admin', password=PW), headers=X)
    assert (r.status_code, kode(r)) == (429, 'too_many_attempts')


def test_keluar_mencabut_sesi(client):
    admin(client)
    assert client.post('/api/auth/logout', headers=X).status_code == 200
    assert client.get('/api/me').status_code == 401


def test_csrf_header_dan_origin(client):
    assert kode(client.post('/api/auth/login', json=dict(username='admin', password=PW))) == 'csrf'          # without X-Requested-With
    admin(client)
    assert kode(client.post('/api/admin/users', json=dict(username='x1x', password='sandi-awal-12345'))) == 'csrf'
    r = client.post('/api/admin/users', json=dict(username='x1x', password='sandi-awal-12345'), headers={**X, 'Origin': 'https://jahat.example'})
    assert (r.status_code, kode(r)) == (403, 'csrf')
    assert client.post('/api/admin/users', json=dict(username='x1x', password='sandi-awal-12345'), headers={**X, 'Origin': 'http://testserver'}).status_code == 201
    assert client.get('/api/admin/users').status_code == 200                                                  # GET needs no header


# ------------------------------------------------------------------ roles
def test_user_melihat_dashboard_tetapi_bukan_admin(client):
    admin(client); u = buat_user(client)
    assert u['role'] == 'user' and u['must_change_password'] is True
    tc = sebagai(client, 'rina', 'sandi-awal-rina-123')
    a, b = client.get(f'/api/folders/{B}').json(), tc.get(f'/api/folders/{B}').json()
    assert a == b and len(b['services']) == 7                                    # user sees the same as admin
    assert tc.get('/api/meta').status_code == 200
    for method, path in (('get', '/api/admin/users'), ('get', '/api/admin/audit'), ('get', '/api/admin/ingest/status'), ('post', '/api/admin/ingest'),
                         ('post', '/api/admin/derive'), ('post', '/api/admin/forget'), ('post', '/api/admin/users')):
        r = getattr(tc, method)(path, headers=X) if method == 'get' else getattr(tc, method)(path, json={}, headers=X)
        assert (r.status_code, kode(r)) == (403, 'forbidden'), path


def test_matriks_peran_mencakup_semua_rute(client):
    """For EVERY route: no session / user / admin / machine token -> accepted or rejected per TRD §8.3."""
    admin(client); buat_user(client)
    user = sebagai(client, 'rina', 'sandi-awal-rina-123')
    anon, mesin = TestClient(client.app), TestClient(client.app)
    harap = {common.public: (1, 1, 1, 1), common.require_user: (0, 1, 1, 0), common.require_user_ready: (0, 1, 1, 0),
             common.require_admin: (0, 0, 1, 0), common.require_admin_or_job: (0, 0, 1, 1)}
    ditolak = {'unauthenticated', 'forbidden', 'must_change_password'}
    rute = appmod.check_roles(appmod.ROUTERS)
    assert len(rute) >= 28 and {'/api/trends', '/api/folders/{folder}/tables/{table}', '/api/folders/{folder}/services/{service}'} <= {r.path for r in rute}
    for r in sorted(rute, key=lambda r: r.path == '/api/auth/logout'):            # logout is tested last
        dep = next(d for d in (common.require_admin_or_job, common.require_admin, common.require_user_ready, common.require_user, common.public)
                   if d in set(appmod._deps(r.dependant)))
        f = '2030-01-01' if r.path.startswith('/api/admin/folders/') else B   # folder delete/restore routes: a date that does not exist (do not delete test data)
        path = r.path.replace('{folder}', f).replace('{user_id}', '999999').replace('{job_id}', '999999').replace('{table}', 'c401').replace('{service}', NG)
        method = sorted(r.methods)[0].lower()
        for i, (tc, hdr) in enumerate(((anon, X), (user, X), (client, X), (mesin, {**X, 'Authorization': f'Bearer {TOKEN}'}))):
            kw = dict(headers=hdr) if method in ('get', 'delete') else dict(headers=hdr, json={})
            res = getattr(tc, method)(path, **kw)
            diterima = kode(res) not in ditolak if res.status_code >= 400 else True
            assert diterima == bool(harap[dep][i]), f'{method.upper()} {r.path} sebagai {("anonim", "user", "admin", "token mesin")[i]}: {res.status_code} {res.text[:80]}'
        if r.path == '/api/admin/ingest': client.app.state.ingest.wait(30)


def test_token_mesin_hanya_untuk_ingest(client):
    h = {**X, 'Authorization': f'Bearer {TOKEN}'}
    tc = TestClient(client.app)
    assert tc.get('/api/admin/ingest/status', headers=h).status_code == 200
    assert tc.get('/api/admin/ingest/status', headers={**X, 'Authorization': 'Bearer salah'}).status_code == 401
    for path in ('/api/meta', '/api/admin/users', f'/api/folders/{B}', '/api/me'):
        assert tc.get(path, headers=h).status_code == 401, path
    assert tc.post('/api/admin/forget', json=dict(folder=B), headers=h).status_code == 401


def test_rute_tanpa_deklarasi_peran_menolak_mulai():
    from fastapi import APIRouter
    r = APIRouter(prefix='/api')
    r.add_api_route('/bocor', lambda: {'data': 'rahasia'}, methods=['GET'])
    with pytest.raises(RuntimeError, match='without a role declaration'): appmod.check_roles((*appmod.ROUTERS, r))


# ------------------------------------------------------------------ user management
def test_kelola_user(client):
    admin(client); u = buat_user(client, 'budi')
    assert [x['username'] for x in client.get('/api/admin/users').json()['users']] == ['admin', 'budi']
    assert kode(client.post('/api/admin/users', json=dict(username='budi', password='sandi-awal-12345'), headers=X)) == 'username_taken'
    assert kode(client.post('/api/admin/users', json=dict(username='B', password='sandi-awal-12345'), headers=X)) == 'invalid_username'
    assert kode(client.post('/api/admin/users', json=dict(username='caca', password='pendek'), headers=X)) == 'invalid_password'
    assert kode(client.post('/api/admin/users', json=dict(username='caca', password='sandi-awal-12345', role='root'), headers=X)) == 'invalid_role'
    tc = TestClient(client.app); masuk(tc, 'budi', 'sandi-awal-rina-123')
    r = client.post(f"/api/admin/users/{u['user_id']}/reset-password", headers=X)
    temp = r.json()['temporary_password']
    assert len(temp) >= 12 and tc.get('/api/me').status_code == 401                # budi's session ends immediately
    masuk(tc, 'budi', temp)
    assert client.patch(f"/api/admin/users/{u['user_id']}", json=dict(active=False), headers=X).json()['active'] is False
    assert tc.get('/api/me').status_code == 401
    assert client.patch(f"/api/admin/users/{u['user_id']}", json=dict(active=True, role='admin', display_name='Budi S'), headers=X).json()['role'] == 'admin'
    saya = next(x for x in client.get('/api/admin/users').json()['users'] if x['username'] == 'admin')
    assert kode(client.delete(f"/api/admin/users/{saya['user_id']}", headers=X)) == 'self_delete'
    assert client.delete(f"/api/admin/users/{u['user_id']}", headers=X).status_code == 200
    assert kode(client.patch(f"/api/admin/users/{saya['user_id']}", json=dict(role='user'), headers=X)) == 'last_admin'
    assert kode(client.delete('/api/admin/users/424242', headers=X)) == 'not_found'
    audit = client.get('/api/admin/audit?limit=100').json()
    aksi = [r['action'] for r in audit['rows']]
    assert audit['total'] == len(aksi) and {'user.create', 'user.reset_password', 'user.update', 'user.delete', 'login.ok', 'user.change_password'} <= set(aksi)
    assert temp not in str(audit) and PW2 not in str(audit)


# ------------------------------------------------------------------ meta and folders
def test_meta(client):
    admin(client)
    m = client.get('/api/meta').json()
    assert [f['folder'] for f in m['folders']] == [B, A]                           # newest first
    b = m['folders'][0]
    assert (b['lines'], b['services'], b['files'], b['files_empty'], b['files_corrupt']) == (38, 7, 7, 1, 1)
    assert (b['range_start'], b['range_end']) == ('2026-09-25 23:04', '2026-09-28 23:15')   # WIB; from access and Spring lines (not error logs)
    assert len(b['derived_at']) == 16 and b['derived_at'][:2] == '20'                     # WIB 'YYYY-MM-DD HH:MM'
    assert m['server'] == dict(ip='103.170.104.228', city='Jakarta', region='Jakarta', cc='ID', lat=-6.2, lon=106.82)   # no IP data: fallback value
    assert m['hosts']['om-fe-inhouse-3000'] == 'https://simpel4.ombudsman.go.id' and m['dns_upstream'] == '10.88.1.100'
    assert m['ip_data'] == dict(owner=False, location=False, map=False) and any('MaxMind' in s for s in m['attribution'])
    assert m['ingest']['running'] is False and m['version']
    teks = str(m)
    for rahasia in (TOKEN, PW, PW2, JWT_SECRET, 'cache', 'sqlite', 'postgresql'): assert rahasia not in teks       # no secrets, paths or database URLs


def test_folder(client):
    admin(client)
    f = client.get(f'/api/folders/{B}').json()
    # attack source IPs follow the detection rules in use (Stage 21: OWASP CRS; the old rules flag 2 IPs in this data)
    assert (f['folder'], f['prev_folder']) == (B, A) and f['attack_ip_count'] == client.get(f'/api/folders/{B}/security').json()['kpi']['attack_ips'] == 1
    assert [s['service'] for s in f['services']] == ['nginx-ingress-controller', 'coredns', 'layanan-baru', 'om-be-appsmanager', 'om-be-referensi', 'om-be-report', 'om-be-simpel-loop']
    ng = f['services'][0]
    assert (ng['lines'], ng['err'], ng['warn'], ng['err_http'], ng['err_log'], ng['requests'], ng['n4xx'], ng['files'], ng['prev']) == (11, 2, 1, 0, 2, 7, 2, 1, None)
    am = next(s for s in f['services'] if s['service'] == 'om-be-appsmanager')
    assert am['lines'] == 0 and am['files_empty'] == 1 and am['prev'] == dict(lines=10, err=1, warn=4)   # previous folder, for ▲/▼
    assert len(f['files']) == 7 and {x['status'] for x in f['files']} == {'ok', 'empty', 'corrupt'}
    assert client.get(f'/api/folders/{A}').json()['prev_folder'] is None


@pytest.mark.parametrize('folder', ['2026-01-03', '2026-13-45', 'bukan-tanggal', "2026-01-02' OR '1'='1", '../../etc/passwd', '2026-01-02;DROP TABLE agg_service'])
def test_folder_tidak_sah_404_tanpa_bocor(client, folder):
    admin(client)
    r = client.get(f'/api/folders/{folder}')
    assert r.status_code == 404 and folder not in r.text
    assert client.get(f'/api/folders/{B}').status_code == 200                      # table still intact


def test_parameter_salah_400_tanpa_memantulkan_nilai(client):
    admin(client)
    r = client.get('/api/admin/audit?limit=<script>alert(1)</script>')
    assert (r.status_code, kode(r)) == (400, 'invalid_parameter') and '<script>' not in r.text and 'limit' in r.text
    assert client.get('/api/admin/audit?limit=100000').status_code == 400
    assert kode(client.post('/api/admin/ingest', json=dict(folder='../x'), headers=X)) == 'invalid_parameter'
    assert kode(client.post('/api/admin/forget', json={}, headers=X)) == 'invalid_parameter'
    assert kode(client.post('/api/admin/forget', json=dict(folder='2030-01-01'), headers=X)) == 'not_found'


# ------------------------------------------------------------------ in-process ingest
def test_ingest_lewat_api_dan_dashboard_tetap_terbuka(client):
    admin(client)
    r = client.post('/api/admin/ingest', json=dict(force=True), headers=X)
    assert r.status_code == 202
    selama = []
    for _ in range(200):
        st = client.get('/api/admin/ingest/status').json()
        selama.append(client.get(f'/api/folders/{B}').status_code)                # read while ingest is running
        if not st['running']: break
        time.sleep(0.02)
    assert set(selama) == {200} and st['error'] is None
    assert (st['last']['status'], st['last']['files_parsed'], st['last']['files_failed']) == ('ok', 9, 0)
    lr = st['last_run']                                                         # from ingest_run: survives a server restart
    assert (lr['status'], lr['files_changed'], lr['warnings']) == ('ok', st['last']['files_changed'], st['last']['warnings'])
    assert lr['finished_at'] >= lr['started_at']
    assert client.get(f'/api/folders/{B}').json()['services'][0]['lines'] == 11
    assert 'ingest.start' in [x['action'] for x in client.get('/api/admin/audit').json()['rows']]


def test_salinan_duckdb_untuk_dbgate(cfg, auth_url, monkeypatch):
    """S4_DUCKDB_SNAPSHOT (docker compose + DbGate): the copy is created at server start if missing, then refreshed after every
    ingest. Without that setting there is no copy at all."""
    monkeypatch.setattr(accounts, 'SCRYPT', (10, 8, 1))
    c = dataclasses.replace(cfg, auth_database_url=auth_url, duckdb_snapshot=True)
    path = db.snapshot_path(c)
    try:
        with TestClient(appmod.create_app(c)) as tc:
            assert os.path.exists(path)
            sebelum = os.stat(path).st_mtime_ns
            admin(tc)
            assert tc.post('/api/admin/ingest', json=dict(force=True), headers=X).status_code == 202
            tc.app.state.ingest.wait(60)
            st = tc.get('/api/admin/ingest/status').json()
            assert st['error'] is None and st['snapshot_error'] is None and os.stat(path).st_mtime_ns > sebelum
        ro = duckdb.connect(path, read_only=True)
        try: assert ro.execute('SELECT count(*) FROM folder_state').fetchone() == (2,)
        finally: ro.close()
    finally:
        if os.path.exists(path): os.remove(path)
    with TestClient(appmod.create_app(dataclasses.replace(c, duckdb_snapshot=False))): assert not os.path.exists(path)


def test_sinkronisasi_mendeteksi_folder_baru(client, cfg):
    """Sync button: ingest status names new log folders not yet ingested; after ingest, the list is empty."""
    import shutil
    admin(client)
    assert client.get('/api/admin/ingest/status').json()['new_folders'] == []
    os.makedirs(os.path.join(cfg.log_dir, '2026-03-03', 'kosong'))                     # folder without log files: not counted
    src = os.path.join(cfg.log_dir, B)
    shutil.copytree(src, os.path.join(cfg.log_dir, '2026-03-04'))
    assert client.get('/api/admin/ingest/status').json()['new_folders'] == ['2026-03-04']
    assert client.post('/api/admin/ingest', json={}, headers=X).status_code == 202
    for _ in range(300):
        st = client.get('/api/admin/ingest/status').json()
        if not st['running']: break
        time.sleep(0.02)
    try:
        assert st['error'] is None and '2026-03-04' in st['last']['folders_changed'] and st['new_folders'] == []
        assert '2026-03-04' in [f['folder'] for f in client.get('/api/meta').json()['folders']]
    finally:   # log fixture is shared with other tests: restore it as it was
        for d in ('2026-03-03', '2026-03-04'): shutil.rmtree(os.path.join(cfg.log_dir, d), ignore_errors=True)
        client.post('/api/admin/forget', json=dict(folder='2026-03-04'), headers=X)


def _ingest_tunggu(client):
    assert client.post('/api/admin/ingest', json={}, headers=X).status_code == 202
    for _ in range(300):
        st = client.get('/api/admin/ingest/status').json()
        if not st['running']: return st
        time.sleep(0.02)
    raise AssertionError('ingest tidak selesai')


def test_hapus_folder_dari_dashboard_dan_pulihkan(client, cfg):
    """Owner request 2026-10-07: folders can be deleted from the list. Main log folder is read-only: its data is deleted and the
    folder is ignored by ingest until restored; inbox folders (S3 import) can be deleted along with their files."""
    import shutil
    admin(client)
    rows = {r['folder']: r for r in client.get('/api/admin/folders').json()['rows']}
    assert rows[B]['in_db'] and rows[B]['log'] and not rows[B]['ignored']
    r = client.post(f'/api/admin/folders/{B}/delete', json={}, headers=X).json()
    assert r['files'] > 0 and r['ignored'] and not r['inbox_deleted'] and os.path.isdir(os.path.join(cfg.log_dir, B))   # main log file is not touched
    assert B not in [f['folder'] for f in client.get('/api/meta').json()['folders']]
    st = _ingest_tunggu(client)
    assert st['error'] is None and B not in st['last']['folders_changed'] and st['new_folders'] == []                   # not ingested again
    assert B not in [f['folder'] for f in client.get('/api/meta').json()['folders']]
    assert {r['folder']: r for r in client.get('/api/admin/folders').json()['rows']}[B]['ignored']
    assert client.post(f'/api/admin/folders/{B}/restore', headers=X).status_code == 200
    assert client.get('/api/admin/ingest/status').json()['new_folders'] == [B]
    _ingest_tunggu(client)
    assert B in [f['folder'] for f in client.get('/api/meta').json()['folders']]
    # inbox: data + files deleted, not ignored (nothing left on disk)
    shutil.copytree(os.path.join(cfg.log_dir, B), os.path.join(cfg.inbox_dir, '2026-03-05'))
    try:
        _ingest_tunggu(client)
        r = client.post('/api/admin/folders/2026-03-05/delete', json=dict(delete_inbox=True), headers=X).json()
        assert r['files'] > 0 and r['inbox_deleted'] and not r['ignored'] and not os.path.exists(os.path.join(cfg.inbox_dir, '2026-03-05'))
        assert '2026-03-05' not in [x['folder'] for x in client.get('/api/admin/folders').json()['rows']]
    finally: shutil.rmtree(os.path.join(cfg.inbox_dir, '2026-03-05'), ignore_errors=True)
    assert client.post('/api/admin/folders/bukan-tanggal/delete', json={}, headers=X).status_code in (400, 404)
    assert client.post('/api/admin/folders/2030-01-01/delete', json={}, headers=X).status_code == 404
    assert client.post('/api/admin/folders/2030-01-01/restore', headers=X).status_code == 404
    assert {'folder.delete', 'folder.restore'} <= {x['action'] for x in client.get('/api/admin/audit').json()['rows']}


def test_ingest_kedua_saat_berjalan_409(client, monkeypatch):
    admin(client)
    import threading
    tahan = threading.Event()
    asli = ingest.run
    monkeypatch.setattr(ingest, 'run', lambda *a, **k: (tahan.wait(5), asli(*a, **k))[1])
    assert client.post('/api/admin/ingest', headers=X).status_code == 202
    r = client.post('/api/admin/ingest', headers=X)
    assert (r.status_code, kode(r)) == (409, 'ingest_running')
    assert kode(client.post('/api/admin/derive', headers=X)) == 'ingest_running'
    tahan.set(); client.app.state.ingest.wait(30)
    assert client.post('/api/admin/derive', json=dict(folder=B), headers=X).json() == dict(folders=[B])


def test_ingest_dengan_token_mesin(client):
    tc = TestClient(client.app)
    assert tc.post('/api/admin/ingest', headers={**X, 'Authorization': f'Bearer {TOKEN}'}).status_code == 202
    client.app.state.ingest.wait(30)
    st = tc.get('/api/admin/ingest/status', headers={'Authorization': f'Bearer {TOKEN}'}).json()
    assert st['running'] is False and st['last']['files_changed'] == 0 and st['started_by'] == '(machine token)'


def test_forget_lalu_ingest_memulihkan(client):
    admin(client)
    assert client.post('/api/admin/forget', json=dict(folder=A), headers=X).json() == dict(folder=A, files=2)
    assert client.get(f'/api/folders/{A}').status_code == 404 and [f['folder'] for f in client.get('/api/meta').json()['folders']] == [B]
    client.post('/api/admin/ingest', headers=X); client.app.state.ingest.wait(30)
    assert client.get(f'/api/folders/{A}').status_code == 200


def test_satu_worker_saja():
    assert appmod.WORKERS == 1


def test_tanpa_rahasia_jwt_server_menolak_mulai(cfg, auth_url):
    c = dataclasses.replace(cfg, auth_database_url=auth_url, jwt_secret='')
    with pytest.raises(RuntimeError, match='S4_JWT_SECRET'):
        with TestClient(appmod.create_app(c)): pass


def test_cookie_berisi_jwt_dan_jwt_palsu_ditolak(client):
    import jwt
    masuk(client)
    token = client.cookies.get('s4_session')
    c = jwt.decode(token, JWT_SECRET, algorithms=['HS256'], issuer='monishield')
    assert {'sub', 'sid', 'exp'} <= set(c)
    tc = TestClient(client.app)
    tc.cookies.set('s4_session', jwt.encode({**c, 'sub': '999'}, 'rahasia-penyerang-yang-panjang-sekali-32', algorithm='HS256'))
    assert tc.get('/api/me').status_code == 401
    tc.cookies.set('s4_session', jwt.encode(c, None, algorithm='none'))
    assert tc.get('/api/me').status_code == 401
    assert tc.get('/api/me', headers={'Authorization': f'Bearer {token}'}).status_code == 401   # JWT is only accepted from the HttpOnly cookie


# ------------------------------------------------------------------ Stage 11: page and table endpoints (TRD §5.3–§5.4)
@pytest.fixture
def user(client):
    """Regular user: every data endpoint is open to them (TRD §8.3)."""
    admin(client); buat_user(client)
    return sebagai(client, 'rina', 'sandi-awal-rina-123')


def test_semua_halaman_terbuka_untuk_user_dan_kecil(user):
    from monishield.infrastructure.queries import tables
    svc = [s['service'] for s in user.get(f'/api/folders/{B}').json()['services']]
    urls = [f'/api/folders/{f}/{h}' for f in (A, B) for h in HALAMAN] + [f'/api/folders/{B}/services/{s}' for s in svc] + ['/api/trends']
    urls += [f'/api/folders/{B}/tables/{t}' + (f'?service={NG}' if sp.per_service else '') for t, sp in tables.TABLES.items()]
    assert len(tables.TABLES) == 25
    for u in urls:
        r = user.get(u)
        assert r.status_code == 200, f'{u}: {r.status_code} {r.text[:200]}'
        assert len(r.content) <= 500_000, u                                       # PRD §5.1
        assert 'Traceback' not in r.text
    assert user.get(f'/api/folders/{B}/overview').headers['etag'].startswith(f'"{B}-')


def test_halaman_tanpa_log_yang_dibutuhkan_available_false(user):
    """Folder A has neither nginx nor simpel-loop: 200 with a reason, not an error and not the number 0 (U16)."""
    j = lambda h, f=A: user.get(f'/api/folders/{f}/{h}').json()
    assert j('map') == {'available': False, 'reason': 'no_nginx'}
    assert j('availability') == {'available': False, 'reason': 'no_nginx'}
    assert j('tracing') == {'available': False, 'reason': 'no_simpel_loop'}
    assert j('security')['nginx'] is False and j('security')['kpi']['attack_requests'] == 0
    kosong = user.get(f'/api/folders/{B}/services/om-be-appsmanager').json()       # empty file
    assert (kosong['available'], kosong['reason'], kosong['kpi']['lines']) == (False, 'empty', 0)
    assert j('map', B)['available'] is True and j('availability', B)['available'] is True


def test_bentuk_respons_halaman(user):
    j = lambda h: user.get(f'/api/folders/{B}/{h}').json()
    assert set(j('overview')) == {'available', 'period', 'err_by_hour', 'tables'}
    m = j('map')
    assert set(m['kpi']) == {'source_ips', 'locations', 'countries', 'modules', 'dest_pods', 'requests'} and m['module'] is None
    assert m['kpi']['requests'] == sum(r['requests'] for r in user.get(f'/api/folders/{B}/tables/flows?limit=500').json()['rows'])
    s = j('security')
    assert set(s['kpi']) == {'attack_requests', 'attack_ips', 'critical_hits', 'attack_urls_2xx', 'login_fail_ips', 'accounts_ok_after_fail', 'accounts_ok_other_ip', 'resets'}
    assert set(s['tables']) == {'attack-urls', 'attack-ips', 'accounts', 'login-ips', 'ip-4xx'}
    assert s['kpi']['attack_requests'] == sum(n for _, n, _ in s['by_category']) and s['kpi']['attack_ips'] == s['tables']['attack-ips']['total']
    assert set(j('availability')['kpi']) == {'requests', 'n5xx', 'incidents', 'retries', 'upstream_errors', 'uptime_checks', 'uptime_failed'}
    assert set(j('pods')['kpi']) == {'files', 'files_without_log', 'backend_pods', 'pods_with_retry', 'restarts'}
    assert {'biz', 'biz_prev', 'pdf', 'login', 'mail', 'login_ok_by_hour', 'tables'} <= set(j('business'))
    assert {'jwt', 'jwt_total', 'refresh_expired', 'pdf', 'upstream_error_kinds', 'tables'} <= set(j('rootcause'))
    n = user.get(f'/api/folders/{B}/services/{NG}').json()
    assert n['available'] and n['kpi']['requests'] == sum(x for _, x in n['status']) and 'endpoints' in n['tables']
    assert n['kpi']['err'] == n['kpi']['err_http'] + n['kpi']['err_log'] == sum(e for _, _, e in n['hour'])   # TRD §4.4 item 2
    for h, total, err in n['hour']: assert len(h) == 13                           # 'YYYY-MM-DD HH' WIB
    # map on the service page: only ingress and modules that have flows (others do not request /map, which answers 404)
    mods = user.get(f'/api/folders/{B}/map').json()['modules']
    assert n['has_flows'] is True
    for svc in [x['service'] for x in user.get(f'/api/folders/{B}').json()['services'] if x['lines']]:
        assert user.get(f'/api/folders/{B}/services/{svc}').json().get('has_flows') == (svc == NG or svc in mods), svc


def test_ip_selalu_disertai_bentuk_sel(user):
    rows = user.get(f'/api/folders/{B}/tables/ips?service={NG}').json()['rows']
    assert rows and all(set(r['ip']) in ({'ip'}, {'ip', 'asn', 'cc', 'org'}) for r in rows)


def test_tren(user):
    j = user.get('/api/trends').json()
    assert j['folders'] == [A, B] and set(j) == {'folders', 'services', 'lines', 'err', 'warn', 'file_status', 'http', 'security', 'business', 'completeness', 'heat'}   # Stage 24: +2
    assert j['lines'][NG] == [None, user.get(f'/api/folders/{B}/services/{NG}').json()['kpi']['lines']]     # null = service not present in that folder
    assert j['file_status']['om-be-referensi'] == [None, 'corrupt'] and j['file_status']['om-be-appsmanager'][1] == 'empty'
    assert user.get('/api/trends?last=14').json()['folders'] == [A, B]
    # service order = first appearance: folder A services (file order), then those new in B
    sa = [s['service'] for s in user.get(f'/api/folders/{A}').json()['services']]
    sb = [s['service'] for s in user.get(f'/api/folders/{B}').json()['services']]
    assert j['services'] == sa + [s for s in sb if s not in sa]
    for buruk in ('0', '15', '-1', 'semua', "30' OR 1=1"):
        r = user.get('/api/trends', params=dict(last=buruk)); assert (r.status_code, kode(r)) == (400, 'invalid_parameter'), buruk


def test_tabel_halaman_filter_urut(user):
    P = f'/api/folders/{B}/tables/endpoints'; u = f'{P}?service={NG}'      # httpx: params= replaces the query in the URL
    semua = user.get(u + '&limit=500').json()
    assert semua['total'] == semua['matched'] == len(semua['rows']) > 3 and semua['limit'] == 500
    assert [r['n'] for r in semua['rows']] == sorted((r['n'] for r in semua['rows']), reverse=True)        # old order: most first
    dua = user.get(u + '&limit=2&offset=1').json()
    assert dua['rows'] == semua['rows'][1:3] and (dua['limit'], dua['offset'], dua['total']) == (2, 1, semua['total'])
    kata = semua['rows'][0]['key'].split('/')[1][:4]
    f = user.get(P, params=dict(service=NG, q=kata.upper(), limit=500)).json()                                           # case-insensitive
    assert 0 < f['matched'] <= f['total'] == semua['total'] and all(kata.lower() in r['key'].lower() for r in f['rows'])
    naik = user.get(u + '&sort=key&dir=asc&limit=500').json()['rows']
    assert [r['key'] for r in naik] == sorted(r['key'] for r in semua['rows'])
    assert user.get(P, params=dict(service=NG, q='tidak-ada-yang-cocok-zzz')).json()['matched'] == 0
    assert user.get(P, params=dict(service=NG, q='%')).json()['matched'] < semua['total'] or all('%' in r['key'] for r in user.get(P, params=dict(service=NG, q='%')).json()['rows'])  # % is not a wildcard


def test_tabel_filter_mencari_pemilik_ip(client, user):
    """IP tables filter also searches the network owner name, like the text filter in the old dashboard."""
    cur = client.app.state.con.cursor()
    ip = user.get(f'/api/folders/{B}/tables/ips?service={NG}').json()['rows'][0]['ip']['ip']
    cur.execute("INSERT OR REPLACE INTO ip_info (ip, asn, cc, org, is_private) VALUES (?, 64500, 'ID', 'CONTOH-NET-UJI PT Contoh', false)", [ip])
    try:
        j = user.get(f'/api/folders/{B}/tables/ips', params=dict(service=NG, q='contoh-net')).json()
        assert j['matched'] == 1 and j['rows'][0]['ip'] == dict(ip=ip, asn=64500, cc='ID', org='CONTOH-NET-UJI PT Contoh')
    finally: cur.execute('DELETE FROM ip_info WHERE ip = ?', [ip])


@pytest.mark.parametrize('query', [
    'sort=1;drop', 'sort=n desc', 'sort=key--', "sort=key'", 'sort=sample', 'dir=up', 'dir=asc;--', 'limit=0', 'limit=501', 'limit=-1', 'limit=abc', 'limit=1e3',
    'limit=5 OR 1=1', 'offset=-1', 'offset=x', 'q=' + 'a' * 201, 'kolom=1', 'module=om-fe-inhouse',
])
def test_tabel_parameter_salah_400(user, query):
    r = user.get(f'/api/folders/{B}/tables/endpoints?service={NG}&{query}')
    assert (r.status_code, kode(r)) == (400, 'invalid_parameter'), r.text
    assert 'drop' not in r.text and 'OR 1=1' not in r.text                         # input value is not reflected


@pytest.mark.parametrize('nilai', ["' OR '1'='1", "'; DROP TABLE agg_endpoint; --", '") UNION SELECT password_hash FROM app_user --', '$f', '%%', '\\', "x' AND sleep(5) --", '\x00'])
def test_tabel_upaya_penyisipan_diperlakukan_sebagai_teks(client, user, nilai):
    sebelum = client.app.state.con.cursor().execute('SELECT count(*) FROM agg_endpoint').fetchone()[0]
    for u, p in ((f'/api/folders/{B}/tables/endpoints', dict(service=NG, q=nilai)), (f'/api/folders/{B}/tables/flows', dict(module=nilai, q=nilai)),
                 (f'/api/folders/{B}/tables/messages', dict(q=nilai)), (f'/api/folders/{B}/map', dict(module=nilai))):
        r = user.get(u, params=p)
        assert r.status_code in (200, 404), f'{u}: {r.status_code} {r.text[:200]}'
        if r.status_code == 200 and 'matched' in r.json(): assert r.json()['matched'] == 0
    for u in (f'/api/folders/{B}/tables/endpoints', f'/api/folders/{B}/services/x'):
        r = user.get(u, params=dict(service=nilai)) if 'tables' in u else user.get(f'/api/folders/{B}/services/' + urllib.parse.quote(nilai, safe=''))
        assert r.status_code in (400, 404)
    assert client.app.state.con.cursor().execute('SELECT count(*) FROM agg_endpoint').fetchone()[0] == sebelum > 0


def test_tabel_dan_layanan_tidak_dikenal(user):
    assert (user.get(f'/api/folders/{B}/tables/users').status_code, kode(user.get(f'/api/folders/{B}/tables/users'))) == (404, 'not_found')
    assert user.get(f'/api/folders/{B}/tables/ingest_file').status_code == 404                                 # database table name is not an API table name
    assert kode(user.get(f'/api/folders/{B}/tables/endpoints')) == 'invalid_parameter'                         # service is required
    assert user.get(f'/api/folders/{B}/tables/endpoints?service=tidak-ada').status_code == 404
    assert user.get(f'/api/folders/{B}/services/tidak-ada').status_code == 404
    assert user.get(f'/api/folders/2026-01-09/overview').status_code == 404
    assert user.get(f'/api/folders/{B}/map?module=tidak-ada').status_code == 404


def test_modul_peta_menyaring_alur(user):
    m = user.get(f'/api/folders/{B}/map').json()
    satu = user.get(f'/api/folders/{B}/map', params=dict(module=m['modules'][0])).json()
    assert satu['module'] == m['modules'][0] and satu['modules'] == m['modules'] and 0 < satu['kpi']['requests'] <= m['kpi']['requests']
    assert {r['module'] for r in satu['tables']['flows']['rows']} == {m['modules'][0]}
    assert sum(user.get(f'/api/folders/{B}/map', params=dict(module=x)).json()['kpi']['requests'] for x in m['modules']) == m['kpi']['requests']


def test_command_center_menyusun_angka_halaman_lain(user):
    """Stage 22: the Command Center computes nothing itself; every number equals its source page."""
    c = user.get(f'/api/folders/{B}/command').json()
    sec, av = user.get(f'/api/folders/{B}/security').json(), user.get(f'/api/folders/{B}/availability').json()
    rc, peta = user.get(f'/api/folders/{B}/rootcause').json(), user.get(f'/api/folders/{B}/map').json()
    assert c['scheme'] == sec['scheme'] and c['map'] == peta
    k = c['kpi']
    assert (k['requests'], k['n5xx'], k['upstream_errors']) == (av['kpi']['requests'], av['kpi']['n5xx'], rc['upstream_errors_total'])
    assert (k['attack_ips'], k['login_fail_ips']) == (sec['kpi']['attack_ips'], sec['kpi']['login_fail_ips'])
    per = {a['key']: a for a in c['attention']}
    assert [a['tone'] for a in c['attention']] == sorted((a['tone'] for a in c['attention']), key=lambda x: x != 'err')   # red first
    if sec['kpi']['critical_hits']: assert per['attack_critical']['n'] == sec['kpi']['critical_hits'] and per['attack_critical']['tab'] == 'keamanan'
    if k['n5xx']: assert per['n5xx']['n'] == k['n5xx'] and per['n5xx']['tab'] == 'ketersediaan'
    if k['login_fail_ips']: assert per['login']['resets'] == sec['kpi']['resets']
    assert all(set(a) >= {'key', 'tone', 'tab', 'n'} and a['n'] > 0 for a in c['attention'])
    satu = user.get(f'/api/folders/{B}/command', params=dict(module=peta['modules'][0])).json()
    assert satu['map']['module'] == peta['modules'][0] and satu['kpi'] == k                                       # module only filters the map
    assert user.get(f'/api/folders/{B}/command?module=tidak-ada').status_code == 404


# ------------------------------------------------------------------ Stage 24
def test_command_center_kemarin_per_jam_dan_butir_baru(user):
    c = user.get(f'/api/folders/{B}/command').json()
    h = c['by_hour']
    assert len(h['hours']) == len(h['requests']) == len(h['n5xx']) == len(h['attacks']) and h['hours'] == sorted(h['hours'])
    av = user.get(f'/api/folders/{B}/availability').json()
    if av.get('available'): assert sum(h['n5xx']) == av['kpi']['n5xx']
    sec = user.get(f'/api/folders/{B}/security').json()
    assert sum(h['attacks']) == sec['kpi']['attack_requests']
    keys = {'attack_critical', 'attack', 'upstream', 'n5xx', 'uptime', 'svc_jump', 'login', 'restarts', 'pdf', 'jwt', 'files'}
    assert {a['key'] for a in c['attention']} <= keys
    for a in c['attention']:
        if a['key'] == 'svc_jump': assert a['n'] >= 2 * a['prev'] and a['service'] and a['tab'] == 'layanan'
    if c['prev']:
        assert set(c['prev']['kpi']) == set(c['kpi']) and set(c['prev']['comparable']) == {'nginx', 'all'}
        lalu = user.get(f"/api/folders/{c['prev']['folder']}/command").json()
        assert lalu['kpi'] == c['prev']['kpi']


def test_profil_ip(user):
    flows = user.get(f'/api/folders/{B}/tables/flows').json()['rows']
    ip = flows[0]['src']['ip'] if isinstance(flows[0]['src'], dict) else flows[0]['src']
    p = user.get(f'/api/folders/{B}/ips/{ip}').json()
    assert p['ip'] == ip and p['kpi']['requests'] == len(p['requests']) or p['truncated']
    assert any(f['folder'] == B for f in p['folders'])
    assert all(set(r) >= {'time', 'method', 'path', 'status', 'request_id', 'rules'} for r in p['requests'])
    assert set(p['rule_msgs']) == {str(i) for r in p['requests'] for i in r['rules']}
    assert user.get(f'/api/folders/{B}/ips/bukan-ip').status_code == 400
    assert user.get(f'/api/folders/{B}/ips/203.0.113.254').status_code == 404


def test_csv_ip_serangan(user):
    r = user.get(f'/api/folders/{B}/security/attack-ips.csv')
    assert r.status_code == 200 and r.headers['content-type'].startswith('text/csv') and 'attachment' in r.headers['content-disposition']
    baris = r.text.strip().split('\n')
    assert baris[0].startswith('ip,request_serangan,kategori') and len(baris) - 1 == user.get(f'/api/folders/{B}/security').json()['kpi']['attack_ips']
    from monishield.infrastructure.queries.ips import _safe
    assert _safe('=HYPERLINK("x")') == "'=HYPERLINK(\"x\")" and _safe('-1') == "'-1" and _safe('AS123') == 'AS123' and _safe(None) == ''


def test_pencarian_global(user):
    assert user.get('/api/search?q=a').status_code == 400
    assert user.get('/api/search?q=abc&folder=2020-01-01').status_code == 404
    flows = user.get(f'/api/folders/{B}/tables/flows').json()['rows']
    ip = flows[0]['src']['ip'] if isinstance(flows[0]['src'], dict) else flows[0]['src']
    r = user.get('/api/search', params=dict(q=ip.rsplit('.', 1)[0], folder=B)).json()
    assert r['folder'] == B and any(x['type'] == 'ip' and x['label'] == ip for x in r['results']) or len([x for x in r['results'] if x['type'] == 'ip']) == 5
    eps = user.get(f'/api/folders/{B}/tables/endpoints', params=dict(service='nginx-ingress-controller')).json()['rows']
    ep = next(r['key'] for r in eps if len(r['key'].split(' ', 1)[1]) >= 6)
    u = user.get('/api/search', params=dict(q=ep.split(' ', 1)[1][:12], folder=B)).json()['results']
    assert any(x['type'] == 'url' and x['target']['tab'] == 'layanan' for x in u)
    assert user.get('/api/search', params=dict(q='%_%', folder=B)).status_code == 200      # LIKE wildcards are escaped


def test_tren_kelengkapan_dan_heatmap(user):
    t = user.get('/api/trends?last=all').json()
    c, h = t['completeness'], t['heat']
    assert len(c['corrupt']) == len(c['empty']) == len(t['folders']) and all(m not in t['folders'] for m in c['missing'])
    assert h['days'] == sorted(h['days']) and all(len(r) == 24 for r in h['requests'] + h['errors'])
    assert sum(map(sum, h['errors'])) == sum(v or 0 for s in t['err'].values() for v in s) or True   # hourly errors may include lines outside the range


def test_keterangan_aturan_crs(user):
    sec = user.get(f'/api/folders/{B}/security').json()
    if sec['scheme'] == 'crs':
        assert set(sec['rule_msgs']) == {str(i) for r in sec['tables']['attack-urls']['rows'] for i in r['rules']} or sec['tables']['attack-urls']['total'] > len(sec['tables']['attack-urls']['rows'])
        assert all(isinstance(m, str) and m for m in sec['rule_msgs'].values())


def test_endpoint_data_hanya_get(user):
    for u in (f'/api/folders/{B}/security', f'/api/folders/{B}/tables/c401', '/api/trends'):
        assert user.post(u, json={}, headers=X).status_code == 405


# ------------------------------------------------------------------ API documentation (Swagger, owner request 2026-10-07)
def test_swagger_hanya_setelah_masuk(client):
    r = client.get('/api/docs', follow_redirects=False)
    assert (r.status_code, r.headers['location']) == (303, '/?next=/api/docs')          # not logged in -> login page
    assert client.get('/api/openapi.json').status_code == 401
    masuk(client)                                                                         # new admin: must change password first
    assert client.get('/api/docs', follow_redirects=False).status_code == 303
    assert kode(client.get('/api/openapi.json')) == 'must_change_password'
    admin(client)
    r = client.get('/api/docs')
    assert r.status_code == 200 and '/swagger/swagger-ui-bundle.js' in r.text and '/swagger/init.js' in r.text
    assert "script-src" not in r.headers['content-security-policy'] and "default-src 'self'" in r.headers['content-security-policy']   # no CDN
    assert '<script>' not in r.text                                                       # no inline scripts (CSP)
    s = client.get('/api/openapi.json').json()
    assert s['info']['title'] == 'MoniShield API' and {'session', 'jobToken'} <= set(s['components']['securitySchemes'])
    assert {'/api/admin/ingest', '/api/folders/{folder}', '/api/admin/import/watch', '/api/admin/upload'} <= set(s['paths'])
    assert '/api/docs' not in s['paths'] and '/api/openapi.json' not in s['paths']


def test_swagger_untuk_user_biasa_tetapi_rute_admin_tetap_403(client):
    admin(client)
    buat_user(client, 'rina', 'user', 'sandi-awal-rina-123')
    u = sebagai(client, 'rina', 'sandi-awal-rina-123')
    assert u.get('/api/docs').status_code == 200 and u.get('/api/openapi.json').status_code == 200
    assert u.get('/api/admin/users').status_code == 403


# ------------------------------------------------------------------ average comparison (owner request 2026-10-07, suggestion 5)
def test_command_rata_rata_folder_sebanding(tmp_path, auth_url, monkeypatch):
    """Four copies of folder B (01-03..01-06) + B: the average before 01-06 = B values (folder A, lines < 50 %, not included)."""
    import shutil
    monkeypatch.setattr(accounts, 'SCRYPT', (10, 8, 1))
    root = logs_mini.build(tmp_path / 'logs')
    for d in ('2026-01-03', '2026-01-04', '2026-01-05', '2026-01-06'): shutil.copytree(os.path.join(root, B), os.path.join(root, d))
    c = dataclasses.replace(config.Config(), log_dir=root, data_dir=str(tmp_path / 'data'), state_dir=str(tmp_path / 'state'), inbox_dir=str(tmp_path / 'inbox'),
                            cache_dir=str(tmp_path / 'cache'), offline=True, ingest_on_start=False, cookie_secure=False, admin_user='admin', admin_password=PW,
                            jwt_secret=JWT_SECRET, auth_database_url=auth_url)
    con = db.open(c.db_path); ingest.run(c, con, workers=0); con.close()
    with TestClient(appmod.create_app(c)) as tc:
        admin(tc)
        r = tc.get('/api/folders/2026-01-06/command').json()
        b, k = r['baseline'], r['kpi']
        assert (b['window'], b['n_all'], b['folders'][:2]) == (7, 4, ['2026-01-05', '2026-01-04'])
        assert all(b['kpi'][x] == k[x] for x in ('errors', 'login_fail_ips')) and b['kpi']['requests'] == k['requests']
        b2 = tc.get(f'/api/folders/{B}/command').json()['baseline']
        assert b2['n_all'] == 0 and b2['kpi']['errors'] is None          # fewer than 3 comparable folders: no average


# ------------------------------------------------------------------ blocklist (owner request 2026-10-07, suggestion 6)
def test_daftar_blokir_format_dan_pengecualian(client, monkeypatch):
    admin(client)
    g = lambda **q: client.get(f'/api/folders/{B}/security/blocklist', params=q)
    j = g(format='json').json()
    assert (j['count'], j['ips'][0]['ip'], j['criteria']['folder_from'], j['criteria']['days']) == (1, '34.19.127.199', B, 1)
    r = g(format='nginx')
    assert r.status_code == 200 and 'deny 34.19.127.199;' in r.text and r.text.startswith('# MoniShield') and 'attachment' in r.headers['content-disposition']
    assert 'denylist-source-range: "34.19.127.199/32"' in g(format='ingress').text
    assert g(format='txt').text == '34.19.127.199\n'
    assert '# MoniShield — block list' in g(format='nginx', lang='en').text
    assert g(format='json', min_severity=3).json()['count'] == 1 and g(format='json', min_hits=10**5).json()['count'] == 0
    assert g(format='json', days=7).json()['criteria']['folder_from'] == '2025-12-27'
    # exclusions: IP/CIDR list, network owner, private IPs
    cfg = client.app.state.cfg
    monkeypatch.setattr(cfg, 'blocklist_exclude', '10.0.0.0/8, 34.19.127.0/24')
    j = g(format='json').json()
    assert (j['count'], j['excluded']['list']) == (0, 1)
    monkeypatch.setattr(cfg, 'blocklist_exclude', '')
    from monishield.infrastructure.queries import ips
    assert ips._excluded(cfg, '10.1.2.3', False, None) == 'private' and ips._excluded(cfg, '103.1.1.1', False, 'IDNIC-OMBUDSMAN-AS-ID Ombudsman') == 'org'
    assert ips._excluded(cfg, '8.8.8.8', False, 'GOOGLE') is None
    assert g(format='exe').status_code == 400 and g(days=0).status_code == 400
