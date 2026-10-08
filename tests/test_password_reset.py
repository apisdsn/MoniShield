"""Forgot password by email, user emails, the shared MoniShield letter and the mail server settings (owner request
2026-10-08). No network: smtplib.SMTP is replaced by a recorder."""
import dataclasses, re, smtplib

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from monishield.domain import accounts, letters
from monishield.infrastructure import auth as authmod, config, letter, mailer
from monishield.interfaces.api import app as appmod
from conftest import JWT_SECRET

X = {'X-Requested-With': 'uji'}
PW, PW2 = 'sandi-admin-pertama', 'sandi-admin-sesudah-diganti'
RINA_PW = 'sandi-awal-rina-123'


# ------------------------------------------------------------------ rules and letter
def test_temporary_password_mixes_all_kinds():
    seen = set()
    for _ in range(300):
        p = accounts.temp_password()
        assert len(p) == accounts.TEMP_LENGTH and p not in seen
        seen.add(p)
        for chars in (accounts.TEMP_UPPER, accounts.TEMP_LOWER, accounts.TEMP_DIGIT, accounts.TEMP_SPECIAL):
            assert sum(c in chars for c in p) >= 2
        assert not set(p) & set('0O1lI')
        accounts.check_password(p)


def test_email_rules():
    assert accounts.check_email(' Rina@Contoh.GO.id ') == 'rina@contoh.go.id'
    assert accounts.check_email('') is None and accounts.check_email(None) is None
    for bad in ('rina', 'rina@', 'a b@x.id', 'rina@x', '<rina@x.id>'):
        with pytest.raises(accounts.AuthError): accounts.check_email(bad)


def test_one_letter_layout_for_every_email():
    lt = letters.password_reset('id', 'Rina <b>', 'rina', 'Ab3$Xy7!kQ2#mN9@', 30, 'https://monishield.contoh.go.id')
    html, body = letter.render_html(lt, 'cid-x'), letter.render_text(lt)
    assert 'cid:cid-x' in html and 'MoniShield' in html and 'Ab3$Xy7!kQ2#mN9@' in html and 'Rina &lt;b&gt;' in html   # escaped
    assert 'Kata sandi sementara: Ab3$Xy7!kQ2#mN9@' in body and 'Berlaku selama 30 menit' in body and 'https://monishield.contoh.go.id' in body
    m = letter.message(lt, 'MoniShield <noreply@contoh.go.id>', 'rina@contoh.go.id')
    kinds = [p.get_content_type() for p in m.walk()]
    assert kinds == ['multipart/alternative', 'text/plain', 'multipart/related', 'text/html', 'image/png']
    assert m['Auto-Submitted'] == 'auto-generated'
    # the same layout for an OTP code and a notification
    otp = letters.otp('en', 'Rina', '483920', 10, 'confirm your sign-in')
    assert otp['code']['value'] == '483920' and 'confirm your sign-in' in letter.render_text(otp)
    n = letters.notification('id', 'Lonjakan di folder 2026-01-06', '• Respons 5xx: 120\nBuka: https://x.id/#/peta?folder=2026-01-06')
    assert n['items'] == ['Respons 5xx: 120'] and n['button']['url'] == 'https://x.id/#/peta?folder=2026-01-06'


# ------------------------------------------------------------------ API
class Outbox(list):
    pass


@pytest.fixture
def outbox(monkeypatch):
    box = Outbox()
    box.fail = None

    class FakeSMTP:
        def __init__(self, host, port, timeout=None, **kw): box.host = (host, port)
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def starttls(self, context=None): pass
        def login(self, u, p): pass
        def send_message(self, m):
            if box.fail: raise box.fail
            box.append(m)
    monkeypatch.setattr(smtplib, 'SMTP', FakeSMTP)
    return box


@pytest.fixture
def make(tmp_path, auth_url, monkeypatch):
    monkeypatch.setattr(accounts, 'SCRYPT', (10, 8, 1))
    monkeypatch.setattr(authmod, 'RESET_GAP_S', 0)

    def build(**over):
        base = dict(log_dir=str(tmp_path / 'logs'), data_dir=str(tmp_path / 'data'), state_dir=str(tmp_path / 'state'),
                    inbox_dir=str(tmp_path / 'inbox'), cache_dir=str(tmp_path / 'cache'), offline=True, ingest_on_start=False, cookie_secure=False,
                    admin_user='admin', admin_password=PW, jwt_secret=JWT_SECRET, auth_database_url=auth_url,
                    smtp_host='smtp.contoh.go.id', smtp_port=587, smtp_from='MoniShield <noreply@contoh.go.id>', dashboard_url='https://ms.contoh.go.id')
        c = dataclasses.replace(config.Config(), **dict(base, **over))
        tc = TestClient(appmod.create_app(c))
        tc.__enter__()
        assert tc.post('/api/auth/login', json=dict(username='admin', password=PW), headers=X).status_code == 200
        assert tc.post('/api/me/password', json=dict(old_password=PW, new_password=PW2), headers=X).status_code == 200
        r = tc.post('/api/admin/users', json=dict(username='rina', display_name='Rina', role='user', password=RINA_PW, email='Rina@Contoh.go.id'), headers=X)
        assert r.status_code == 201 and r.json()['email'] == 'rina@contoh.go.id'
        tc.post('/api/auth/logout', headers=X)
        return tc
    yield build


def temp_from(m):
    return re.search(r'(?:Kata sandi sementara|Temporary password): (\S+)', m.get_body(('plain',)).get_content()).group(1)


def test_forgot_password_flow(make, outbox):
    tc = make()
    assert tc.get('/api/auth/options').json() == dict(forgot_password=True)
    r = tc.post('/api/auth/forgot', json=dict(login='rina', lang='id'), headers=X)
    assert r.status_code == 200 and r.json() == dict(sent=True, minutes=30)
    tc.app.state.resets.wait()
    assert len(outbox) == 1 and outbox[0]['To'] == 'rina@contoh.go.id' and outbox[0]['Subject'] == 'Kata sandi sementara akun MoniShield Anda'
    temp = temp_from(outbox[0])
    assert temp not in r.text and temp not in tc.app.state.auth.audit_list(50)[1].__repr__()
    # the old password still works and cancels the pending reset: asking for resets cannot lock anyone out
    assert tc.post('/api/auth/login', json=dict(username='rina', password=RINA_PW), headers=X).status_code == 200
    tc.post('/api/auth/logout', headers=X)
    assert tc.post('/api/auth/login', json=dict(username='rina', password=temp), headers=X).status_code == 401
    # a new request by email address; the temporary password signs in once and forces a new password
    tc.post('/api/auth/forgot', json=dict(login='RINA@contoh.go.id', lang='en'), headers=X); tc.app.state.resets.wait()
    assert outbox[-1]['Subject'] == 'Your MoniShield temporary password'
    temp = temp_from(outbox[-1])
    r = tc.post('/api/auth/login', json=dict(username='rina', password=temp), headers=X)
    assert r.status_code == 200 and r.json()['must_change_password'] is True
    assert tc.post('/api/me/password', json=dict(old_password=temp, new_password='sandi-baru-rina-milik-sendiri'), headers=X).status_code == 200
    tc.post('/api/auth/logout', headers=X)
    assert tc.post('/api/auth/login', json=dict(username='rina', password=RINA_PW), headers=X).status_code == 401
    audit = repr(tc.app.state.auth.audit_list(100))
    assert 'password.forgot' in audit and 'password.reset_used' in audit and temp not in audit


def test_same_answer_for_unknown_accounts_and_limits(make, outbox):
    tc = make()
    for login in ('tidak-ada', 'orang@lain.id', 'admin'):   # admin has no email
        r = tc.post('/api/auth/forgot', json=dict(login=login), headers=X)
        assert r.status_code == 200 and r.json()['sent'] is True
    tc.app.state.resets.wait()
    assert len(outbox) == 0
    for _ in range(2): assert tc.post('/api/auth/forgot', json=dict(login='rina'), headers=X).status_code == 200
    r = tc.post('/api/auth/forgot', json=dict(login='rina'), headers=X)   # the 6th request from one address within 15 minutes
    assert r.status_code == 429 and r.json()['error']['code'] == 'too_many_attempts'
    assert tc.post('/api/auth/forgot', json=dict(login='rina')).status_code == 403   # CSRF header required


def test_expired_and_failed_email(make, outbox):
    tc = make()
    tc.post('/api/auth/forgot', json=dict(login='rina'), headers=X); tc.app.state.resets.wait()
    temp = temp_from(outbox[-1])
    with tc.app.state.auth.engine.begin() as c: c.execute(text("UPDATE password_reset SET expires_at = '2000-01-01 00:00:00'"))
    assert tc.post('/api/auth/login', json=dict(username='rina', password=temp), headers=X).status_code == 401
    outbox.fail = smtplib.SMTPAuthenticationError(535, b'no')
    tc.post('/api/auth/forgot', json=dict(login='rina'), headers=X); tc.app.state.resets.wait()
    with tc.app.state.auth.engine.begin() as c: assert c.execute(text('SELECT count(*) FROM password_reset')).scalar() == 0   # withdrawn
    assert 'email not sent: The mail server rejected the username or password.' in repr(tc.app.state.auth.audit_list(20))


def test_without_mail_server(make, outbox):
    tc = make(smtp_host='')
    assert tc.get('/api/auth/options').json() == dict(forgot_password=False)
    r = tc.post('/api/auth/forgot', json=dict(login='rina'), headers=X)
    assert r.status_code == 503 and r.json()['error']['code'] == 'mail_not_configured'


def test_user_email_unique_editable_and_migrated(make, outbox, auth_url):
    tc = make()
    tc.post('/api/auth/login', json=dict(username='admin', password=PW2), headers=X)
    r = tc.post('/api/admin/users', json=dict(username='budi', role='user', password='sandi-awal-budi-123', email='rina@contoh.go.id'), headers=X)
    assert r.status_code == 409 and r.json()['error']['code'] == 'email_taken'
    assert tc.post('/api/admin/users', json=dict(username='budi', role='user', password='sandi-awal-budi-123', email='bukan email'), headers=X).json()['error']['code'] == 'invalid_email'
    rid = next(u['user_id'] for u in tc.get('/api/admin/users').json()['users'] if u['username'] == 'rina')
    assert tc.patch(f'/api/admin/users/{rid}', json=dict(email='rina.baru@contoh.go.id'), headers=X).json()['email'] == 'rina.baru@contoh.go.id'
    assert tc.patch(f'/api/admin/users/{rid}', json=dict(email=''), headers=X).json()['email'] is None
    # an account database from before emails existed gets the column on start
    a = tc.app.state.auth
    with a.engine.begin() as c:
        c.execute(text('DROP INDEX ux_app_user_email')); c.execute(text('ALTER TABLE app_user DROP COLUMN email'))
    b = authmod.Auth(auth_url, JWT_SECRET)
    assert all('email' in u for u in b.list_users())
    b.close()


def test_mail_server_settings_and_test_email(make, outbox):
    tc = make(smtp_host='')
    tc.post('/api/auth/login', json=dict(username='admin', password=PW2), headers=X)
    r = tc.put('/api/admin/config', json=dict(smtp_host='mail.contoh.go.id', smtp_port='465', smtp_security='ssl', smtp_username='ms',
                                              smtp_password='rahasia-smtp-01', smtp_from='MoniShield <ms@contoh.go.id>'), headers=X)
    assert r.status_code == 200, r.text
    v = r.json()['smtp']
    assert v['smtp_host']['value'] == 'mail.contoh.go.id' and v['smtp_password'] == dict(set=True, source='file', env='SMTP_PASSWORD')
    assert 'rahasia-smtp-01' not in r.text
    assert tc.put('/api/admin/config', json=dict(smtp_from='bukan alamat'), headers=X).status_code == 400
    r = tc.post('/api/admin/config/test', json=dict(kind='smtp'), headers=X)   # admin has no email yet
    assert r.status_code == 400 and r.json()['error']['code'] == 'mail_no_recipient'
    tc.app.state.cfg.smtp_security = 'starttls'   # the recorder speaks plain SMTP only
    r = tc.post('/api/admin/config/test', json=dict(kind='smtp', to='ops@contoh.go.id', lang='en'), headers=X)
    assert r.status_code == 200 and outbox[-1]['Subject'] == 'MoniShield email test' and outbox[-1]['To'] == 'ops@contoh.go.id'
    assert tc.get('/api/auth/options').json() == dict(forgot_password=True)
