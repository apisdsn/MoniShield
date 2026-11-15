"""Analysis Settings (stage 62): the domain rules (parse, validate, write, match) and the request ID field of the readers."""
import tomllib

import pytest

from monishield.domain import analysis as an, formats, log_formats as lf


def test_a_missing_file_or_key_is_auto():
    got = an.parse({})
    assert set(got) == set(an.SOURCES) and all(s.default for s in got.values())
    one = an.parse({'collector': {'access_log': 'web-1'}})
    assert one['collector'].access_log == 'web-1' and one['collector'].app_logs == 'auto' and one['s3'].default


def test_settings_round_trip_through_toml():
    doc = {'collector': dict(access_log='web-1', app_logs=['app-1', 'worker-1'], request_id='trace_id', business=[
        dict(name='Sign-ins', service='web-1', match='request', method='post', path='/api/login', status='2xx'),
        dict(name='Payments "Received"', service='app-1', match='log_line', text='Payment received')]),
        's3': dict(business=[dict(name='Orders', service='api', match='request', path='/orders/*', status='201')])}
    parsed = an.parse(doc)
    assert parsed['collector'].business[0].method == 'POST'
    text = an.dumps(parsed)
    assert an.parse(tomllib.loads(text)) == parsed
    assert '[kafka]' not in text and '[collector]' in text and '[[s3.business]]' in text


@pytest.mark.parametrize('doc', [
    {'tape': {}}, {'s3': {'nope': 1}}, {'s3': {'access_log': 'bad name'}}, {'s3': {'app_logs': []}}, {'s3': {'app_logs': 'x'}},
    {'s3': {'request_id': 'a b'}},
    {'s3': {'business': [dict(name='', service='a', match='request', method='GET')]}},
    {'s3': {'business': [dict(name='x', service='a', match='request')]}},                                      # nothing to match on
    {'s3': {'business': [dict(name='x', service='a', match='request', status='6xx')]}},
    {'s3': {'business': [dict(name='x', service='a', match='request', method='FETCH')]}},
    {'s3': {'business': [dict(name='x', service='a', match='request', path='api')]}},
    {'s3': {'business': [dict(name='x', service='a', match='request', path='/a*b')]}},
    {'s3': {'business': [dict(name='x', service='a', match='log_line')]}},
    {'s3': {'business': [dict(name='x', service='a', match='log_line', text='t', path='/a')]}},
    {'s3': {'business': [dict(name='x', service='a', match='request', method='GET', text='t')]}},
    {'s3': {'business': [dict(name='x', service='a', match='other', text='t')]}},
    {'s3': {'business': [dict(name='x', service='a', match='log_line', text='t', extra=1)]}},
    {'s3': {'business': [dict(name='x', service='a', match='log_line', text='t'), dict(name='X', service='b', match='log_line', text='t')]}},   # same name
])
def test_bad_settings_are_refused(doc):
    with pytest.raises(an.AnalysisError): an.parse(doc)


def test_at_most_thirty_rules():
    rules = [dict(name=f'r{i}', service='a', match='log_line', text='t') for i in range(31)]
    with pytest.raises(an.AnalysisError): an.parse({'s3': {'business': rules}})


def metric(**kw): return an.metric_from(dict(name='m', service='web', match='request', **kw), 'x')


def test_request_rules():
    m = metric(method='POST', path='/api/login', status='2xx')
    assert an.request_matches(m, 'web', 'POST', '/api/login', 200) and an.request_matches(m, 'web', 'post', '/api/login', 299)
    assert not an.request_matches(m, 'web', 'POST', '/api/login', 401) and not an.request_matches(m, 'web', 'GET', '/api/login', 200)
    assert not an.request_matches(m, 'web', 'POST', '/api/login/x', 200) and not an.request_matches(m, 'other', 'POST', '/api/login', 200)
    assert not an.request_matches(m, 'web', 'POST', '/api/login', None)
    assert an.request_matches(metric(path='/orders/*'), 'web', 'GET', '/orders/:n', None) and not an.request_matches(metric(path='/orders/*'), 'web', 'GET', '/order', 200)
    assert an.request_matches(metric(status='201'), 'web', None, '/x', 201) and not an.request_matches(metric(status='201'), 'web', None, '/x', 200)


def test_log_line_rules():
    m = an.metric_from(dict(name='p', service='app', match='log_line', text='Payment received'), 'x')
    assert an.line_matches(m, 'app', 'INFO payment RECEIVED for order 4') and not an.line_matches(m, 'app', 'nothing') and not an.line_matches(m, 'web', 'Payment received')
    assert not an.request_matches(m, 'app', 'GET', '/', 200)


def test_like_pattern_and_bounds():
    assert an.like_pattern('/a_b%') == '/a\\_b\\%' and an.like_pattern('/orders/*') == '/orders/%'
    assert an.status_bounds('2xx') == (200, 299) and an.status_bounds('404') == (404, 404) and an.status_bounds('') is None


def test_suggested_names():
    assert an.suggest_name('POST', '/api/v1/auth/login') == 'Auth Login' and an.suggest_name('POST', '/api/v1/collectors') == 'Collectors'
    assert an.suggest_name('POST', '/orders/:n/pay') == 'Orders Pay' and an.suggest_name('POST', '/') == 'POST'


def test_current_settings_follow_use():
    before = an.all_current()
    try:
        an.use(an.parse({'kafka': {'request_id': 'trace_id'}}))
        assert an.current('kafka').request_id == 'trace_id' and an.current('s3').default and an.id_fields(an.all_current()) == ('trace_id',)
    finally: an.use(before)


# The request ID field of the readers
CADDY = '{"level":"info","ts":1760180401.5,"msg":"handled request","request":{"client_ip":"203.0.113.5","method":"GET","uri":"/a","headers":{"X-Request-Id":["h1"],"X-Request-ID":["h2"]}},"status":200,"duration":0.01,"size":5%s}'


def read_caddy(extra=''): return formats.reader(lf.Rule('*', 'caddy-json', 'http'))(CADDY % extra)


def test_caddy_reads_a_logged_request_id_or_the_header():
    assert read_caddy(',"request_id":"abc"')['request_id'] == 'abc'
    assert read_caddy()['request_id'] == 'h2'
    assert read_caddy(',"trace_id":"t9"')['request_id'] == 'h2'   # the header comes first; trace_id is read when there is neither


def test_a_configured_field_is_read_first_for_new_lines():
    try:
        formats.use_id_fields(('corr',))
        assert read_caddy(',"corr":"c1","request_id":"abc"')['request_id'] == 'c1'
        j = formats.reader(lf.Rule('*', 'json', 'app'))('{"ts":"2026-10-11T10:00:00Z","msg":"hi","level":"info","meta":{"corr":"deep"}}')
        assert 'request_id' not in j
        formats.use_id_fields(('meta.corr',))
        assert formats.reader(lf.Rule('*', 'json', 'app'))('{"ts":"2026-10-11T10:00:00Z","msg":"hi","level":"info","meta":{"corr":"deep"}}')['request_id'] == 'deep'
    finally: formats.use_id_fields(())


def test_nginx_combined_reads_a_trailing_request_id():
    line = '203.0.113.5 - - [11/Oct/2026:10:00:01 +0000] "GET /a HTTP/1.1" 200 5 "-" "UA" 0.120 0123456789abcdef0123456789abcdef'
    assert formats.reader(lf.Rule('*', 'nginx-combined', 'http'))(line)['request_id'] == '0123456789abcdef0123456789abcdef'
