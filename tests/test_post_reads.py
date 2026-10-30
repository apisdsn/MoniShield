"""Reads whose parameters can hold personal data have a POST form (owner request 2026-10-30): the web UI sends the search
text, IP, email, request ID or file name in the (encrypted) JSON body instead of the URL. Same answers as the GET forms."""
from test_api import B, NG, X, admin, as_user, cfg, client, make_user   # noqa: F401  (fixtures and helpers of the API tests)


def user_client(client):
    admin(client); make_user(client)
    return as_user(client, 'rina', 'rina-initial-password-123')


def test_post_forms_answer_like_the_get_forms(client):
    u = user_client(client)
    ip = '66.66.66.213'
    pairs = [
        (u.get('/api/search', params=dict(q=ip, folder=B)), u.post('/api/search', json=dict(q=ip, folder=B), headers=X)),
        (u.get(f'/api/folders/{B}/tables/ips', params=dict(service=NG, q='66.66', limit=5)),
         u.post(f'/api/folders/{B}/tables/ips', json=dict(service=NG, q='66.66', limit=5), headers=X)),
        (u.get(f'/api/folders/{B}/ips/{ip}'), u.post(f'/api/folders/{B}/ip-profile', json=dict(ip=ip), headers=X)),
        (u.get(f'/api/folders/{B}/raw', params=dict(q='GET', limit=3)), u.post(f'/api/folders/{B}/raw', json=dict(q='GET', limit=3), headers=X)),
    ]
    for g, p in pairs:
        assert g.status_code == p.status_code == 200, (g.text, p.text)
        a, b = g.json(), p.json()
        a.pop('seconds', None); b.pop('seconds', None)
        assert a == b
    row = pairs[-1][1].json()['rows'][0]
    ctx = u.post(f'/api/folders/{B}/raw/context', json=dict(file=row['file'], line=row['line'], n=1), headers=X)
    assert ctx.status_code == 200 and ctx.json()['entry']['text'] == row['text']


def test_raw_download_as_json_is_audited(client):
    u = user_client(client)
    r = u.post(f'/api/folders/{B}/raw/download', json=dict(q='GET', services=NG), headers=X)
    assert r.status_code == 200 and r.headers['content-type'].startswith('application/json')
    j = r.json()
    assert j['filename'] == f'monishield-raw-{B}.log' and j['entries'] >= 3 and j['text'].startswith(f'{B}/') and ': ' in j['text']
    audit = [x for x in client.get('/api/admin/audit').json()['rows'] if x['action'] == 'raw.download']
    assert audit and audit[0]['username'] == 'rina' and 'q=GET' in audit[0]['detail']


def test_post_forms_check_the_body_and_the_session(client):
    u = user_client(client)
    for path, body in (('/api/search', dict(q=['x'])), (f'/api/folders/{B}/ip-profile', {}), (f'/api/folders/{B}/raw', dict(q={'a': 1}))):
        r = u.post(path, json=body, headers=X)
        assert r.status_code == 400 and r.json()['error']['code'] == 'invalid_parameter', (path, r.text)
    assert u.post('/api/search', json=dict(q='GET')).status_code == 403          # no X-Requested-With: CSRF guard
    from fastapi.testclient import TestClient
    anon = TestClient(client.app)
    assert anon.post('/api/search', json=dict(q='GET'), headers=X).status_code == 401
