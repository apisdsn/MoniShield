"""Feature aggregates (TRD §3.4–§3.5): attacks, login, accounts, incidents, correlation, business, JWT, PDF.
(a) logs_mini and synthetic cases, values computed by hand; (b) three real folders vs the old system's raw statistics."""
import collections, json

import pytest

import logs_mini
from monishield.infrastructure import ingest
from test_derive_core import make, q, H, M, A, B, NG, SL, AM

C = collections.Counter
ID = lambda ch: ch * 32  # 32-hex-digit request id


@pytest.fixture
def mini(tmp_path):
    cfg, con = make(tmp_path, logs_mini.build(tmp_path / 'logs'), workers=0)
    yield con
    con.close()


def ngx(ip, hhmmss, path, status, rid, up='event-api-3000', ua='UA-x', day='27/Sep/2026'):
    return (f'{ip} - - [{day}:{hhmmss} +0000] "GET {path} HTTP/1.1" {status} 100 "-" "{ua}" 355 0.001 '
            f'[{up}] [] 10.42.1.1:3000 100 0.004 {status} {rid}')


def sl(rid, path, status, ms, failed=False, name='E', msg='m'):
    e = dict(requestId=rid, event='http.request.failed' if failed else 'http.request.completed', method='GET', path=path, statusCode=status, durationMs=ms)
    if failed: e['error'] = dict(name=name, message=msg)
    return f"[APP-{'ERROR' if failed else 'INFO'}] " + json.dumps(e)


# ------------------------------------------------------------------ (a) computed by hand
def test_attacks(mini):
    u = {r[:2]: r[2:] for r in q(mini, 'SELECT category, method_path, hits, ip_count, top_ip, status_counts, sizes, upstreams, ua_first, first_wib, last_wib FROM agg_attack_url')}
    assert set(u) == {('Probe PHP / CGI', 'GET /forum/core/css.php'), ('Probe file sensitif', 'GET /.git/config')}
    x = u['Probe PHP / CGI', 'GET /forum/core/css.php']
    assert x[:7] == (1, 1, '66.66.66.107', {'403': 1}, [146], ['-'], 'Go-http-client/1.1') and (M(x[7]), M(x[8])) == ('2026-09-28 04:54', '2026-09-28 04:54')
    y = u['Probe file sensitif', 'GET /.git/config']
    assert y[:6] == (1, 1, '33.33.33.199', {'200': 1}, [5642], ['cattle-system-rancher-80']) and M(y[7]) == '2026-09-28 23:15'
    ip = {r[0]: r[1:] for r in q(mini, 'SELECT ip, hits, cats, status_counts, ua_top FROM agg_attack_ip')}
    assert ip['66.66.66.107'] == (1, {'Probe PHP / CGI': 1}, {'403': 1}, 'Go-http-client/1.1') and len(ip) == 2
    assert {H(r[0]): r[1] for r in q(mini, 'SELECT hour_wib, n FROM agg_attack_hour')} == {'2026-09-28 04': 1, '2026-09-28 23': 1}
    assert dict(q(mini, 'SELECT category, n FROM v_attack_cat')) == {'Probe PHP / CGI': 1, 'Probe file sensitif': 1}


def test_attack_aggregation_order_and_decoding(tmp_path):
    """Key = path decoded ONCE, 200 characters; top IP on a tie = the first to appear; UA = first occurrence."""
    root = str(tmp_path / 'l'); p = '/a%2520b/.env'   # decoded once -> '/a%20b/.env'; classification uses double decoding
    lines = [ngx('9.9.9.9', '10:00:05', p, 404, ID('a'), ua='UA-first'), ngx('1.1.1.1', '10:00:40', p, 200, ID('b'), up='web-frontend-3000', ua='UA-second'),
             ngx('1.1.1.1', '12:30:00', p, 404, ID('c'), ua='UA-second'), ngx('9.9.9.9', '09:15:00', p, 404, ID('d'), ua='UA-first'),
             ngx('5.5.5.5', '09:00:00', '/' + 'x' * 250 + '.php', 404, ID('e'))]
    logs_mini.write(logs_mini.log_path(root, B, 'ingress-nginx', NG, 'pod-n'), '\n'.join(lines) + '\n')
    _, con = make(tmp_path, root, workers=0)
    r = q(con, "SELECT method_path, hits, ip_count, top_ip, status_counts, sizes, upstreams, ua_first, first_wib, last_wib FROM agg_attack_url WHERE category = 'Probe file sensitif'")[0]
    assert r[:8] == ('GET /a%20b/.env', 4, 2, '9.9.9.9', {'200': 1, '404': 3}, [100], ['event-api-3000', 'web-frontend-3000'], 'UA-first')
    assert (M(r[8]), M(r[9])) == ('2026-09-27 16:15', '2026-09-27 19:30')
    assert q(con, "SELECT length(method_path) FROM agg_attack_url WHERE category = 'Probe PHP / CGI'") == [(204,)]  # 'GET ' + 200 characters
    assert q(con, "SELECT hits, cats, ua_top FROM agg_attack_ip WHERE ip = '1.1.1.1'") == [(2, {'Probe file sensitif': 2}, 'UA-second')]
    con.close()


def test_login_and_accounts(mini):
    ip = {r[0]: r[1:] for r in q(mini, 'SELECT ip, fail, lock, ok, accounts, first_wib, last_wib FROM agg_login_ip WHERE folder = ?', A)}
    assert ip['66.66.66.114'][:4] == (1, 0, 0, ['jane.doe@example.com']) and M(ip['66.66.66.114'][4]) == '2026-09-28 06:39'
    assert ip['66.66.66.41'][:4] == (0, 1, 0, ['jane.doe@example.com']) and ip['66.66.66.129'][:4] == (0, 0, 1, [])  # accounts from successful logins are not recorded
    assert {H(r[0]): r[1:] for r in q(mini, 'SELECT hour_wib, fail, ok FROM agg_login_hour WHERE folder = ?', A)} == {'2026-09-28 06': (1, 0), '2026-09-28 05': (0, 1)}
    r = q(mini, 'SELECT account, fail, lock, ok, fail_ips, ok_ips, flags, first_wib, last_wib, notes FROM agg_account WHERE folder = ?', A)
    assert len(r) == 1 and r[0][:7] == ('jane.doe', 1, 1, 1, ['66.66.66.114'], ['66.66.66.129'], []) and (M(r[0][7]), M(r[0][8]), r[0][9]) == ('2026-09-28 05:39', '2026-09-28 06:44', [])
    assert q(mini, 'SELECT count(*) FROM agg_login_ip WHERE folder = ?', B) == [(0,)]  # 'unknown-service' contains the same login lines, but is not the auth service


def test_account_warning_flags_and_no_truncation(tmp_path):
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


def test_incidents(tmp_path):
    root = str(tmp_path / 'l')
    lines = [ngx('1.1.1.1', '17:00:10', '/a', 502, ID('a')), ngx('1.1.1.1', '17:00:50', '/a', 502, ID('b')), ngx('1.1.1.1', '17:03:00', '/a', 504, ID('c'), up='web-frontend-3000'),
             ngx('1.1.1.1', '17:08:00', '/a', 502, ID('d')),        # 5-minute gap from 17:03 -> still the same incident
             ngx('1.1.1.1', '17:14:00', '/a', 503, ID('e')),        # 6-minute gap -> new incident
             ngx('1.1.1.1', '17:15:00', '/a', 200, ID('f'))]
    logs_mini.write(logs_mini.log_path(root, B, 'ingress-nginx', NG, 'pod-n'), '\n'.join(lines) + '\n')
    _, con = make(tmp_path, root, workers=0)
    r = q(con, 'SELECT seq, start_wib, end_wib, n, upstreams, statuses FROM agg_incident ORDER BY seq')
    assert [(x[0], M(x[1]), M(x[2]), x[3], x[4], x[5]) for x in r] == [
        (1, '2026-09-28 00:00', '2026-09-28 00:08', 4, {'event-api-3000': 3, 'web-frontend-3000': 1}, {'502': 3, '504': 1}),
        (2, '2026-09-28 00:14', '2026-09-28 00:14', 1, {'event-api-3000': 1}, {'503': 1})]
    assert q(con, 'SELECT sum(n5xx) FROM agg_upstream') == [(5,)]
    con.close()


def test_correlation_within_and_across_folders_and_duplicate_ids(tmp_path):
    F1, F2 = '2026-02-01', '2026-02-02'; root = str(tmp_path / 'l')
    X, Y, Y2, Z = ID('1'), ID('2'), ID('3'), ID('4')
    logs_mini.write(logs_mini.log_path(root, F1, 'tenant', SL, 'pod-s'), '\n'.join([
        sl(X, '/tx/12', 401, 1, True, 'UnauthorizedError', 'Unauthorized'),   # its nginx is only in F2 -> matched across folders
        sl(Y, '/slow-page', 200, 6000),                                          # slow >= 5 s -> included in traces
        sl(Z, '/error-page', 500, 20, True, 'Boom', 'x'),                          # duplicate request id: F1 and F2
        sl(Y2, '/fast-page', 200, 5),                                             # matched, not included in traces
        sl(ID('9'), '/tanpa-nginx', 500, 1, True)]) + '\n')
    logs_mini.write(logs_mini.log_path(root, F1, 'ingress-nginx', NG, 'pod-n'), '\n'.join([
        ngx('7.7.7.7', '17:30:00', '/slow-page?a=1%20b', 200, Y, ua='U' * 130), ngx('1.1.1.1', '18:10:00', '/error-page', 500, Z), ngx('7.7.7.7', '17:59:59', '/fast-page', 200, Y2)]) + '\n')
    cfg, con = make(tmp_path, root, workers=0)
    assert q(con, 'SELECT matched, total FROM agg_corr') == [(3, 5)]
    tr = lambda: {r[:4]: r[4:] for r in q(con, 'SELECT ip, status, error, key, n, url, upstream, ua, first_wib, max_ms FROM agg_trace WHERE folder = ?', F1)}
    t = tr()
    assert set(t) == {('7.7.7.7', 200, 'Lambat 6.0 dtk', 'GET /slow-page'), ('1.1.1.1', 500, 'Boom: x', 'GET /error-page')}
    assert t['7.7.7.7', 200, 'Lambat 6.0 dtk', 'GET /slow-page'][:4] == (1, 'GET /slow-page?a=1 b', 'event-api-3000', 'U' * 120) and t['7.7.7.7', 200, 'Lambat 6.0 dtk', 'GET /slow-page'][5] == 6000
    hour = lambda: {H(r[0]): r[1:] for r in q(con, 'SELECT hour_wib, total, err FROM agg_hour WHERE folder = ? AND service = ?', F1, SL)}
    assert hour() == {'2026-09-28 00': (2, 0), '2026-09-28 01': (1, 1)}       # events-service time = its nginx request's time
    # next folder arrives: holds nginx for X and a second copy of Z
    logs_mini.write(logs_mini.log_path(root, F2, 'ingress-nginx', NG, 'pod-n'), '\n'.join([
        ngx('8.8.8.8', '20:00:00', '/tx/12?x=1', 401, X, day='28/Sep/2026'), ngx('2.2.2.2', '21:00:00', '/error-page', 500, Z, day='28/Sep/2026')]) + '\n')
    r = ingest.run(cfg, con, workers=0)
    assert r['folders_changed'] == [F2] and r['folders_recorrelated'] == [F1]
    assert q(con, 'SELECT folder::VARCHAR, matched, total FROM agg_corr') == [(F1, 4, 5)]   # F2 without events-service events: no rows
    t = tr()
    assert set(t) == {('7.7.7.7', 200, 'Lambat 6.0 dtk', 'GET /slow-page'), ('2.2.2.2', 500, 'Boom: x', 'GET /error-page'), ('8.8.8.8', 401, 'UnauthorizedError: Unauthorized', 'GET /tx/:n')}
    assert t['8.8.8.8', 401, 'UnauthorizedError: Unauthorized', 'GET /tx/:n'][1] == 'GET /tx/12?x=1'
    assert hour() == {'2026-09-28 00': (2, 0), '2026-09-29 03': (1, 1), '2026-09-29 04': (1, 1)}  # Z now uses the last occurrence (F2)
    before = ingest.checksums(con); ingest.derive_all(con)
    assert ingest.checksums(con) == before and ingest.run(cfg, con, workers=0)['folders_recorrelated'] == []
    con.close()


def test_without_events_service_events_no_correlation_rows(mini):
    assert q(mini, 'SELECT folder::VARCHAR, matched, total FROM agg_corr') == [(B, 0, 4)] and q(mini, 'SELECT count(*) FROM agg_trace') == [(0,)]


def test_business_email_jwt_pdf(mini, tmp_path):
    # POST /files with status 200 but failed (MulterError): the old system counts it as 'files_uploaded' AND 'uploads_rejected_too_large'
    assert dict(q(mini, 'SELECT metric, n FROM agg_biz WHERE folder = ?', B)) == {'files_uploaded': 1, 'uploads_rejected_too_large': 1, 'emails_sent': 1}
    assert q(mini, 'SELECT key, n FROM agg_activity') == [('PATCH /regenerate-document', 1)]   # POST /files is a business metric, not an activity
    assert q(mini, 'SELECT kind, n FROM agg_mail') == [('sendNotificationMailToSupervisor', 1)]
    assert dict(q(mini, 'SELECT bucket, n FROM agg_jwt WHERE folder = ? AND service = ?', A, AM)) == {'5–60 Menit': 1, 'Refresh Token Kedaluwarsa': 1}  # 385,316 ms
    assert {r[0]: r[1:] for r in q(mini, 'SELECT template, ok, fail FROM agg_report')} == {'cover_report': (1, 0), '?': (0, 1)}
    root = str(tmp_path / 'b')
    logs_mini.write(logs_mini.log_path(root, B, 'tenant', SL, 'pod-s'), '\n'.join(
        [sl(ID('a'), '/reports', 201, 5).replace('"GET"', '"POST"'), sl(ID('b'), '/reports/verify-otp', 400, 5, True).replace('"GET"', '"POST"'),
         sl(ID('c'), '/reports/verify-otp', 200, 5).replace('"GET"', '"POST"'), sl(ID('d'), '/x', 415, 5, True, 'UnsupportedMediaTypeError'),
         sl(ID('e'), '/reports/7906a995-b889-48ae-ac6f-f5e60c580953', 200, 5).replace('"GET"', '"DELETE"'), '[APP-ERROR] Failed to send mail']) + '\n')
    _, con = make(tmp_path / 'c', root, workers=0)
    assert dict(q(con, 'SELECT metric, n FROM agg_biz')) == {'reports_created': 1, 'otp_failed': 1, 'otp_verified': 1, 'uploads_rejected_file_type': 1, 'emails_failed': 1}
    assert q(con, 'SELECT key, n FROM agg_activity') == [('DELETE /reports/:id', 1)]
    con.close()


# ------------------------------------------------------------------ (b) real folders vs the old system
FOLDERS = ('2026-09-29', '2026-09-30', '2026-10-06')


def assert_no_sl(con, fd):
    for t in ('agg_corr', 'agg_trace', 'agg_biz', 'agg_activity', 'agg_mail'): assert q(con, f'SELECT count(*) FROM {t} WHERE folder = ?', fd) == [(0,)], t


