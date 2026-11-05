"""API versions (docs/08-architecture.md, "API versions"): every endpoint is under /api/v1; the unversioned browser paths still
work for one release (with Deprecation) and the old collector paths do not."""
import os

import pytest

from monishield.interfaces.api import versioning
from test_wire import base, tc, Browser, PW, WEB   # noqa: F401  (fixtures and helpers of the wire tests)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def paths(app):
    """Every path the app serves: app.routes holds the included routers lazily, so their own routes are read (prefix included)."""
    out = set()
    for r in app.routes:
        if hasattr(r, 'original_router'): out.update(x.path for x in r.original_router.routes)
        else: out.add(getattr(r, 'path', ''))
    return out


def test_every_api_route_is_under_v1_except_health(tc):
    api = sorted(p for p in paths(tc.app) if p.startswith('/api'))
    assert api, 'no /api routes found'
    outside = [p for p in api if not p.startswith('/api/v1/') and p != '/api/health']
    assert outside == [], f'routes outside /api/v1: {outside}'
    assert '/api/health' in api and '/api/v1/collector/logs' in api and '/api/v1/collector/enroll' in api
    assert '/api/v1/docs' in api and '/api/v1/live/map' in api and '/api/v1/public/map' in api


def test_the_other_unversioned_paths_are_the_downloads_and_the_pages(tc):
    other = sorted(p for p in paths(tc.app) if not p.startswith('/api'))
    assert [p for p in other if p.startswith('/collector')] == ['/collector/install.ps1', '/collector/install.sh']


def test_health_is_not_versioned_and_not_deprecated(tc):
    r = tc.get('/api/health')
    assert r.status_code == 200 and 'deprecation' not in r.headers
    assert tc.get('/api/v1/health').status_code == 404


def test_old_browser_path_works_with_deprecation_header(tc):
    new = tc.get('/api/v1/public/map')
    old = tc.get('/api/public/map')
    assert old.status_code == 200 and old.json() == new.json()
    assert old.headers['deprecation'] == 'true' and old.headers['link'] == '</api/v1/public/map>; rel="successor-version"'
    assert 'deprecation' not in new.headers
    assert tc.get('/api/docs', follow_redirects=False).headers['deprecation'] == 'true'   # a bookmark of the Swagger page


def test_old_path_keeps_session_and_errors_in_the_same_shape(tc):
    r = tc.get('/api/me')
    assert r.status_code == 401 and r.headers['deprecation'] == 'true' and r.json()['error']['code']
    assert tc.post('/api/auth/login', json=dict(username='admin', password=PW), headers=WEB).status_code == 200
    assert tc.get('/api/me').json()['username'] == 'admin'          # the cookie works on both
    assert tc.get('/api/v1/me').json()['username'] == 'admin'
    assert tc.get('/api/does-not-exist').status_code == 404


def test_old_collector_paths_are_not_aliased(tc):
    for method, path in (('POST', '/api/collector/v1/logs'), ('POST', '/api/collector/v1/metrics'), ('POST', '/api/collector/enroll'),
                         ('GET', '/api/collector/config'), ('POST', '/api/collector/logs')):
        r = tc.request(method, path, headers=WEB, json={})
        assert r.status_code == 404 and 'deprecation' not in r.headers, path
    assert versioning.successor('/api/collector/enroll') is None and versioning.successor('/api/v1/collector/enroll') is None
    assert tc.post('/api/v1/collector/enroll', json={'token': 'nope'}, headers=WEB).status_code != 404   # the new address exists


def test_successor_rules():
    s = versioning.successor
    assert s('/api/me') == '/api/v1/me' and s('/api/folders/2026-01-02/map') == '/api/v1/folders/2026-01-02/map'
    assert s('/api/health') is None and s('/api/v1/me') is None and s('/map/labels.json') is None and s('/collector/install.sh') is None
    assert s('/api') is None and s('/apix/me') is None


def test_old_tab_with_encrypted_bodies_still_works(tc):
    """An open tab (old JS) seals with the path it sends: AAD = `req POST /api/auth/login`, answer sealed with `resp POST /api/auth/login`."""
    b = Browser(tc)
    r = b.call('POST', '/api/auth/login', dict(username='admin', password=PW))
    assert r.status_code == 200 and PW.encode() not in r.content and r.headers['deprecation'] == 'true'
    assert b.json(r, 'POST', '/api/auth/login')['username'] == 'admin'
    r = b.call('POST', '/api/me/password', dict(old_password=PW, new_password='admin-password-after-change'))
    assert r.status_code == 200 and b.json(r, 'POST', '/api/me/password')
    r = b.call('GET', '/api/meta')
    assert r.status_code == 200 and b.json(r, 'GET', '/api/meta')['folders']
    assert b.call('GET', '/api/v1/meta').status_code == 200   # the same tab at the new address
    # the address is part of what is authenticated: a body sealed for the old address is refused at the new one
    import os as _os
    nonce = _os.urandom(12)
    sealed = nonce + b.key.encrypt(nonce, b'{"username":"admin","password":"x"}', b'req POST /api/auth/login')
    r = tc.post('/api/v1/auth/login', content=sealed, headers=dict(WEB, **{'X-MS-Enc': b.kid, 'Content-Type': 'application/octet-stream'}))
    assert r.status_code == 400 and r.json()['error']['code'] == 'enc_invalid'


def test_the_handshake_works_at_the_old_address_too(tc):
    import base64
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
    pub = base64.b64encode(ec.generate_private_key(ec.SECP256R1()).public_key().public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)).decode()
    r = tc.post('/api/crypto/handshake', json=dict(pub=pub), headers=WEB)
    assert r.status_code == 200 and r.json()['enabled'] is True and r.headers['deprecation'] == 'true'


def test_ingest_host_serves_only_the_collector_api_and_the_installers():
    text = open(os.path.join(ROOT, 'deploy', 'caddy', 'ingest.caddy'), encoding='utf-8').read()
    paths = [l.split(None, 2)[2:] for l in text.splitlines() if l.strip().startswith('@receiver path')]
    assert paths == [['/api/v1/collector/* /collector/install.sh /collector/install.ps1']]
    assert '/api/collector' not in text.replace('/api/v1/collector', '')       # the old address is gone
    handles = [l.strip() for l in text.splitlines() if l.strip().startswith('handle')]
    assert handles == ['handle @receiver {', 'handle {'] and 'respond 404' in text.split('handle {')[1]


def test_nothing_in_the_repository_still_calls_an_unversioned_endpoint():
    """The web app, tools, scripts and docs use /api/v1 (or /api/health); the Swagger and old-path notes name the old form in words."""
    import re
    bad = re.compile(r'(?<![\w.:-])/api/(?!v1\b|health|\)|`|\*|<|"|\'|\s|$)')
    skip = {'test_api_versions.py', 'versioning.py', 'App.svelte', '09-status.md', '08-architecture.md', 'CHANGELOG.md', '12-collector.md', 'robots.txt'}
    found = []
    for top in ('web/src', 'tools', 'deploy', 'monishield/infrastructure/assets'):
        for d, _, names in os.walk(os.path.join(ROOT, top)):
            if '__pycache__' in d or 'otelcol' in d: continue
            for n in names:
                if n in skip or not n.endswith(('.js', '.cjs', '.svelte', '.py', '.sh', '.ps1', '.caddy', '.json')): continue
                for i, line in enumerate(open(os.path.join(d, n), encoding='utf-8', errors='replace'), 1):
                    if bad.search(line): found.append(f'{os.path.relpath(os.path.join(d, n), ROOT)}:{i}: {line.strip()[:100]}')
    assert found == []
