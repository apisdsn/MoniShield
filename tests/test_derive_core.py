"""Agregat inti (TRD §3.4, §4.3): (a) logs_mini, nilai dihitung tangan dari baris di fixtures/lines;
(b) dua folder nyata dibandingkan dengan statistik mentah parser lama, tanpa pemotongan top-N."""
import collections, dataclasses, glob, os

import pytest

import logs_mini
from simpel4 import config, db, ingest, rules
from conftest import ROOT

A, B = '2026-01-01', '2026-01-02'
NG, FE, SL, AM = 'nginx-ingress-controller', 'om-fe-inhouse', 'om-be-simpel-loop', 'om-be-appsmanager'
C = collections.Counter


def make(tmp_path, log_dir, **kw):
    cfg = dataclasses.replace(config.Config(), log_dir=str(log_dir), data_dir=str(tmp_path / 'data'), inbox_dir=str(tmp_path / 'inbox'),
                              state_dir=str(tmp_path / 'data'), cache_dir=str(tmp_path / 'cache'), offline=True)
    con = db.open(cfg.db_path)
    ingest.run(cfg, con, **kw)
    return cfg, con


@pytest.fixture
def mini(tmp_path):
    cfg, con = make(tmp_path, logs_mini.build(tmp_path / 'logs'), workers=0)
    yield con
    con.close()


def q(con, sql, *p): return con.execute(sql, list(p)).fetchall()
def H(ts): return f'{ts:%Y-%m-%d %H}'
def M(ts): return f'{ts:%Y-%m-%d %H:%M}'


# ------------------------------------------------------------------ (a) dihitung tangan
def test_service(mini):
    rows = {r[1]: r[2:] for r in q(mini, 'SELECT * FROM agg_service WHERE folder = ?', B)}
    #            lines err warn err_http err_log files empty corrupt requests n4xx n5xx ip_unique users_ok
    assert rows[NG] == (11, 2, 1, 0, 2, 1, 0, 0, 7, 2, 0, 7, 0)
    assert rows[SL] == (9, 0, 2, 0, 0, 1, 0, 0, 4, 1, 0, 2, 0)          # 2 event gagal non-5xx = warning
    assert rows['coredns'] == (3, 1, 0, 0, 1, 1, 0, 0, 0, 0, 0, 0, 0)
    assert rows['om-be-referensi'] == (1, 0, 0, 0, 0, 1, 0, 1, 0, 0, 0, 0, 0)  # file rusak: 1 baris, 0 isi
    assert rows[AM] == (0, 0, 0, 0, 0, 1, 1, 0, 0, 0, 0, 0, 0)                  # file kosong tetap punya baris layanan
    assert rows['layanan-baru'][:3] == (10, 1, 4) and rows['layanan-baru'][-1] == 1
    a = {r[1]: r[2:] for r in q(mini, 'SELECT * FROM agg_service WHERE folder = ?', A)}
    assert a[FE] == (5, 1, 0, 0, 1, 1, 0, 0, 2, 1, 0, 2, 0) and a[AM] == (10, 1, 4, 0, 1, 1, 0, 0, 0, 0, 0, 0, 1)


def test_hour_wib_dan_error_log_masuk_per_jam(mini):
    h = lambda svc, f: {H(r[0]): r[1:] for r in q(mini, 'SELECT hour_wib, total, err FROM agg_hour WHERE folder = ? AND service = ?', f, svc)}
    # akses nginx: 17:03, 17:02, 17:10, 17:22 UTC 27 Sep -> 00 WIB 28 Sep; 21:54 -> 04; 02:05 (28) -> 09; 16:15 (28) -> 23
    # error log: [error] 18:45 UTC 27 Sep -> 01 WIB; [crit] 16:31 UTC 29 Sep -> 23 WIB 29 Sep; [warn] tidak dihitung
    assert h(NG, B) == {'2026-09-28 00': (4, 0), '2026-09-28 01': (0, 1), '2026-09-28 04': (1, 0), '2026-09-28 09': (1, 0),
                        '2026-09-28 23': (1, 0), '2026-09-29 23': (0, 1)}
    assert h(FE, A) == {'2026-09-28 00': (1, 0), '2026-09-28 06': (1, 1)}       # 404 bukan error; baris [error] 23:29 UTC -> 06 WIB
    assert h(AM, A) == {'2026-09-25 23': (2, 0), '2026-09-28 00': (1, 1), '2026-09-28 05': (1, 0), '2026-09-28 06': (3, 0)}
    assert h('om-be-report', B) == {'2026-09-28 02': (3, 0), '2026-09-28 09': (1, 0)}
    assert h(SL, B) == {} and h('coredns', B) == {}                              # tanpa cap waktu
    for svc, f in ((NG, B), (FE, A), (AM, A)):                                   # jumlah error per jam = KPI Error
        assert sum(v[1] for v in h(svc, f).values()) == q(mini, 'SELECT err FROM agg_service WHERE folder = ? AND service = ?', f, svc)[0][0]


def test_status_upstream_ua(mini):
    assert dict(q(mini, 'SELECT status, n FROM agg_status WHERE folder = ? AND service = ?', B, NG)) == {200: 4, 403: 1, 401: 1, 101: 1}
    assert dict(q(mini, 'SELECT status, n FROM agg_status WHERE folder = ? AND service = ?', B, SL)) == {200: 3, 401: 1}
    assert {r[0]: r[1:] for r in q(mini, 'SELECT upstream, requests, n5xx FROM agg_upstream WHERE folder = ?', B)} == {
        'om-fe-inhouse-3000': (2, 0), 'om-be-simpel-loop-3000': (1, 0), '-': (1, 0), 'om-be-appsmanager-3000': (1, 0), 'cattle-system-rancher-80': (2, 0)}
    ua = dict(q(mini, 'SELECT ua90, n FROM agg_ua WHERE folder = ?', B))
    assert sum(ua.values()) == 7 and ua['Uptime-Kuma/2.0.2'] == 1 and ua['Go-http-client/1.1'] == 1 and max(map(len, ua)) <= 90


def test_endpoint_dan_persentil(mini):
    e = {r[0]: r[1:] for r in q(mini, 'SELECT key, requests, n4xx, n5xx, dur_n, dur_max, p50, p95, p99 FROM agg_endpoint WHERE folder = ? AND service = ?', B, NG)}
    assert e['GET /tx-laporan/count'] == (1, 0, 0, 1, 117.933, 117.933, 117.933, 117.933)     # query dibuang dari kunci
    assert e['GET /forum/core/css.php'] == (1, 1, 0, 1, 0.0, 0.0, 0.0, 0.0) and e['GET /v1/user/select'][:3] == (1, 1, 0)
    assert e['GET /v3/projects/local:p-24lsk/subscribe'] == (1, 0, 0, 0, None, None, None, None)  # 101 websocket: tanpa durasi
    assert len(e) == 7
    s = {r[0]: r[1:] for r in q(mini, 'SELECT key, requests, n4xx, dur_n, p50 FROM agg_endpoint WHERE folder = ? AND service = ?', B, SL)}
    assert s == {'GET /tx-file-upload': (1, 0, 1, 0.048), 'PATCH /regenerate-dokumen': (1, 0, 1, 3.243), 'GET /tx-laporan/count': (1, 1, 1, 0.001), 'POST /files': (1, 0, 1, 0.088)}
    assert q(mini, "SELECT key, requests FROM agg_endpoint WHERE service = 'coredns'") == [('backup-simpel4-volume.s3.ap-southeast-3.amazonaws.com.', 1)]
    assert q(mini, 'SELECT domain, n FROM v_dns') == [('backup-simpel4-volume.s3.ap-southeast-3.amazonaws.com.', 1)]
    assert {r[0] for r in q(mini, 'SELECT key FROM agg_endpoint WHERE service = ?', FE)} == {'GET /lapor-ombudsman', 'GET /apple-touch-icon-precomposed.png'}


def test_persentil_aturan_indeks_lama(tmp_path, old):
    """pct() lama: v[min(n-1, int(q*n))] atas durasi terurut; diuji untuk banyak ukuran sampel."""
    con = db.open(':memory:')
    for n in (1, 2, 3, 4, 5, 7, 10, 19, 20, 21, 99, 100, 101, 200):
        vals = [((i * 7919) % 1000) / 10 for i in range(n)]
        con.execute('DELETE FROM sl_event')
        con.executemany("INSERT INTO sl_event VALUES (1, ?, DATE '2026-01-01', 'INFO', NULL, NULL, 'GET', '/x', '/x', 200, NULL, ?, false, NULL, NULL)", [[i, v * 1000] for i, v in enumerate(vals)])
        stmt = dict((nm.split('_', 1)[1], s) for nm, s in __import__('simpel4.derive', fromlist=['x']).statements() if 'endpoint.sql' in nm and 'INSERT' in s)
        con.execute('DELETE FROM agg_endpoint'); con.execute(stmt['endpoint.sql'], {'f': '2026-01-01'})
        got = con.execute('SELECT dur_n, p50, p95, p99, dur_max FROM agg_endpoint').fetchone()
        v = sorted(vals)
        assert got == pytest.approx((n, old.pct(v, .5), old.pct(v, .95), old.pct(v, .99), v[-1])), n


def test_endpoint_error(mini):
    assert q(mini, 'SELECT status, key, n FROM agg_endpoint_error WHERE service = ? ORDER BY 1', NG) == [(401, 'GET /v1/user/select', 1), (403, 'GET /forum/core/css.php', 1)]
    assert q(mini, 'SELECT status, key, n FROM agg_endpoint_error WHERE service = ?', FE) == [(404, '/apple-touch-icon-precomposed.png', 1)]  # tanpa metode
    assert q(mini, 'SELECT status, key, n FROM agg_endpoint_error WHERE service = ? ORDER BY 1', SL) == [(200, 'POST /files', 1), (401, 'GET /tx-laporan/count', 1)]  # hanya event gagal


def test_ip(mini):
    ip = {r[0]: r[1:] for r in q(mini, 'SELECT ip, requests, n4xx, ua_first_4xx FROM agg_ip WHERE folder = ? AND service = ?', B, NG)}
    assert len(ip) == 7 and ip['143.198.199.107'] == (1, 1, 'Go-http-client/1.1') and ip['103.160.147.100'] == (1, 0, None)
    assert ip['182.6.7.221'][:2] == (1, 1) and ip['182.6.7.221'][2].startswith('Mozilla/5.0 (Linux; Android 10; K)') and len(ip['182.6.7.221'][2]) == 100
    assert dict(q(mini, 'SELECT ip, requests FROM agg_ip WHERE service = ?', SL)) == {'103.176.97.213': 1, '103.235.153.126': 1}  # event gagal tanpa ipAddress
    assert dict(q(mini, 'SELECT ip, n4xx FROM agg_ip WHERE service = ?', FE)) == {'103.176.97.213': 0, '103.142.111.209': 1}


def test_level_efektif_simpel_loop(mini):
    assert dict(q(mini, 'SELECT level, n FROM agg_level WHERE folder = ? AND service = ?', B, SL)) == {'INFO': 4, 'PERFORMANCE': 1, 'WARN': 2}  # tag asli: ERROR 2
    assert dict(q(mini, 'SELECT level, n FROM agg_level WHERE folder = ? AND service = ?', A, AM)) == {'ERROR': 1, 'INFO': 2, 'WARN': 4, 'Hibernate SQL': 1}


def test_message_dan_contoh_pertama(mini, tmp_path):
    m = {r[0]: r[1:] for r in q(mini, 'SELECT msg_key, level, n, sample_raw FROM agg_message WHERE folder = ? AND service = ?', B, NG)}
    assert set(m) == {'ERROR | recv() failed (#: Connection reset by peer) while reading response header from upstream',
                      'WARN | a client request body is buffered to a temporary file /tmp/client-body/#',
                      'CRIT | connect() to #.#:# failed (#: Invalid argument) while connecting to upstream'}
    assert all(v[1] == 1 and v[2].startswith('2026/09/') for v in m.values())
    # dua file, kunci sama: contoh diambil dari file yang lebih dulu menurut relpath
    root = logs_mini.build(tmp_path / 'dua')
    err = logs_mini.lines(NG).splitlines()[7]
    logs_mini.write(logs_mini.log_path(root, B, 'ingress-nginx', NG, 'pod-a'), err.replace('*90237038', '*111') + '\n')
    logs_mini.write(logs_mini.log_path(root, B, 'ingress-nginx', NG, 'pod-z'), err.replace('*90237038', '*999') + '\n')
    _, con = make(tmp_path / 'x', root, workers=0)
    n, raw = q(con, "SELECT n, sample_raw FROM agg_message WHERE service = ? AND msg_key LIKE 'ERROR | recv%'", NG)[0]
    assert n == 3 and '*111 ' in raw
    con.close()


def test_slow_flow_pod_retry(mini):
    assert q(mini, 'SELECT seq, duration_ms, key, status FROM agg_slow') == [(1, 3243.0, 'PATCH /regenerate-dokumen', 200)]
    flow = {r[:3]: r[3] for r in q(mini, 'SELECT ip, upstream, pod, n FROM agg_flow')}
    assert len(flow) == 7 and flow['36.68.184.81', 'om-be-simpel-loop-3000', '10.42.191.163:3000'] == 1 and flow['143.198.199.107', '-', '-'] == 1  # pod terakhir = yang menjawab
    assert {r[:2]: r[2:] for r in q(mini, 'SELECT upstream, addr, attempts, n5xx FROM agg_pod')} == {
        ('om-be-simpel-loop-3000', '10.42.191.169:3000'): (1, 1), ('om-be-simpel-loop-3000', '10.42.191.163:3000'): (1, 0),
        ('om-fe-inhouse-3000', '10.42.245.161:3000'): (1, 0), ('om-fe-inhouse-3000', '10.42.233.139:3000'): (1, 0),
        ('om-be-appsmanager-3000', '10.42.233.151:3000'): (1, 0), ('cattle-system-rancher-80', '10.42.191.133:80'): (2, 0)}
    assert q(mini, 'SELECT upstream, addr_first, status_first, n FROM agg_retry') == [('om-be-simpel-loop-3000', '10.42.191.169:3000', '502', 1)]
    assert q(mini, 'SELECT count(*) FROM v_upstream_error WHERE folder = ?', B) == [(2,)] and q(mini, 'SELECT count(*) FROM v_upstream_error WHERE folder = ?', A) == [(0,)]
    assert q(mini, 'SELECT service, pod, restart_app, restart_seconds FROM v_restart ORDER BY 1') == [('layanan-baru', 'pod-u', 'AppsmanagerApplication', 17.163), (AM, 'pod-a', 'AppsmanagerApplication', 17.163)]


def test_c401_dan_uptime_kuma(mini, tmp_path):
    r = q(mini, 'SELECT ip, key, n, peak_per_min, first_wib, last_wib FROM agg_c401')
    assert [(x[0], x[1], x[2], x[3], M(x[4]), M(x[5])) for x in r] == [('182.6.7.221', 'GET /v1/user/select', 1, 1, '2026-09-28 00:10', '2026-09-28 00:10')]
    assert [(H(x[0]), x[1], x[2]) for x in q(mini, 'SELECT hour_wib, n, fail FROM agg_uk_hour')] == [('2026-09-28 00', 1, 0)]
    assert q(mini, 'SELECT target, n FROM agg_uk_target') == [('GET / → om-fe-inhouse-3000', 1)]
    # puncak per menit: 3 kali di menit yang sama + 1 di menit lain; cek Uptime-Kuma gagal (503)
    root = str(tmp_path / 'p'); l401 = logs_mini.lines(NG).splitlines()[4]; uk = logs_mini.lines(NG).splitlines()[1]
    logs_mini.write(logs_mini.log_path(root, B, 'ingress-nginx', NG, 'pod-n'), '\n'.join(
        [l401, l401.replace('17:10:16', '17:10:59'), l401.replace('17:10:16', '17:10:00'), l401.replace('17:10:16', '18:30:00'), uk.replace('" 200 6599', '" 503 6599')]) + '\n')
    _, con = make(tmp_path / 'y', root, workers=0)
    x = q(con, 'SELECT n, peak_per_min, first_wib, last_wib FROM agg_c401')[0]
    assert (x[0], x[1], M(x[2]), M(x[3])) == (4, 3, '2026-09-28 00:10', '2026-09-28 01:30')
    assert q(con, 'SELECT n, fail FROM agg_uk_hour') == [(1, 1)]
    con.close()


def test_derive_ulang_sama_dan_folder_state(mini):
    before = ingest.checksums(mini)
    assert ingest.derive_all(mini) == [A, B] and ingest.checksums(mini) == before
    assert ingest.derive_all(mini, B) == [B] and ingest.checksums(mini) == before
    assert q(mini, 'SELECT folder::VARCHAR, lines, files, files_empty, files_corrupt FROM folder_state ORDER BY 1') == [(A, 15, 2, 0, 0), (B, 38, 7, 1, 1)]


def test_hapus_file_menurunkan_ulang_agregat(tmp_path):
    root = logs_mini.build(tmp_path / 'logs'); cfg, con = make(tmp_path, root, workers=0)
    os.remove(logs_mini.log_path(root, B, 'ingress-nginx', NG, 'pod-n')); ingest.run(cfg, con, workers=0)
    for t in ('agg_flow', 'agg_pod', 'agg_retry', 'agg_c401', 'agg_uk_hour', 'agg_upstream', 'agg_ua'):
        assert q(con, f'SELECT count(*) FROM {t}') == [(0,)], t
    assert q(con, 'SELECT count(*) FROM agg_service WHERE service = ?', NG) == [(0,)] and q(con, 'SELECT count(*) FROM agg_service WHERE folder = ?', B)[0][0] == 6
    assert ingest.forget(con, A) == 2 and q(con, 'SELECT count(*) FROM agg_service WHERE folder = ?', A) == [(0,)] and q(con, 'SELECT count(*) FROM agg_hour WHERE folder = ?', A) == [(0,)]
    con.close()


# ------------------------------------------------------------------ (b) folder nyata vs statistik mentah parser lama
@pytest.fixture(scope='module')
def real(old, tmp_path_factory):
    tmp = tmp_path_factory.mktemp('real'); out = {}
    cfg = dataclasses.replace(config.Config(), log_dir=ROOT, data_dir=str(tmp / 'data'), inbox_dir=str(tmp / 'inbox'), state_dir=str(tmp / 'data'), cache_dir=str(tmp / 'c'), offline=True)
    con = db.open(cfg.db_path)
    for folder in ('2026-09-30', '2026-10-06'):
        ingest.run(cfg, con, folder=folder)
        for f in sorted(glob.glob(os.path.join(ROOT, folder, '**', '*.log'), recursive=True)):
            svc = os.path.basename(os.path.dirname(f)); s = out.setdefault((folder, svc), old.new_stats()); s['_pod'] = rules.pod_name(svc, os.path.basename(f))
            for line in open(f, errors='replace'): old.parse(svc, line, s)
    yield con, out
    con.close()


def test_nyata_sama_dengan_parser_lama(real, old):
    con, stats = real
    assert len(stats) == 11
    for (fd, svc), s in stats.items():
        g = lambda sql: q(con, sql + ' WHERE folder = ? AND service = ?', fd, svc)
        tag = f'{fd} {svc}'
        hours = {H(r[0]): r[1:] for r in g('SELECT hour_wib, total, err FROM agg_hour')}
        if svc != SL: assert {h: v[0] for h, v in hours.items() if v[0]} == dict(s['hour']), tag
        assert all(v[1] >= s['herr'].get(h, 0) for h, v in hours.items()), tag
        if svc in (NG, FE) or svc.startswith('om-be-') and svc != SL:
            assert sum(v[1] for v in hours.values()) == s['err'], tag                      # TRD §4.4 butir 2
        assert {str(r[0]): r[1] for r in g('SELECT status, n FROM agg_status')} == dict(s['status']), tag
        ep = {r[0]: r[1:] for r in g('SELECT key, requests, n4xx, n5xx, dur_n, p50, p95, p99, dur_max FROM agg_endpoint')}
        assert {k: v[0] for k, v in ep.items()} == dict(s['paths']), tag
        assert {k: list(v[1:3]) for k, v in ep.items() if v[1] or v[2]} == {k: v for k, v in s['pe'].items() if v[0] or v[1]}, tag
        assert {k: v[3] for k, v in ep.items() if v[3]} == {k: len(v) for k, v in s['dur'].items()}, tag
        for k, v in s['dur'].items():
            v = sorted(v); assert ep[k][4:] == pytest.approx((old.pct(v, .5), old.pct(v, .95), old.pct(v, .99), v[-1])), (tag, k)
        key = (lambda r: f'{r[0]} {r[1]}')
        assert {key(r): r[2] for r in g('SELECT status, key, n FROM agg_endpoint_error')} == dict(s['perr']), tag
        ips = {r[0]: r[1:] for r in g('SELECT ip, requests, n4xx, ua_first_4xx FROM agg_ip')}
        assert {k: v[0] for k, v in ips.items()} == dict(s['ips']), tag
        assert {r[0]: r[1] for r in g('SELECT msg_key, n FROM agg_message')} == dict(s['msgs']), tag
        assert {r[0]: r[1] for r in g('SELECT msg_key, sample_raw FROM agg_message')} == s['samples'], tag
        lv = dict(g('SELECT level, n FROM agg_level'))
        if svc == SL:
            assert sum(lv.values()) == sum(s['extra'].values()) and lv.get('WARN', 0) == s['warn'] and lv.get('ERROR', 0) == s['err'], tag  # butir 4
            assert {k: v for k, v in lv.items() if k not in ('ERROR', 'WARN')} == {k: v for k, v in s['extra'].items() if k not in ('ERROR', 'WARN')}, tag
            slow = q(con, 'SELECT duration_ms, key, status::VARCHAR FROM agg_slow WHERE folder = ? ORDER BY seq', fd)
            assert len(slow) == len(s['slow']) and slow[:15] == [(float(d), k, st) for d, k, st in sorted(s['slow'], reverse=True)[:15]], tag
        else:
            assert lv == dict(s['extra']), tag
        row = q(con, 'SELECT lines > 0, err, warn FROM agg_service WHERE folder = ? AND service = ?', fd, svc)[0]
        assert row[1:] == (s['err'], s['warn']), tag
        if svc != NG: continue
        f1 = lambda sql: q(con, sql + ' WHERE folder = ?', fd)
        assert {k: v[1] for k, v in ips.items() if v[1]} == dict(s['ip4']) and {k: v[2] for k, v in ips.items() if v[1]} == s['ip4ua'], tag
        up = {r[0]: r[1:] for r in f1('SELECT upstream, requests, n5xx FROM agg_upstream')}
        assert {k: v[0] for k, v in up.items()} == dict(s['up']) and {k: v[1] for k, v in up.items() if v[1]} == dict(s['up5']), tag
        assert dict(f1('SELECT ua90, n FROM agg_ua')) == dict(s['ua']), tag
        flow = collections.defaultdict(C)
        for ip, u, pod, n in f1('SELECT ip, upstream, pod, n FROM agg_flow'): flow[ip, u][pod] = n
        assert flow == s['flow'], tag
        pod = {r[:2]: r[2:] for r in f1('SELECT upstream, addr, attempts, n5xx FROM agg_pod')}
        assert {k: v[0] for k, v in pod.items()} == dict(s['pod']) and {k: v[1] for k, v in pod.items() if v[1]} == {k: v for k, v in s['pod5'].items() if v}, tag
        assert {r[:3]: r[3] for r in f1('SELECT upstream, addr_first, status_first, n FROM agg_retry')} == dict(s['retry']), tag
        c401 = {r[:2]: (r[2], r[3], M(r[4]), M(r[5])) for r in f1('SELECT ip, key, n, peak_per_min, first_wib, last_wib FROM agg_c401')}
        assert c401 == {k: (c['n'], max(c['m'].values()), c['first'], c['last']) for k, c in s['c401'].items()}, tag
        uk = {H(r[0]): r[1:] for r in f1('SELECT hour_wib, n, fail FROM agg_uk_hour')}
        assert {h: v[0] for h, v in uk.items()} == dict(s['uk']) and {h: v[1] for h, v in uk.items() if v[1]} == dict(s['ukf']), tag
        assert dict(f1('SELECT target, n FROM agg_uk_target')) == dict(s['uk_t']), tag
        assert f1('SELECT count(*) FROM v_upstream_error')[0][0] == len(s['uperr']) and sum(s['retry'].values()) == f1('SELECT sum(n) FROM agg_retry')[0][0], tag
    assert q(con, "SELECT count(*) FROM v_upstream_error WHERE folder = '2026-09-30'") == [(1200,)]   # inv. §8 butir 6: lama menampilkan 200
