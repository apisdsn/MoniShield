"""Parser v2 (TRD §9.1): (a) sample lines per format -> table rows and counters."""
import collections, csv, datetime, glob, os

import pytest

from monishield.infrastructure import db, logfiles
from monishield.domain import parse

FIX = os.path.join(os.path.dirname(__file__), 'fixtures', 'lines')
C = collections.Counter


def read_tables(out_dir):
    out = {}
    for f in glob.glob(os.path.join(out_dir, '*.csv')):
        with open(f, newline='', encoding='utf-8') as fh:
            rows = list(csv.reader(fh, quoting=csv.QUOTE_NOTNULL))  # empty without quotes -> None
        out[os.path.basename(f)[:-4]] = [dict(zip(rows[0], r)) for r in rows[1:]]
    return out


def run(tmp_path, service, fixture=None, lines=None):
    src = os.path.join(FIX, fixture or service + '.txt')
    if lines is not None:
        os.makedirs(tmp_path, exist_ok=True)
        src = str(tmp_path / 'in.log'); open(src, 'w', encoding='utf-8').write(''.join(l + '\n' for l in lines))
    s = logfiles.parse_file(src, service, str(tmp_path / 'out'))
    return s, collections.defaultdict(list, read_tables(str(tmp_path / 'out')))


# ------------------------------------------------------------------ (a) real lines per format
def test_csv_columns_match_the_schema():
    con = db.open(':memory:')
    for table, cols in parse.TABLES.items():
        schema_cols = [r[0] for r in con.execute(f"select column_name from information_schema.columns where table_name = '{table}' order by ordinal_position").fetchall()]
        derived = ['crs_rules', 'capec', 'crs_attack', 'crs_severity', 'crs_score'] if table == 'nginx_access' else []   # Stage 21: filled by derive, not the parser
        assert schema_cols == ['file_id', 'line_no', 'folder'] + cols[1:] + derived, table
    db.open(':memory:').execute(open(db.SCHEMA).read())  # schema is safe to run twice


def test_nginx(tmp_path):
    s, t = run(tmp_path, 'nginx-ingress-controller')
    a = t['nginx_access']
    assert (s['lines'], s['err'], s['warn'], s['corrupt_lines'], s['known_service']) == (11, 2, 1, 0, True)  # err: [error] + [crit]
    assert len(a) == 7 and [r['line_no'] for r in a] == list('1234567')
    assert a[0]['ts_utc'] == '2026-09-27 17:03:25' and a[0]['ip'] == '66.66.66.213'
    assert (a[0]['method'], a[0]['path'], a[0]['status'], a[0]['bytes'], a[0]['upstream']) == ('GET', '/css/chunk-vendors.e727ec85.css', '200', '141491', 'web-frontend-3000')
    assert a[0]['attack_cat'] is None and a[0]['is_uptime_kuma'] == 'false' and len(a[0]['request_id']) == 32
    assert a[1]['is_uptime_kuma'] == 'true' and a[1]['pod_final'] == '10.42.233.139:3000' and a[1]['up_addrs'] == '10.42.233.139:3000' and a[1]['up_statuses'] == '200'
    assert a[1]['request_id'] == 'bbc49c2ed69b931599dd60d93314128c' and a[1]['request_time'] == '0.001'
    # retry: two attempts, answering pod = last address
    addrs, sts = a[2]['up_addrs'].split(','), a[2]['up_statuses'].split(',')
    assert len(addrs) == len(sts) == 2 and a[2]['pod_final'] == addrs[-1] and a[2]['path_key'] == '/reports/count' and '?' in a[2]['path']
    # rejected at the ingress: no upstream
    assert (a[3]['upstream'], a[3]['pod_final'], a[3]['up_addrs'], a[3]['up_statuses'], a[3]['status']) == ('-', '-', '-', '-', '403')
    assert a[3]['attack_cat'] == 'Probe PHP / CGI'
    assert a[4]['status'] == '401' and a[4]['path_key'] == '/v1/user/select'
    assert a[5]['attack_cat'] == 'Probe file sensitif' and a[5]['upstream'] == 'cattle-system-rancher-80'
    assert a[6]['status'] == '101'
    e = t['nginx_error']
    assert [(r['line_no'], r['level']) for r in e] == [('8', 'error'), ('9', 'warn'), ('10', 'crit')]
    assert e[0] == dict(line_no='8', service='nginx-ingress-controller', ts_utc='2026-09-27 18:45:30', level='error',
                        message='recv() failed (104: Connection reset by peer) while reading response header from upstream',
                        upstream_host='10.42.245.132:8080', kind='recv() failed (Connection reset by peer) while reading response header from upstream', request='GET /')
    assert (e[1]['upstream_host'], e[1]['kind'], e[1]['request']) == (None, None, None)  # not an upstream error
    assert e[2]['upstream_host'] == '10.42.245.145:3000'
    m = t['log_message']
    assert [(r['line_no'], r['level']) for r in m] == [('8', 'ERROR'), ('9', 'WARN'), ('10', 'CRIT')]
    assert m[1]['msg_key'] == 'WARN | a client request body is buffered to a temporary file /tmp/client-body/#' and m[1]['raw'].startswith('2026/09/27 19:23:53 [warn]')
    assert s['rows'] == dict(nginx_access=7, nginx_error=3, log_message=3) and s['counters'] == []  # control lines ignored


def test_frontend(tmp_path):
    s, t = run(tmp_path, 'web-frontend')
    assert (s['lines'], s['err'], s['warn']) == (5, 1, 0)  # [notice] without '*N' and entrypoint are ignored
    assert t['fe_access'] == [
        dict(line_no='1', ts_utc='2026-09-27 17:03:24', ip='66.66.66.213', method='GET', path='/submit-report', path_key='/submit-report', status='200'),
        dict(line_no='2', ts_utc='2026-09-27 23:29:19', ip='66.66.66.209', method='GET', path='/apple-touch-icon-precomposed.png', path_key='/apple-touch-icon-precomposed.png', status='404')]
    assert [(r['service'], r['level'], r['ts_utc']) for r in t['nginx_error']] == [('web-frontend', 'error', '2026-09-27 23:29:19')]
    assert t['log_message'][0]['level'] == 'ERROR'


def test_nginx_error_level_same_in_ingress_and_frontend(tmp_path):
    """TRD §4.4 item 3: crit/alert/emerg = error in both services (old: the frontend counted them as warnings)."""
    crit = open(os.path.join(FIX, 'nginx-ingress-controller.txt')).read().splitlines()[9]
    lines = [crit, crit.replace('[crit]', '[alert]'), crit.replace('[crit]', '[emerg]'), crit.replace('[crit]', '[warn]'), crit.replace('[crit]', '[info]')]
    for svc in ('nginx-ingress-controller', 'web-frontend'):
        s, _ = run(tmp_path / svc, svc, lines=lines)
        assert (s['err'], s['warn']) == (3, 2), svc


def test_events_service(tmp_path):
    s, t = run(tmp_path, 'event-api')
    assert (s['lines'], s['err'], s['warn']) == (9, 0, 2)  # two non-5xx failed events
    ev = t['sl_event']
    assert ev[0] == dict(line_no='1', level='INFO', request_id='b822909ecd30abd7322cb20867352854', event='http.request.completed', method='GET',
                         path='/uploads', path_key='/uploads', status='200', ip='66.66.66.213', duration_ms='48', failed='false', err_name=None, err_message=None)
    assert (ev[1]['method'], ev[1]['duration_ms'], ev[1]['status']) == ('PATCH', '3243', '200')
    assert ev[2] == dict(line_no='3', level='ERROR', request_id='69dda3958192b7ac11f28e3e2dc2f10c', event='http.request.failed', method='GET', path='/reports/count',
                         path_key='/reports/count', status='401', ip=None, duration_ms='1', failed='true', err_name='UnauthorizedError', err_message='Unauthorized')
    assert (ev[3]['status'], ev[3]['failed'], ev[3]['err_name']) == ('200', 'true', 'MulterError')  # failed even though status 200
    assert [r['msg_key'] for r in t['log_message']] == ['WARN | # UnauthorizedError: Unauthorized', 'WARN | # MulterError: File too large']
    assert s['counters'] == [['biz', 'emails_sent', 1], ['level', 'ERROR', 2], ['level', 'INFO', 4], ['level', 'PERFORMANCE', 1],
                             ['mail', 'sendNotificationMailToSupervisor', 1]]


def test_events_service_text_lines(tmp_path):
    s, t = run(tmp_path, 'event-api', lines=['[APP-ERROR] Failed to send mail: timeout', '[APP-WARN] lambat 12 ms', '[APP-INFO] {bukan json',
                                                    '[APP-ERROR] {"event":"http.request.failed","statusCode":500,"path":"/x/12"}'])
    assert (s['err'], s['warn']) == (2, 1)
    assert ['biz', 'emails_failed', 1] in s['counters'] and ['level', 'ERROR', 2] in s['counters']
    assert [r['msg_key'] for r in t['log_message']] == ['ERROR | Failed to send mail: timeout', 'WARN | lambat # ms', 'ERROR | # None: None']
    assert t['sl_event'] == [dict(line_no='4', level='ERROR', request_id=None, event='http.request.failed', method='None', path='/x/12', path_key='/x/:n',
                                  status='500', ip=None, duration_ms='0', failed='true', err_name=None, err_message=None)]


def test_spring_auth_service(tmp_path):
    s, t = run(tmp_path, 'auth-service')
    assert (s['lines'], s['err'], s['warn']) == (10, 1, 4)
    r = t['spring_line']
    assert len(r) == 7 and (r[0]['ts_utc'], r[0]['level'], r[0]['thread'], r[0]['logger']) == ('2026-09-25 16:04:28', 'INFO', '           main', 'c.e.auth.AuthApplication')
    assert (r[0]['restart_app'], r[0]['restart_seconds']) == ('AuthApplication', '17.163')
    assert r[1]['jwt_expired_ms'] == '385316' and r[1]['refresh_expired'] == 'false' and r[1]['level'] == 'ERROR'
    assert r[2]['refresh_expired'] == 'true' and r[2]['jwt_expired_ms'] is None  # JWT pattern does not match the refresh line
    assert (r[3]['login_kind'], r[3]['login_account'], r[3]['login_ip']) == ('fail', 'jane.doe@example.com', '66.66.66.114')
    assert (r[4]['login_kind'], r[4]['login_ip']) == ('lock', '66.66.66.41')
    assert (r[5]['login_kind'], r[5]['login_account'], r[5]['login_ip']) == ('ok', 'jane.doe', '66.66.66.129')
    assert r[6]['login_kind'] is None and r[6]['level'] == 'WARN'
    assert [(m['line_no'], m['level']) for m in t['log_message']] == [('2', 'ERROR'), ('3', 'WARN'), ('4', 'WARN'), ('5', 'WARN'), ('7', 'WARN'), ('8', 'EXC')]
    assert t['log_message'][2]['msg_key'] == "WARN | UserController: SECURITY EVENT: Invalid password for user/email: '<email>' from IP: #.# (Attempt #/#)"
    assert s['counters'] == [['level', 'ERROR', 1], ['level', 'Hibernate SQL', 1], ['level', 'INFO', 2], ['level', 'WARN', 4]]  # EXC does not add to err


def test_spring_report_template_per_thread(tmp_path):
    s, t = run(tmp_path, 'report-service')
    assert [(r['pdf_template'], r['pdf_failed']) for r in t['spring_line']] == [(None, None), ('cover_report', 'false'), (None, None), ('?', 'true')]
    # line 4 uses another thread (exec-10) than 'pdf path' on line 3 (exec-3) -> template '?', like the old system


def test_coredns(tmp_path):
    s, t = run(tmp_path, 'coredns')
    assert (s['lines'], s['err'], s['warn']) == (3, 1, 0)
    assert t['coredns_error'] == [dict(line_no='1', level='ERROR', domain='backup-example-volume.s3.ap-southeast-3.amazonaws.com.', rtype='AAAA',
                                       message='read udp 10.42.191.189:58401->10.0.1.100:53: i/o timeout')]
    assert t['log_message'][0]['msg_key'] == 'ERROR | backup-example-volume.s3.ap-southeast-#.amazonaws.com. AAAA: read udp X->X: i/o timeout'


@pytest.mark.parametrize('service', ['nginx-ingress-controller', 'web-frontend', 'event-api', 'auth-service', 'coredns'])
def test_corrupt_lines_are_counted_but_produce_no_rows(tmp_path, service):
    s, t = run(tmp_path, service, fixture='corrupt.txt')
    assert (s['lines'], s['err'], s['warn'], s['corrupt_lines'], s['rows'], s['counters']) == (1, 0, 0, 1, {}, []) and not t


def test_unknown_service_uses_the_spring_parser(tmp_path):
    s, t = run(tmp_path, 'unknown-service', fixture='auth-service.txt')
    assert s['known_service'] is False and len(t['spring_line']) == 7 and t['spring_line'][0]['service'] == 'unknown-service'


def test_gz_same_as_log(tmp_path):
    import gzip, shutil
    src = os.path.join(FIX, 'event-api.txt'); gz = str(tmp_path / 'x.log.gz')
    with open(src, 'rb') as a, gzip.open(gz, 'wb') as b: shutil.copyfileobj(a, b)
    s1 = logfiles.parse_file(src, 'event-api', str(tmp_path / 'a')); s2 = logfiles.parse_file(gz, 'event-api', str(tmp_path / 'b'))
    assert s1 == s2 and read_tables(str(tmp_path / 'a')) == read_tables(str(tmp_path / 'b'))


def test_empty_text_differs_from_null(tmp_path):
    line = '1.2.3.4 - - [04/Oct/2026:17:00:34 +0000] "GET / HTTP/1.1" 200 6599 "-" "" 355 0.001 [] [] - - - - ' + 'a' * 32
    _, t = run(tmp_path, 'nginx-ingress-controller', lines=[line, line[:-33]])
    assert t['nginx_access'][0]['ua'] == '' and t['nginx_access'][0]['attack_cat'] is None and t['nginx_access'][0]['upstream'] == '-'
    assert t['nginx_access'][1]['request_id'] is None and t['nginx_access'][1]['pod_final'] == '-'  # tail does not match


# ------------------------------------------------------------------ (b) real files vs old parse()
FOLDERS = ('2026-09-27', '2026-09-29', '2026-10-06')
SERVICES = ('nginx-ingress-controller', 'web-frontend', 'event-api', 'auth-service', 'reference-service', 'report-service', 'coredns')


def wib(ts, n=16): return (datetime.datetime.fromisoformat(ts) + datetime.timedelta(hours=7)).strftime('%Y-%m-%d %H:%M:%S')[:n]


