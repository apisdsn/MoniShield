"""Analysis Settings API (stage 62): roles, what Auto picks, saving without a restart, the test of rules on a folder, suggestions."""
import os, tomllib

from fastapi.testclient import TestClient

from monishield.domain import analysis as an
from test_log_formats_page import site, signed_in, ok, err   # noqa: F401  (the fixture and the encrypted-call helpers)
from test_wire import WEB

BASE = '/api/v1/admin/analysis'


def test_only_admins_may_use_the_api(site):
    assert site.post(BASE + '/view', headers=WEB).status_code == 401
    b = signed_in(site)
    assert b.call('POST', '/api/v1/admin/users', dict(username='rina', display_name='Rina', role='user', password='rina-initial-password-123')).status_code in (200, 201)
    other = TestClient(site.app)
    assert other.post('/api/v1/auth/login', json=dict(username='rina', password='rina-initial-password-123'), headers=WEB).status_code == 200
    other.post('/api/v1/me/password', json=dict(old_password='rina-initial-password-123', new_password='rina-next-password-12345'), headers=WEB)
    for method, path, body in (('POST', '/view', None), ('PUT', '', dict(source='s3', settings={})), ('POST', '/test', dict(source='s3')), ('POST', '/suggest', dict(source='s3'))):
        assert other.request(method, BASE + path, json=body, headers=WEB).status_code == 403, (method, path)
    assert site.get(BASE).status_code in (404, 405)


def test_view_shows_what_auto_picks_encrypted(site):
    b = signed_in(site)
    d = ok(b, 'POST', BASE + '/view')
    s3 = d['sources']['s3']
    assert d['file']['exists'] is False and s3['settings'] == dict(access_log='auto', app_logs='auto', request_id='auto', business=[])
    assert s3['access']['service'] == 'monishield-https-1' and s3['access']['format'] == 'caddy-json' and s3['access']['chosen'] is False
    assert s3['app_logs'] == ['portfolio-api-1'] and s3['request_id']['access'] == [0, s3['request_id']['access'][1]]
    assert d['sources']['kafka']['access'] is None and d['sources']['collector']['folder'] is None and 'request_id' in d['id_fields']


def test_save_writes_the_file_and_is_used_without_a_restart(site):
    b = signed_in(site)
    path = site.app.state.analysisfile.path
    bad = err(b, 'PUT', BASE, dict(source='s3', settings=dict(business=[dict(name='x', service='a', match='request')])))
    assert bad['code'] == 'invalid_analysis' and bad['message'].endswith('.') and not os.path.exists(path)
    assert err(b, 'PUT', BASE, dict(source='tape', settings={}))['code'] == 'invalid_parameter'
    rule = dict(name='Sign-ins', service='monishield-https-1', match='request', method='POST', path='/api/v1/login', status='4xx')
    d = ok(b, 'PUT', BASE, dict(source='s3', settings=dict(request_id='trace_id', business=[rule])))
    assert d['file']['exists'] and d['sources']['s3']['settings']['business'][0]['name'] == 'Sign-ins'
    assert d['sources']['s3']['counts'] == {'Sign-ins': 1}
    assert an.current('s3').request_id == 'trace_id'
    assert an.parse(tomllib.load(open(path, 'rb'))) == an.all_current()
    assert [f for f in os.listdir(os.path.dirname(path)) if f.endswith('.tmp')] == []
    ok(b, 'PUT', BASE, dict(source='collector', settings=dict(access_log='x')))
    assert an.current('s3').request_id == 'trace_id' and an.current('collector').access_log == 'x'   # one source does not reset another
    assert any(a['action'] == 'analysis.save' for a in site.app.state.auth.audit_list(20)[1])
    ok(b, 'PUT', BASE, dict(source='s3', settings={}))
    assert an.current('s3').default


def test_the_chosen_access_log_changes_the_http_cards(site):
    b = signed_in(site)
    ok(b, 'PUT', BASE, dict(source='s3', settings=dict(access_log='portfolio-api-1')))
    assert ok(b, 'POST', BASE + '/view')['sources']['s3']['access'] is None   # that service has no requests: nothing to show, nothing invented
    ok(b, 'PUT', BASE, dict(source='s3', settings={}))
    assert ok(b, 'POST', BASE + '/view')['sources']['s3']['access']['service'] == 'monishield-https-1'


def test_rules_are_tested_on_a_folder_without_saving(site):
    b = signed_in(site)
    rules = [dict(name='Logins', service='monishield-https-1', match='request', method='POST', path='/api/v1/login', status='4xx'),
             dict(name='Bad gateways', service='monishield-https-1', match='request', status='502'),
             dict(name='Anything under api', service='monishield-https-1', match='request', path='/api/*'),
             dict(name='Quiet', service='portfolio-api-1', match='log_line', text='no such text')]
    d = ok(b, 'POST', BASE + '/test', dict(source='s3', business=rules))
    assert d['folder'] == site.today and d['counts'] == {'Logins': 1, 'Bad gateways': 1, 'Anything under api': 1, 'Quiet': 0}
    assert not os.path.exists(site.app.state.analysisfile.path) and an.current('s3').default
    assert err(b, 'POST', BASE + '/test', dict(source='s3', business=[dict(name='x')]))['code'] == 'invalid_analysis'
    assert err(b, 'POST', BASE + '/test', dict(source='s3', business=[], folder='1999-01-01'), 404)['code'] == 'not_found'
    assert ok(b, 'POST', BASE + '/test', dict(source='kafka', business=rules[:1]))['counts'] == {'Logins': 0}


def test_suggestions_are_the_successful_post_endpoints(site):
    b = signed_in(site)
    assert ok(b, 'POST', BASE + '/suggest', dict(source='s3'))['suggestions'] == []   # the only POST of the sample failed (401)
    con = site.app.state.sources['s3'].con
    for n in range(3):
        con.execute("INSERT INTO http_access (file_id, line_no, folder, service, ts_utc, ip, method, path, path_key, status) VALUES (999, ?, ?, 'monishield-https-1', now()::TIMESTAMP, '203.0.113.7', 'POST', '/api/v1/orders', '/api/v1/orders', 201)", [n, site.today])
    d = ok(b, 'POST', BASE + '/suggest', dict(source='s3'))
    assert [s['rule']['path'] for s in d['suggestions']] == ['/api/v1/orders'] and d['suggestions'][0]['count'] == 3
    r = d['suggestions'][0]['rule']
    assert (r['method'], r['status'], r['service'], r['name']) == ('POST', '2xx', 'monishield-https-1', 'Orders')
    ok(b, 'PUT', BASE, dict(source='s3', settings=dict(business=[r])))
    assert ok(b, 'POST', BASE + '/suggest', dict(source='s3'))['suggestions'] == []   # already a rule
    assert ok(b, 'POST', BASE + '/suggest', dict(source='collector'))['suggestions'] == []
