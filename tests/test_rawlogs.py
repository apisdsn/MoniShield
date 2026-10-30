"""Raw Logs (owner request 2026-10-30): entries, time, level and matching rules (domain/rawlog.py), the file search
(infrastructure/queries/rawlogs.py) and the API: every signed-in user, text as written, searches and downloads audited."""
import dataclasses, os

import pytest

from monishield.domain import rawlog, timezone
from monishield.domain.errors import Fail
from monishield.infrastructure import config, db, ingest
from monishield.infrastructure.queries import rawlogs
from test_api import B, X, admin, as_user, cfg, client, make_user   # noqa: F401  (fixtures and helpers of the API tests)

NGINX = ('66.66.66.100 - - [27/Sep/2026:17:02:58 +0000] "POST /reports/verify-otp HTTP/1.1" 400 61 "-" "Mozilla/5.0" 355 0.043 '
         '[app-event-api-80] [] 10.42.233.139:3000 61 0.042 400 {rid}')
EVENT = '[APP-WARN] {{"requestId":"{rid}","method":"POST","path":"/reports/verify-otp","statusCode":400,"error":{{"name":"BadRequestError","message":"OTP code is invalid"}}}}'
JAVA = """2026-09-27 17:30:23.317 ERROR 1 --- [nio-3000-exec-7] c.e.report.PdfService   : Failed to fill template monthly
net.sf.jasperreports.engine.JRException: Error retrieving field value
\tat net.sf.jasperreports.engine.fill.JRFillDataset.next(JRFillDataset.java:1340)
Caused by: java.sql.SQLException: timeout
\t... 12 more
2026-09-27 17:30:24.001  INFO 1 --- [nio-3000-exec-8] c.e.report.PdfService   : next report"""


def q(text, mode='text', **k): return rawlog.Query(mode=mode, text=text, rx=rawlog.pattern(mode, text), **k)


def test_a_stack_trace_stays_with_its_line():
    e = list(rawlog.entries(JAVA.splitlines(True)))
    assert [(n, c) for n, c, _ in e] == [(1, 5), (6, 1)] and 'Caused by' in e[0][2] and e[1][2].endswith('next report')
    hits = list(rawlog.search(JAVA.splitlines(True), q('SQLException')))
    assert [(h['line'], h['lines'], h['kind'], h['time']) for h in hits] == [(1, 5, 'ERROR', '2026-09-27 17:30:23.317')]


def test_time_level_and_fields_of_each_log_shape():
    rid = 'a' * 32
    line, ev = NGINX.format(rid=rid), EVENT.format(rid=rid)
    assert (rawlog.line_time(line), rawlog.kind_of(line)) == ('2026-09-27 17:02:58', '4xx')
    assert (rawlog.line_time(ev), rawlog.kind_of(ev)) == (None, 'WARN')             # JSON events carry no time
    assert rawlog.fields(line) == dict(request_id=rid, ip='66.66.66.100', status=400, method='POST', path='/reports/verify-otp')
    assert rawlog.fields(ev) == dict(request_id=rid, ip=None, status=400, method='POST', path='/reports/verify-otp')
    err = '2026/09/27 23:29:19 [error] 27#27: *6403 open() "/app/x.png" failed (2: No such file or directory), client: 10.0.1.102'
    assert (rawlog.line_time(err), rawlog.kind_of(err)) == ('2026-09-27 23:29:19', 'ERROR')
    assert rawlog.kind_of('[INFO] plugin/reload: Running configuration MD5 = bc6e') == 'INFO'
    assert rawlog.kind_of('2026-09-25 16:04:28.984  INFO 1 --- [main] c.e.App : Started') == 'INFO'
    assert rawlog.line_time('{"time":"2026-10-10T13:55:36+07:00","level":"warn","msg":"x"}') == '2026-10-10 06:55:36'
    assert rawlog.kind_of('{"time":"2026-10-10T13:55:36Z","level":"warn"}') == 'WARN' and rawlog.kind_of('just text') == 'other'
    assert rawlog.line_time('2026-10-10 13:55:36 plain', naive_utc=False) == '2026-10-10 06:55:36'   # rules file formats: site zone


def test_search_modes():
    assert rawlog.pattern('text', 'VERIFY-otp').search('POST /reports/verify-otp')
    ip = rawlog.pattern('ip', '66.66.66.21')
    assert ip.search('client 66.66.66.21:443') and not ip.search('66.66.66.213 - -') and not ip.search('166.66.66.21')
    rid = rawlog.pattern('request', 'b12e40d7')
    assert rid.search('"requestId":"b12e40d7"') and not rid.search('b12e40d7ff')
    assert rawlog.pattern('regex', r'status(Code)?":5\d\d').search('"statusCode":503')
    for mode, text, msg in (('text', '  ', 'Enter something'), ('regex', '(a+)+', 'nested repeat'), ('regex', '[a', 'not a valid'),
                            ('ip', '999.1.1.1', 'one IP'), ('request', 'x y', 'request ID'), ('grep', 'x', 'mode must'),
                            ('text', 'x' * 501, 'longer than 500')):
        with pytest.raises(Fail, match=msg): rawlog.pattern(mode, text)
    assert list(rawlog.search(['aaa\n'], q('a*', 'regex'))) and not list(rawlog.search(['bbb\n'], q('a*', 'regex')))   # empty matches do not count


def test_local_time_window_and_parameters():
    zone = timezone.Zone(420, 'WIB')
    assert rawlog.local_window('2026-10-25', '16:00', '16:59', zone) == ('2026-10-25 09:00:00', '2026-10-25 10:00:00')
    assert rawlog.local_window('2026-10-25', '', '', zone) == (None, None)
    for a, b in (('25:00', ''), ('16:00', '15:00')):
        with pytest.raises(Fail): rawlog.local_window('2026-10-25', a, b, zone)
    qq = rawlog.query_from({'q': 'x', 'services': 'a, b', 'kinds': 'ERROR,4xx'}, '2026-10-25', zone)
    assert (qq.services, qq.kinds, qq.mode) == (frozenset({'a', 'b'}), frozenset({'ERROR', '4xx'}), 'text')
    with pytest.raises(Fail, match='Unknown level'): rawlog.query_from({'q': 'x', 'kinds': 'LOUD'}, '2026-10-25', zone)
    assert 'q=x' in qq.describe() and 'services=a,b' in qq.describe()


def test_context_around_an_entry():
    lines = [f'2026-09-27 17:00:0{i}.000  INFO 1 --- [main] c.e.App : line {i}\n' for i in range(8)]
    c = rawlog.context(lines, 5, 2)
    assert [x['line'] for x in c['before']] == [3, 4] and c['entry']['line'] == 5 and [x['line'] for x in c['after']] == [6, 7]
    assert rawlog.context(lines, 99, 2)['entry'] is None


def test_events_borrow_the_time_of_their_ingress_request(tmp_path):
    """JSON event lines have no time: the ingress line with the same request ID gives it, so a time filter and the order work."""
    root, folder, rid = tmp_path / 'logs', '2026-09-28', 'c' * 32
    for svc, text in (('nginx-ingress-controller', NGINX.format(rid=rid)), ('event-api', EVENT.format(rid=rid) + '\n' + EVENT.format(rid='d' * 32))):
        d = root / folder / 'app' / svc
        d.mkdir(parents=True)
        (d / f'log_{svc}_pod-1_{folder}-00-00.log').write_text(text + '\n')
    cfg_ = dataclasses.replace(config.Config(), log_dir=str(root), data_dir=str(tmp_path / 'data'), inbox_dir=str(tmp_path / 'inbox'), offline=True)
    con = db.open(cfg_.db_path)
    ingest.run(cfg_, con, workers=0)
    r = rawlogs.run(con, [str(root)], folder, q('verify-otp'))
    got = [(h['service'], h['time'], h.get('time_from')) for h in r['hits']]
    assert got == [('nginx-ingress-controller', '2026-09-27 17:02:58', None), ('event-api', '2026-09-27 17:02:58', 'near'),
                   ('event-api', '2026-09-27 17:02:58', 'request')]       # the second event takes the time of the one above it
    assert r['total'] == 3 and r['services']['event-api']['matches'] == 2
    late = rawlogs.run(con, [str(root)], folder, q('verify-otp', start='2026-09-27 18:00:00'))
    assert late['total'] == 0


def test_raw_logs_api_for_every_user_with_audit(client):
    admin(client); make_user(client)
    user = as_user(client, 'rina', 'rina-initial-password-123')     # an ordinary user, not an admin
    base = f'/api/folders/{B}/raw'
    r = user.get(base, params=dict(q='GET', services='nginx-ingress-controller', limit=2))
    assert r.status_code == 200, r.text
    j = r.json()
    assert j['total'] >= 3 and len(j['rows']) == 2 and j['partial'] is None and {s['service'] for s in j['services']} >= {'event-api', 'nginx-ingress-controller'}
    row = j['rows'][0]
    assert row['service'] == 'nginx-ingress-controller' and row['text'][slice(*row['spans'][0])] == 'GET' and row['time'] >= j['rows'][1]['time']
    assert user.get(base, params=dict(q='GET', services='nginx-ingress-controller', limit=2, offset=2)).status_code == 200   # paging: not audited
    c = user.get(f'{base}/context', params=dict(file=row['file'], line=row['line'], n=1)).json()
    assert c['entry']['line'] == row['line'] and c['entry']['text'] == row['text']
    for bad in (dict(file='../../etc/passwd', line=1), dict(file=row['file'], line=99999)):
        assert user.get(f'{base}/context', params=bad).status_code == 404
    assert user.get(base, params=dict(q='x', mode='grep')).status_code == 400
    assert user.get(base, params=dict(q='(a+)+', mode='regex')).json()['error']['code'] == 'invalid_parameter'
    d = user.get(f'{base}/download', params=dict(q='GET', services='nginx-ingress-controller'))
    assert d.status_code == 200 and 'attachment' in d.headers['content-disposition'] and d.text.startswith(f'{B}/') and ': ' in d.text.splitlines()[0]
    audit = [x for x in client.get('/api/admin/audit').json()['rows'] if x['action'].startswith('raw.')]
    assert [(x['action'], x['username']) for x in audit] == [('raw.download', 'rina'), ('raw.search', 'rina')]
    assert f'folder={B}' in audit[1]['detail'] and 'mode=text q=GET' in audit[1]['detail'] and 'matches=' in audit[1]['detail']
    assert client.get(base, params=dict(q='GET')).status_code == 200 and user.get(f'/api/folders/2030-01-01/raw', params=dict(q='x')).status_code == 404


def test_folder_files_prefers_the_log_over_its_gz(tmp_path):
    d = tmp_path / '2026-01-02' / 'tenant' / 'svc'
    d.mkdir(parents=True)
    for name in ('log_svc_p1_2026-01-02-00-00.log', 'log_svc_p1_2026-01-02-00-00.log.gz', 'log_svc_p2_2026-01-02-00-00.log.gz', 'notes.txt'):
        (d / name).write_bytes(b'')
    assert [os.path.basename(f['path']) for f in rawlogs.folder_files([str(tmp_path)], '2026-01-02')] == \
        ['log_svc_p1_2026-01-02-00-00.log', 'log_svc_p2_2026-01-02-00-00.log.gz']
