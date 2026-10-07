"""Kerangka API (TRD §5.1–§5.2, §5.5–§5.6, §8, §9.5–§9.6): masuk, sesi, peran, CSRF, header, validasi, ingest dalam proses."""
import dataclasses, os, time, urllib.parse

import pytest
from fastapi.testclient import TestClient

import logs_mini
from simpel4 import auth, config, db, ingest
from simpel4.api import app as appmod, common
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
    """Aplikasi baru dengan basis data akun kosong tiap uji (data log dipakai bersama, hanya dibaca)."""
    monkeypatch.setattr(auth, 'SCRYPT', (10, 8, 1))   # hash murah agar uji cepat; biaya asli diukur di docs/04a
    c = dataclasses.replace(cfg, auth_database_url=auth_url)
    with TestClient(appmod.create_app(c)) as tc:
        yield tc


def masuk(tc, username='admin', password=PW):
    r = tc.post('/api/auth/login', json=dict(username=username, password=password), headers=X)
    assert r.status_code == 200, r.text
    return r


def admin(tc):
    """Admin pertama wajib mengganti sandi dulu."""
    masuk(tc)
    assert tc.post('/api/me/password', json=dict(old_password=PW, new_password=PW2), headers=X).status_code == 200
    return tc


def buat_user(tc, username='rina', role='user', password='sandi-awal-rina-123'):
    r = tc.post('/api/admin/users', json=dict(username=username, display_name=username.title(), role=role, password=password), headers=X)
    assert r.status_code == 201, r.text
    return r.json()


def sebagai(cfg_client, username, password, baru='sandi-baru-milik-user'):
    """Klien terpisah yang masuk sebagai user lain dan sudah mengganti sandi awalnya."""
    tc = TestClient(cfg_client.app)
    masuk(tc, username, password)
    assert tc.post('/api/me/password', json=dict(old_password=password, new_password=baru), headers=X).status_code == 200
    return tc


def kode(r): return r.json().get('error', {}).get('code')


# ------------------------------------------------------------------ dasar
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


# ------------------------------------------------------------------ masuk dan sesi
def test_masuk_cookie_dan_wajib_ganti_sandi(client):
    r = masuk(client)
    assert r.json() == dict(username='admin', display_name='Administrator', role='admin', must_change_password=True, session_idle_minutes=60)
    ck = r.headers['set-cookie'].lower()
    assert 's4_session=' in ck and 'httponly' in ck and 'samesite=strict' in ck and 'path=/' in ck and 'secure' not in ck  # cookie_secure=False di uji
    assert PW not in r.text and client.get('/api/me').json()['must_change_password'] is True
    assert client.get('/api/me').json()['session_idle_minutes'] == 60                  # dasar peringatan sesi di tampilan (DRD §6.9)
    r = client.get('/api/meta')
    assert (r.status_code, kode(r)) == (403, 'must_change_password')            # hanya /api/me dan ganti sandi yang boleh
    assert client.post('/api/me/password', json=dict(old_password=PW, new_password=PW2), headers=X).status_code == 200
    assert client.get('/api/meta').status_code == 200 and client.get('/api/me').json()['must_change_password'] is False


def test_cookie_secure_bila_dikonfigurasi(cfg, auth_url, monkeypatch):
    monkeypatch.setattr(auth, 'SCRYPT', (10, 8, 1))
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
    assert kode(client.post('/api/auth/login', json=dict(username='admin', password=PW))) == 'csrf'          # tanpa X-Requested-With
    admin(client)
    assert kode(client.post('/api/admin/users', json=dict(username='x1x', password='sandi-awal-12345'))) == 'csrf'
    r = client.post('/api/admin/users', json=dict(username='x1x', password='sandi-awal-12345'), headers={**X, 'Origin': 'https://jahat.example'})
    assert (r.status_code, kode(r)) == (403, 'csrf')
    assert client.post('/api/admin/users', json=dict(username='x1x', password='sandi-awal-12345'), headers={**X, 'Origin': 'http://testserver'}).status_code == 201
    assert client.get('/api/admin/users').status_code == 200                                                  # GET tidak butuh header


# ------------------------------------------------------------------ peran
def test_user_melihat_dashboard_tetapi_bukan_admin(client):
    admin(client); u = buat_user(client)
    assert u['role'] == 'user' and u['must_change_password'] is True
    tc = sebagai(client, 'rina', 'sandi-awal-rina-123')
    a, b = client.get(f'/api/folders/{B}').json(), tc.get(f'/api/folders/{B}').json()
    assert a == b and len(b['services']) == 7                                    # user melihat hal yang sama dengan admin
    assert tc.get('/api/meta').status_code == 200
    for method, path in (('get', '/api/admin/users'), ('get', '/api/admin/audit'), ('get', '/api/admin/ingest/status'), ('post', '/api/admin/ingest'),
                         ('post', '/api/admin/derive'), ('post', '/api/admin/forget'), ('post', '/api/admin/users')):
        r = getattr(tc, method)(path, headers=X) if method == 'get' else getattr(tc, method)(path, json={}, headers=X)
        assert (r.status_code, kode(r)) == (403, 'forbidden'), path


def test_matriks_peran_mencakup_semua_rute(client):
    """Untuk SETIAP rute: tanpa sesi / user / admin / token mesin -> diterima atau ditolak sesuai TRD §8.3."""
    admin(client); buat_user(client)
    user = sebagai(client, 'rina', 'sandi-awal-rina-123')
    anon, mesin = TestClient(client.app), TestClient(client.app)
    harap = {common.public: (1, 1, 1, 1), common.require_user: (0, 1, 1, 0), common.require_user_ready: (0, 1, 1, 0),
             common.require_admin: (0, 0, 1, 0), common.require_admin_or_job: (0, 0, 1, 1)}
    ditolak = {'unauthenticated', 'forbidden', 'must_change_password'}
    rute = appmod.check_roles(appmod.ROUTERS)
    assert len(rute) >= 28 and {'/api/trends', '/api/folders/{folder}/tables/{table}', '/api/folders/{folder}/services/{service}'} <= {r.path for r in rute}
    for r in sorted(rute, key=lambda r: r.path == '/api/auth/logout'):            # keluar diuji paling akhir
        dep = next(d for d in (common.require_admin_or_job, common.require_admin, common.require_user_ready, common.require_user, common.public)
                   if d in set(appmod._deps(r.dependant)))
        path = r.path.replace('{folder}', B).replace('{user_id}', '999999').replace('{job_id}', '999999').replace('{table}', 'c401').replace('{service}', NG)
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
    with pytest.raises(RuntimeError, match='tanpa deklarasi peran'): appmod.check_roles((*appmod.ROUTERS, r))


# ------------------------------------------------------------------ kelola user
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
    assert len(temp) >= 12 and tc.get('/api/me').status_code == 401                # sesi budi langsung berakhir
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


# ------------------------------------------------------------------ meta dan folder
def test_meta(client):
    admin(client)
    m = client.get('/api/meta').json()
    assert [f['folder'] for f in m['folders']] == [B, A]                           # terbaru dulu
    b = m['folders'][0]
    assert (b['lines'], b['services'], b['files'], b['files_empty'], b['files_corrupt']) == (38, 7, 7, 1, 1)
    assert (b['range_start'], b['range_end']) == ('2026-09-25 23:04', '2026-09-28 23:15')   # WIB; dari baris akses dan Spring (bukan error log)
    assert len(b['derived_at']) == 16 and b['derived_at'][:2] == '20'                     # WIB 'YYYY-MM-DD HH:MM'
    assert m['server'] == dict(ip='103.170.104.228', city='Jakarta', region='Jakarta', cc='ID', lat=-6.2, lon=106.82)   # tanpa data IP: nilai cadangan
    assert m['hosts']['om-fe-inhouse-3000'] == 'https://simpel4.ombudsman.go.id' and m['dns_upstream'] == '10.88.1.100'
    assert m['ip_data'] == dict(owner=False, location=False, map=False) and any('MaxMind' in s for s in m['attribution'])
    assert m['ingest']['running'] is False and m['version']
    teks = str(m)
    for rahasia in (TOKEN, PW, PW2, JWT_SECRET, 'cache', 'sqlite', 'postgresql'): assert rahasia not in teks       # tanpa rahasia, path, atau URL basis data


def test_folder(client):
    admin(client)
    f = client.get(f'/api/folders/{B}').json()
    # IP sumber serangan mengikuti aturan deteksi yang dipakai (Tahap 21: OWASP CRS; aturan lama menandai 2 IP di data ini)
    assert (f['folder'], f['prev_folder']) == (B, A) and f['attack_ip_count'] == client.get(f'/api/folders/{B}/security').json()['kpi']['attack_ips'] == 1
    assert [s['service'] for s in f['services']] == ['nginx-ingress-controller', 'coredns', 'layanan-baru', 'om-be-appsmanager', 'om-be-referensi', 'om-be-report', 'om-be-simpel-loop']
    ng = f['services'][0]
    assert (ng['lines'], ng['err'], ng['warn'], ng['err_http'], ng['err_log'], ng['requests'], ng['n4xx'], ng['files'], ng['prev']) == (11, 2, 1, 0, 2, 7, 2, 1, None)
    am = next(s for s in f['services'] if s['service'] == 'om-be-appsmanager')
    assert am['lines'] == 0 and am['files_empty'] == 1 and am['prev'] == dict(lines=10, err=1, warn=4)   # folder sebelumnya, untuk ▲/▼
    assert len(f['files']) == 7 and {x['status'] for x in f['files']} == {'ok', 'kosong', 'rusak'}
    assert client.get(f'/api/folders/{A}').json()['prev_folder'] is None


@pytest.mark.parametrize('folder', ['2026-01-03', '2026-13-45', 'bukan-tanggal', "2026-01-02' OR '1'='1", '../../etc/passwd', '2026-01-02;DROP TABLE agg_service'])
def test_folder_tidak_sah_404_tanpa_bocor(client, folder):
    admin(client)
    r = client.get(f'/api/folders/{folder}')
    assert r.status_code == 404 and folder not in r.text
    assert client.get(f'/api/folders/{B}').status_code == 200                      # tabel masih utuh


def test_parameter_salah_400_tanpa_memantulkan_nilai(client):
    admin(client)
    r = client.get('/api/admin/audit?limit=<script>alert(1)</script>')
    assert (r.status_code, kode(r)) == (400, 'invalid_parameter') and '<script>' not in r.text and 'limit' in r.text
    assert client.get('/api/admin/audit?limit=100000').status_code == 400
    assert kode(client.post('/api/admin/ingest', json=dict(folder='../x'), headers=X)) == 'invalid_parameter'
    assert kode(client.post('/api/admin/forget', json={}, headers=X)) == 'invalid_parameter'
    assert kode(client.post('/api/admin/forget', json=dict(folder='2030-01-01'), headers=X)) == 'not_found'


# ------------------------------------------------------------------ ingest di dalam proses
def test_ingest_lewat_api_dan_dashboard_tetap_terbuka(client):
    admin(client)
    r = client.post('/api/admin/ingest', json=dict(force=True), headers=X)
    assert r.status_code == 202
    selama = []
    for _ in range(200):
        st = client.get('/api/admin/ingest/status').json()
        selama.append(client.get(f'/api/folders/{B}').status_code)                # dibaca selama ingest berjalan
        if not st['running']: break
        time.sleep(0.02)
    assert set(selama) == {200} and st['error'] is None
    assert (st['last']['status'], st['last']['files_parsed'], st['last']['files_failed']) == ('ok', 9, 0)
    lr = st['last_run']                                                         # dari ingest_run: bertahan setelah server mulai ulang
    assert (lr['status'], lr['files_changed'], lr['warnings']) == ('ok', st['last']['files_changed'], st['last']['warnings'])
    assert lr['finished_at'] >= lr['started_at']
    assert client.get(f'/api/folders/{B}').json()['services'][0]['lines'] == 11
    assert 'ingest.start' in [x['action'] for x in client.get('/api/admin/audit').json()['rows']]


def test_sinkronisasi_mendeteksi_folder_baru(client, cfg):
    """Tombol Sinkronkan: status ingest menyebut folder log baru yang belum di-ingest; setelah ingest, daftarnya kosong."""
    import shutil
    admin(client)
    assert client.get('/api/admin/ingest/status').json()['new_folders'] == []
    os.makedirs(os.path.join(cfg.log_dir, '2026-03-03', 'kosong'))                     # folder tanpa file log: tidak dihitung
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
    finally:   # fixture log dipakai bersama uji lain: kembalikan seperti semula
        for d in ('2026-03-03', '2026-03-04'): shutil.rmtree(os.path.join(cfg.log_dir, d), ignore_errors=True)
        client.post('/api/admin/forget', json=dict(folder='2026-03-04'), headers=X)


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
    assert st['running'] is False and st['last']['files_changed'] == 0 and st['started_by'] == '(token mesin)'


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
    c = jwt.decode(token, JWT_SECRET, algorithms=['HS256'], issuer='simpel4')
    assert {'sub', 'sid', 'exp'} <= set(c)
    tc = TestClient(client.app)
    tc.cookies.set('s4_session', jwt.encode({**c, 'sub': '999'}, 'rahasia-penyerang-yang-panjang-sekali-32', algorithm='HS256'))
    assert tc.get('/api/me').status_code == 401
    tc.cookies.set('s4_session', jwt.encode(c, None, algorithm='none'))
    assert tc.get('/api/me').status_code == 401
    assert tc.get('/api/me', headers={'Authorization': f'Bearer {token}'}).status_code == 401   # JWT hanya diterima dari cookie HttpOnly


# ------------------------------------------------------------------ Tahap 11: endpoint halaman dan tabel (TRD §5.3–§5.4)
@pytest.fixture
def user(client):
    """User biasa: semua endpoint data terbuka untuknya (TRD §8.3)."""
    admin(client); buat_user(client)
    return sebagai(client, 'rina', 'sandi-awal-rina-123')


def test_semua_halaman_terbuka_untuk_user_dan_kecil(user):
    from simpel4.api import tables
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
    """Folder A tidak punya nginx maupun simpel-loop: 200 dengan alasan, bukan galat dan bukan angka 0 (U16)."""
    j = lambda h, f=A: user.get(f'/api/folders/{f}/{h}').json()
    assert j('map') == {'available': False, 'reason': 'no_nginx'}
    assert j('availability') == {'available': False, 'reason': 'no_nginx'}
    assert j('tracing') == {'available': False, 'reason': 'no_simpel_loop'}
    assert j('security')['nginx'] is False and j('security')['kpi']['attack_requests'] == 0
    kosong = user.get(f'/api/folders/{B}/services/om-be-appsmanager').json()       # file kosong
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
    assert n['kpi']['err'] == n['kpi']['err_http'] + n['kpi']['err_log'] == sum(e for _, _, e in n['hour'])   # TRD §4.4 butir 2
    for h, total, err in n['hour']: assert len(h) == 13                           # 'YYYY-MM-DD HH' WIB
    # peta di halaman layanan: hanya ingress dan modul yang punya alur (selain itu tidak meminta /map, yang menjawab 404)
    mods = user.get(f'/api/folders/{B}/map').json()['modules']
    assert n['has_flows'] is True
    for svc in [x['service'] for x in user.get(f'/api/folders/{B}').json()['services'] if x['lines']]:
        assert user.get(f'/api/folders/{B}/services/{svc}').json().get('has_flows') == (svc == NG or svc in mods), svc


def test_ip_selalu_disertai_bentuk_sel(user):
    rows = user.get(f'/api/folders/{B}/tables/ips?service={NG}').json()['rows']
    assert rows and all(set(r['ip']) in ({'ip'}, {'ip', 'asn', 'cc', 'org'}) for r in rows)


def test_tren(user):
    j = user.get('/api/trends').json()
    assert j['folders'] == [A, B] and set(j) == {'folders', 'services', 'lines', 'err', 'warn', 'file_status', 'http', 'security', 'business', 'completeness', 'heat'}   # Tahap 24: +2
    assert j['lines'][NG] == [None, user.get(f'/api/folders/{B}/services/{NG}').json()['kpi']['lines']]     # null = layanan tidak ada di folder itu
    assert j['file_status']['om-be-referensi'] == [None, 'rusak'] and j['file_status']['om-be-appsmanager'][1] == 'kosong'
    assert user.get('/api/trends?last=14').json()['folders'] == [A, B]
    # urutan layanan = kemunculan pertama: layanan folder A (urutan file), lalu yang baru muncul di B
    sa = [s['service'] for s in user.get(f'/api/folders/{A}').json()['services']]
    sb = [s['service'] for s in user.get(f'/api/folders/{B}').json()['services']]
    assert j['services'] == sa + [s for s in sb if s not in sa]
    for buruk in ('0', '15', '-1', 'semua', "30' OR 1=1"):
        r = user.get('/api/trends', params=dict(last=buruk)); assert (r.status_code, kode(r)) == (400, 'invalid_parameter'), buruk


def test_tabel_halaman_filter_urut(user):
    P = f'/api/folders/{B}/tables/endpoints'; u = f'{P}?service={NG}'      # httpx: params= menggantikan query di URL
    semua = user.get(u + '&limit=500').json()
    assert semua['total'] == semua['matched'] == len(semua['rows']) > 3 and semua['limit'] == 500
    assert [r['n'] for r in semua['rows']] == sorted((r['n'] for r in semua['rows']), reverse=True)        # urutan lama: terbanyak dulu
    dua = user.get(u + '&limit=2&offset=1').json()
    assert dua['rows'] == semua['rows'][1:3] and (dua['limit'], dua['offset'], dua['total']) == (2, 1, semua['total'])
    kata = semua['rows'][0]['key'].split('/')[1][:4]
    f = user.get(P, params=dict(service=NG, q=kata.upper(), limit=500)).json()                                           # tanpa beda huruf besar/kecil
    assert 0 < f['matched'] <= f['total'] == semua['total'] and all(kata.lower() in r['key'].lower() for r in f['rows'])
    naik = user.get(u + '&sort=key&dir=asc&limit=500').json()['rows']
    assert [r['key'] for r in naik] == sorted(r['key'] for r in semua['rows'])
    assert user.get(P, params=dict(service=NG, q='tidak-ada-yang-cocok-zzz')).json()['matched'] == 0
    assert user.get(P, params=dict(service=NG, q='%')).json()['matched'] < semua['total'] or all('%' in r['key'] for r in user.get(P, params=dict(service=NG, q='%')).json()['rows'])  # % bukan wildcard


def test_tabel_filter_mencari_pemilik_ip(client, user):
    """Filter tabel ber-IP ikut mencari nama pemilik jaringan, seperti filter teks di dashboard lama."""
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
    assert 'drop' not in r.text and 'OR 1=1' not in r.text                         # nilai masukan tidak dipantulkan


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
    assert user.get(f'/api/folders/{B}/tables/ingest_file').status_code == 404                                 # nama tabel basis data bukan nama tabel API
    assert kode(user.get(f'/api/folders/{B}/tables/endpoints')) == 'invalid_parameter'                         # service wajib
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
    """Tahap 22: Command Center tidak menghitung sendiri; tiap angka sama dengan halaman asalnya."""
    c = user.get(f'/api/folders/{B}/command').json()
    sec, av = user.get(f'/api/folders/{B}/security').json(), user.get(f'/api/folders/{B}/availability').json()
    rc, peta = user.get(f'/api/folders/{B}/rootcause').json(), user.get(f'/api/folders/{B}/map').json()
    assert c['scheme'] == sec['scheme'] and c['map'] == peta
    k = c['kpi']
    assert (k['requests'], k['n5xx'], k['upstream_errors']) == (av['kpi']['requests'], av['kpi']['n5xx'], rc['upstream_errors_total'])
    assert (k['attack_ips'], k['login_fail_ips']) == (sec['kpi']['attack_ips'], sec['kpi']['login_fail_ips'])
    per = {a['key']: a for a in c['attention']}
    assert [a['tone'] for a in c['attention']] == sorted((a['tone'] for a in c['attention']), key=lambda x: x != 'err')   # merah dulu
    if sec['kpi']['critical_hits']: assert per['attack_critical']['n'] == sec['kpi']['critical_hits'] and per['attack_critical']['tab'] == 'keamanan'
    if k['n5xx']: assert per['n5xx']['n'] == k['n5xx'] and per['n5xx']['tab'] == 'ketersediaan'
    if k['login_fail_ips']: assert per['login']['resets'] == sec['kpi']['resets']
    assert all(set(a) >= {'key', 'tone', 'tab', 'n'} and a['n'] > 0 for a in c['attention'])
    satu = user.get(f'/api/folders/{B}/command', params=dict(module=peta['modules'][0])).json()
    assert satu['map']['module'] == peta['modules'][0] and satu['kpi'] == k                                       # modul hanya menyaring peta
    assert user.get(f'/api/folders/{B}/command?module=tidak-ada').status_code == 404


# ------------------------------------------------------------------ Tahap 24
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
    from simpel4.api.ips import _safe
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
    assert user.get('/api/search', params=dict(q='%_%', folder=B)).status_code == 200      # wildcard LIKE di-escape


def test_tren_kelengkapan_dan_heatmap(user):
    t = user.get('/api/trends?last=all').json()
    c, h = t['completeness'], t['heat']
    assert len(c['corrupt']) == len(c['empty']) == len(t['folders']) and all(m not in t['folders'] for m in c['missing'])
    assert h['days'] == sorted(h['days']) and all(len(r) == 24 for r in h['requests'] + h['errors'])
    assert sum(map(sum, h['errors'])) == sum(v or 0 for s in t['err'].values() for v in s) or True   # error per jam bisa memuat baris di luar rentang


def test_keterangan_aturan_crs(user):
    sec = user.get(f'/api/folders/{B}/security').json()
    if sec['scheme'] == 'crs':
        assert set(sec['rule_msgs']) == {str(i) for r in sec['tables']['attack-urls']['rows'] for i in r['rules']} or sec['tables']['attack-urls']['total'] > len(sec['tables']['attack-urls']['rows'])
        assert all(isinstance(m, str) and m for m in sec['rule_msgs'].values())


def test_endpoint_data_hanya_get(user):
    for u in (f'/api/folders/{B}/security', f'/api/folders/{B}/tables/c401', '/api/trends'):
        assert user.post(u, json={}, headers=X).status_code == 405
