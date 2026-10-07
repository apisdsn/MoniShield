"""Akun, sandi, sesi, penguncian, peran, audit (TRD §8.2–§8.3, §9.6). Unit atas monishield.auth, tanpa HTTP."""
import datetime

import jwt
import pytest
from sqlalchemy import select

from monishield import auth
from conftest import JWT_SECRET

PW = 'sandi-yang-cukup-panjang'


@pytest.fixture
def a(auth_url):
    x = auth.Auth(auth_url, JWT_SECRET)
    yield x
    x.close()


def baris(a, model):
    with a._tx() as s: return list(s.scalars(select(model)))


@pytest.fixture
def admin(a): return a.create_user('admin', 'Admin', 'admin', PW, must_change=False)


def test_sandi_disimpan_sebagai_hash_bergaram(a, admin):
    b = a.create_user('budi', 'Budi', 'user', PW)
    u = baris(a, auth.User)
    assert u[0].password_hash != u[1].password_hash and u[0].password_salt != u[1].password_salt   # sandi sama, hash dan garam berbeda
    assert all(len(x.password_hash) == 32 and len(x.password_salt) == 16 and x.hash_params == '15:8:1' for x in u)
    assert all(PW.encode() not in bytes(x.password_hash) + bytes(x.password_salt) for x in u) and b['must_change_password'] is True


@pytest.mark.parametrize('username', ['ab', 'budi santoso', 'x' * 33, '', None, 'budi;drop'])
def test_nama_user_tidak_sah(a, username):
    with pytest.raises(auth.AuthError) as e: a.create_user(username, 'x', 'user', PW)
    assert e.value.code in ('invalid_username',)


def test_nama_user_dinormalkan_ke_huruf_kecil(a):
    assert a.create_user(' Budi ', 'x', 'user', PW)['username'] == 'budi'


@pytest.mark.parametrize('pw', ['pendek', 'x' * 129, '', None, 'budi.santoso'])
def test_sandi_tidak_sah(a, pw):
    with pytest.raises(auth.AuthError) as e: a.create_user('budi.santoso', 'x', 'user', pw)
    assert e.value.code == 'invalid_password'


def test_nama_dobel_dan_peran_salah(a, admin):
    with pytest.raises(auth.AuthError) as e: a.create_user('ADMIN', 'x', 'user', PW)
    assert e.value.code == 'username_taken' and e.value.status == 409
    with pytest.raises(auth.AuthError) as e: a.create_user('lain', 'x', 'root', PW)
    assert e.value.code == 'invalid_role'


def test_masuk_dan_sesi(a, admin):
    token, user = a.login('Admin ', PW, '1.2.3.4', 'UA')
    assert user['username'] == 'admin' and token.count('.') == 2 and a.session_user(token)['role'] == 'admin'
    ses = baris(a, auth.Session)
    assert len(ses) == 1 and token not in str(vars(ses[0])) and (ses[0].ip, ses[0].user_agent) == ('1.2.3.4', 'UA')   # token tidak disimpan
    assert a.session_user('token-palsu') is None and a.session_user(None) is None
    a.logout(token, user)
    assert a.session_user(token) is None


def test_pesan_galat_sama_untuk_user_tidak_ada_dan_sandi_salah(a, admin):
    with pytest.raises(auth.AuthError) as e1: a.login('admin', 'sandi-salah-sekali')
    with pytest.raises(auth.AuthError) as e2: a.login('tidak-ada', 'sandi-salah-sekali')
    assert (e1.value.code, e1.value.message, e1.value.status) == (e2.value.code, e2.value.message, e2.value.status) == ('invalid_credentials', 'Nama user atau sandi salah.', 401)


def test_dikunci_setelah_lima_gagal(a, admin):
    for _ in range(5):
        with pytest.raises(auth.AuthError) as e: a.login('admin', 'salah-salah-salah', '9.9.9.9')
        assert e.value.status == 401
    with pytest.raises(auth.AuthError) as e: a.login('admin', PW, '9.9.9.9')       # percobaan ke-6, sandi BENAR pun ditolak
    assert (e.value.status, e.value.code) == (429, 'too_many_attempts')
    assert a.list_users()[0]['locked'] is True


def test_pembatas_per_ip(a, admin, monkeypatch):
    monkeypatch.setattr(auth, 'IP_MAX_FAILED', 3)
    for i in range(3):
        with pytest.raises(auth.AuthError): a.login(f'tidak-ada-{i}', 'x' * 12, '7.7.7.7')
    with pytest.raises(auth.AuthError) as e: a.login('admin', PW, '7.7.7.7')
    assert e.value.status == 429
    assert a.login('admin', PW, '8.8.8.8')[1]['username'] == 'admin'            # IP lain tidak terdampak


def test_sesi_habis_karena_diam_dan_karena_umur(a, admin, monkeypatch):
    token, _ = a.login('admin', PW)
    asli = auth.now()
    monkeypatch.setattr(auth, 'now', lambda: asli + datetime.timedelta(minutes=59))
    assert a.session_user(token)                                                 # aktivitas memperpanjang masa diam
    monkeypatch.setattr(auth, 'now', lambda: asli + datetime.timedelta(minutes=59 + 61))
    assert a.session_user(token) is None
    monkeypatch.setattr(auth, 'now', lambda: asli)
    token, _ = a.login('admin', PW)
    for jam in range(1, 12):
        monkeypatch.setattr(auth, 'now', lambda j=jam: asli + datetime.timedelta(minutes=50 * j))
        assert a.session_user(token), jam
    monkeypatch.setattr(auth, 'now', lambda: asli + datetime.timedelta(hours=12, minutes=1))
    assert a.session_user(token) is None                                         # batas total 12 jam walau terus aktif


def test_ganti_sandi_mencabut_sesi_lain(a, admin):
    t1, u = a.login('admin', PW); t2, _ = a.login('admin', PW)
    with pytest.raises(auth.AuthError) as e: a.change_password(u, 'sandi-lama-salah', 'sandi-baru-yang-panjang')
    assert e.value.code == 'wrong_password'
    with pytest.raises(auth.AuthError): a.change_password(u, PW, 'pendek')
    with pytest.raises(auth.AuthError): a.change_password(u, PW, PW)
    a.change_password(u, PW, 'sandi-baru-yang-panjang', keep_token=t1)
    assert a.session_user(t1) and a.session_user(t2) is None
    with pytest.raises(auth.AuthError): a.login('admin', PW)
    assert a.login('admin', 'sandi-baru-yang-panjang')[1]['must_change_password'] is False


def test_reset_dan_nonaktif_mencabut_sesi(a, admin):
    b = a.create_user('budi', 'Budi', 'user', PW, by=admin)
    t, _ = a.login('budi', PW)
    temp = a.reset_password(b['user_id'], admin)
    assert a.session_user(t) is None and len(temp) >= 12
    t, u = a.login('budi', temp)
    assert u['must_change_password'] is True
    a.update_user(b['user_id'], admin, active=False)
    assert a.session_user(t) is None
    with pytest.raises(auth.AuthError) as e: a.login('budi', temp)
    assert e.value.code == 'invalid_credentials'                                 # akun nonaktif: pesan yang sama
    a.update_user(b['user_id'], admin, active=True)
    assert a.login('budi', temp)


def test_admin_terakhir_dilindungi(a, admin):
    for fn in (lambda: a.update_user(admin['user_id'], admin, role='user'), lambda: a.update_user(admin['user_id'], admin, active=False)):
        with pytest.raises(auth.AuthError) as e: fn()
        assert e.value.code == 'last_admin'
    with pytest.raises(auth.AuthError) as e: a.delete_user(admin['user_id'], admin)
    assert e.value.code == 'self_delete'
    kedua = a.create_user('admin2', 'A2', 'admin', PW, by=admin)
    with pytest.raises(auth.AuthError) as e: a.delete_user(kedua['user_id'], kedua)
    assert e.value.code == 'self_delete'
    a.update_user(admin['user_id'], kedua, role='user')                          # boleh: masih ada admin lain
    with pytest.raises(auth.AuthError) as e: a.delete_user(kedua['user_id'], admin)
    assert e.value.code == 'last_admin'


def test_perubahan_peran_berlaku_pada_permintaan_berikutnya(a, admin):
    b = a.create_user('budi', 'Budi', 'user', PW, by=admin)
    t, _ = a.login('budi', PW)
    assert a.session_user(t)['role'] == 'user'
    a.update_user(b['user_id'], admin, role='admin')
    assert a.session_user(t)['role'] == 'admin'                                  # tanpa masuk ulang, tanpa cache


def test_admin_pertama_hanya_bila_belum_ada_user(a):
    assert a.bootstrap_admin('', PW) is None and a.bootstrap_admin('admin', '') is None
    u = a.bootstrap_admin('admin', PW)
    assert u['role'] == 'admin' and u['must_change_password'] is True
    assert a.bootstrap_admin('lain', PW) is None and a.count_users() == 1


def test_audit_tanpa_rahasia(a, admin):
    b = a.create_user('budi', 'Budi', 'user', PW, by=admin, ip='1.1.1.1')
    token, _ = a.login('budi', PW, '2.2.2.2')
    with pytest.raises(auth.AuthError): a.login('budi', 'sandi-salah-rahasia', '3.3.3.3')
    temp = a.reset_password(b['user_id'], admin)
    a.update_user(b['user_id'], admin, role='admin'); a.delete_user(b['user_id'], admin)
    total, rows = a.audit_list(50)
    assert [r['action'] for r in rows][::-1] == ['user.create', 'user.create', 'login.ok', 'login.fail', 'user.reset_password', 'user.update', 'user.delete']  # yang pertama: pembuatan admin oleh fixture
    teks = str(rows)
    assert PW not in teks and temp not in teks and token not in teks and 'sandi-salah-rahasia' not in teks
    assert rows[-2]['username'] == 'admin' and rows[-2]['ip'] == '1.1.1.1' and 'peran user -> admin' in teks


def test_token_mesin():
    assert auth.job_token_ok('rahasia', 'rahasia') and not auth.job_token_ok('rahasia', 'salah')
    assert not auth.job_token_ok('', '') and not auth.job_token_ok('', 'apa-saja') and not auth.job_token_ok('rahasia', None)


# ------------------------------------------------------------------ JWT
def test_isi_jwt_dan_tidak_memuat_rahasia(a, admin):
    token, user = a.login('admin', PW)
    c = jwt.decode(token, JWT_SECRET, algorithms=['HS256'], issuer='simpel4')
    assert set(c) == {'iss', 'sub', 'sid', 'iat', 'exp'} and c['sub'] == str(user['user_id'])
    assert c['exp'] - c['iat'] == 12 * 3600                                       # umur maksimum sesi
    assert jwt.get_unverified_header(token)['alg'] == 'HS256'
    assert 'admin' not in str(c) and 'role' not in c                              # peran dibaca dari basis data, bukan dari token


def _palsu(claims, secret=JWT_SECRET, alg='HS256', **header): return jwt.encode(claims, secret, algorithm=alg, headers=header or None)


def test_jwt_palsu_ditolak(a, admin):
    token, user = a.login('admin', PW)
    c = jwt.decode(token, JWT_SECRET, algorithms=['HS256'], issuer='simpel4')
    assert a.session_user(token)
    assert a.session_user(_palsu(c, 'rahasia-lain-yang-juga-panjang-sekali-32')) is None       # tanda tangan salah
    assert a.session_user(jwt.encode(c, None, algorithm='none')) is None                          # alg none
    assert a.session_user(_palsu(c, alg='HS512')) is None                                         # algoritma lain
    assert a.session_user(token[:-3] + ('aaa' if not token.endswith('aaa') else 'bbb')) is None   # diutak-atik
    assert a.session_user(_palsu({**c, 'iss': 'lain'})) is None
    assert a.session_user(_palsu({k: v for k, v in c.items() if k != 'sid'})) is None             # klaim wajib hilang
    assert a.session_user(_palsu({**c, 'exp': c['iat'] - 10})) is None                            # kedaluwarsa
    assert a.session_user(_palsu({**c, 'sid': 'sesi-yang-tidak-ada'})) is None                    # sah tetapi sesinya tidak ada
    for sampah in ('', 'a.b.c', 'bukan-jwt', None, 123): assert a.session_user(sampah) is None


def test_jwt_sah_untuk_user_lain_ditolak(a, admin):
    """Token yang tanda tangannya sah tetapi `sub`-nya ditukar tidak boleh menjadi user lain."""
    b = a.create_user('budi', 'Budi', 'user', PW, by=admin)
    token, _ = a.login('budi', PW)
    c = jwt.decode(token, JWT_SECRET, algorithms=['HS256'], issuer='simpel4')
    assert a.session_user(_palsu({**c, 'sub': str(admin['user_id'])})) is None


def test_jwt_tetap_bisa_dicabut(a, admin):
    """Alasan sesi diperiksa di basis data: JWT yang belum kedaluwarsa pun mati setelah keluar."""
    token, user = a.login('admin', PW)
    a.logout(token, user)
    assert jwt.decode(token, JWT_SECRET, algorithms=['HS256'], issuer='simpel4')  # tanda tangan masih sah
    assert a.session_user(token) is None


def test_rahasia_jwt_pendek_ditolak(auth_url):
    with pytest.raises(ValueError, match='minimal 32'): auth.Auth(auth_url, 'pendek')


def test_tanpa_rahasia_tidak_bisa_masuk(auth_url):
    x = auth.Auth(auth_url)                      # cara baris perintah membuka: kelola akun saja
    x.create_user('admin', 'A', 'admin', PW)
    with pytest.raises(RuntimeError, match='S4_JWT_SECRET'): x.login('admin', PW)
    assert x.session_user('apa.saja.token') is None
    x.close()


def test_url_basis_data_disamarkan():
    assert auth.redact_url('postgresql+psycopg://simpel4:sandi-rahasia@db:5432/simpel4') == 'postgresql+psycopg://simpel4:***@db:5432/simpel4'
    assert auth.redact_url('sqlite:////data/auth.db') == 'sqlite:////data/auth.db'
