"""Command line: python -m monishield <command>. Subcommands grow per stage (docs/04-plan.md)."""
import argparse, os, sys

from monishield import __version__
from monishield.infrastructure import config
from monishield.domain import log_formats, rules, services, timezone

RAW = ('nginx_access', 'nginx_error', 'fe_access', 'sl_event', 'spring_line', 'coredns_error', 'log_message', 'http_access', 'app_line')


def _n(x): return f'{x:,}'.replace(',', '.')


def cmd_status(cfg, args):
    print(f'monishield {__version__}')
    if not args.folder and not args.checksum:
        for k, v in cfg.public().items():
            if isinstance(v, dict): v = f'{len(v)} entries'
            print(f'  {k:22} {v}')
        from monishield.infrastructure import auth
        print(f'  {"account database":22} {auth.redact_url(cfg.auth_url)}')
        from monishield.domain import s3_import
        from monishield.infrastructure import importer
        cs = importer.Credentials(cfg).status()
        print(f'  {"S3 import":22} ' + (f'on: {", ".join(s3_import.allowed_examples(cfg))}' if cfg.import_buckets else 'not enabled'))
        print(f'  {"import credentials":22} ' + ('available (environment)' if cs['available'] else 'none'))
        folders = sorted(d for d in os.listdir(cfg.log_dir) if rules.DATE_DIR.fullmatch(d)) if os.path.isdir(cfg.log_dir) else []
        print(f'log folders on disk: {len(folders)}' + (f' ({folders[0]} … {folders[-1]})' if folders else ' (none)'))
    if not os.path.exists(cfg.db_path):
        print(f'no database yet ({cfg.db_path}); run ingest'); return 0
    from monishield.infrastructure import db, ingest
    con = db.open(cfg.db_path)
    if args.checksum:
        for t, (n, h) in ingest.checksums(con).items(): print(f'  {t:22} {n:>10} {h:020d}')
        return 0
    if args.folder:
        rows = con.execute("""SELECT service, count(*), sum(lines), sum(err), sum(warn), count(*) FILTER (WHERE lines = 0),
                                     count(*) FILTER (WHERE status = 'corrupt'), count(*) FILTER (WHERE status = 'failed')
                              FROM ingest_file WHERE folder = ? GROUP BY service ORDER BY service""", [args.folder]).fetchall()
        if not rows: print(f'folder {args.folder} not ingested yet'); return 1
        print(f'folder {args.folder}:  service | files | lines | error | warning | 0-line files | corrupt | failed')
        for r in rows: print(f'  {r[0]:26} {r[1]:>3} {_n(r[2]):>9} {_n(r[3]):>7} {_n(r[4]):>7} {r[5]:>3} {r[6]:>3} {r[7]:>3}')
        print(f'  {"total":26} {sum(r[1] for r in rows):>3} {_n(sum(r[2] for r in rows)):>9} {_n(sum(r[3] for r in rows)):>7} {_n(sum(r[4] for r in rows)):>7}')
        for t in RAW:
            n = con.execute(f'SELECT count(*) FROM {t} WHERE folder = ?', [args.folder]).fetchone()[0]
            if n: print(f'  {t:26} {_n(n):>9} lines')
        agg = con.execute('SELECT service, requests, n4xx, n5xx, err, warn, err_http, err_log, ip_unique FROM agg_service WHERE folder = ? AND requests > 0 ORDER BY 1', [args.folder]).fetchall()
        if agg: print('aggregates:  service | request | 4xx | 5xx | error (5xx + log) | warning | unique IPs')
        for r in agg: print(f'  {r[0]:26} {_n(r[1]):>9} {_n(r[2]):>7} {_n(r[3]):>5} {_n(r[4]):>6} ({_n(r[6])} + {_n(r[7])}) {_n(r[5]):>7} {_n(r[8]):>6}')
        x = con.execute("""SELECT (SELECT count(*) FROM (SELECT DISTINCT ip, upstream FROM agg_flow WHERE folder = $f)),
                                  (SELECT count(*) FROM v_upstream_error WHERE folder = $f), (SELECT coalesce(sum(n), 0) FROM agg_retry WHERE folder = $f),
                                  (SELECT count(*) FROM agg_c401 WHERE folder = $f), (SELECT count(*) FROM agg_pod WHERE folder = $f)""", {'f': args.folder}).fetchone()
        if x[0]: print(f'  nginx: IP flows {_n(x[0])}; pod connection errors {_n(x[1])}; retry {_n(x[2])}; 401 clients {_n(x[3])}; backend pods {_n(x[4])}')
        y = con.execute("""SELECT (SELECT coalesce(sum(hits), 0) FROM agg_attack_url WHERE folder = $f), (SELECT count(*) FROM agg_attack_url WHERE folder = $f),
                                  (SELECT count(*) FROM agg_attack_ip WHERE folder = $f), (SELECT count(*) FROM agg_incident WHERE folder = $f),
                                  (SELECT coalesce(sum(fail), 0) FROM agg_login_ip WHERE folder = $f), (SELECT coalesce(sum(lock), 0) FROM agg_login_ip WHERE folder = $f),
                                  (SELECT coalesce(sum(ok), 0) FROM agg_login_ip WHERE folder = $f), (SELECT count(*) FROM agg_account WHERE folder = $f),
                                  (SELECT coalesce(sum(ok), 0) FROM agg_report WHERE folder = $f), (SELECT coalesce(sum(fail), 0) FROM agg_report WHERE folder = $f),
                                  (SELECT count(*) FROM agg_trace WHERE folder = $f)""", {'f': args.folder}).fetchone()
        print(f'  attacks: {_n(y[0])} requests / {_n(y[1])} URLs / {_n(y[2])} IPs; 5xx incidents {y[3]}')
        print(f'  login: failed {_n(y[4])}, reset {_n(y[5])}, success {_n(y[6])}; accounts analysed {_n(y[7])}; PDF {_n(y[8])} success / {_n(y[9])} failed')
        corr = con.execute('SELECT matched, total FROM agg_corr WHERE folder = ?', [args.folder]).fetchone()
        if corr: print(f'  correlation: {_n(corr[0])} of {_n(corr[1])} events-service events; traces {_n(y[10])} rows')
        biz = con.execute('SELECT metric, n FROM agg_biz WHERE folder = ? ORDER BY n DESC, metric', [args.folder]).fetchall()
        if biz: print('  business: ' + '; '.join(f'{k} {_n(v)}' for k, v in biz))
        return 0
    f = con.execute("""SELECT count(DISTINCT folder), count(*), coalesce(sum(lines), 0), count(*) FILTER (WHERE lines = 0),
                              count(*) FILTER (WHERE status = 'corrupt'), count(*) FILTER (WHERE status = 'failed') FROM ingest_file""").fetchone()
    print(f'database: {f[0]} folders, {f[1]} files, total lines {_n(f[2])}; 0-line files: {f[3]}; corrupt: {f[4]}; failed: {f[5]}')
    for t in RAW: print(f'  {t:22} {_n(con.execute(f"SELECT count(*) FROM {t}").fetchone()[0]):>10}')
    ip = con.execute("""SELECT count(*), count(*) FILTER (WHERE org IS NOT NULL), count(*) FILTER (WHERE is_private),
                               count(*) FILTER (WHERE geo_checked), count(*) FILTER (WHERE lat IS NOT NULL),
                               count(DISTINCT country), max(asn_db_date), max(geo_db_date) FROM ip_info""").fetchone()
    if ip[0]:
        print(f'IP: {_n(ip[0])} known; network owner {_n(ip[1])} ({ip[2]} private); location {_n(ip[4])} of {_n(ip[3])} public v4 IPs '
              f'({round(100 * ip[4] / ip[3], 1) if ip[3] else 0}%); {ip[5]} countries')
        print(f'  databases: ip2asn {ip[6]}, GeoLite2 {ip[7]}')
        srv = con.execute('SELECT city, region, country, lat, lon FROM ip_info WHERE ip = ?', [cfg.server_ip]).fetchone()
        if srv: print(f'  server {cfg.server_ip}: {srv[0]}, {srv[1]}, {srv[2]} ({srv[3]}, {srv[4]})')
    mapping = os.path.join(cfg.data_dir, 'map')
    if os.path.isdir(mapping): print('map files: ' + ', '.join(f'{f} {os.path.getsize(os.path.join(mapping, f)) // 1024} KB' for f in sorted(os.listdir(mapping))))
    last = con.execute('SELECT run_id, started_at, finished_at, status, files_seen, files_changed FROM ingest_run ORDER BY run_id DESC LIMIT 1').fetchone()
    if last: print(f'last ingest: #{last[0]} {last[1]:%Y-%m-%d %H:%M} UTC, {last[3]}, {last[4]} files seen, {last[5]} changed')
    return 0


def _api(cfg, method, path, body=None):
    """Call the local server API with the machine token. None when the server is not running."""
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
    """When the server is running, DuckDB is owned by that process (TRD K1): ingest is triggered via the API, not opened here."""
    import time
    first = _api(cfg, 'GET', '/api/health')
    if first is None and cfg.api_url:   # separate trigger (Docker): without the server no DuckDB may be opened here
        print(f'server {cfg.api_url} unreachable; ingest not run', file=sys.stderr); return 2
    if first is None: return None
    if not cfg.job_token:
        print('server is running but S4_JOB_TOKEN is empty; set it in .env so ingest can be triggered via the API', file=sys.stderr); return 2
    q = '' if getattr(args, 'source', 's3') == 's3' else f'?source={args.source}'   # the Kafka source has its own database
    code, body = _api(cfg, 'POST', '/api/admin/ingest' + q, dict(folder=args.folder, force=args.force))
    if code not in (202, 409): print(f"failed to trigger ingest: {code} {body.get('error', {}).get('message', '')}", file=sys.stderr); return 2
    if code == 409: print('ingest already running on the server; waiting for it to finish', file=sys.stderr)
    while True:
        time.sleep(1)
        code, st = _api(cfg, 'GET', '/api/admin/ingest' + q) or (None, None)
        if code != 200: print('server stopped responding while ingest was running', file=sys.stderr); return 2
        if not st['running']: break
    if st['error']: print('ingest failed:', st['error'], file=sys.stderr); return 1
    r = st['last']
    for w in r['warnings']: print('  warning:', w, file=sys.stderr)
    print(f"ingest #{r['run_id']} (via server API): {r['status']}; {r['files_seen']} files seen, {r['files_changed']} files changed "
          f"({r['files_parsed']} parsed, {r['files_removed']} removed, {r['files_failed']} failed); {len(r['folders_changed'])} folders changed; {r['seconds']} seconds")
    _slowest(r.get('timings'))
    return 1 if r['files_failed'] else 0


def _slowest(timings, n=4):
    """Where the ingest spent its time (derive steps), when it was not instant: helps to see what to optimise."""
    top = sorted((timings or {}).items(), key=lambda kv: -kv[1])[:n]
    if top and top[0][1] >= 1: print('  slowest steps: ' + ', '.join(f'{k} {v:.1f}s' for k, v in top))


def cmd_ingest(cfg, args):
    import dataclasses

    from monishield.infrastructure import ingest
    cfg = dataclasses.replace(cfg, offline=cfg.offline or args.offline)
    via = _ingest_via_api(cfg, args)
    if via is not None: return via
    if getattr(args, 'source', 's3') == 'kafka':
        from monishield.domain import config_model
        cfg = config_model.kafka_config(cfg)   # own database, own inbox

    def progress(phase, **k):
        if phase == 'parse' and (k['done'] % 20 == 0 or k['done'] == k['total']): print(f"  parse {k['done']}/{k['total']}", file=sys.stderr)
    r = ingest.run(cfg, folder=args.folder, force=args.force, progress=progress)
    for w in r['warnings']: print('  warning:', w, file=sys.stderr)
    if r.get('refdata'): print(f"  refdata: {r['refdata']['ip']['new_ips']} new IPs, {r['refdata']['ip']['owners']} got an owner, {r['refdata']['ip']['locations']} got a location", file=sys.stderr)
    print(f"ingest #{r['run_id']}: {r['status']}; {r['files_seen']} files seen, {r['files_changed']} files changed "
          f"({r['files_parsed']} parsed, {r['files_removed']} removed, {r['files_failed']} failed); "
          f"{len(r['folders_changed'])} folders changed; {r['seconds']} seconds")
    _slowest(r.get('timings'))
    return 1 if r['files_failed'] else 0


def _import_print(r):
    for o in r['objects']:
        print(f"  {'fetch ' if o['action'] == 'fetch' else 'skip  '} {o['rel']:70} {_n(o['size']):>13} B" + (f"  ({o['reason']})" if o['reason'] else ''))
    for w in r.get('warnings', []): print('  warning:', w, file=sys.stderr)
    print(f"{r['take']} objects {'would be fetched' if r['dry_run'] else 'fetched'} ({_n(r['bytes'])} B), {r['skipped']} skipped; "
          f"downloaded {r['downloaded']} objects / {_n(r['downloaded_bytes'])} B; {r.get('extracted', 0)} .gz extracted; credentials: {r['credentials']}")


def cmd_import(cfg, args):
    """Import from an S3 prefix (TRD §3.8). Server running -> via the API (machine token); otherwise in this process, then ingest that folder."""
    import time

    from monishield.infrastructure import importer
    try: importer.parse_url(cfg, args.url)                 # allow list checked before anything contacts AWS
    except importer.ImportFail as e: print(f'rejected: {e.message}', file=sys.stderr); return 2
    up = _api(cfg, 'GET', '/api/health') is not None
    if not up and not importer.library_ok(): print(importer.NO_LIBRARY, file=sys.stderr); return 2
    if not up and cfg.api_url: print(f'server {cfg.api_url} unreachable; import not run', file=sys.stderr); return 2
    if up:
        if not cfg.job_token: print('server is running but S4_JOB_TOKEN is empty', file=sys.stderr); return 2
        code, body = _api(cfg, 'POST', '/api/admin/imports', dict(url=args.url, dry_run=args.dry_run))
        if code != 202: print(f"rejected: {body.get('error', {}).get('message', code)}", file=sys.stderr); return 2
        while True:
            time.sleep(1)
            code, j = _api(cfg, 'GET', f"/api/admin/imports/{body['job_id']}") or (None, None)
            if code != 200: print('server stopped responding while the import was running', file=sys.stderr); return 2
            if not j['running'] and j['status'] not in ('running',) and (j['result'] or j['status'] == 'failed'): break
        if j['status'] == 'failed': print(f"import failed: {j['message']}", file=sys.stderr); return 1
        _import_print(j['result']); print(f"import #{j['job_id']} (via server API): {j['message']}"); return 0
    try: r = importer.run(cfg, args.url, importer.Credentials(cfg), dry_run=args.dry_run)
    except importer.ImportFail as e: print(f'import failed: {e.message}', file=sys.stderr); return 1
    _import_print(r)
    if not args.dry_run:
        from monishield.infrastructure import ingest
        g = ingest.run(cfg, folder=r['folder'])
        print(f"ingest #{g['run_id']}: {g['status']}; {g['files_changed']} files changed ({g['files_failed']} failed)")
        return 1 if g['files_failed'] else 0
    return 0


def cmd_sync(cfg, args):
    """Check the automatic sync parent folder now (same as the "Sync data" button), through the running server with the
    machine token, and wait for the result. For cron: no API path to remember."""
    import time
    if _api(cfg, 'GET', '/api/health') is None: print('server unreachable; sync runs inside the server', file=sys.stderr); return 2
    if not cfg.job_token: print('S4_JOB_TOKEN is empty; set it in .env so sync can be triggered', file=sys.stderr); return 2
    code, body = _api(cfg, 'POST', '/api/admin/imports/sync', {})
    if code != 202: print(f"sync not started: {body.get('error', {}).get('message', code)}", file=sys.stderr); return 2
    while True:   # the ingest status (allowed for the machine token) carries the sync state
        time.sleep(2)
        code, v = _api(cfg, 'GET', '/api/admin/ingest') or (None, None)
        if code != 200: print('server stopped responding while sync was running', file=sys.stderr); return 2
        if not v['s3']['running']: break
    s = v['s3']
    for e in s.get('last_errors', []): print(f"  error: {e.get('where') or ''} {e['message']}", file=sys.stderr)
    print(f"sync: {len(s['last_imported'])} folders imported or rechecked {s['last_imported']}; {len(s['last_errors'])} errors")
    return 1 if s['last_errors'] else 0


def cmd_refdata(cfg, args):
    import dataclasses

    from monishield.infrastructure import db, refdata
    cfg = dataclasses.replace(cfg, offline=cfg.offline or args.offline)
    r = refdata.run(cfg, db.open(cfg.db_path), offline=cfg.offline, force_map=True, log=lambda m: print('  ', m, file=sys.stderr))
    ip = r['ip']
    print(f"new IPs: {_n(ip['new_ips'])}; got an owner: {_n(ip['owners'])}; got a location: {_n(ip['locations'])}")
    for m in ip['skipped']: print('  skipped:', m)
    for f, v in r['map'].items(): print(f'  {f}: {v}')
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

    from monishield.infrastructure import auth
    os.makedirs(cfg.state_dir, exist_ok=True)
    a = auth.Auth(cfg.auth_url)   # no JWT secret: the command line only manages accounts, it does not create sessions
    if args.action == 'list':
        for u in a.list_users(): print(f"  {u['username']:20} {u['role']:6} {'active' if u['active'] else 'inactive':9} last login: {u['last_login_at'] or '-'}")
        return 0
    pw = sys.stdin.readline().rstrip('\n') if args.password_stdin else getpass.getpass('Password (at least 12 characters): ')
    try: u = a.create_user(args.username, args.name or args.username, 'admin' if args.admin else 'user', pw, must_change=not args.no_change)
    except auth.AuthError as e: print('failed:', e.message, file=sys.stderr); return 1
    print(f"user {u['username']} ({u['role']}) created" + ('' if args.no_change else '; password must be changed at first login'))
    return 0


def _local_db(cfg):
    """Open DuckDB directly; if the server holds it, explain (TRD K1)."""
    import duckdb

    from monishield.infrastructure import db
    try: return db.open(cfg.db_path)
    except duckdb.IOException:
        raise SystemExit('database is in use by the dashboard server; do this from the admin page, or stop the server first') from None


def cmd_derive(cfg, args):
    from monishield.infrastructure import ingest
    from monishield.domain import detect
    detect.use(cfg)
    done = ingest.derive_all(_local_db(cfg), args.folder)
    print(f'aggregates re-derived for {len(done)} folders' + (f' ({done[0]} … {done[-1]})' if done else ''))
    return 0


def cmd_forget(cfg, args):
    from monishield.infrastructure import ingest
    n = ingest.forget(_local_db(cfg), args.folder)
    print(f'folder {args.folder}: data of {n} files removed from the database (log files untouched)')
    return 0 if n else 1


def cmd_backup(cfg, args):
    """Make today's backup now: through the running server (machine token), or directly when the server is stopped."""
    if _api(cfg, 'GET', '/api/health') is not None:
        if not cfg.job_token: print('S4_JOB_TOKEN is empty; set it in .env so a backup can be started through the server', file=sys.stderr); return 2
        code, body = _api(cfg, 'POST', '/api/admin/backup/run', {})
        if code != 200: print(f"backup failed: {body.get('error', {}).get('message', code)}", file=sys.stderr); return 1
        r = body['last']
    else:
        import types
        from sqlalchemy import create_engine
        from monishield.application.backup_service import BackupService
        from monishield.domain import config_model
        from monishield.infrastructure import backup, db
        cons = {'s3': db.open(cfg.db_path), 'kafka': db.open(config_model.kafka_config(cfg).db_path)}
        ctx = types.SimpleNamespace(cfg=cfg, backups=backup.Backups(cfg), auth=types.SimpleNamespace(engine=create_engine(cfg.auth_url), audit=lambda *a, **k: None),
                                    sources={k: types.SimpleNamespace(con=c) for k, c in cons.items()})
        try: r = BackupService(ctx).run('(command line)')
        finally:
            for c in cons.values(): c.close()
    print(f"backup {r['day']}: {_n(r.get('bytes', 0))} bytes in {cfg.backup_path}" + (f"; copied to {r['uploaded']}" if r.get('uploaded') else '')
          + (f"; removed {', '.join(r['pruned'])}" if r.get('pruned') else ''))
    return 0


def cmd_restore(cfg, args):
    """Put a backup back. The server must be stopped (DuckDB has one owner); the account database must be empty."""
    if _api(cfg, 'GET', '/api/health') is not None: print('the server is running: stop it first (docker compose stop app), then restore', file=sys.stderr); return 2
    from sqlalchemy import create_engine
    from monishield.infrastructure import backup
    from monishield.infrastructure.auth import Base
    engine = create_engine(cfg.auth_url); Base.metadata.create_all(engine)
    r = backup.restore(cfg, args.folder, engine, Base.metadata, accounts=not args.no_accounts, databases=not args.no_databases)
    for k, v in r.items(): print(f'  {k}: {v}')
    print('restored; start the server again')
    return 0


def _date(s):
    if not rules.DATE_DIR.fullmatch(s): raise argparse.ArgumentTypeError('must be YYYY-MM-DD')
    return s


def main(argv=None):
    ap = argparse.ArgumentParser(prog='monishield', description='MoniShield v2: log and security dashboard')
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('status', help='effective configuration and data state'); p.set_defaults(fn=cmd_status)
    p.add_argument('--folder', type=_date, help='details of one folder'); p.add_argument('--checksum', action='store_true', help='row count and checksum of each table')
    p = sub.add_parser('ingest', help='ingest new or changed log folders'); p.set_defaults(fn=cmd_ingest)
    p.add_argument('--folder', type=_date, help='only this folder'); p.add_argument('--force', action='store_true', help='re-parse even if unchanged')
    p.add_argument('--source', choices=('s3', 'kafka'), default='s3', help='data source to ingest (default s3; kafka has its own database)')
    p.add_argument('--offline', action='store_true', help='do not download IP databases / map files')
    sub.add_parser('serve', help='run the dashboard server (one process, one worker)').set_defaults(fn=cmd_serve)
    p = sub.add_parser('user', help='manage accounts from the command line (e.g. create the first admin)'); p.set_defaults(fn=cmd_user)
    us = p.add_subparsers(dest='action', required=True)
    us.add_parser('list')
    c = us.add_parser('create'); c.add_argument('username'); c.add_argument('--admin', action='store_true'); c.add_argument('--name')
    c.add_argument('--password-stdin', action='store_true', help='read the password from stdin'); c.add_argument('--no-change', action='store_true', help='no password change required at first login')
    p = sub.add_parser('derive', help='re-derive aggregates from the raw tables (no re-parse)'); p.set_defaults(fn=cmd_derive)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument('--folder', type=_date); g.add_argument('--all', action='store_true')
    p = sub.add_parser('refdata', help='fill in IP owner & location and rebuild the map files'); p.set_defaults(fn=cmd_refdata)
    p.add_argument('--offline', action='store_true', help='do not download anything')
    p = sub.add_parser('import', help='import a log folder from an S3 prefix (s3://<bucket>/<prefix>/<YYYY-MM-DD>/)'); p.set_defaults(fn=cmd_import)
    p.add_argument('url'); p.add_argument('--dry-run', action='store_true', help='only list objects and the plan; no download')
    sub.add_parser('sync', help='check the automatic sync parent folder now (needs the running server and S4_JOB_TOKEN)').set_defaults(fn=cmd_sync)
    sub.add_parser('backup', help="make today's backup now (both databases + accounts)").set_defaults(fn=cmd_backup)
    p = sub.add_parser('restore', help='put a backup folder back (server stopped; the account database must be empty)'); p.set_defaults(fn=cmd_restore)
    p.add_argument('folder', help='backup folder, e.g. data/backup/2026-10-27'); p.add_argument('--no-accounts', action='store_true'); p.add_argument('--no-databases', action='store_true')
    p = sub.add_parser('forget', help='remove one folder\'s data from the database'); p.set_defaults(fn=cmd_forget)
    p.add_argument('folder', type=_date)
    args = ap.parse_args(argv)
    cfg = config.load()
    services.use(services.from_config(cfg))   # the site's service names for parsers and queries
    timezone.use(timezone.from_config(cfg))   # the site's local time
    log_formats.use(config.log_format_rules(cfg))   # how each service logs
    return args.fn(cfg, args)
