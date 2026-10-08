"""Encrypted API bodies for the web UI (owner request 2026-10-08): ECDH handshake, AES-GCM request and response bodies
bound to method + path, plain JSON still served to clients without the header, files and CSV untouched."""
import base64, dataclasses, json, os

import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from fastapi.testclient import TestClient

import logs_mini
from monishield.domain import accounts
from monishield.infrastructure import config, db, ingest, wirecrypto
from monishield.interfaces.api import app as appmod
from conftest import JWT_SECRET

PW, PW2 = 'sandi-admin-pertama', 'sandi-admin-sesudah-diganti'
WEB = {'X-Requested-With': 'monishield-web'}


@pytest.fixture(scope='module')
def base(tmp_path_factory):
    tmp = tmp_path_factory.mktemp('wire')
    c = dataclasses.replace(config.Config(), log_dir=logs_mini.build(tmp / 'logs'), data_dir=str(tmp / 'data'), state_dir=str(tmp / 'state'),
                            inbox_dir=str(tmp / 'inbox'), cache_dir=str(tmp / 'cache'), offline=True, ingest_on_start=False, cookie_secure=False,
                            admin_user='admin', admin_password=PW, jwt_secret=JWT_SECRET)
    con = db.open(c.db_path); ingest.run(c, con, workers=0); con.close()
    return c


@pytest.fixture
def tc(base, auth_url, monkeypatch):
    monkeypatch.setattr(accounts, 'SCRYPT', (10, 8, 1))
    with TestClient(appmod.create_app(dataclasses.replace(base, auth_database_url=auth_url))) as c:
        yield c


class Browser:
    """What web/src/api.js does with WebCrypto, done with the cryptography package."""

    def __init__(self, tc):
        self.tc = tc
        mine = ec.generate_private_key(ec.SECP256R1())
        pub = base64.b64encode(mine.public_key().public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)).decode()
        r = tc.post('/api/crypto/handshake', json=dict(pub=pub), headers=WEB)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d['enabled'] is True
        peer = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), base64.b64decode(d['pub']))
        self.kid, self.key = d['kid'], AESGCM(wirecrypto.derive(mine.exchange(ec.ECDH(), peer)))

    def call(self, method, path, body=None, kid=None):
        h = dict(WEB, **{'X-MS-Enc': kid or self.kid})
        data = None
        if body is not None:
            nonce = os.urandom(12)
            data = nonce + self.key.encrypt(nonce, json.dumps(body).encode(), f'req {method} {path.split("?")[0]}'.encode())
            h['Content-Type'] = 'application/octet-stream'
        return self.tc.request(method, path, content=data, headers=h)

    def json(self, r, method, path):
        assert r.headers['x-ms-enc'] == '1' and r.headers['content-type'] == 'application/octet-stream'
        raw = r.content
        return json.loads(self.key.decrypt(raw[:12], raw[12:], f'resp {method} {path.split("?")[0]}'.encode()))


def test_encrypted_login_and_pages(tc, base):
    b = Browser(tc)
    r = b.call('POST', '/api/auth/login', dict(username='admin', password=PW))
    assert r.status_code == 200 and PW.encode() not in r.content and b'admin' not in r.content   # response body is ciphertext too
    assert b.json(r, 'POST', '/api/auth/login')['username'] == 'admin'
    r = b.call('POST', '/api/me/password', dict(old_password=PW, new_password=PW2))
    assert r.status_code == 200, r.content
    r = b.call('GET', '/api/meta')
    assert r.status_code == 200 and b.json(r, 'GET', '/api/meta')['folders']
    # errors from the application are encrypted as well
    r = b.call('GET', '/api/folders/1999-01-01/overview')
    assert r.status_code == 404 and b.json(r, 'GET', '/api/folders/1999-01-01/overview')['error']['code'] == 'not_found'


def test_plain_clients_still_work(tc):
    r = tc.post('/api/auth/login', json=dict(username='admin', password=PW), headers=WEB)
    assert r.status_code == 200 and r.headers['content-type'].startswith('application/json') and 'x-ms-enc' not in r.headers


def test_unknown_key_and_tampered_body_rejected(tc):
    b = Browser(tc)
    r = b.call('GET', '/api/me', kid='tidak-dikenal')
    assert r.status_code == 400 and r.json()['error']['code'] == 'enc_key_unknown'
    # a body encrypted for one endpoint cannot be replayed on another (method + path are bound)
    nonce = os.urandom(12)
    blob = nonce + b.key.encrypt(nonce, b'{"username": "admin", "password": "x"}', b'req POST /api/auth/login')
    r = tc.post('/api/me/password', content=blob, headers=dict(WEB, **{'X-MS-Enc': b.kid, 'Content-Type': 'application/octet-stream'}))
    assert r.status_code == 400 and r.json()['error']['code'] == 'enc_invalid'
    r = tc.post('/api/crypto/handshake', json=dict(pub='bukan-kunci'), headers=WEB)
    assert r.status_code == 400 and r.json()['error']['code'] == 'enc_invalid'


def test_files_untouched_and_switch_off(tc, base, auth_url):
    b = Browser(tc)
    b.call('POST', '/api/auth/login', dict(username='admin', password=PW))
    b.call('POST', '/api/me/password', dict(old_password=PW, new_password=PW2))
    folder = b.json(b.call('GET', '/api/meta'), 'GET', '/api/meta')['folders'][0]['folder']
    r = b.call('GET', f'/api/folders/{folder}/security/attack-ips.csv')
    assert r.status_code == 200 and r.headers['content-type'].startswith('text/csv') and 'x-ms-enc' not in r.headers
    tc.app.state.cfg.api_encryption = False
    r = tc.post('/api/crypto/handshake', json=dict(pub='x'), headers=WEB)
    assert r.json() == dict(enabled=False)


def test_key_store_is_bounded():
    w = wirecrypto.WireCrypto(max_keys=3)
    pub = lambda: base64.b64encode(ec.generate_private_key(ec.SECP256R1()).public_key().public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)).decode()
    kids = [w.handshake(pub())[0] for _ in range(5)]
    with pytest.raises(wirecrypto.WireError): w.seal(kids[0], b'x', b'')
    assert w.open(kids[-1], w.seal(kids[-1], b'isi', b'a'), b'a') == b'isi'
