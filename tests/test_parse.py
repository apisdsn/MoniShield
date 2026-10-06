"""Parser v2 (TRD §9.1): (a) baris asli per format -> baris tabel dan penghitung; (b) file log nyata di tiga
folder -> sama dengan parse() sistem lama: baris, error, warning, level, dan isi yang kelak diagregasi."""
import collections, csv, datetime, glob, os

import pytest

from simpel4 import db, parse, rules
from conftest import ROOT

FIX = os.path.join(os.path.dirname(__file__), 'fixtures', 'lines')
C = collections.Counter


def read_tables(out_dir):
    out = {}
    for f in glob.glob(os.path.join(out_dir, '*.csv')):
        with open(f, newline='', encoding='utf-8') as fh:
            rows = list(csv.reader(fh, quoting=csv.QUOTE_NOTNULL))  # kosong tanpa kutip -> None
        out[os.path.basename(f)[:-4]] = [dict(zip(rows[0], r)) for r in rows[1:]]
    return out


def run(tmp_path, service, fixture=None, lines=None):
    src = os.path.join(FIX, fixture or service + '.txt')
    if lines is not None:
        os.makedirs(tmp_path, exist_ok=True)
        src = str(tmp_path / 'in.log'); open(src, 'w', encoding='utf-8').write(''.join(l + '\n' for l in lines))
    s = parse.parse_file(src, service, str(tmp_path / 'out'))
    return s, collections.defaultdict(list, read_tables(str(tmp_path / 'out')))


# ------------------------------------------------------------------ (a) baris asli per format
def test_kolom_csv_sama_dengan_skema():
    con = db.open(':memory:')
    for table, cols in parse.TABLES.items():
        skema = [r[0] for r in con.execute(f"select column_name from information_schema.columns where table_name = '{table}' order by ordinal_position").fetchall()]
        assert skema == ['file_id', 'line_no', 'folder'] + cols[1:], table
    db.open(':memory:').execute(open(db.SCHEMA).read())  # skema aman dijalankan dua kali


def test_nginx(tmp_path):
    s, t = run(tmp_path, 'nginx-ingress-controller')
    a = t['nginx_access']
    assert (s['lines'], s['err'], s['warn'], s['corrupt_lines'], s['known_service']) == (11, 2, 1, 0, True)  # err: [error] + [crit]
    assert len(a) == 7 and [r['line_no'] for r in a] == list('1234567')
    assert a[0]['ts_utc'] == '2026-09-27 17:03:25' and a[0]['ip'] == '103.176.97.213'
    assert (a[0]['method'], a[0]['path'], a[0]['status'], a[0]['bytes'], a[0]['upstream']) == ('GET', '/css/chunk-vendors.e727ec85.css', '200', '141491', 'om-fe-inhouse-3000')
    assert a[0]['attack_cat'] is None and a[0]['is_uptime_kuma'] == 'false' and len(a[0]['request_id']) == 32
    assert a[1]['is_uptime_kuma'] == 'true' and a[1]['pod_final'] == '10.42.233.139:3000' and a[1]['up_addrs'] == '10.42.233.139:3000' and a[1]['up_statuses'] == '200'
    assert a[1]['request_id'] == 'bbc49c2ed69b931599dd60d93314128c' and a[1]['request_time'] == '0.001'
    # retry: dua percobaan, pod yang menjawab = alamat terakhir
    addrs, sts = a[2]['up_addrs'].split(','), a[2]['up_statuses'].split(',')
    assert len(addrs) == len(sts) == 2 and a[2]['pod_final'] == addrs[-1] and a[2]['path_key'] == '/tx-laporan/count' and '?' in a[2]['path']
    # ditolak di ingress: tanpa upstream
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
    assert (e[1]['upstream_host'], e[1]['kind'], e[1]['request']) == (None, None, None)  # bukan error upstream
    assert e[2]['upstream_host'] == '10.42.245.145:3000'
    m = t['log_message']
    assert [(r['line_no'], r['level']) for r in m] == [('8', 'ERROR'), ('9', 'WARN'), ('10', 'CRIT')]
    assert m[1]['msg_key'] == 'WARN | a client request body is buffered to a temporary file /tmp/client-body/#' and m[1]['raw'].startswith('2026/09/27 19:23:53 [warn]')
    assert s['rows'] == dict(nginx_access=7, nginx_error=3, log_message=3) and s['counters'] == []  # baris pengendali diabaikan


def test_frontend(tmp_path):
    s, t = run(tmp_path, 'om-fe-inhouse')
    assert (s['lines'], s['err'], s['warn']) == (5, 1, 0)  # [notice] tanpa '*N' dan entrypoint diabaikan
    assert t['fe_access'] == [
        dict(line_no='1', ts_utc='2026-09-27 17:03:24', ip='103.176.97.213', method='GET', path='/lapor-ombudsman', path_key='/lapor-ombudsman', status='200'),
        dict(line_no='2', ts_utc='2026-09-27 23:29:19', ip='103.142.111.209', method='GET', path='/apple-touch-icon-precomposed.png', path_key='/apple-touch-icon-precomposed.png', status='404')]
    assert [(r['service'], r['level'], r['ts_utc']) for r in t['nginx_error']] == [('om-fe-inhouse', 'error', '2026-09-27 23:29:19')]
    assert t['log_message'][0]['level'] == 'ERROR'


def test_level_error_nginx_sama_di_ingress_dan_frontend(tmp_path):
    """TRD §4.4 butir 3: crit/alert/emerg = error di kedua layanan (lama: frontend menghitungnya warning)."""
    crit = open(os.path.join(FIX, 'nginx-ingress-controller.txt')).read().splitlines()[9]
    lines = [crit, crit.replace('[crit]', '[alert]'), crit.replace('[crit]', '[emerg]'), crit.replace('[crit]', '[warn]'), crit.replace('[crit]', '[info]')]
    for svc in ('nginx-ingress-controller', 'om-fe-inhouse'):
        s, _ = run(tmp_path / svc, svc, lines=lines)
        assert (s['err'], s['warn']) == (3, 2), svc


def test_simpel_loop(tmp_path):
    s, t = run(tmp_path, 'om-be-simpel-loop')
    assert (s['lines'], s['err'], s['warn']) == (9, 0, 2)  # dua event gagal non-5xx
    ev = t['sl_event']
    assert ev[0] == dict(line_no='1', level='INFO', request_id='b822909ecd30abd7322cb20867352854', event='http.request.completed', method='GET',
                         path='/tx-file-upload', path_key='/tx-file-upload', status='200', ip='103.176.97.213', duration_ms='48', failed='false', err_name=None, err_message=None)
    assert (ev[1]['method'], ev[1]['duration_ms'], ev[1]['status']) == ('PATCH', '3243', '200')
    assert ev[2] == dict(line_no='3', level='ERROR', request_id='69dda3958192b7ac11f28e3e2dc2f10c', event='http.request.failed', method='GET', path='/tx-laporan/count',
                         path_key='/tx-laporan/count', status='401', ip=None, duration_ms='1', failed='true', err_name='UnauthorizedError', err_message='Unauthorized')
    assert (ev[3]['status'], ev[3]['failed'], ev[3]['err_name']) == ('200', 'true', 'MulterError')  # gagal walau status 200
    assert [r['msg_key'] for r in t['log_message']] == ['WARN | # UnauthorizedError: Unauthorized', 'WARN | # MulterError: File too large']
    assert s['counters'] == [['biz', 'Email Terkirim', 1], ['level', 'ERROR', 2], ['level', 'INFO', 4], ['level', 'PERFORMANCE', 1],
                             ['mail', 'sendNotificationMailToKepalaKeasistenanRiksa', 1]]


def test_simpel_loop_baris_teks(tmp_path):
    s, t = run(tmp_path, 'om-be-simpel-loop', lines=['[OM-ERROR] Failed to send mail: timeout', '[OM-WARN] lambat 12 ms', '[OM-INFO] {bukan json',
                                                    '[OM-ERROR] {"event":"http.request.failed","statusCode":500,"path":"/x/12"}'])
    assert (s['err'], s['warn']) == (2, 1)
    assert ['biz', 'Email Gagal', 1] in s['counters'] and ['level', 'ERROR', 2] in s['counters']
    assert [r['msg_key'] for r in t['log_message']] == ['ERROR | Failed to send mail: timeout', 'WARN | lambat # ms', 'ERROR | # None: None']
    assert t['sl_event'] == [dict(line_no='4', level='ERROR', request_id=None, event='http.request.failed', method='None', path='/x/12', path_key='/x/:n',
                                  status='500', ip=None, duration_ms='0', failed='true', err_name=None, err_message=None)]


def test_spring_appsmanager(tmp_path):
    s, t = run(tmp_path, 'om-be-appsmanager')
    assert (s['lines'], s['err'], s['warn']) == (10, 1, 4)
    r = t['spring_line']
    assert len(r) == 7 and (r[0]['ts_utc'], r[0]['level'], r[0]['thread'], r[0]['logger']) == ('2026-09-25 16:04:28', 'INFO', '           main', 'i.c.appsmanager.AppsmanagerApplication')
    assert (r[0]['restart_app'], r[0]['restart_seconds']) == ('AppsmanagerApplication', '17.163')
    assert r[1]['jwt_expired_ms'] == '385316' and r[1]['refresh_expired'] == 'false' and r[1]['level'] == 'ERROR'
    assert r[2]['refresh_expired'] == 'true' and r[2]['jwt_expired_ms'] is None  # pola JWT tidak cocok pada baris refresh
    assert (r[3]['login_kind'], r[3]['login_account'], r[3]['login_ip']) == ('fail', 'akun.contoh@ombudsman.go.id', '39.194.3.114')
    assert (r[4]['login_kind'], r[4]['login_ip']) == ('lock', '36.83.211.41')
    assert (r[5]['login_kind'], r[5]['login_account'], r[5]['login_ip']) == ('ok', 'akun.contoh', '103.189.62.129')
    assert r[6]['login_kind'] is None and r[6]['level'] == 'WARN'
    assert [(m['line_no'], m['level']) for m in t['log_message']] == [('2', 'ERROR'), ('3', 'WARN'), ('4', 'WARN'), ('5', 'WARN'), ('7', 'WARN'), ('8', 'EXC')]
    assert t['log_message'][2]['msg_key'] == "WARN | UserController: SECURITY EVENT: Invalid password for user/email: '<email>' from IP: #.# (Attempt #/#)"
    assert s['counters'] == [['level', 'ERROR', 1], ['level', 'Hibernate SQL', 1], ['level', 'INFO', 2], ['level', 'WARN', 4]]  # EXC tidak menambah err


def test_spring_report_template_per_thread(tmp_path):
    s, t = run(tmp_path, 'om-be-report')
    assert [(r['pdf_template'], r['pdf_failed']) for r in t['spring_line']] == [(None, None), ('cover_map_kuning', 'false'), (None, None), ('?', 'true')]
    # baris ke-4 memakai thread lain (exec-10) daripada 'pdf path' di baris ke-3 (exec-3) -> template '?', seperti sistem lama


def test_coredns(tmp_path):
    s, t = run(tmp_path, 'coredns')
    assert (s['lines'], s['err'], s['warn']) == (3, 1, 0)
    assert t['coredns_error'] == [dict(line_no='1', level='ERROR', domain='backup-simpel4-volume.s3.ap-southeast-3.amazonaws.com.', rtype='AAAA',
                                       message='read udp 10.42.191.189:58401->10.88.1.100:53: i/o timeout')]
    assert t['log_message'][0]['msg_key'] == 'ERROR | backup-simpel4-volume.s3.ap-southeast-#.amazonaws.com. AAAA: read udp X->X: i/o timeout'


@pytest.mark.parametrize('service', ['nginx-ingress-controller', 'om-fe-inhouse', 'om-be-simpel-loop', 'om-be-appsmanager', 'coredns'])
def test_baris_rusak_dihitung_tetapi_tidak_menghasilkan_baris(tmp_path, service):
    s, t = run(tmp_path, service, fixture='rusak.txt')
    assert (s['lines'], s['err'], s['warn'], s['corrupt_lines'], s['rows'], s['counters']) == (1, 0, 0, 1, {}, []) and not t


def test_layanan_tak_dikenal_memakai_parser_spring(tmp_path):
    s, t = run(tmp_path, 'layanan-baru', fixture='om-be-appsmanager.txt')
    assert s['known_service'] is False and len(t['spring_line']) == 7 and t['spring_line'][0]['service'] == 'layanan-baru'


def test_gz_sama_dengan_log(tmp_path):
    import gzip, shutil
    src = os.path.join(FIX, 'om-be-simpel-loop.txt'); gz = str(tmp_path / 'x.log.gz')
    with open(src, 'rb') as a, gzip.open(gz, 'wb') as b: shutil.copyfileobj(a, b)
    s1 = parse.parse_file(src, 'om-be-simpel-loop', str(tmp_path / 'a')); s2 = parse.parse_file(gz, 'om-be-simpel-loop', str(tmp_path / 'b'))
    assert s1 == s2 and read_tables(str(tmp_path / 'a')) == read_tables(str(tmp_path / 'b'))


def test_teks_kosong_dibedakan_dari_null(tmp_path):
    line = '1.2.3.4 - - [04/Oct/2026:17:00:34 +0000] "GET / HTTP/1.1" 200 6599 "-" "" 355 0.001 [] [] - - - - ' + 'a' * 32
    _, t = run(tmp_path, 'nginx-ingress-controller', lines=[line, line[:-33]])
    assert t['nginx_access'][0]['ua'] == '' and t['nginx_access'][0]['attack_cat'] is None and t['nginx_access'][0]['upstream'] == '-'
    assert t['nginx_access'][1]['request_id'] is None and t['nginx_access'][1]['pod_final'] == '-'  # ekor tidak cocok


# ------------------------------------------------------------------ (b) file nyata vs parse() lama
FOLDERS = ('2026-09-27', '2026-09-29', '2026-10-06')
SERVICES = ('nginx-ingress-controller', 'om-fe-inhouse', 'om-be-simpel-loop', 'om-be-appsmanager', 'om-be-referensi', 'om-be-report', 'coredns')


def wib(ts, n=16): return (datetime.datetime.fromisoformat(ts) + datetime.timedelta(hours=7)).strftime('%Y-%m-%d %H:%M:%S')[:n]


@pytest.mark.parametrize('folder', FOLDERS)
@pytest.mark.parametrize('service', SERVICES)
def test_sama_dengan_parser_lama(old, tmp_path, folder, service):
    files = sorted(glob.glob(os.path.join(ROOT, folder, '**', service, '*.log'), recursive=True))
    if not files: pytest.skip(f'{service} tidak ada di {folder}')
    s = old.new_stats(); T = collections.defaultdict(list); counters = C(); samples = {}
    for i, f in enumerate(files):
        pod = rules.pod_name(service, os.path.basename(f)); s['_pod'] = pod; e0, w0, n = s['err'], s['warn'], 0
        for n, line in enumerate(open(f, errors='replace'), 1): old.parse(service, line, s)
        new = parse.parse_file(f, service, str(tmp_path / str(i)))
        assert (new['lines'], new['err'], new['warn']) == (n, s['err'] - e0, s['warn'] - w0), os.path.basename(f)  # = D.files lama
        for k, key, c in new['counters']: counters[k, key] += c
        for table, rows in read_tables(str(tmp_path / str(i))).items():
            for r in rows: T[table].append(dict(r, pod=pod))
        for r in T['log_message']:
            if r['raw'] is not None: samples.setdefault(r['msg_key'], r['raw'])
    assert {k: c for (kind, k), c in counters.items() if kind == 'level'} == dict(s['extra'])
    assert C(r['msg_key'] for r in T['log_message']) == s['msgs'] and samples == s['samples']
    a, e = T['nginx_access'] + T['fe_access'], T['nginx_error']
    if service == 'nginx-ingress-controller':
        assert C(r['status'] for r in a) == s['status'] and C(r['ip'] for r in a) == s['ips'] and C(r['upstream'] for r in a) == s['up']
        assert C(wib(r['ts_utc'], 13) for r in a) == s['hour'] and C(r['ua'][:90] for r in a) == s['ua']
        assert C(f"{r['method']} {r['path_key']}" for r in a) == s['paths']
        flow = collections.defaultdict(C)
        for r in a: flow[r['ip'], r['upstream']][r['pod_final']] += 1
        assert flow == s['flow']
        assert C(r['attack_cat'] for r in a if r['attack_cat']) == s['atk_cat']
        assert {r['request_id'] for r in a if r['request_id']} == {rid for rid, v in old.REQ.items()} & {r['request_id'] for r in a}
        pod, retry = C(), C()
        for r in a:
            if r['up_addrs'] is None: continue
            addrs, sts = r['up_addrs'].split(','), r['up_statuses'].split(',')
            for ad, us in zip(addrs, sts):
                if ad != '-': pod[r['upstream'], ad] += 1
            if len(addrs) > 1: retry[r['upstream'], addrs[0], sts[0]] += 1
        assert pod == s['pod'] and retry == s['retry']
        assert C((wib(r['ts_utc']), r['upstream'], r['status']) for r in a if r['status'][0] == '5') == s['inc']
        assert C(wib(r['ts_utc'], 13) for r in a if r['is_uptime_kuma'] == 'true') == s['uk']
        assert sorted((wib(r['ts_utc']), r['kind'], r['upstream_host'], r['request']) for r in e if r['upstream_host']) == sorted(s['uperr'])
        dur = collections.defaultdict(list)
        for r in a:
            if r['status'] != '101': dur[f"{r['method']} {r['path_key']}"].append(float(r['request_time']))
        assert dur == s['dur']
    elif service == 'om-fe-inhouse':
        assert C(r['status'] for r in a) == s['status'] and C(r['ip'] for r in a) == s['ips'] and C(wib(r['ts_utc'], 13) for r in a) == s['hour']
        assert C(f"{r['method']} {r['path_key']}" for r in a) == s['paths']
    elif service == 'om-be-simpel-loop':
        ev = T['sl_event']
        assert [(r['request_id'], f"{r['method']} {r['path_key']}", r['status'], float(r['duration_ms']), r['failed'] == 'true',
                 f"{r['err_name']}: {r['err_message']}" if r['failed'] == 'true' else '') for r in ev] == [(a_, b, c, float(d), f, g) for a_, b, c, d, f, g in s['sl']]
        assert C(r['status'] for r in ev) == s['status'] and C(r['ip'] for r in ev if r['ip'] is not None) == s['ips']
        assert {k: c for (kind, k), c in counters.items() if kind == 'mail'} == dict(s['mail'])
        assert all(counters['biz', k] == s['biz'][k] for k in ('Email Terkirim', 'Email Gagal'))
    elif service == 'coredns':
        assert C(r['domain'] for r in T['coredns_error']) == s['paths']
    else:
        sp = T['spring_line']
        assert C(wib(r['ts_utc'], 13) for r in sp) == s['hour']
        assert [(wib(r['ts_utc']), r['login_account'].split('@')[0].lower(), r['login_ip'], r['login_kind']) for r in sp if r['login_kind']] == s['lev']
        assert sorted((wib(r['ts_utc']), r['pod'], r['restart_app'], float(r['restart_seconds'])) for r in sp if r['restart_app']) == sorted(s['restart'])
        jwt = C(rules.jwt_bucket(int(r['jwt_expired_ms'])) for r in sp if r['jwt_expired_ms'])
        jwt.update({'Refresh Token Kedaluwarsa': n for n in [sum(r['refresh_expired'] == 'true' for r in sp)] if n})
        assert jwt == s['jwt']
        rep = collections.defaultdict(lambda: [0, 0])
        for r in sp:
            if r['pdf_template'] is not None: rep[r['pdf_template']][r['pdf_failed'] == 'true'] += 1
        assert rep == s['rep']
