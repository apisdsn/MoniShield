"""Feature aggregates (TRD §3.4–§3.5): attacks, login, accounts, incidents, correlation, business, JWT, PDF.
(a) logs_mini and synthetic cases, values computed by hand; (b) three real folders vs the old system's raw statistics."""
import collections, dataclasses, glob, json, os

import pytest

import logs_mini
from monishield.infrastructure import config, db, ingest
from monishield.domain import rules
from conftest import ROOT
from test_derive_core import make, q, H, M, A, B, NG, FE, SL, AM

C = collections.Counter
ID = lambda ch: ch * 32  # 32-hex-digit request id


@pytest.fixture
def mini(tmp_path):
    cfg, con = make(tmp_path, logs_mini.build(tmp_path / 'logs'), workers=0)
    yield con
    con.close()


def ngx(ip, hhmmss, path, status, rid, up='om-be-simpel-loop-3000', ua='UA-x', day='27/Sep/2026'):
    return (f'{ip} - - [{day}:{hhmmss} +0000] "GET {path} HTTP/1.1" {status} 100 "-" "{ua}" 355 0.001 '
            f'[ombudsman-ombudsman-{up}] [] 10.42.1.1:3000 100 0.004 {status} {rid}')


def sl(rid, path, status, ms, failed=False, name='E', msg='m'):
    e = dict(requestId=rid, event='http.request.failed' if failed else 'http.request.completed', method='GET', path=path, statusCode=status, durationMs=ms)
    if failed: e['error'] = dict(name=name, message=msg)
    return f"[OM-{'ERROR' if failed else 'INFO'}] " + json.dumps(e)


# ------------------------------------------------------------------ (a) computed by hand
def test_serangan(mini):
    u = {r[:2]: r[2:] for r in q(mini, 'SELECT category, method_path, hits, ip_count, top_ip, status_counts, sizes, upstreams, ua_first, first_wib, last_wib FROM agg_attack_url')}
    assert set(u) == {('Probe PHP / CGI', 'GET /forum/core/css.php'), ('Probe file sensitif', 'GET /.git/config')}
    x = u['Probe PHP / CGI', 'GET /forum/core/css.php']
    assert x[:7] == (1, 1, '143.198.199.107', {'403': 1}, [146], ['-'], 'Go-http-client/1.1') and (M(x[7]), M(x[8])) == ('2026-09-28 04:54', '2026-09-28 04:54')
    y = u['Probe file sensitif', 'GET /.git/config']
    assert y[:6] == (1, 1, '34.19.127.199', {'200': 1}, [5642], ['cattle-system-rancher-80']) and M(y[7]) == '2026-09-28 23:15'
    ip = {r[0]: r[1:] for r in q(mini, 'SELECT ip, hits, cats, status_counts, ua_top FROM agg_attack_ip')}
    assert ip['143.198.199.107'] == (1, {'Probe PHP / CGI': 1}, {'403': 1}, 'Go-http-client/1.1') and len(ip) == 2
    assert {H(r[0]): r[1] for r in q(mini, 'SELECT hour_wib, n FROM agg_attack_hour')} == {'2026-09-28 04': 1, '2026-09-28 23': 1}
    assert dict(q(mini, 'SELECT category, n FROM v_attack_cat')) == {'Probe PHP / CGI': 1, 'Probe file sensitif': 1}


def test_serangan_agregasi_urutan_dan_decode(tmp_path):
    """Key = path decoded ONCE, 200 characters; top IP on a tie = the first to appear; UA = first occurrence."""
    root = str(tmp_path / 'l'); p = '/a%2520b/.env'   # decoded once -> '/a%20b/.env'; classification uses double decoding
    lines = [ngx('9.9.9.9', '10:00:05', p, 404, ID('a'), ua='UA-pertama'), ngx('1.1.1.1', '10:00:40', p, 200, ID('b'), up='om-fe-inhouse-3000', ua='UA-kedua'),
             ngx('1.1.1.1', '12:30:00', p, 404, ID('c'), ua='UA-kedua'), ngx('9.9.9.9', '09:15:00', p, 404, ID('d'), ua='UA-pertama'),
             ngx('5.5.5.5', '09:00:00', '/' + 'x' * 250 + '.php', 404, ID('e'))]
    logs_mini.write(logs_mini.log_path(root, B, 'ingress-nginx', NG, 'pod-n'), '\n'.join(lines) + '\n')
    _, con = make(tmp_path, root, workers=0)
    r = q(con, "SELECT method_path, hits, ip_count, top_ip, status_counts, sizes, upstreams, ua_first, first_wib, last_wib FROM agg_attack_url WHERE category = 'Probe file sensitif'")[0]
    assert r[:8] == ('GET /a%20b/.env', 4, 2, '9.9.9.9', {'200': 1, '404': 3}, [100], ['om-be-simpel-loop-3000', 'om-fe-inhouse-3000'], 'UA-pertama')
    assert (M(r[8]), M(r[9])) == ('2026-09-27 16:15', '2026-09-27 19:30')
    assert q(con, "SELECT length(method_path) FROM agg_attack_url WHERE category = 'Probe PHP / CGI'") == [(204,)]  # 'GET ' + 200 characters
    assert q(con, "SELECT hits, cats, ua_top FROM agg_attack_ip WHERE ip = '1.1.1.1'") == [(2, {'Probe file sensitif': 2}, 'UA-kedua')]
    con.close()


def test_login_dan_akun(mini):
    ip = {r[0]: r[1:] for r in q(mini, 'SELECT ip, fail, lock, ok, accounts, first_wib, last_wib FROM agg_login_ip WHERE folder = ?', A)}
    assert ip['39.194.3.114'][:4] == (1, 0, 0, ['akun.contoh@ombudsman.go.id']) and M(ip['39.194.3.114'][4]) == '2026-09-28 06:39'
    assert ip['36.83.211.41'][:4] == (0, 1, 0, ['akun.contoh@ombudsman.go.id']) and ip['103.189.62.129'][:4] == (0, 0, 1, [])  # accounts from successful logins are not recorded
    assert {H(r[0]): r[1:] for r in q(mini, 'SELECT hour_wib, fail, ok FROM agg_login_hour WHERE folder = ?', A)} == {'2026-09-28 06': (1, 0), '2026-09-28 05': (0, 1)}
    r = q(mini, 'SELECT account, fail, lock, ok, fail_ips, ok_ips, flags, first_wib, last_wib, notes FROM agg_account WHERE folder = ?', A)
    assert len(r) == 1 and r[0][:7] == ('akun.contoh', 1, 1, 1, ['39.194.3.114'], ['103.189.62.129'], []) and (M(r[0][7]), M(r[0][8]), r[0][9]) == ('2026-09-28 05:39', '2026-09-28 06:44', [])
    assert q(mini, 'SELECT count(*) FROM agg_login_ip WHERE folder = ?', B) == [(0,)]  # 'layanan-baru' contains the same login lines, but is not appsmanager


def test_akun_tanda_bahaya_dan_tidak_terpotong(tmp_path):
    root = str(tmp_path / 'l'); out = []
    line = lambda t, kind, user, ip: f"2026-09-27 {t}.000  WARN 1 --- [x] c.UserController : " + (
        f"SECURITY EVENT: Invalid password for user/email: '{user}' from IP: {ip} (Attempt 1/3)" if kind == 'fail' else f"SECURITY EVENT: User '{user}' successfully logged in from IP: {ip}")
    out += [line(f'10:0{i}:00', 'fail', 'Korban@x.id', '1.1.1.1') for i in range(3)] + [line('10:30:00', 'ok', 'korban', '2.2.2.2')]   # 3 failures then success from another IP
    out += [line('11:00:00', 'fail', 'dua@x.id', '3.3.3.3'), line('11:01:00', 'fail', 'dua@x.id', '4.4.4.4')]                           # tried from 2 IPs
    out += [line(f'12:{i % 60:02d}:00', 'fail', f'u{i}@x.id', '5.5.5.5') for i in range(170)]                                           # > 150 accounts
    logs_mini.write(logs_mini.log_path(root, A, None, AM, 'pod-a'), '\n'.join(out) + '\n')
    _, con = make(tmp_path, root, workers=0)
    r = q(con, "SELECT fail, ok, fail_ips, ok_ips, flags, notes FROM agg_account WHERE account = 'korban'")
    assert r == [(3, 1, ['1.1.1.1'], ['2.2.2.2'], ['Sukses Dari IP Berbeda', 'Sukses Setelah ≥3 Gagal'], ['2026-09-27 17:30 sukses dari 2.2.2.2'])]
    assert q(con, "SELECT flags FROM agg_account WHERE account = 'dua'") == [(['Dicoba Dari ≥2 IP'],)]
    assert q(con, 'SELECT count(*) FROM agg_account') == [(172,)]                       # the old system truncates at 150
    assert q(con, "SELECT accounts FROM agg_login_ip WHERE ip = '1.1.1.1'") == [(['Korban@x.id'],)] and q(con, 'SELECT users_ok FROM agg_service WHERE service = ?', AM) == [(1,)]
    con.close()


def test_insiden(tmp_path):
    root = str(tmp_path / 'l')
    lines = [ngx('1.1.1.1', '17:00:10', '/a', 502, ID('a')), ngx('1.1.1.1', '17:00:50', '/a', 502, ID('b')), ngx('1.1.1.1', '17:03:00', '/a', 504, ID('c'), up='om-fe-inhouse-3000'),
             ngx('1.1.1.1', '17:08:00', '/a', 502, ID('d')),        # 5-minute gap from 17:03 -> still the same incident
             ngx('1.1.1.1', '17:14:00', '/a', 503, ID('e')),        # 6-minute gap -> new incident
             ngx('1.1.1.1', '17:15:00', '/a', 200, ID('f'))]
    logs_mini.write(logs_mini.log_path(root, B, 'ingress-nginx', NG, 'pod-n'), '\n'.join(lines) + '\n')
    _, con = make(tmp_path, root, workers=0)
    r = q(con, 'SELECT seq, start_wib, end_wib, n, upstreams, statuses FROM agg_incident ORDER BY seq')
    assert [(x[0], M(x[1]), M(x[2]), x[3], x[4], x[5]) for x in r] == [
        (1, '2026-09-28 00:00', '2026-09-28 00:08', 4, {'om-be-simpel-loop-3000': 3, 'om-fe-inhouse-3000': 1}, {'502': 3, '504': 1}),
        (2, '2026-09-28 00:14', '2026-09-28 00:14', 1, {'om-be-simpel-loop-3000': 1}, {'503': 1})]
    assert q(con, 'SELECT sum(n5xx) FROM agg_upstream') == [(5,)]
    con.close()


def test_korelasi_dalam_folder_lintas_folder_dan_id_ganda(tmp_path):
    F1, F2 = '2026-02-01', '2026-02-02'; root = str(tmp_path / 'l')
    X, Y, Y2, Z = ID('1'), ID('2'), ID('3'), ID('4')
    logs_mini.write(logs_mini.log_path(root, F1, 'ombudsman', SL, 'pod-s'), '\n'.join([
        sl(X, '/tx/12', 401, 1, True, 'UnauthorizedError', 'Unauthorized'),   # its nginx is only in F2 -> matched across folders
        sl(Y, '/lambat', 200, 6000),                                          # slow >= 5 s -> included in traces
        sl(Z, '/galat', 500, 20, True, 'Boom', 'x'),                          # duplicate request id: F1 and F2
        sl(Y2, '/cepat', 200, 5),                                             # matched, not included in traces
        sl(ID('9'), '/tanpa-nginx', 500, 1, True)]) + '\n')
    logs_mini.write(logs_mini.log_path(root, F1, 'ingress-nginx', NG, 'pod-n'), '\n'.join([
        ngx('7.7.7.7', '17:30:00', '/lambat?a=1%20b', 200, Y, ua='U' * 130), ngx('1.1.1.1', '18:10:00', '/galat', 500, Z), ngx('7.7.7.7', '17:59:59', '/cepat', 200, Y2)]) + '\n')
    cfg, con = make(tmp_path, root, workers=0)
    assert q(con, 'SELECT matched, total FROM agg_corr') == [(3, 5)]
    tr = lambda: {r[:4]: r[4:] for r in q(con, 'SELECT ip, status, error, key, n, url, upstream, ua, first_wib, max_ms FROM agg_trace WHERE folder = ?', F1)}
    t = tr()
    assert set(t) == {('7.7.7.7', 200, 'Lambat 6.0 dtk', 'GET /lambat'), ('1.1.1.1', 500, 'Boom: x', 'GET /galat')}
    assert t['7.7.7.7', 200, 'Lambat 6.0 dtk', 'GET /lambat'][:4] == (1, 'GET /lambat?a=1 b', 'om-be-simpel-loop-3000', 'U' * 120) and t['7.7.7.7', 200, 'Lambat 6.0 dtk', 'GET /lambat'][5] == 6000
    hour = lambda: {H(r[0]): r[1:] for r in q(con, 'SELECT hour_wib, total, err FROM agg_hour WHERE folder = ? AND service = ?', F1, SL)}
    assert hour() == {'2026-09-28 00': (2, 0), '2026-09-28 01': (1, 1)}       # simpel-loop time = its nginx request's time
    # next folder arrives: holds nginx for X and a second copy of Z
    logs_mini.write(logs_mini.log_path(root, F2, 'ingress-nginx', NG, 'pod-n'), '\n'.join([
        ngx('8.8.8.8', '20:00:00', '/tx/12?x=1', 401, X, day='28/Sep/2026'), ngx('2.2.2.2', '21:00:00', '/galat', 500, Z, day='28/Sep/2026')]) + '\n')
    r = ingest.run(cfg, con, workers=0)
    assert r['folders_changed'] == [F2] and r['folders_recorrelated'] == [F1]
    assert q(con, 'SELECT folder::VARCHAR, matched, total FROM agg_corr') == [(F1, 4, 5)]   # F2 without simpel-loop events: no rows
    t = tr()
    assert set(t) == {('7.7.7.7', 200, 'Lambat 6.0 dtk', 'GET /lambat'), ('2.2.2.2', 500, 'Boom: x', 'GET /galat'), ('8.8.8.8', 401, 'UnauthorizedError: Unauthorized', 'GET /tx/:n')}
    assert t['8.8.8.8', 401, 'UnauthorizedError: Unauthorized', 'GET /tx/:n'][1] == 'GET /tx/12?x=1'
    assert hour() == {'2026-09-28 00': (2, 0), '2026-09-29 03': (1, 1), '2026-09-29 04': (1, 1)}  # Z now uses the last occurrence (F2)
    before = ingest.checksums(con); ingest.derive_all(con)
    assert ingest.checksums(con) == before and ingest.run(cfg, con, workers=0)['folders_recorrelated'] == []
    con.close()


def test_tanpa_event_simpel_loop_tidak_ada_baris_korelasi(mini):
    assert q(mini, 'SELECT folder::VARCHAR, matched, total FROM agg_corr') == [(B, 0, 4)] and q(mini, 'SELECT count(*) FROM agg_trace') == [(0,)]


def test_bisnis_email_jwt_pdf(mini, tmp_path):
    # POST /files with status 200 but failed (MulterError): the old system counts it as 'File Diunggah' AND 'Upload Ditolak'
    assert dict(q(mini, 'SELECT metric, n FROM agg_biz WHERE folder = ?', B)) == {'File Diunggah': 1, 'Upload Ditolak (Terlalu Besar)': 1, 'Email Terkirim': 1}
    assert q(mini, 'SELECT key, n FROM agg_activity') == [('PATCH /regenerate-dokumen', 1)]   # POST /files is a business metric, not an activity
    assert q(mini, 'SELECT kind, n FROM agg_mail') == [('sendNotificationMailToKepalaKeasistenanRiksa', 1)]
    assert dict(q(mini, 'SELECT bucket, n FROM agg_jwt WHERE folder = ? AND service = ?', A, AM)) == {'5–60 Menit': 1, 'Refresh Token Kedaluwarsa': 1}  # 385,316 ms
    assert {r[0]: r[1:] for r in q(mini, 'SELECT template, ok, fail FROM agg_report')} == {'cover_map_kuning': (1, 0), '?': (0, 1)}
    root = str(tmp_path / 'b')
    logs_mini.write(logs_mini.log_path(root, B, 'ombudsman', SL, 'pod-s'), '\n'.join(
        [sl(ID('a'), '/tx-laporan', 201, 5).replace('"GET"', '"POST"'), sl(ID('b'), '/tx-laporan/verify-otp', 400, 5, True).replace('"GET"', '"POST"'),
         sl(ID('c'), '/tx-laporan/verify-otp', 200, 5).replace('"GET"', '"POST"'), sl(ID('d'), '/x', 415, 5, True, 'UnsupportedMediaTypeError'),
         sl(ID('e'), '/tx-laporan/7906a995-b889-48ae-ac6f-f5e60c580953', 200, 5).replace('"GET"', '"DELETE"'), '[OM-ERROR] Failed to send mail']) + '\n')
    _, con = make(tmp_path / 'c', root, workers=0)
    assert dict(q(con, 'SELECT metric, n FROM agg_biz')) == {'Laporan Dibuat': 1, 'OTP Gagal': 1, 'OTP Terverifikasi': 1, 'Upload Ditolak (Tipe File)': 1, 'Email Gagal': 1}
    assert q(con, 'SELECT key, n FROM agg_activity') == [('DELETE /tx-laporan/:id', 1)]
    con.close()


# ------------------------------------------------------------------ (b) real folders vs the old system
FOLDERS = ('2026-09-29', '2026-09-30', '2026-10-06')


@pytest.fixture(scope='module')
def real(old, tmp_path_factory):
    tmp = tmp_path_factory.mktemp('real'); data = {}
    cfg = dataclasses.replace(config.Config(), log_dir=ROOT, data_dir=str(tmp / 'data'), inbox_dir=str(tmp / 'inbox'), state_dir=str(tmp / 'data'), cache_dir=str(tmp / 'c'), offline=True)
    con = db.open(cfg.db_path); old.REQ.clear()
    for folder in FOLDERS:
        ingest.run(cfg, con, folder=folder)
        for f in sorted(glob.glob(os.path.join(ROOT, folder, '**', '*.log'), recursive=True)):
            svc = os.path.basename(os.path.dirname(f)); s = data.setdefault(folder, {}).setdefault(svc, old.new_stats()); s['_pod'] = rules.pod_name(svc, os.path.basename(f))
            for line in open(f, errors='replace'): old.parse(svc, line, s)
    old.correlate(data)
    yield con, data
    con.close()


@pytest.mark.parametrize('fd', FOLDERS)
def test_nyata_sama_dengan_sistem_lama(real, old, fd):
    con, data = real; f1 = lambda sql: q(con, sql + ' WHERE folder = ?', fd)
    n = data[fd][NG]
    got = {(r[0], r[1]): r[2:] for r in f1('SELECT category, method_path, hits, ip_count, top_ip, status_counts, sizes, upstreams, ua_first, first_wib, last_wib FROM agg_attack_url')}
    want = {tuple(k.split('\t')): (a['n'], len(a['ips']), a['ips'].most_common(1)[0][0], dict(a['st']), sorted(a['size'])[:5], sorted(a['up']), a['ua'], a['first'], a['last']) for k, a in n['atk'].items()}
    assert {k: (*v[:7], M(v[7]), M(v[8])) for k, v in got.items()} == want and len(want) > 15
    got = {r[0]: (r[1], r[2], r[3], r[4], M(r[5]), M(r[6])) for r in f1('SELECT ip, hits, cats, status_counts, ua_top, first_wib, last_wib FROM agg_attack_ip')}
    assert got == {ip: (a['n'], dict(a['cat']), dict(a['st']), a['ua'].most_common(1)[0][0], a['first'], a['last']) for ip, a in n['atk_ip'].items()}
    assert {H(r[0]): r[1] for r in f1('SELECT hour_wib, n FROM agg_attack_hour')} == dict(n['atk_h']) and dict(f1('SELECT category, n FROM v_attack_cat')) == dict(n['atk_cat'])
    inc = [[M(r[0]), M(r[1]), r[2], r[3], r[4]] for r in q(con, 'SELECT start_wib, end_wib, n, upstreams, statuses FROM agg_incident WHERE folder = ? ORDER BY seq', fd)]
    assert inc == old.incidents(n['inc']) and len(inc) >= 1
    assert [(list(r[3]), list(r[4])) for r in inc] == [(list(r[3]), list(r[4])) for r in old.incidents(n['inc'])]  # key order is also the same (display order)
    before = ingest.checksums(con); ingest.derive_all(con, fd)
    assert ingest.checksums(con) == before  # re-deriving = identical result

    a = data[fd][AM]
    got = {r[0]: (r[1], r[2], r[3], set(r[4]), M(r[5]), M(r[6])) for r in f1('SELECT ip, fail, lock, ok, accounts, first_wib, last_wib FROM agg_login_ip')}
    assert got == {ip: (u['fail'], u['lock'], u['ok'], u['users'], u['first'], u['last']) for ip, u in a['login'].items()} and len(got) > 50
    lh = {H(r[0]): r[1:] for r in f1('SELECT hour_wib, fail, ok FROM agg_login_hour')}
    assert {h: v[0] for h, v in lh.items() if v[0]} == dict(a['login_h']) and {h: v[1] for h, v in lh.items() if v[1]} == dict(C(e[0][:13] for e in a['lev'] if e[3] == 'ok'))
    acct = {r[0]: [r[0], r[1], r[2], r[3], r[4], r[5], r[6], M(r[7]), M(r[8]), r[9]] for r in f1('SELECT account, fail, lock, ok, fail_ips, ok_ips, flags, first_wib, last_wib, notes FROM agg_account')}
    lama = old.accounts(a['lev'])
    assert acct == {r[0]: r for r in lama} and len(lama) < 150
    assert q(con, 'SELECT users_ok FROM agg_service WHERE folder = ? AND service = ?', fd, AM)[0][0] == len({e[1] for e in a['lev'] if e[3] == 'ok'})
    for svc in (AM, 'om-be-referensi', 'om-be-report'):
        if svc in data[fd]: assert dict(q(con, 'SELECT bucket, n FROM agg_jwt WHERE folder = ? AND service = ?', fd, svc)) == dict(data[fd][svc]['jwt']), svc
    if 'om-be-report' in data[fd]:
        assert {r[0]: [r[1], r[2]] for r in f1('SELECT template, ok, fail FROM agg_report')} == dict(data[fd]['om-be-report']['rep'])

    s = data[fd].get(SL)
    if not s: return assert_no_sl(con, fd)
    assert list(f1('SELECT matched, total FROM agg_corr')[0]) == s['corr'] and s['corr'][0] > 1000
    hours = {H(r[0]): r[1:] for r in q(con, 'SELECT hour_wib, total, err FROM agg_hour WHERE folder = ? AND service = ?', fd, SL)}
    assert {h: v[0] for h, v in hours.items()} == dict(s['hour']) and {h: v[1] for h, v in hours.items() if v[1]} == dict(s['herr'])
    tr = {(r[0], str(r[1]), r[2], r[3]): [r[4], r[5], r[6], r[7], M(r[8]), M(r[9]), r[10]] for r in f1('SELECT ip, status, error, key, n, url, upstream, ua, first_wib, last_wib, max_ms FROM agg_trace')}
    lama = {tuple(r[:4]): r[4:] for r in s['trace']}                                     # the old system truncates to the top 300
    assert {k: tr[k] for k in lama} == {k: [v[0], v[1], v[2], v[3], v[4], v[5], float(v[6])] for k, v in lama.items()} and len(tr) >= len(lama) > 50
    assert dict(f1('SELECT metric, n FROM agg_biz')) == dict(s['biz']) and dict(f1('SELECT kind, n FROM agg_mail')) == dict(s['mail']) and dict(f1('SELECT key, n FROM agg_activity')) == dict(s['act'])


def assert_no_sl(con, fd):
    for t in ('agg_corr', 'agg_trace', 'agg_biz', 'agg_activity', 'agg_mail'): assert q(con, f'SELECT count(*) FROM {t} WHERE folder = ?', fd) == [(0,)], t


def test_nyata_jejak_tidak_terpotong(real):
    con, data = real
    assert q(con, "SELECT count(*) FROM agg_trace WHERE folder = '2026-09-29'")[0][0] > 300 == len(data['2026-09-29'][SL]['trace'])
