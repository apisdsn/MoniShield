"""OTLP/HTTP JSON log records (domain/otlp_logs.py, step 1 of docs/12-collector.md) on sample payloads in fixtures/otlp."""
import datetime, json, os

import pytest

from monishield.domain import formats as F, log_formats as lf, otlp_logs as otlp, rules, timezone

FIX = os.path.join(os.path.dirname(__file__), 'fixtures', 'otlp')
UTC = datetime.timezone.utc
NOW = datetime.datetime(2026, 11, 4, 10, 0, 0, tzinfo=UTC)       # 17:00 WIB; the fixtures' records are a few minutes older


def payload(name):
    with open(os.path.join(FIX, name + '.json'), encoding='utf-8') as fh: return json.load(fh)


def run(name, now=NOW):
    return otlp.parse_logs(payload(name), 'collector-1', now)


def where(r): return (r['ns'], r['svc'], r['pod'])


@pytest.fixture(autouse=True)
def default_zone():
    timezone.use(timezone.Zone())
    yield
    timezone.use(timezone.Zone())


def one(body, t='1793786136000000000', attrs=None, now=NOW, collector='collector-1'):
    """A request with a single record; t is 2026-11-04T09:55:36Z."""
    rec = {'timeUnixNano': t, 'body': {'stringValue': body} if isinstance(body, str) else body, 'attributes': [{'key': k, 'value': {'stringValue': v}} for k, v in (attrs or {}).items()]}
    return otlp.parse_logs({'resourceLogs': [{'scopeLogs': [{'logRecords': [rec]}]}]}, collector, now)


def test_kubernetes_uses_the_service_names_of_the_kafka_source():
    recs, rej = run('k8s')
    assert rej == {} and len(recs) == 2
    assert where(recs[0]) == ('ingress-nginx', recs[0]['svc'], 'ingress-nginx-controller-7d9c5b6f4-x2k8p') and recs[0]['svc'] != 'controller'
    assert recs[0]['line'].startswith('203.0.113.5 - - [04/Nov/2026') and not recs[0]['line'].endswith('\n')
    assert where(recs[1]) == ('shop', 'orders-api', 'orders-api-5f7c8d9b6-abcde') and recs[1]['line'] == '{"level":"info","msg":"order created"}'
    assert recs[0]['t'] == datetime.datetime(2026, 11, 4, 9, 55, 36, tzinfo=UTC)
    assert recs[1]['relpath'] == os.path.join('2026-11-05', 'shop', 'orders-api', 'log_orders-api_orders-api-5f7c8d9b6-abcde_2026-11-05-16-00.log')


def test_ingress_controller_container_is_matched_like_in_kafka():
    from monishield.domain import kafka_message, parse
    recs, _ = run('k8s')
    assert recs[0]['svc'] == kafka_message.service_of('controller', 'ingress-nginx-controller-7d9c5b6f4-x2k8p', 'ingress-nginx') == parse.NGINX_SVC


def test_host_file_service_name_file_stem_and_defaults():
    recs, rej = run('host_file')
    assert rej == {}
    assert [where(r) for r in recs] == [('web-01', 'payments', 'web-01'), ('web-01', 'app', 'web-01'), ('web-01', 'access', 'web-01'),
                                        ('web-01', 'access-log', 'web-01'), ('web-01', 'app', 'web-01')]
    assert recs[0]['line'] == 'ts=2026-11-04T09:55:36Z level=info msg=charged'             # trailing \r\n removed
    assert recs[1]['t'] == datetime.datetime(2026, 11, 4, 9, 56, 0, tzinfo=UTC)             # observed time when there is no event time
    assert recs[3]['line'] == 'plain bytes line'                                            # bytesValue is base64 text


@pytest.mark.parametrize('path,stem', [('access.log', 'access'), ('app-2026-11-04.log', 'app'), ('access.log.1', 'access'),
                                       ('access.log-20261104.gz', 'access'), ('/var/log/Nginx/Error.LOG', 'error'),
                                       ('C:\\logs\\app.log', 'app'), ('2026-11-04.log', ''), ('syslog', 'syslog')])
def test_file_stem(path, stem):
    assert otlp.file_stem(path) == stem


def test_journald_line_is_read_by_the_syslog_preset():
    recs, rej = run('journald')
    assert rej == {} and [where(r) for r in recs] == [('web-01', 'sshd', 'web-01'), ('web-01', 'kernel', 'web-01'),
                                                      ('web-01', 'journald', 'web-01'), ('collector-1', 'user-1000', 'collector-1')]
    rule = lf.Rule('sshd', 'syslog', 'app')
    got = [F.read_syslog(r['line'], rule) for r in recs]
    assert (got[0]['time'], got[0]['level'], got[0]['message'], got[0]['logger']) == ('2026-11-04 09:55:36', 'INFO', 'Accepted publickey for deploy from 198.51.100.7', 'sshd')
    assert (got[1]['time'], got[1]['level']) == ('2026-11-04 09:55:37', 'ERROR')          # PRIORITY 3 = err
    assert got[2]['level'] == 'INFO' and got[2]['message'] == 'something happened'         # default PRIORITY 6
    assert recs[0]['line'].startswith('<30>1 2026-11-04T09:55:36.000Z web-01 sshd 812 - - ')


def test_windows_event_log_is_one_json_line_read_by_a_json_rule():
    recs, rej = run('windows')
    assert rej == {} and [(r['svc'], r['pod']) for r in recs] == [('windows-application', 'win-01'), ('windows-security', 'win-01')]
    assert recs[0]['ns'] == 'win-01' and recs[0]['line'].startswith('{"channel":"Application","event_id":1000,"level":"Error",')
    rule = lf.match(lf.rules_from({'service': [{'match': 'windows-*', 'format': 'json',
                                               'fields': {'time': 'system_time', 'level': 'level', 'message': 'message'}}]}), 'win-01', 'windows-security')
    d = F.read_json(recs[1]['line'], rule)
    assert (d['time'], d['level']) == ('2026-11-04 09:55:40', 'INFO') and 'Source Network Address: 192.0.2.44' in d['message']
    assert F.read_json(recs[0]['line'], rule)['level'] == 'ERROR'


def test_docker_container():
    recs, rej = run('docker')
    assert rej == {} and where(recs[0]) == ('docker-01', 'redis', 'docker-01')


def test_bad_records_are_rejected_with_a_reason():
    recs, rej = run('bad')
    assert [r['line'] for r in recs] == ['good line', 'from the future']
    assert rej == {'malformed value': 2, 'missing body': 1, 'empty line': 1, 'invalid name': 1, 'invalid time': 1,
                   'malformed record': 1, 'malformed attributes': 1}
    assert recs[1]['t'] == NOW                                      # 5 days ahead: the client clock is wrong
    ps = otlp.partial_success(rej)['partialSuccess']
    assert ps['rejectedLogRecords'] == '8' and 'empty line (1)' in ps['errorMessage'] and 'malformed value (2)' in ps['errorMessage']


def test_partial_success_of_a_clean_request_is_empty():
    assert otlp.partial_success({}) == {}


@pytest.mark.parametrize('bad', [None, [], 'x', {'resourceLogs': 'x'}, {'resourceLogs': [1]}, {'resourceLogs': [{'scopeLogs': {}}]},
                                 {'resourceLogs': [{'resource': [], 'scopeLogs': []}]}, {'resourceLogs': [{'scopeLogs': [{'logRecords': 7}]}]}])
def test_malformed_requests_do_not_raise(bad):
    recs, rej = otlp.parse_logs(bad, 'collector-1', NOW)
    assert recs == [] and sum(rej.values()) == 1 and otlp.partial_success(rej)['partialSuccess']['rejectedLogRecords'] == '1'


def test_empty_request_is_fine():
    assert otlp.parse_logs({}, 'collector-1', NOW) == ([], {}) and otlp.parse_logs({'resourceLogs': []}, 'c', NOW) == ([], {})


def test_any_value_and_attributes():
    v = otlp.any_value({'kvlistValue': {'values': [{'key': 'a', 'value': {'intValue': '7'}}, {'key': 'b', 'value': {'arrayValue': {'values': [
        {'boolValue': True}, {'doubleValue': 1.5}, {'stringValue': 'x'}]}}}]}})
    assert v == {'a': 7, 'b': [True, 1.5, 'x']} and list(v) == ['a', 'b']
    assert otlp.any_value({}) is None and otlp.pairs(None) == {}
    assert otlp.pairs([{'key': 'k', 'value': {'stringValue': 'v'}}]) == {'k': 'v'}
    for bad in ({'intValue': 'x'}, {'intValue': True}, {'stringValue': 5}, {'boolValue': 'true'}, {'what': 1}, {'stringValue': 'a', 'intValue': '1'},
                [], {'arrayValue': {'values': 'x'}}, {'bytesValue': '!!'}):
        with pytest.raises(otlp.Bad): otlp.any_value(bad)
    deep = {'stringValue': 'x'}
    for _ in range(40): deep = {'arrayValue': {'values': [deep]}}
    with pytest.raises(otlp.Bad): otlp.any_value(deep)
    for bad in ('x', [1], [{'key': 1}], [{'value': {}}]):
        with pytest.raises(otlp.Bad): otlp.pairs(bad)


def test_structured_body_without_a_known_shape_is_one_json_line():
    recs, rej = one({'kvlistValue': {'values': [{'key': 'ünï', 'value': {'stringValue': 'ok'}}, {'key': 'n', 'value': {'intValue': '3'}}]}}, attrs={'host.name': 'web-01'})
    assert rej == {} and recs[0]['line'] == '{"ünï":"ok","n":3}'
    assert one({'arrayValue': {'values': [{'stringValue': 'a'}]}})[0][0]['line'] == '["a"]'


def test_record_attribute_wins_over_resource_attribute_and_record_line_ends():
    p = {'resourceLogs': [{'resource': {'attributes': [{'key': 'host.name', 'value': {'stringValue': 'web-01'}}]},
                           'scopeLogs': [{'logRecords': [{'body': {'stringValue': 'a\r\nb\r\n'}, 'timeUnixNano': '1793786136000000000',
                                                          'attributes': [{'key': 'host.name', 'value': {'stringValue': 'web-02'}}]}]}]}]}
    recs, _ = otlp.parse_logs(p, 'c', NOW)
    assert recs[0]['pod'] == 'web-02' and recs[0]['line'] == 'a\nb'


def test_names_never_leave_the_folder():
    for attrs in ({'service.name': '../x'}, {'host.name': '..'}, {'host.name': 'a\\b'}, {'service.name': '.hidden'}, {'service.name': 'x' * 300}):
        recs, rej = one('line', attrs=attrs)
        assert recs == [] and rej == {'invalid name': 1}, attrs
    recs, _ = one('line', attrs={'host.name': 'web 01', 'service.name': 'my/app'})
    assert where(recs[0]) == ('web-01', 'my-app', 'web-01')
    recs, _ = one('line', attrs={'host.name': 'h' * 120, 'service.name': 's' * 120})
    assert recs == []                                               # the file name would be longer than 255 bytes


def test_long_lines_are_cut_but_kept():
    recs, rej = one({'stringValue': 'é' * 40000})
    line = recs[0]['line']
    assert rej == {} and line.endswith(' [cut]') and len(line.encode()) <= 64 * 1024 and len(line.encode()) > 64 * 1024 - 10
    assert one({'stringValue': 'x' * 65536})[0][0]['line'] == 'x' * 65536


def test_time_rules():
    t = lambda **kw: otlp.time_of(kw, NOW)
    assert t(timeUnixNano='1793786136000000000') == datetime.datetime(2026, 11, 4, 9, 55, 36, tzinfo=UTC)
    assert t(timeUnixNano='0', observedTimeUnixNano='1793786137000000000').second == 37
    assert t() == NOW and t(timeUnixNano=1793786136000000000).second == 36
    assert t(timeUnixNano='1793786700000000000') == datetime.datetime(2026, 11, 4, 10, 5, tzinfo=UTC)    # exactly 5 minutes ahead: kept
    assert t(timeUnixNano='1793786701000000000') == NOW                                                   # 5 minutes and a second: now
    for bad in ('x', '-5', 1.5, True, '9' * 30):
        with pytest.raises(otlp.Bad): t(timeUnixNano=bad)


def test_hour_files_follow_the_local_time_around_midnight():
    timezone.use(timezone.Zone(330, 'IST'))                         # +05:30
    now = datetime.datetime(2026, 11, 5, 0, 0, tzinfo=UTC)
    at = lambda h, m, s, d=4: str(int(datetime.datetime(2026, 11, d, h, m, s, tzinfo=UTC).timestamp()) * 10 ** 9)
    before, _ = one('a', t=at(18, 29, 59), attrs={'service.name': 'app'}, now=now)       # 23:59:59 local
    after, _ = one('b', t=at(18, 30, 1), attrs={'service.name': 'app'}, now=now)         # 00:00:01 local, next day
    noon, _ = one('c', t=at(6, 30, 0), attrs={'service.name': 'app'}, now=now)           # 12:00 local
    names = [os.path.basename(r[0]['relpath']) for r in (before, after, noon)]
    assert names == ['log_app_collector-1_2026-11-05-23-00.log', 'log_app_collector-1_2026-11-06-00-00.log', 'log_app_collector-1_2026-11-05-12-00.log']
    assert before[0]['relpath'].split(os.sep)[:3] == ['2026-11-05', 'collector-1', 'app']


def test_relpath_is_a_valid_inbox_path():
    for name in ('k8s', 'host_file', 'journald', 'windows', 'docker'):
        for r in run(name)[0]:
            date, ns, svc, fname = rules.split_relpath(r['relpath'])
            assert (ns, svc) == (r['ns'], r['svc']) and rules.pod_name(svc, fname) == r['pod'], r['relpath']
            assert date == r['relpath'].split(os.sep)[0] and fname.endswith('-00.log')


def test_too_many_records():
    rec = {'body': {'stringValue': 'x'}, 'timeUnixNano': '1793786136000000000'}
    p = {'resourceLogs': [{'scopeLogs': [{'logRecords': [rec] * (otlp.MAX_RECORDS + 5)}]}]}
    recs, rej = otlp.parse_logs(p, 'c', NOW)
    assert len(recs) == otlp.MAX_RECORDS and rej == {'too many records': 5}
