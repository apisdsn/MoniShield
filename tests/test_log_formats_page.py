"""Log Formats page (docs/11-log-formats.md, step 1e): TOML writer, override rules, suggestion and test of a format, and the admin API
(roles, validation, saving puts the rules in use without a restart, read today again, encrypted bodies)."""
import dataclasses, datetime, json, os, tomllib

import pytest
from fastapi.testclient import TestClient

import logs_mini
from monishield.domain import accounts, format_check as fc, log_formats as lf, retention
from monishield.infrastructure import config, db, ingest
from monishield.interfaces.api import app as appmod
from conftest import JWT_SECRET
from test_wire import PW, PW2, Browser, WEB

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FORMATS = os.path.join(ROOT, 'tests', 'fixtures', 'formats')
CASES = json.load(open(os.path.join(ROOT, 'tests', 'fixtures', 'override_cases.json')))


def sample(name): return open(os.path.join(FORMATS, name), encoding='utf-8').read().splitlines()


# ---- TOML writer
def test_the_written_file_reads_back_to_the_same_rules():
    for rules in (lf.rules_from(tomllib.load(open(os.path.join(ROOT, 'log-formats.example.toml'), 'rb'))),
                  lf.default_rules(__import__('monishield.domain.services', fromlist=['x']).Profile())):
        text = lf.dumps(rules)
        assert lf.rules_from(tomllib.loads(text)) == rules
    odd = (lf.Rule('host-1/a?b*', 'regex', 'app', pattern='^(?P<time>\\S+) "(?P<message>.*)" \\u00e9 \x7f$', time_format='%d/%m/%Y %H:%M:%S', multiline='^\\[',
                   levels=(('SEVERE web', 'ERROR'),), features=('logins', 'pdf')),
           lf.Rule('x', 'json', 'http', fields=(('path', 'req.url'), ('status', 'res.status[0]')), duration_unit='us', ip_header='x-forwarded-for'),
           lf.Rule('y', 'events-json', 'app', tag='APP'), lf.Rule('z', 'auto', None), lf.Rule('*', 'plain', 'app'))
    assert lf.rules_from(tomllib.loads(lf.dumps(odd))) == odd


def test_the_last_rule_must_be_the_catch_all():
    ok = (lf.Rule('a', 'plain', 'app'), lf.Rule('*', 'plain', 'app'))
    assert lf.check_saveable(ok) == ok
    for bad in ((), (lf.Rule('a', 'plain', 'app'),), (lf.Rule('*', 'plain', 'app'), lf.Rule('b/*', 'plain', 'app'))):
        with pytest.raises(lf.FormatError): lf.check_saveable(bad)


# ---- one service from the Services tab (the same cases run in tests/test_logformats.mjs)
@pytest.mark.parametrize('case', CASES, ids=[c['name'] for c in CASES])
def test_override(case):
    rules = tuple(lf.Rule(m, f, lf.PRESETS[f]) for m, f in case['rules'])
    ns, svc, fmt = case['set']
    got = lf.override(rules, ns, svc, fmt)
    assert [(r.match, r.format) for r in got] == [tuple(x) for x in case['expect']]
    assert lf.match(got, ns, svc).format == fmt


def test_override_refuses_what_a_rule_cannot_say():
    with pytest.raises(lf.FormatError): lf.override((lf.Rule('*', 'plain', 'app'),), None, 'a b', 'json')
    with pytest.raises(lf.FormatError): lf.override((lf.Rule('*', 'plain', 'app'),), None, 'a', 'regex')


# ---- suggestion and test
@pytest.mark.parametrize('name,best', [('caddy-json.log', 'caddy-json'), ('nginx-combined.log', 'nginx-combined'), ('apache-combined.log', 'nginx-combined'),
                                       ('logfmt.log', 'logfmt'), ('pino.json.log', 'json'), ('syslog.log', 'syslog'), ('plain.log', 'plain')])
def test_suggestion_per_sample(name, best):
    s = fc.suggest(sample(name), lf.Rule('*', 'spring-boot', 'app'))
    assert s['suggested']['format'] == best and s['better'] is True


def test_suggestion_is_not_better_when_the_current_format_reads_as_well():
    s = fc.suggest(sample('syslog.log'), lf.Rule('*', 'syslog', 'app'))
    assert s['suggested']['format'] == 'syslog' and s['better'] is False
    assert fc.suggest(sample('plain.log'), lf.Rule('*', 'plain', 'app'))['better'] is False
    assert fc.suggest([], lf.Rule('*', 'plain', 'app')) is None


def test_plain_is_suggested_only_when_nothing_reads_half():
    junk = ['nothing here', 'still nothing', 'free text again', 'and more words']
    s = fc.suggest(junk, lf.Rule('*', 'spring-boot', 'app'))
    assert s['suggested']['format'] == 'plain' and s['current']['read_pct'] == 0.0 and s['better'] is True


def test_an_access_log_format_beats_a_generic_one_that_reads_more():
    s = fc.suggest(sample('caddy-json.log'), lf.Rule('*', 'plain', 'app'))   # certificate lines are JSON too
    assert s['suggested'] == dict(format='caddy-json', kind='http', read_pct=50.0)


def test_test_gives_rows_and_the_unread_lines():
    t = fc.test(lf.Rule('*', 'caddy-json', 'http'), sample('caddy-json.log'))
    assert (t['read'], t['total']) == (3, 6) and len(t['rows']) == 5
    ok = [r for r in t['rows'] if r['read']]
    assert ok[0]['ip'] and ok[0]['method'] and ok[0]['path'].startswith('/') and isinstance(ok[0]['status'], int) and ok[0]['time'].startswith('2022-')
    assert [r['read'] for r in t['rows']][-1] is False and t['rows'][-1]['text'] == 'not json at all'
    wrong = fc.test(lf.Rule('*', 'spring-boot', 'app'), sample('caddy-json.log'))
    assert wrong['read'] == 0


# ---- the API
@pytest.fixture
def site(tmp_path, auth_url, monkeypatch):
    monkeypatch.setattr(accounts, 'SCRYPT', (10, 8, 1))
    today = retention.today_local(datetime.datetime.now(datetime.timezone.utc)).isoformat()
    root = str(tmp_path / 'logs')
    caddy = '\n'.join(sample('caddy-json.log')) + '\n'
    logs_mini.write(logs_mini.log_path(root, today, 'host1', 'monishield-https-1', 'p1'), caddy)
    logs_mini.write(logs_mini.log_path(root, today, 'host1', 'portfolio-api-1', 'p1'), '\n'.join(sample('logfmt.log')) + '\n')
    cfg = dataclasses.replace(config.Config(), log_dir=root, data_dir=str(tmp_path / 'data'), state_dir=str(tmp_path / 'state'), inbox_dir=str(tmp_path / 'inbox'),
                              cache_dir=str(tmp_path / 'cache'), offline=True, ingest_on_start=False, cookie_secure=False, admin_user='admin',
                              admin_password=PW, jwt_secret=JWT_SECRET, auth_database_url=auth_url)
    cfg.log_formats_file = str(tmp_path / 'state' / 'log-formats.toml')
    con = db.open(cfg.db_path)
    rules = lf.rules_from(dict(service=[dict(match='monishield-https-1', format='caddy-json'), dict(match='*', format='spring-boot')]))
    os.makedirs(cfg.state_dir); open(cfg.log_formats_file, 'w').write(lf.dumps(rules))
    lf.use(rules); ingest.run(cfg, con, workers=0); con.close()
    with TestClient(appmod.create_app(cfg)) as c:
        c.today = today
        yield c
    lf.use(None)


def signed_in(tc):
    b = Browser(tc)
    assert b.call('POST', '/api/v1/auth/login', dict(username='admin', password=PW)).status_code == 200
    assert b.call('POST', '/api/v1/me/password', dict(old_password=PW, new_password=PW2)).status_code == 200
    return b


def ok(b, method, path, body=None, status=200):
    r = b.call(method, path, body)
    assert r.status_code == status, (method, path, r.status_code, r.content[:300])
    assert r.headers['x-ms-enc'] == '1' and r.headers['content-type'] == 'application/octet-stream'
    for text in (b'monishield-https-1', b'caddy-json', b'"rules"', b'handled request'): assert text not in r.content, (path, text)
    return b.json(r, method, path)


def err(b, method, path, body, status=400):
    r = b.call(method, path, body)
    assert r.status_code == status, (path, r.status_code, r.content[:200])
    return b.json(r, method, path)['error']


def test_only_admins_may_use_the_page(site):
    assert site.get('/api/v1/admin/log-formats').status_code == 401
    b = signed_in(site)
    made = b.call('POST', '/api/v1/admin/users', dict(username='rina', display_name='Rina', role='user', password='rina-initial-password-123'))
    assert made.status_code in (200, 201)
    other = TestClient(site.app)
    login = other.post('/api/v1/auth/login', json=dict(username='rina', password='rina-initial-password-123'), headers=WEB)
    assert login.status_code == 200
    other.post('/api/v1/me/password', json=dict(old_password='rina-initial-password-123', new_password='rina-next-password-12345'), headers=WEB)
    for method, path, body in (('GET', '', None), ('PUT', '', dict(rules=[])), ('POST', '/suggest', dict(service='x')), ('POST', '/test', dict(service='x', rule={})),
                               ('POST', '/read-today', dict(source='s3'))):
        r = other.request(method, '/api/v1/admin/log-formats' + path, json=body, headers=WEB)
        assert r.status_code == 403, (method, path, r.status_code)


def test_rules_and_services_are_listed_encrypted(site):
    b = signed_in(site)
    d = ok(b, 'GET', '/api/v1/admin/log-formats')
    assert d['file']['exists'] is True and d['rules'][-1]['match'] == '*' and 'caddy-json' in d['formats']
    rows = {(r['source'], r['service']): r for r in d['services']}
    https = rows['s3', 'monishield-https-1']
    assert https['namespace'] == 'host1' and https['format'] == 'caddy-json' and https['lines_today'] == 6 and https['read_pct'] is not None
    assert https['own_rule'] is False
    assert rows['s3', 'portfolio-api-1']['format'] == 'spring-boot' and rows['s3', 'portfolio-api-1']['read_pct'] is None


def test_suggest_and_test_read_the_newest_lines(site):
    b = signed_in(site)
    s = ok(b, 'POST', '/api/v1/admin/log-formats/suggest', dict(source='s3', namespace='host1', service='portfolio-api-1'))
    assert s['available'] and s['suggested']['format'] == 'logfmt' and s['better'] is True and s['lines'] == len(sample('logfmt.log'))
    t = ok(b, 'POST', '/api/v1/admin/log-formats/test', dict(source='s3', namespace='host1', service='monishield-https-1', rule=dict(match='*', format='caddy-json')))
    assert (t['read'], t['total']) == (3, 6) and [r['read'] for r in t['rows']].count(True) == 2 and len(t['rows'][0]['time']) == 8
    assert not ok(b, 'POST', '/api/v1/admin/log-formats/suggest', dict(source='kafka', service='nothing-here'))['available']
    assert err(b, 'POST', '/api/v1/admin/log-formats/test', dict(source='s3', service='x', rule=dict(match='*', format='nope')))['code'] == 'invalid_rule'
    assert err(b, 'POST', '/api/v1/admin/log-formats/suggest', dict(source='tape', service='x'))['code'] == 'invalid_parameter'


def test_save_validates_writes_the_file_and_uses_the_rules_without_a_restart(site):
    b = signed_in(site)
    path = site.app.state.logformats.path
    assert err(b, 'PUT', '/api/v1/admin/log-formats', dict(rules=[dict(match='a', format='plain')]))['message'] == 'The last rule must be "*", so every other service has a format.'
    assert err(b, 'PUT', '/api/v1/admin/log-formats', dict(rules=[dict(match='*', format='regex')]))['message'].startswith('Rule 1')
    assert err(b, 'PUT', '/api/v1/admin/log-formats', dict(rules=[]))['code'] == 'invalid_rule'
    before = open(path).read()   # the refused saves wrote nothing
    assert lf.match(lf.current(), 'host1', 'portfolio-api-1').format == 'spring-boot'
    rules = [dict(match='host1/portfolio-api-1', format='logfmt', kind='app'), dict(match='monishield-https-1', format='caddy-json', kind='http'), dict(match='*', format='spring-boot', kind='app')]
    d = ok(b, 'PUT', '/api/v1/admin/log-formats', dict(rules=rules))
    assert open(path).read() != before
    assert d['file']['exists'] and [r['match'] for r in d['rules']] == ['host1/portfolio-api-1', 'monishield-https-1', '*']
    assert lf.match(lf.current(), 'host1', 'portfolio-api-1').format == 'logfmt'   # in use now
    assert config.log_format_rules(site.app.state.cfg) == lf.current()               # and what the next start reads
    assert next(r for r in d['services'] if r['service'] == 'portfolio-api-1')['own_rule'] is True
    assert [f for f in os.listdir(os.path.dirname(path)) if f.endswith('.tmp')] == []
    audit = site.app.state.auth.audit_list(20)[1]
    assert any(a['action'] == 'log_formats.save' for a in audit)


def test_read_today_again_starts_a_forced_ingest_of_todays_folder(site, monkeypatch):
    b = signed_in(site)
    calls = []
    monkeypatch.setattr(site.app.state.ingest, 'start', lambda folder=None, force=False, by=None: calls.append((folder, force, by)))
    d = ok(b, 'POST', '/api/v1/admin/log-formats/read-today', dict(source='s3'), 202)
    assert d == dict(started=True, folder=site.today) and calls == [(site.today, True, 'admin')]
    assert err(b, 'POST', '/api/v1/admin/log-formats/read-today', dict(source='kafka'), 404)['code'] == 'not_found'
    assert any(a['action'] == 'log_formats.read_today' for a in site.app.state.auth.audit_list(20)[1])
