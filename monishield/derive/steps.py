"""Agregat yang diturunkan dengan Python karena memakai fungsi sistem lama apa adanya (rules.py), atau
bergantung pada urutan kemunculan dan unquote_plus() yang tidak punya padanan persis di SQL.

Masukannya hasil query kecil (baris serangan, event login, menit ber-5xx, event terkorelasi), bukan seluruh log.
Tiap fungsi: hapus baris folder ini, sisipkan yang baru. Dipanggil di dalam transaksi pemanggil.
"""
import collections
from urllib.parse import unquote_plus

from .. import detect, rules

C = collections.Counter
WIB = "date_trunc('minute', {} + INTERVAL 7 HOUR)::VARCHAR"  # 'YYYY-MM-DD HH:MM:SS' -> dipotong [:16] = menit WIB
MAP = 'CAST(map(?, ?) AS MAP(VARCHAR, INTEGER))'


def _map(d): return [[str(k) for k in d], [int(v) for v in d.values()]]


def attack(con, folder):  # lama:71 add_attack + bagian atk/atk_ip/atk_h summarize()
    rows = con.execute(f"""SELECT a.attack_cat, {WIB.format('a.ts_utc')}, a.ip, a.method, a.path, a.status::VARCHAR, a.bytes, a.ua, a.upstream
                           FROM nginx_access a JOIN ingest_file f USING (file_id)
                           WHERE a.folder = ? AND a.attack_cat IS NOT NULL ORDER BY f.relpath, a.line_no""", [folder]).fetchall()
    atk, atk_ip, atk_h = {}, {}, C()
    for cat, h, ip, meth, path, st, size, ua, up in rows:
        h = h[:16]
        k = (cat, f'{meth} {unquote_plus(path)[:200]}')
        a = atk.setdefault(k, dict(n=0, ips=C(), st=C(), size=set(), up=set(), ua=ua[:100], first=h, last=h))
        a['n'] += 1; a['ips'][ip] += 1; a['st'][st] += 1; a['size'].add(int(size)); a['up'].add(up)
        a['first'] = min(a['first'], h); a['last'] = max(a['last'], h)
        i = atk_ip.setdefault(ip, dict(n=0, cat=C(), st=C(), ua=C(), first=h, last=h))
        i['n'] += 1; i['cat'][cat] += 1; i['st'][st] += 1; i['ua'][ua[:100]] += 1
        i['first'] = min(i['first'], h); i['last'] = max(i['last'], h)
        atk_h[h[:13]] += 1
    for t in ('agg_attack_url', 'agg_attack_ip', 'agg_attack_hour'): con.execute(f'DELETE FROM {t} WHERE folder = ?', [folder])
    if atk: con.executemany(f'INSERT INTO agg_attack_url VALUES (?, ?, ?, ?, ?, ?, {MAP}, ?, ?, ?, ?, ?)', [
        [folder, cat, mp, a['n'], len(a['ips']), a['ips'].most_common(1)[0][0], *_map(dict(sorted(a['st'].items()))), sorted(a['size'])[:5], sorted(a['up']),
         a['ua'], a['first'], a['last']] for (cat, mp), a in atk.items()])
    if atk_ip: con.executemany(f'INSERT INTO agg_attack_ip VALUES (?, ?, ?, {MAP}, {MAP}, ?, ?, ?)', [
        [folder, ip, a['n'], *_map(a['cat']), *_map(dict(sorted(a['st'].items()))), a['ua'].most_common(1)[0][0], a['first'], a['last']] for ip, a in atk_ip.items()])
    if atk_h: con.executemany('INSERT INTO agg_attack_hour VALUES (?, ?, ?)', [[folder, h + ':00:00', n] for h, n in atk_h.items()])


def crs(con, folder):  # Tahap 21, TRD §4.6: klasifikasi OWASP CRS per pasangan unik (metode, path, UA), lalu agregat ber-CAPEC
    """Isi kolom crs_* di nginx_access folder ini dan agg_crs_url/ip/hour. Aturan lama (attack_cat, agg_attack_*) tidak disentuh."""
    con.execute('UPDATE nginx_access SET crs_rules = NULL, capec = NULL, crs_attack = NULL, crs_severity = NULL, crs_score = NULL '
                'WHERE folder = ? AND crs_score IS NOT NULL', [folder])
    found = []
    for meth, path, ua in con.execute('SELECT DISTINCT method, path, ua FROM nginx_access WHERE folder = ?', [folder]).fetchall():
        r = detect.classify(meth, path, ua, detect.PARANOIA)
        if r: found.append([meth, path, ua, r['rules'], r['capec'], r['attack'], r['severity'], r['score']])
    if found:
        con.execute('CREATE OR REPLACE TEMP TABLE _crs (method VARCHAR, path VARCHAR, ua VARCHAR, rules INTEGER[], capec VARCHAR, attack VARCHAR, sev TINYINT, score SMALLINT)')
        con.executemany('INSERT INTO _crs VALUES (?, ?, ?, ?, ?, ?, ?, ?)', found)
        con.execute("""UPDATE nginx_access a SET crs_rules = c.rules, capec = c.capec, crs_attack = c.attack, crs_severity = c.sev, crs_score = c.score
                       FROM _crs c WHERE a.folder = ? AND a.method = c.method AND a.path = c.path AND a.ua = c.ua""", [folder])
        con.execute('DROP TABLE _crs')
    rows = con.execute(f"""SELECT a.capec, a.crs_attack, a.crs_severity, a.crs_rules, {WIB.format('a.ts_utc')}, a.ip, a.method, a.path, a.status::VARCHAR,
                                  a.bytes, a.ua, a.upstream
                           FROM nginx_access a JOIN ingest_file f USING (file_id)
                           WHERE a.folder = ? AND a.crs_score IS NOT NULL ORDER BY f.relpath, a.line_no""", [folder]).fetchall()
    url, ipa, hour = {}, {}, C()
    for capec, fam, sev, rids, h, ip, meth, path, st, size, ua, up in rows:   # bentuk sama dengan attack() di atas
        h, cat = h[:16], f'{capec}/{fam}'   # kategori = CAPEC/keluarga CRS: XSS dan injeksi PHP sama-sama CAPEC-242, tetap terpisah
        a = url.setdefault((cat, f'{meth} {unquote_plus(path)[:200]}'),
                           dict(n=0, ips=C(), st=C(), size=set(), up=set(), ua=ua[:100], first=h, last=h, fam=C(), sev=0, rules=set()))
        a['n'] += 1; a['ips'][ip] += 1; a['st'][st] += 1; a['size'].add(int(size)); a['up'].add(up); a['fam'][fam] += 1
        a['sev'] = max(a['sev'], sev); a['rules'].update(rids); a['first'] = min(a['first'], h); a['last'] = max(a['last'], h)
        i = ipa.setdefault(ip, dict(n=0, cat=C(), st=C(), ua=C(), first=h, last=h, sev=0))
        i['n'] += 1; i['cat'][cat] += 1; i['st'][st] += 1; i['ua'][ua[:100]] += 1; i['sev'] = max(i['sev'], sev)
        i['first'] = min(i['first'], h); i['last'] = max(i['last'], h)
        hour[h[:13]] += 1
    for t in ('agg_crs_url', 'agg_crs_ip', 'agg_crs_hour'): con.execute(f'DELETE FROM {t} WHERE folder = ?', [folder])
    if url: con.executemany(f'INSERT INTO agg_crs_url VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, {MAP}, ?, ?, ?, ?, ?)', [
        [folder, cat, mp, a['fam'].most_common(1)[0][0], a['sev'], sorted(a['rules']), a['n'], len(a['ips']), a['ips'].most_common(1)[0][0],
         *_map(dict(sorted(a['st'].items()))), sorted(a['size'])[:5], sorted(a['up']), a['ua'], a['first'], a['last']] for (cat, mp), a in url.items()])
    if ipa: con.executemany(f'INSERT INTO agg_crs_ip VALUES (?, ?, ?, {MAP}, ?, {MAP}, ?, ?, ?)', [
        [folder, ip, a['n'], *_map(a['cat']), a['sev'], *_map(dict(sorted(a['st'].items()))), a['ua'].most_common(1)[0][0], a['first'], a['last']]
        for ip, a in ipa.items()])
    if hour: con.executemany('INSERT INTO agg_crs_hour VALUES (?, ?, ?)', [[folder, h + ':00:00', n] for h, n in hour.items()])


def accounts(con, folder):  # lama:251 accounts(); event login appsmanager dalam urutan baca
    lev = con.execute(f"""SELECT {WIB.format('s.ts_utc')}, lower(split_part(s.login_account, '@', 1)), s.login_ip, s.login_kind
                          FROM spring_line s JOIN ingest_file f USING (file_id)
                          WHERE s.folder = ? AND s.service = 'om-be-appsmanager' AND s.login_kind IS NOT NULL ORDER BY f.relpath, s.line_no""", [folder]).fetchall()
    per = collections.defaultdict(list)
    for ts, user, ip, kind in lev: per[user].append((ts[:16], user, ip, kind))
    # rules.accounts() memotong hasilnya 150 baris; dipanggil per akun agar agregat tidak terpotong (TRD K4).
    rows = [r for ev in per.values() for r in rules.accounts(ev)]
    con.execute('DELETE FROM agg_account WHERE folder = ?', [folder])
    if rows: con.executemany('INSERT INTO agg_account VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)', [[folder, *r] for r in rows])


def incidents(con, folder):  # lama:271 incidents(); menit ber-5xx per (upstream, status)
    # urut kemunculan pertama, seperti Counter lama: menentukan urutan upstream/status di dalam tiap insiden
    inc = {(ts[:16], up, st): n for ts, up, st, n in con.execute(
        f"""SELECT {WIB.format('a.ts_utc')} AS ts, a.upstream, a.status::VARCHAR, count(*) FROM nginx_access a JOIN ingest_file f USING (file_id)
            WHERE a.folder = ? AND a.status BETWEEN 500 AND 599 GROUP BY ALL ORDER BY min((f.relpath, a.line_no))""", [folder]).fetchall()}
    con.execute('DELETE FROM agg_incident WHERE folder = ?', [folder])
    rows = rules.incidents(inc)
    if rows: con.executemany(f'INSERT INTO agg_incident VALUES (?, ?, ?, ?, ?, {MAP}, {MAP})', [[folder, i, a, b, n, *_map(u), *_map(st)] for i, (a, b, n, u, st) in enumerate(rows, 1)])


def correlation(con, folder):  # lama:481 correlate(); TRD §3.5
    """Gabungkan event simpel-loop folder ini dengan request nginx (SEMUA folder) lewat request id.

    Request id yang muncul lebih dari sekali: yang terakhir menurut urutan baca (relpath, line_no) yang dipakai,
    seperti kamus REQ sistem lama. Mengisi agg_corr, agg_trace, dan agg_hour simpel-loop.
    """
    for t in ('agg_corr', 'agg_trace'): con.execute(f'DELETE FROM {t} WHERE folder = ?', [folder])
    con.execute("DELETE FROM agg_hour WHERE folder = ? AND service = 'om-be-simpel-loop'", [folder])
    total = con.execute('SELECT count(*) FROM sl_event WHERE folder = ?', [folder]).fetchone()[0]
    if not total: return
    con.execute("""CREATE OR REPLACE TEMP TABLE _corr AS
        WITH ids AS (SELECT DISTINCT request_id FROM sl_event WHERE folder = $f AND request_id IS NOT NULL),
        req AS (SELECT a.request_id, arg_max(struct_pack(ts := a.ts_utc, ip := a.ip, method := a.method, path := a.path, upstream := a.upstream, ua := a.ua),
                                             (f.relpath, a.line_no)) AS r
                FROM nginx_access a JOIN ingest_file f USING (file_id) SEMI JOIN ids USING (request_id) GROUP BY a.request_id)
        SELECT g.relpath, e.line_no, e.method || ' ' || e.path_key AS pk, e.status, e.duration_ms, e.failed, e.err_name, e.err_message,
               date_trunc('minute', req.r.ts + INTERVAL 7 HOUR) AS ts, req.r.ip AS ip, req.r.method AS method, req.r.path AS path, req.r.upstream AS upstream, req.r.ua AS ua
        FROM sl_event e JOIN ingest_file g USING (file_id) JOIN req USING (request_id) WHERE e.folder = $f""", {'f': folder})
    matched = con.execute('SELECT count(*) FROM _corr').fetchone()[0]
    con.execute('INSERT INTO agg_corr VALUES (?, ?, ?)', [folder, matched, total])
    con.execute("""INSERT INTO agg_hour SELECT ?, 'om-be-simpel-loop', date_trunc('hour', ts), count(*), count(*) FILTER (WHERE failed) FROM _corr GROUP BY ALL""", [folder])
    tr = {}
    for pk, st, d, failed, name, msg, ts, ip, meth, path, up, ua in con.execute(
            """SELECT pk, status, duration_ms, failed, err_name, err_message, ts::VARCHAR, ip, method, path, upstream, ua
               FROM _corr WHERE failed OR duration_ms >= 5000 ORDER BY relpath, line_no""").fetchall():
        ts = ts[:16]; err = f'{name}: {msg}' if failed else ''  # None -> teks 'None', seperti f-string lama
        key = (ip, st, err or f'Lambat {d / 1000:.1f} dtk', pk)
        t = tr.setdefault(key, dict(n=0, first=ts, last=ts, url=f'{meth} ' + unquote_plus(path)[:300], up=up, ua=ua[:120], d=0))
        t['n'] += 1; t['first'] = min(t['first'], ts); t['last'] = max(t['last'], ts); t['d'] = max(t['d'], d)
    if tr: con.executemany('INSERT INTO agg_trace VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)', [
        [folder, k[0], k[1], k[2], k[3], t['n'], t['url'], t['up'], t['ua'], t['first'], t['last'], t['d']] for k, t in tr.items()])
    con.execute('DROP TABLE _corr')


def business(con, folder):  # lama:190-194 + baris teks (penghitung per file)
    biz, act = C(), C()
    for pk, st, name, n in con.execute("SELECT method || ' ' || path_key, status::VARCHAR, err_name, count(*) FROM sl_event WHERE folder = ? GROUP BY ALL", [folder]).fetchall():
        if st[0] == '2' and pk in rules.BIZ_EP: biz[rules.BIZ_EP[pk]] += n
        if pk == 'POST /tx-laporan/verify-otp' and st[0] != '2': biz['OTP Gagal'] += n
        if name == 'MulterError': biz['Upload Ditolak (Terlalu Besar)'] += n
        if name == 'UnsupportedMediaTypeError': biz['Upload Ditolak (Tipe File)'] += n
        if st[0] == '2' and pk.split()[0] in ('POST', 'PATCH', 'PUT', 'DELETE') and pk not in rules.BIZ_EP: act[pk] += n
    for key, n in con.execute("SELECT c.key, sum(c.n) FROM file_counter c JOIN ingest_file f USING (file_id) WHERE f.folder = ? AND c.kind = 'biz' GROUP BY c.key", [folder]).fetchall():
        biz[key] += int(n)
    for t in ('agg_biz', 'agg_activity'): con.execute(f'DELETE FROM {t} WHERE folder = ?', [folder])
    if biz: con.executemany('INSERT INTO agg_biz VALUES (?, ?, ?)', [[folder, k, n] for k, n in biz.items()])
    if act: con.executemany('INSERT INTO agg_activity VALUES (?, ?, ?)', [[folder, k, n] for k, n in act.items()])


def jwt(con, folder):  # lama:223-224; kelompok umur lewat rules.jwt_bucket()
    out = C()
    for svc, ms, n in con.execute('SELECT service, jwt_expired_ms, count(*) FROM spring_line WHERE folder = ? AND jwt_expired_ms IS NOT NULL GROUP BY ALL', [folder]).fetchall():
        out[svc, rules.jwt_bucket(ms)] += n
    for svc, n in con.execute('SELECT service, count(*) FROM spring_line WHERE folder = ? AND refresh_expired GROUP BY service', [folder]).fetchall():
        out[svc, 'Refresh Token Kedaluwarsa'] += n
    con.execute('DELETE FROM agg_jwt WHERE folder = ?', [folder])
    if out: con.executemany('INSERT INTO agg_jwt VALUES (?, ?, ?, ?)', [[folder, svc, b, n] for (svc, b), n in out.items()])


STEPS = (attack, crs, accounts, incidents, correlation, business, jwt)


def affected_by(con, changed):
    """Folder LAIN yang event simpel-loop-nya ber-request-id sama dengan nginx di folder yang baru berubah (TRD §3.5).

    ponytail: hanya menangkap kecocokan yang BERTAMBAH. Bila file nginx dihapus dari folder F, folder lain yang
    tadinya cocok dengannya tidak disegarkan (kecocokan lintas folder = 0 pada data nyata); `derive --all` membetulkannya.
    """
    if not changed: return []
    marks = ', '.join('?' * len(changed))
    return [str(r[0]) for r in con.execute(f"""SELECT DISTINCT e.folder FROM sl_event e
        WHERE e.folder NOT IN ({marks}) AND e.request_id IN (SELECT request_id FROM nginx_access WHERE folder IN ({marks}))
        ORDER BY 1""", list(changed) * 2).fetchall()]
