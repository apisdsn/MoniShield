#!/usr/bin/env python3
"""Size and performance gate (TRD §9.7, PRD §5.1–§5.3).

  python3 tools/ukur.py [data/sim.duckdb] [--ingest] [--scrypt]
  python3 tools/ukur.py --api [host:port] [--user admin] [--folder 2026-09-29]     # HTTP layer (Stage 11)

Measures: file size and size per table; time of the queries each dashboard page will use; (optional)
ingest time of one extra folder and of an ingest without changes; (optional) password hash cost.
The queries below are the ones the Stage 11 API will use: all read aggregate tables, not raw tables.

--api measures every page endpoint over HTTP: response time and size. Without a host: the app runs inside
this process on the real database (the server must be stopped). With a host: the running server; session from the
S4_COOKIE environment variable (s4_session cookie value from a signed-in browser), or sign in as --user with the
password from S4_UKUR_PASSWORD (or prompted).
"""
import argparse, os, statistics, sys, time

V2 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, V2)

TARGET = dict(ukuran_gb=10, halaman_ms=200, tren_ms=500, ingest_folder_dtk=60, ingest_kosong_dtk=5, api_ms=300, api_kb=500)

# (page name, SQL). $f = folder. One API page calls several of these queries; their sum is measured.
HALAMAN = [
    ('Overview: services', 'SELECT * FROM agg_service WHERE folder = $f'),
    ('Overview: errors per hour', 'SELECT service, hour_wib, err FROM agg_hour WHERE folder = $f AND err > 0'),
    ('Overview: messages across services', 'SELECT service, msg_key, level, n FROM agg_message WHERE folder = $f ORDER BY n DESC LIMIT 25'),
    ('Overview: files', 'SELECT service, pod, lines, err, warn, size_bytes, status FROM ingest_file WHERE folder = $f'),
    ('Service: endpoints', "SELECT key, requests, n4xx, n5xx FROM agg_endpoint WHERE folder = $f AND service = 'nginx-ingress-controller' ORDER BY requests DESC LIMIT 20"),
    ('Service: endpoint performance', "SELECT key, requests, p50, p95, p99, dur_max FROM agg_endpoint WHERE folder = $f AND service = 'nginx-ingress-controller' AND dur_n >= 5 ORDER BY p95 DESC LIMIT 25"),
    ('Service: client IPs', "SELECT ip, requests FROM agg_ip WHERE folder = $f AND service = 'nginx-ingress-controller' ORDER BY requests DESC LIMIT 15"),
    ('Service: messages', "SELECT msg_key, level, n, sample_raw FROM agg_message WHERE folder = $f AND service = 'om-be-appsmanager' ORDER BY n DESC LIMIT 40"),
    ('Security: KPI', """SELECT (SELECT coalesce(sum(hits), 0) FROM agg_attack_url WHERE folder = $f), (SELECT count(*) FROM agg_attack_ip WHERE folder = $f),
                                (SELECT count(*) FROM agg_login_ip WHERE folder = $f AND (fail > 0 OR lock > 0)), (SELECT count(*) FROM agg_account WHERE folder = $f)"""),
    ('Security: attack URLs', 'SELECT * FROM agg_attack_url WHERE folder = $f ORDER BY hits DESC LIMIT 300'),
    ('Security: attacker IPs + owner', 'SELECT a.*, i.asn, i.cc, i.org FROM agg_attack_ip a LEFT JOIN ip_info i USING (ip) WHERE a.folder = $f ORDER BY a.hits DESC LIMIT 100'),
    ('Security: account analysis', 'SELECT * FROM agg_account WHERE folder = $f ORDER BY fail DESC LIMIT 150'),
    ('Root cause: 401', 'SELECT * FROM agg_c401 WHERE folder = $f ORDER BY n DESC LIMIT 30'),
    ('Root cause: JWT', 'SELECT service, bucket, n FROM agg_jwt WHERE folder = $f'),
    ('Availability: incidents', 'SELECT * FROM agg_incident WHERE folder = $f ORDER BY seq'),
    ('Availability: pod connection errors', 'SELECT * FROM v_upstream_error WHERE folder = $f ORDER BY ts_utc DESC LIMIT 200'),
    ('Pods: traffic spread', 'SELECT p.*, coalesce(r.n, 0) FROM agg_pod p LEFT JOIN (SELECT upstream, addr_first, sum(n) n FROM agg_retry WHERE folder = $f GROUP BY ALL) r ON r.upstream = p.upstream AND r.addr_first = p.addr WHERE p.folder = $f'),
    ('Business: summary', 'SELECT (SELECT list(struct_pack(m := metric, n := n)) FROM agg_biz WHERE folder = $f), (SELECT list(struct_pack(k := kind, n := n)) FROM agg_mail WHERE folder = $f)'),
    ('Tracing: traces', 'SELECT * FROM agg_trace WHERE folder = $f ORDER BY n DESC LIMIT 300'),
    ('Map: points', """SELECT i.lat, i.lon, i.city, i.region, i.country, count(DISTINCT f.ip), sum(f.n) FROM agg_flow f JOIN ip_info i USING (ip)
                       WHERE f.folder = $f AND i.lat IS NOT NULL GROUP BY 1, 2, 3, 4, 5"""),
    ('Map: flow table', """SELECT f.ip, i.org, i.city, f.upstream, list(struct_pack(pod := f.pod, n := f.n) ORDER BY f.n DESC)[:3], sum(f.n) AS total
                            FROM agg_flow f LEFT JOIN ip_info i USING (ip) WHERE f.folder = $f GROUP BY 1, 2, 3, 4 ORDER BY total DESC LIMIT 100"""),
]
TREN = [
    ('Trends: lines/errors/warnings per day', 'SELECT folder, service, lines, err, warn FROM agg_service ORDER BY folder'),
    ('Trends: HTTP per day', "SELECT folder, sum(n) FILTER (WHERE status BETWEEN 400 AND 499), sum(n) FILTER (WHERE status BETWEEN 500 AND 599), sum(n) FROM agg_status WHERE service = 'nginx-ingress-controller' GROUP BY folder ORDER BY folder"),
    ('Trends: security per day', """SELECT folder, (SELECT coalesce(sum(hits), 0) FROM agg_attack_url a WHERE a.folder = s.folder),
                                          (SELECT coalesce(sum(fail), 0) FROM agg_login_ip l WHERE l.folder = s.folder) FROM folder_state s ORDER BY folder"""),
    ('Trends: business per day', 'SELECT folder, metric, n FROM agg_biz ORDER BY folder'),
    ('Folder list', 'SELECT folder, range_start_utc, range_end_utc, lines, files, files_empty, files_corrupt FROM folder_state ORDER BY folder DESC'),
]


def waktu(con, sql, params, ulang=5):
    con.execute(sql, params).fetchall()  # warm-up: file cache, not query results
    t = []
    for _ in range(ulang):
        a = time.perf_counter(); con.execute(sql, params).fetchall(); t.append((time.perf_counter() - a) * 1000)
    return min(t), statistics.median(t)


def ukuran_tabel(con):
    blok = con.execute('SELECT block_size FROM pragma_database_size()').fetchone()[0]
    out = {}
    for (t,) in con.execute("SELECT table_name FROM duckdb_tables() WHERE database_name = current_database()").fetchall():
        n = con.execute(f"SELECT count(DISTINCT block_id) FROM pragma_storage_info('{t}') WHERE block_id IS NOT NULL").fetchone()[0]
        baris = con.execute(f'SELECT count(*) FROM {t}').fetchone()[0]
        out[t] = (baris, n * blok)
    return out


def ukur_api(host, folder, user='admin', ulang=5):
    """HTTP layer (PRD §5.1/§5.2): every page endpoint ≤ 300 ms and ≤ 500 KB. Returns an exit code (1 when any misses).

    Empty host: the app in process on the real database (the server must be stopped). With a host: the running server; session
    from S4_COOKIE (s4_session cookie value) when set, otherwise sign in as `user` (password: S4_UKUR_PASSWORD or prompted).
    """
    import json
    sys.path.insert(0, os.path.join(V2, 'tools'))
    if host:
        import getpass, http.cookiejar, urllib.error, urllib.request
        base = host if '://' in host else f'http://{host}'
        if os.environ.get('S4_COOKIE'):
            def get(path):
                with urllib.request.urlopen(urllib.request.Request(base + path, headers={'Cookie': 's4_session=' + os.environ['S4_COOKIE']})) as r: return r.read()
        else:
            op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
            pw = os.environ.get('S4_UKUR_PASSWORD') or getpass.getpass(f'Password for {user}: ')
            masuk = urllib.request.Request(base + '/api/auth/login', data=json.dumps(dict(username=user, password=pw)).encode(),
                                           headers={'Content-Type': 'application/json', 'X-Requested-With': 'ukur'})
            try: op.open(masuk).read()
            except urllib.error.HTTPError as e: sys.exit(f'sign-in failed: {e.code} {e.read()[:200]!r}')
            get = lambda path: op.open(base + path).read()
    else:
        import kesetaraan
        tc = kesetaraan.klien_api(); get = lambda path: tc.get(path).content
    folders = json.loads(get('/api/meta'))['folders']
    folder = folder or max(folders, key=lambda f: f['lines'])['folder']
    svc = [s['service'] for s in json.loads(get(f'/api/folders/{folder}'))['services']]
    urls = ['/api/meta', f'/api/folders/{folder}'] + [f'/api/folders/{folder}/{h}' for h in ('overview', 'map', 'security', 'rootcause', 'availability', 'pods', 'business', 'tracing')]
    urls += [f'/api/folders/{folder}/services/{s}' for s in svc] + ['/api/trends', '/api/trends?last=all',
             f'/api/folders/{folder}/tables/flows?limit=500', f'/api/folders/{folder}/tables/trace?q=unauthorized']
    print(f'# Endpoints over HTTP ({host or "in process"}), folder {folder}; min / median of {ulang} (ms), size (KB); '
          f'target ≤ {TARGET["api_ms"]} ms and ≤ {TARGET["api_kb"]} KB')
    gagal = []
    for u in urls:
        get(u); t = []   # warm-up
        for _ in range(ulang):
            a = time.perf_counter(); body = get(u); t.append((time.perf_counter() - a) * 1000)
        md, kb = statistics.median(t), len(body) / 1000
        ok = md <= TARGET['api_ms'] and kb <= TARGET['api_kb']
        if not ok: gagal.append(u)
        print(f'  {u:62} {min(t):6.1f} / {md:6.1f}  {kb:7.1f} KB  {"ok" if ok else "MISSED"}')
    print(f'\n{len(urls)} endpoints; above target: {gagal or "none"}')
    return 1 if gagal else 0


def main():
    import duckdb
    ap = argparse.ArgumentParser()
    ap.add_argument('db', nargs='?', default=os.path.join(V2, 'data', 'sim.duckdb'))
    ap.add_argument('--ingest', action='store_true', help='also measure ingest time (uses the real database)')
    ap.add_argument('--scrypt', action='store_true', help='measure the password hash cost')
    ap.add_argument('--api', nargs='?', const='', default=None, metavar='HOST:PORT', help='measure endpoints over HTTP (without a host: in process)')
    ap.add_argument('--user', default='admin', help='account for --api HOST when S4_COOKIE is empty')
    ap.add_argument('--folder', help='folder for --api (default: the one with the most lines)')
    a = ap.parse_args()
    if a.api is not None: sys.exit(ukur_api(a.api, a.folder, a.user))
    con = duckdb.connect(a.db, read_only=True)
    folders = [str(r[0]) for r in con.execute('SELECT folder FROM folder_state ORDER BY folder').fetchall()]
    n = len(folders)
    byte = os.path.getsize(a.db)
    print(f'# Size and performance — {os.path.basename(a.db)}')
    print(f'\nFolders: {n}; file {byte / 2**30:.2f} GB ({byte / n / 2**20:.1f} MB per folder)')
    if n != 365: print(f'Extrapolated to 365 folders: {byte / n * 365 / 2**30:.2f} GB')
    gb365 = byte / n * 365 / 2**30
    print(f"Target ≤ {TARGET['ukuran_gb']} GB: {'PASS' if gb365 <= TARGET['ukuran_gb'] else 'FAIL'}")

    print('\n## Size per table (10 largest, estimated from blocks)')
    tab = sorted(ukuran_tabel(con).items(), key=lambda kv: -kv[1][1])
    for t, (baris, b) in tab[:10]: print(f'  {t:22} {baris:>12,} rows  {b / 2**20:>8.1f} MB')
    print(f'  {"(aggregates only)":22} {sum(v[0] for k, v in tab if k.startswith("agg_")):>12,} rows  {sum(v[1] for k, v in tab if k.startswith("agg_")) / 2**20:>8.1f} MB')

    print(f'\n## Query time per page (latest folder; min / median of 5, ms); target ≤ {TARGET["halaman_ms"]} ms')
    f = folders[-1]
    total, lambat = 0, []
    for nama, sql in HALAMAN:
        mn, md = waktu(con, sql, {'f': f})
        total += md
        if md > TARGET['halaman_ms']: lambat.append((nama, md))
        print(f'  {nama:38} {mn:7.1f} / {md:7.1f}')
    print(f'  {"SUM of all page queries":38} {"":7}   {total:7.1f}')
    print(f'\n## Trends (all {n} folders); target ≤ {TARGET["tren_ms"]} ms')
    tren_total = 0
    for nama, sql in TREN:
        mn, md = waktu(con, sql, {})
        tren_total += md
        print(f'  {nama:38} {mn:7.1f} / {md:7.1f}')
    print(f'  {"SUM of Trends tab queries":38} {"":7}   {tren_total:7.1f}')
    if n != 365: print(f'  estimate at 365 folders: {tren_total * 365 / n:.1f} ms')
    print(f'\nPages above target: {lambat or "none"}')

    if a.scrypt:
        import hashlib, secrets
        print('\n## Password hash cost (scrypt)')
        for nlog, r, p in ((14, 8, 1), (15, 8, 1), (16, 8, 1)):
            t0 = time.perf_counter(); hashlib.scrypt(b'sandi-contoh-panjang', salt=secrets.token_bytes(16), n=2**nlog, r=r, p=p, maxmem=2**30); ms = (time.perf_counter() - t0) * 1000
            print(f'  n=2^{nlog} r={r} p={p}: {ms:.0f} ms')

    if a.ingest:
        import subprocess
        print('\n## Ingest time (real database)')
        for label, args in (('no changes', ['ingest']), ('one folder forced again', ['ingest', '--folder', '2026-09-29', '--force'])):
            t0 = time.perf_counter()
            subprocess.run([sys.executable, '-m', 'monishield', *args], cwd=V2, capture_output=True, check=True)
            print(f'  {label:28} {time.perf_counter() - t0:.1f} s')
    con.close()


if __name__ == '__main__':
    main()
