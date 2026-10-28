"""Accounts, passwords, sessions, lockout, roles, audit (TRD §8.2–§8.3, §9.6). Units over monishield.auth, no HTTP."""
import datetime

import jwt
import pytest
from sqlalchemy import select

from monishield.domain import accounts
from monishield.infrastructure import auth
from conftest import JWT_SECRET

PW = 'sandi-yang-cukup-panjang'


@pytest.fixture
def a(auth_url):
    x = auth.Auth(auth_url, JWT_SECRET)
    yield x
    x.close()


def lines_(a, model):
    with a._tx() as s: return list(s.scalars(select(model)))


@pytest.fixture
def admin(a): return a.create_user('admin', 'Admin', 'admin', PW, must_change=False)


def test_password_is_stored_as_a_salted_hash(a, admin):
    b = a.create_user('budi', 'Budi', 'user', PW)
    u = lines_(a, auth.User)
    assert u[0].password_hash != u[1].password_hash and u[0].password_salt != u[1].password_salt   # same password, different hash and salt
    assert all(len(x.password_hash) == 32 and len(x.password_salt) == 16 and x.hash_params == '15:8:1' for x in u)
    assert all(PW.encode() not in bytes(x.password_hash) + bytes(x.password_salt) for x in u) and b['must_change_password'] is True


@pytest.mark.parametrize('username', ['ab', 'budi santoso', 'x' * 33, '', None, 'budi;drop'])
def test_invalid_username(a, username):
    with pytest.raises(auth.AuthError) as e: a.create_user(username, 'x', 'user', PW)
    assert e.value.code in ('invalid_username',)


def test_username_is_lowercased(a):
    assert a.create_user(' Budi ', 'x', 'user', PW)['username'] == 'budi'


@pytest.mark.parametrize('pw', ['pendek', 'x' * 129, '', None, 'budi.santoso'])
def test_invalid_password(a, pw):
    with pytest.raises(auth.AuthError) as e: a.create_user('budi.santoso', 'x', 'user', pw)
    assert e.value.code == 'invalid_password'


def test_duplicate_name_and_wrong_role(a, admin):
    with pytest.raises(auth.AuthError) as e: a.create_user('ADMIN', 'x', 'user', PW)
    assert e.value.code == 'username_taken' and e.value.status == 409
    with pytest.raises(auth.AuthError) as e: a.create_user('lain', 'x', 'root', PW)
    assert e.value.code == 'invalid_role'


def test_sign_in_and_sessions(a, admin):
    token, user = a.login('Admin ', PW, '1.2.3.4', 'UA')
    assert user['username'] == 'admin' and token.count('.') == 2 and a.session_user(token)['role'] == 'admin'
    ses = lines_(a, auth.Session)
    assert len(ses) == 1 and token not in str(vars(ses[0])) and (ses[0].ip, ses[0].user_agent) == ('1.2.3.4', 'UA')   # token is not stored
    assert a.session_user('token-palsu') is None and a.session_user(None) is None
    a.logout(token, user)
    assert a.session_user(token) is None


def test_same_error_for_unknown_user_and_wrong_password(a, admin):
    with pytest.raises(auth.AuthError) as e1: a.login('admin', 'sandi-salah-sekali')
    with pytest.raises(auth.AuthError) as e2: a.login('tidak-ada', 'sandi-salah-sekali')
    assert (e1.value.code, e1.value.message, e1.value.status) == (e2.value.code, e2.value.message, e2.value.status) == ('invalid_credentials', 'Wrong username or password.', 401)


def test_locked_after_five_failures(a, admin):
    for _ in range(5):
        with pytest.raises(auth.AuthError) as e: a.login('admin', 'salah-salah-salah', '9.9.9.9')
        assert e.value.status == 401
    with pytest.raises(auth.AuthError) as e: a.login('admin', PW, '9.9.9.9')       # 6th attempt: even the CORRECT password is rejected
    assert (e.value.status, e.value.code) == (429, 'too_many_attempts')
    assert a.list_users()[0]['locked'] is True


def test_rate_limit_per_ip(a, admin, monkeypatch):
    monkeypatch.setattr(auth, 'IP_MAX_FAILED', 3)
    for i in range(3):
        with pytest.raises(auth.AuthError): a.login(f'tidak-ada-{i}', 'x' * 12, '7.7.7.7')
    with pytest.raises(auth.AuthError) as e: a.login('admin', PW, '7.7.7.7')
    assert e.value.status == 429
    assert a.login('admin', PW, '8.8.8.8')[1]['username'] == 'admin'            # other IPs unaffected


def test_session_expires_by_idle_time_and_by_age(a, admin, monkeypatch):
    token, _ = a.login('admin', PW)
    original = auth.now()
    monkeypatch.setattr(auth, 'now', lambda: original + datetime.timedelta(minutes=59))
    assert a.session_user(token)                                                 # activity extends the idle timeout
    monkeypatch.setattr(auth, 'now', lambda: original + datetime.timedelta(minutes=59 + 61))
    assert a.session_user(token) is None
    monkeypatch.setattr(auth, 'now', lambda: original)
    token, _ = a.login('admin', PW)
    for jam in range(1, 12):
        monkeypatch.setattr(auth, 'now', lambda j=jam: original + datetime.timedelta(minutes=50 * j))
        assert a.session_user(token), jam
    monkeypatch.setattr(auth, 'now', lambda: original + datetime.timedelta(hours=12, minutes=1))
    assert a.session_user(token) is None                                         # 12-hour total limit even while active


def test_password_change_revokes_other_sessions(a, admin):
    t1, u = a.login('admin', PW); t2, _ = a.login('admin', PW)
    with pytest.raises(auth.AuthError) as e: a.change_password(u, 'sandi-lama-salah', 'sandi-baru-yang-panjang')
    assert e.value.code == 'wrong_password'
    with pytest.raises(auth.AuthError): a.change_password(u, PW, 'pendek')
    with pytest.raises(auth.AuthError): a.change_password(u, PW, PW)
    a.change_password(u, PW, 'sandi-baru-yang-panjang', keep_token=t1)
    assert a.session_user(t1) and a.session_user(t2) is None
    with pytest.raises(auth.AuthError): a.login('admin', PW)
    assert a.login('admin', 'sandi-baru-yang-panjang')[1]['must_change_password'] is False


def test_reset_and_disable_revoke_sessions(a, admin):
    b = a.create_user('budi', 'Budi', 'user', PW, by=admin)
    t, _ = a.login('budi', PW)
    temp = a.reset_password(b['user_id'], admin)
    assert a.session_user(t) is None and len(temp) >= 12
    t, u = a.login('budi', temp)
    assert u['must_change_password'] is True
    a.update_user(b['user_id'], admin, active=False)
    assert a.session_user(t) is None
    with pytest.raises(auth.AuthError) as e: a.login('budi', temp)
    assert e.value.code == 'invalid_credentials'                                 # inactive account: same message
    a.update_user(b['user_id'], admin, active=True)
    assert a.login('budi', temp)


def test_last_admin_is_protected(a, admin):
    for fn in (lambda: a.update_user(admin['user_id'], admin, role='user'), lambda: a.update_user(admin['user_id'], admin, active=False)):
        with pytest.raises(auth.AuthError) as e: fn()
        assert e.value.code == 'last_admin'
    with pytest.raises(auth.AuthError) as e: a.delete_user(admin['user_id'], admin)
    assert e.value.code == 'self_delete'
    second = a.create_user('admin2', 'A2', 'admin', PW, by=admin)
    with pytest.raises(auth.AuthError) as e: a.delete_user(second['user_id'], second)
    assert e.value.code == 'self_delete'
    a.update_user(admin['user_id'], second, role='user')                          # allowed: another admin still exists
    with pytest.raises(auth.AuthError) as e: a.delete_user(second['user_id'], admin)
    assert e.value.code == 'last_admin'


def test_role_change_applies_to_the_next_request(a, admin):
    b = a.create_user('budi', 'Budi', 'user', PW, by=admin)
    t, _ = a.login('budi', PW)
    assert a.session_user(t)['role'] == 'user'
    a.update_user(b['user_id'], admin, role='admin')
    assert a.session_user(t)['role'] == 'admin'                                  # no re-login, no cache


def test_first_admin_only_when_there_are_no_users(a):
    assert a.bootstrap_admin('', PW) is None and a.bootstrap_admin('admin', '') is None
    u = a.bootstrap_admin('admin', PW)
    assert u['role'] == 'admin' and u['must_change_password'] is True
    assert a.bootstrap_admin('lain', PW) is None and a.count_users() == 1


def test_audit_without_secrets(a, admin):
    b = a.create_user('budi', 'Budi', 'user', PW, by=admin, ip='1.1.1.1')
    token, _ = a.login('budi', PW, '2.2.2.2')
    with pytest.raises(auth.AuthError): a.login('budi', 'sandi-salah-rahasia', '3.3.3.3')
    temp = a.reset_password(b['user_id'], admin)
    a.update_user(b['user_id'], admin, role='admin'); a.delete_user(b['user_id'], admin)
    total, rows = a.audit_list(50)
    assert [r['action'] for r in rows][::-1] == ['user.create', 'user.create', 'login.ok', 'login.fail', 'user.reset_password', 'user.update', 'user.delete']  # the first one: admin creation by the fixture
    text = str(rows)
    assert PW not in text and temp not in text and token not in text and 'sandi-salah-rahasia' not in text
    assert rows[-2]['username'] == 'admin' and rows[-2]['ip'] == '1.1.1.1' and 'role user -> admin' in text


def test_machine_token():
    assert accounts.job_token_ok('rahasia', 'rahasia') and not accounts.job_token_ok('rahasia', 'salah')
    assert not accounts.job_token_ok('', '') and not accounts.job_token_ok('', 'apa-saja') and not accounts.job_token_ok('rahasia', None)


# ------------------------------------------------------------------ JWT
def test_jwt_contents_hold_no_secrets(a, admin):
    token, user = a.login('admin', PW)
    c = jwt.decode(token, JWT_SECRET, algorithms=['HS256'], issuer='monishield')
    assert set(c) == {'iss', 'sub', 'sid', 'iat', 'exp'} and c['sub'] == str(user['user_id'])
    assert c['exp'] - c['iat'] == 12 * 3600                                       # maximum session age
    assert jwt.get_unverified_header(token)['alg'] == 'HS256'
    assert 'admin' not in str(c) and 'role' not in c                              # role is read from the database, not from the token


def _forge(claims, secret=JWT_SECRET, alg='HS256', **header): return jwt.encode(claims, secret, algorithm=alg, headers=header or None)


def test_forged_jwt_is_rejected(a, admin):
    token, user = a.login('admin', PW)
    c = jwt.decode(token, JWT_SECRET, algorithms=['HS256'], issuer='monishield')
    assert a.session_user(token)
    assert a.session_user(_forge(c, 'rahasia-lain-yang-juga-panjang-sekali-32')) is None       # wrong signature
    assert a.session_user(jwt.encode(c, None, algorithm='none')) is None                          # alg none
    assert a.session_user(_forge(c, alg='HS512')) is None                                         # other algorithm
    assert a.session_user(token[:-3] + ('aaa' if not token.endswith('aaa') else 'bbb')) is None   # tampered
    assert a.session_user(_forge({**c, 'iss': 'lain'})) is None
    assert a.session_user(_forge({k: v for k, v in c.items() if k != 'sid'})) is None             # required claim missing
    assert a.session_user(_forge({**c, 'exp': c['iat'] - 10})) is None                            # expired
    assert a.session_user(_forge({**c, 'sid': 'sesi-yang-tidak-ada'})) is None                    # valid but its session does not exist
    for junk in ('', 'a.b.c', 'bukan-jwt', None, 123): assert a.session_user(junk) is None


def test_valid_jwt_for_another_user_is_rejected(a, admin):
    """A token with a valid signature but a swapped `sub` must not become another user."""
    a.create_user('budi', 'Budi', 'user', PW, by=admin)
    token, _ = a.login('budi', PW)
    c = jwt.decode(token, JWT_SECRET, algorithms=['HS256'], issuer='monishield')
    assert a.session_user(_forge({**c, 'sub': str(admin['user_id'])})) is None


def test_jwt_can_still_be_revoked(a, admin):
    """Session validity is checked in the database: even an unexpired JWT dies after logout."""
    token, user = a.login('admin', PW)
    a.logout(token, user)
    assert jwt.decode(token, JWT_SECRET, algorithms=['HS256'], issuer='monishield')  # signature still valid
    assert a.session_user(token) is None


def test_short_jwt_secret_is_rejected(auth_url):
    with pytest.raises(ValueError, match='at least 32'): auth.Auth(auth_url, 'pendek')


def test_without_a_secret_no_sign_in(auth_url):
    x = auth.Auth(auth_url)                      # how the command line opens it: account management only
    x.create_user('admin', 'A', 'admin', PW)
    with pytest.raises(RuntimeError, match='S4_JWT_SECRET'): x.login('admin', PW)
    assert x.session_user('apa.saja.token') is None
    x.close()


def test_database_url_is_redacted():
    assert auth.redact_url('postgresql+psycopg://monishield:sandi-rahasia@db:5432/monishield') == 'postgresql+psycopg://monishield:***@db:5432/monishield'
    assert auth.redact_url('sqlite:////data/auth.db') == 'sqlite:////data/auth.db'
