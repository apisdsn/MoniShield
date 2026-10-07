"""Perintah baris: python -m monishield <perintah>. Subperintah bertambah per tahap (docs/04-rencana.md)."""
import argparse, os, sys

from . import __version__, config, rules

RAW = ('nginx_access', 'nginx_error', 'fe_access', 'sl_event', 'spring_line', 'coredns_error', 'log_message')


def _n(x): return f'{x:,}'.replace(',', '.')


def cmd_status(cfg, args):
    print(f'monishield {__version__}')
    if not args.folder and not args.checksum:
        for k, v in cfg.public().items():
            if isinstance(v, dict): v = f'{len(v)} entri'
            print(f'  {k:22} {v}')
        from . import auth
        print(f'  {"basis data akun":22} {auth.redact_url(cfg.auth_url)}')
        from . import importer
        cs = importer.Credentials(cfg).status()
        print(f'  {"impor S3":22} ' + (f'aktif: {", ".join(importer.allowed_examples(cfg))}' if cfg.import_buckets else 'tidak diaktifkan'))
        print(f'  {"kredensial impor":22} ' + ('tersedia (lingkungan)' if cs['available'] else 'tidak ada'))
        folders = sorted(d for d in os.listdir(cfg.log_dir) if rules.DATE_DIR.fullmatch(d)) if os.path.isdir(cfg.log_dir) else []
        print(f'folder log di disk: {len(folders)}' + (f' ({folders[0]} … {folders[-1]})' if folders else ' (tidak ada)'))
    if not os.path.exists(cfg.db_path):
        print(f'belum ada database ({cfg.db_path}); jalankan ingest'); return 0
    from . import db, ingest
    con = db.open(cfg.db_path)
    if args.checksum:
        for t, (n, h) in ingest.checksums(con).items(): print(f'  {t:22} {n:>10} {h:020d}')
        return 0
    if args.folder:
        rows = con.execute("""SELECT service, count(*), sum(lines), sum(err), sum(warn), count(*) FILTER (WHERE lines = 0),
                                     count(*) FILTER (WHERE status = 'rusak'), count(*) FILTER (WHERE status = 'gagal')
                              FROM ingest_file WHERE folder = ? GROUP BY service ORDER BY service""", [args.folder]).fetchall()
        if not rows: print(f'folder {args.folder} belum ter-ingest'); return 1
        print(f'folder {args.folder}:  layanan | file | baris | error | warning | file 0 baris | rusak | gagal')
        for r in rows: print(f'  {r[0]:26} {r[1]:>3} {_n(r[2]):>9} {_n(r[3]):>7} {_n(r[4]):>7} {r[5]:>3} {r[6]:>3} {r[7]:>3}')
        print(f'  {"total":26} {sum(r[1] for r in rows):>3} {_n(sum(r[2] for r in rows)):>9} {_n(sum(r[3] for r in rows)):>7} {_n(sum(r[4] for r in rows)):>7}')
        for t in RAW:
            n = con.execute(f'SELECT count(*) FROM {t} WHERE folder = ?', [args.folder]).fetchone()[0]
            if n: print(f'  {t:26} {_n(n):>9} baris')
        agg = con.execute('SELECT service, requests, n4xx, n5xx, err, warn, err_http, err_log, ip_unique FROM agg_service WHERE folder = ? AND requests > 0 ORDER BY 1', [args.folder]).fetchall()
        if agg: print('agregat:  layanan | request | 4xx | 5xx | error (5xx + log) | warning | IP unik')
        for r in agg: print(f'  {r[0]:26} {_n(r[1]):>9} {_n(r[2]):>7} {_n(r[3]):>5} {_n(r[4]):>6} ({_n(r[6])} + {_n(r[7])}) {_n(r[5]):>7} {_n(r[8]):>6}')
        x = con.execute("""SELECT (SELECT count(*) FROM (SELECT DISTINCT ip, upstream FROM agg_flow WHERE folder = $f)),
                                  (SELECT count(*) FROM v_upstream_error WHERE folder = $f), (SELECT coalesce(sum(n), 0) FROM agg_retry WHERE folder = $f),
                                  (SELECT count(*) FROM agg_c401 WHERE folder = $f), (SELECT count(*) FROM agg_pod WHERE folder = $f)""", {'f': args.folder}).fetchone()
        if x[0]: print(f'  nginx: alur IP {_n(x[0])}; error koneksi pod {_n(x[1])}; retry {_n(x[2])}; klien 401 {_n(x[3])}; pod backend {_n(x[4])}')
        y = con.execute("""SELECT (SELECT coalesce(sum(hits), 0) FROM agg_attack_url WHERE folder = $f), (SELECT count(*) FROM agg_attack_url WHERE folder = $f),
                                  (SELECT count(*) FROM agg_attack_ip WHERE folder = $f), (SELECT count(*) FROM agg_incident WHERE folder = $f),
                                  (SELECT coalesce(sum(fail), 0) FROM agg_login_ip WHERE folder = $f), (SELECT coalesce(sum(lock), 0) FROM agg_login_ip WHERE folder = $f),
                                  (SELECT coalesce(sum(ok), 0) FROM agg_login_ip WHERE folder = $f), (SELECT count(*) FROM agg_account WHERE folder = $f),
                                  (SELECT coalesce(sum(ok), 0) FROM agg_report WHERE folder = $f), (SELECT coalesce(sum(fail), 0) FROM agg_report WHERE folder = $f),
                                  (SELECT count(*) FROM agg_trace WHERE folder = $f)""", {'f': args.folder}).fetchone()
        print(f'  serangan: {_n(y[0])} request / {_n(y[1])} URL / {_n(y[2])} IP; insiden 5xx {y[3]}')
        print(f'  login: gagal {_n(y[4])}, reset {_n(y[5])}, sukses {_n(y[6])}; akun dianalisis {_n(y[7])}; PDF {_n(y[8])} sukses / {_n(y[9])} gagal')
        corr = con.execute('SELECT matched, total FROM agg_corr WHERE folder = ?', [args.folder]).fetchone()
        if corr: print(f'  korelasi: {_n(corr[0])} dari {_n(corr[1])} event simpel-loop; jejak {_n(y[10])} baris')
        biz = con.execute('SELECT metric, n FROM agg_biz WHERE folder = ? ORDER BY n DESC, metric', [args.folder]).fetchall()
        if biz: print('  bisnis: ' + '; '.join(f'{k} {_n(v)}' for k, v in biz))
        return 0
    f = con.execute("""SELECT count(DISTINCT folder), count(*), coalesce(sum(lines), 0), count(*) FILTER (WHERE lines = 0),
                              count(*) FILTER (WHERE status = 'rusak'), count(*) FILTER (WHERE status = 'gagal') FROM ingest_file""").fetchone()
    print(f'database: {f[0]} folder, {f[1]} file, total baris {_n(f[2])}; file 0 baris: {f[3]}; rusak: {f[4]}; gagal: {f[5]}')
    for t in RAW: print(f'  {t:22} {_n(con.execute(f"SELECT count(*) FROM {t}").fetchone()[0]):>10}')
    ip = con.execute("""SELECT count(*), count(*) FILTER (WHERE org IS NOT NULL), count(*) FILTER (WHERE is_private),
                               count(*) FILTER (WHERE geo_checked), count(*) FILTER (WHERE lat IS NOT NULL),
                               count(DISTINCT country), max(asn_db_date), max(geo_db_date) FROM ip_info""").fetchone()
    if ip[0]:
        print(f'IP: {_n(ip[0])} dikenal; pemilik jaringan {_n(ip[1])} ({ip[2]} privat); lokasi {_n(ip[4])} dari {_n(ip[3])} IP publik v4 '
              f'({round(100 * ip[4] / ip[3], 1) if ip[3] else 0}%); {ip[5]} negara')
        print(f'  basis data: ip2asn {ip[6]}, GeoLite2 {ip[7]}')
        srv = con.execute('SELECT city, region, country, lat, lon FROM ip_info WHERE ip = ?', [cfg.server_ip]).fetchone()
        if srv: print(f'  server {cfg.server_ip}: {srv[0]}, {srv[1]}, {srv[2]} ({srv[3]}, {srv[4]})')
    peta = os.path.join(cfg.data_dir, 'map')
    if os.path.isdir(peta): print('berkas peta: ' + ', '.join(f'{f} {os.path.getsize(os.path.join(peta, f)) // 1024} KB' for f in sorted(os.listdir(peta))))
    last = con.execute('SELECT run_id, started_at, finished_at, status, files_seen, files_changed FROM ingest_run ORDER BY run_id DESC LIMIT 1').fetchone()
    if last: print(f'ingest terakhir: #{last[0]} {last[1]:%Y-%m-%d %H:%M} UTC, {last[3]}, {last[4]} file dilihat, {last[5]} berubah')
    return 0


def _api(cfg, method, path, body=None):
    """Panggil API server lokal dengan token mesin. None bila server tidak berjalan."""
    import json, urllib.error, urllib.request
    host, _, port = cfg.bind.rpartition(':')
    url = (cfg.api_url.rstrip('/') or f"http://{'127.0.0.1' if host in ('', '0.0.0.0') else host}:{port}") + path
    req = urllib.request.Request(url, method=method, data=json.dumps(body or {}).encode() if method != 'GET' else None,
                                 headers={'Authorization': f'Bearer {cfg.job_token}', 'X-Requested-With': 'monishield-cli', 'Content-Type': 'application/json'})
    try:
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=30) as r: return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read() or b'{}')
    except (urllib.error.URLError, OSError): return None


def _ingest_via_api(cfg, args):
    """Bila server berjalan, DuckDB dimiliki proses itu (TRD K1): ingest dipicu lewat API, bukan dibuka sendiri."""
    import time
    first = _api(cfg, 'GET', '/api/health')
    if first is None and cfg.api_url:   # pemicu terpisah (Docker): tanpa server tidak ada DuckDB yang boleh dibuka di sini
        print(f'server {cfg.api_url} tidak terjangkau; ingest tidak dijalankan', file=sys.stderr); return 2
    if first is None: return None
    if not cfg.job_token:
        print('server sedang berjalan tetapi S4_JOB_TOKEN kosong; isi di .env agar ingest bisa dipicu lewat API', file=sys.stderr); return 2
    code, body = _api(cfg, 'POST', '/api/admin/ingest', dict(folder=args.folder, force=args.force))
    if code not in (202, 409): print(f"gagal memicu ingest: {code} {body.get('error', {}).get('message', '')}", file=sys.stderr); return 2
    if code == 409: print('ingest sudah berjalan di server; menunggu selesai', file=sys.stderr)
    while True:
        time.sleep(1)
        code, st = _api(cfg, 'GET', '/api/admin/ingest/status') or (None, None)
        if code != 200: print('server berhenti menjawab saat ingest berjalan', file=sys.stderr); return 2
        if not st['running']: break
    if st['error']: print('ingest gagal:', st['error'], file=sys.stderr); return 1
    r = st['last']
    for w in r['warnings']: print('  peringatan:', w, file=sys.stderr)
    print(f"ingest #{r['run_id']} (lewat API server): {r['status']}; {r['files_seen']} file dilihat, {r['files_changed']} file berubah "
          f"({r['files_parsed']} di-parse, {r['files_removed']} dihapus, {r['files_failed']} gagal); {len(r['folders_changed'])} folder berubah; {r['seconds']} detik")
    return 1 if r['files_failed'] else 0


def cmd_ingest(cfg, args):
    import dataclasses

    from . import ingest
    cfg = dataclasses.replace(cfg, offline=cfg.offline or args.offline)
    via = _ingest_via_api(cfg, args)
    if via is not None: return via

    def progress(phase, **k):
        if phase == 'parse' and (k['done'] % 20 == 0 or k['done'] == k['total']): print(f"  parse {k['done']}/{k['total']}", file=sys.stderr)
    r = ingest.run(cfg, folder=args.folder, force=args.force, progress=progress)
    for w in r['warnings']: print('  peringatan:', w, file=sys.stderr)
    if r.get('refdata'): print(f"  refdata: {r['refdata']['ip']['ip_baru']} IP baru, {r['refdata']['ip']['pemilik']} dapat pemilik, {r['refdata']['ip']['lokasi']} dapat lokasi", file=sys.stderr)
    print(f"ingest #{r['run_id']}: {r['status']}; {r['files_seen']} file dilihat, {r['files_changed']} file berubah "
          f"({r['files_parsed']} di-parse, {r['files_removed']} dihapus, {r['files_failed']} gagal); "
          f"{len(r['folders_changed'])} folder berubah; {r['seconds']} detik")
    return 1 if r['files_failed'] else 0


def _import_print(r):
    for o in r['objects']:
        print(f"  {'ambil ' if o['action'] == 'ambil' else 'lewati'} {o['rel']:70} {_n(o['size']):>13} B" + (f"  ({o['reason']})" if o['reason'] else ''))
    for w in r.get('warnings', []): print('  peringatan:', w, file=sys.stderr)
    print(f"{r['take']} objek {'akan diambil' if r['dry_run'] else 'diambil'} ({_n(r['bytes'])} B), {r['skipped']} dilewati; "
          f"diunduh {r['downloaded']} objek / {_n(r['downloaded_bytes'])} B; {r.get('extracted', 0)} .gz diekstrak; kredensial: {r['credentials']}")


def cmd_import(cfg, args):
    """Impor dari awalan S3 (TRD §3.8). Server berjalan -> lewat API (token mesin); selain itu di proses ini lalu ingest folder itu."""
    import time

    from . import importer
    try: importer.parse_url(cfg, args.url)                 # daftar izin diperiksa sebelum apa pun menghubungi AWS
    except importer.ImportFail as e: print(f'ditolak: {e.message}', file=sys.stderr); return 2
    up = _api(cfg, 'GET', '/api/health') is not None
    if not up and not importer.library_ok(): print(importer.NO_LIBRARY, file=sys.stderr); return 2
    if not up and cfg.api_url: print(f'server {cfg.api_url} tidak terjangkau; impor tidak dijalankan', file=sys.stderr); return 2
    if up:
        if not cfg.job_token: print('server sedang berjalan tetapi S4_JOB_TOKEN kosong', file=sys.stderr); return 2
        code, body = _api(cfg, 'POST', '/api/admin/import', dict(url=args.url, dry_run=args.dry_run))
        if code != 202: print(f"ditolak: {body.get('error', {}).get('message', code)}", file=sys.stderr); return 2
        while True:
            time.sleep(1)
            code, j = _api(cfg, 'GET', f"/api/admin/import/{body['job_id']}") or (None, None)
            if code != 200: print('server berhenti menjawab saat impor berjalan', file=sys.stderr); return 2
            if not j['running'] and j['status'] not in ('berjalan',) and (j['result'] or j['status'] == 'gagal'): break
        if j['status'] == 'gagal': print(f"impor gagal: {j['message']}", file=sys.stderr); return 1
        _import_print(j['result']); print(f"impor #{j['job_id']} (lewat API server): {j['message']}"); return 0
    try: r = importer.run(cfg, args.url, importer.Credentials(cfg), dry_run=args.dry_run)
    except importer.ImportFail as e: print(f'impor gagal: {e.message}', file=sys.stderr); return 1
    _import_print(r)
    if not args.dry_run:
        from . import ingest
        g = ingest.run(cfg, folder=r['folder'])
        print(f"ingest #{g['run_id']}: {g['status']}; {g['files_changed']} file berubah ({g['files_failed']} gagal)")
        return 1 if g['files_failed'] else 0
    return 0


def cmd_refdata(cfg, args):
    import dataclasses

    from . import db, refdata
    cfg = dataclasses.replace(cfg, offline=cfg.offline or args.offline)
    r = refdata.run(cfg, db.open(cfg.db_path), offline=cfg.offline, force_map=True, log=lambda m: print('  ', m, file=sys.stderr))
    ip = r['ip']
    print(f"IP baru: {_n(ip['ip_baru'])}; dapat pemilik: {_n(ip['pemilik'])}; dapat lokasi: {_n(ip['lokasi'])}")
    for m in ip['lewat']: print('  dilewati:', m)
    for f, v in r['peta'].items(): print(f'  {f}: {v}')
    return 0


def cmd_serve(cfg, args):
    import uvicorn

    from .api import app as appmod
    host, _, port = cfg.bind.rpartition(':')
    uvicorn.run(appmod.create_app(cfg, env_path=config.DOTENV), host=host or '127.0.0.1', port=int(port), workers=appmod.WORKERS, log_level='info',
                proxy_headers=cfg.trust_proxy, forwarded_allow_ips='*' if cfg.trust_proxy else None)
    return 0


def cmd_user(cfg, args):
    import getpass

    from . import auth
    os.makedirs(cfg.state_dir, exist_ok=True)
    a = auth.Auth(cfg.auth_url)   # tanpa rahasia JWT: baris perintah hanya mengelola akun, tidak membuat sesi
    if args.action == 'list':
        for u in a.list_users(): print(f"  {u['username']:20} {u['role']:6} {'aktif' if u['active'] else 'nonaktif':9} terakhir masuk: {u['last_login_at'] or '-'}")
        return 0
    pw = sys.stdin.readline().rstrip('\n') if args.password_stdin else getpass.getpass('Sandi (minimal 12 karakter): ')
    try: u = a.create_user(args.username, args.name or args.username, 'admin' if args.admin else 'user', pw, must_change=not args.no_change)
    except auth.AuthError as e: print('gagal:', e.message, file=sys.stderr); return 1
    print(f"user {u['username']} ({u['role']}) dibuat" + ('' if args.no_change else '; sandi wajib diganti saat masuk pertama'))
    return 0


def _local_db(cfg):
    """Buka DuckDB sendiri; bila server sedang memegangnya, jelaskan (TRD K1)."""
    import duckdb

    from . import db
    try: return db.open(cfg.db_path)
    except duckdb.IOException:
        raise SystemExit('database sedang dipakai server dashboard; lakukan lewat layar admin, atau hentikan server dulu') from None


def cmd_derive(cfg, args):
    from . import db, detect, ingest
    detect.use(cfg)
    done = ingest.derive_all(_local_db(cfg), args.folder)
    print(f'agregat diturunkan ulang untuk {len(done)} folder' + (f' ({done[0]} … {done[-1]})' if done else ''))
    return 0


def cmd_forget(cfg, args):
    from . import db, ingest
    n = ingest.forget(_local_db(cfg), args.folder)
    print(f'folder {args.folder}: data {n} file dihapus dari database (berkas log tidak disentuh)')
    return 0 if n else 1


def _date(s):
    if not rules.DATE_DIR.fullmatch(s): raise argparse.ArgumentTypeError('harus YYYY-MM-DD')
    return s


def main(argv=None):
    ap = argparse.ArgumentParser(prog='monishield', description='MoniShield v2: dashboard log dan keamanan')
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('status', help='konfigurasi efektif dan keadaan data'); p.set_defaults(fn=cmd_status)
    p.add_argument('--folder', type=_date, help='rincian satu folder'); p.add_argument('--checksum', action='store_true', help='jumlah baris dan checksum tiap tabel')
    p = sub.add_parser('ingest', help='masukkan folder log yang baru atau berubah'); p.set_defaults(fn=cmd_ingest)
    p.add_argument('--folder', type=_date, help='hanya folder ini'); p.add_argument('--force', action='store_true', help='parse ulang walau tidak berubah')
    p.add_argument('--offline', action='store_true', help='jangan mengunduh database IP / berkas peta')
    sub.add_parser('serve', help='jalankan server dashboard (satu proses, satu worker)').set_defaults(fn=cmd_serve)
    p = sub.add_parser('user', help='kelola akun dari baris perintah (mis. membuat admin pertama)'); p.set_defaults(fn=cmd_user)
    us = p.add_subparsers(dest='action', required=True)
    us.add_parser('list')
    c = us.add_parser('create'); c.add_argument('username'); c.add_argument('--admin', action='store_true'); c.add_argument('--name')
    c.add_argument('--password-stdin', action='store_true', help='baca sandi dari stdin'); c.add_argument('--no-change', action='store_true', help='tidak wajib ganti sandi saat masuk pertama')
    p = sub.add_parser('derive', help='turunkan ulang agregat dari tabel mentah (tanpa parse ulang)'); p.set_defaults(fn=cmd_derive)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument('--folder', type=_date); g.add_argument('--all', action='store_true')
    p = sub.add_parser('refdata', help='lengkapi pemilik & lokasi IP dan buat ulang berkas peta'); p.set_defaults(fn=cmd_refdata)
    p.add_argument('--offline', action='store_true', help='jangan mengunduh apa pun')
    p = sub.add_parser('import', help='impor folder log dari awalan S3 (s3://<bucket>/<awalan>/<YYYY-MM-DD>/)'); p.set_defaults(fn=cmd_import)
    p.add_argument('url'); p.add_argument('--dry-run', action='store_true', help='hanya daftar objek dan rencana; tidak mengunduh')
    p = sub.add_parser('forget', help='hapus data satu folder dari database'); p.set_defaults(fn=cmd_forget)
    p.add_argument('folder', type=_date)
    args = ap.parse_args(argv)
    return args.fn(config.load(), args)
