"""Server for the browser smoke test (tools/smoke_browser.cjs, CI job "Browser smoke test").

    python tools/smoke_server.py <empty work dir> [port]

Builds the small synthetic log folders of tests/logs_mini.py as the S3 source, copies the second day into the Kafka inbox
as the Kafka source and into the collector inbox as the collector source, ingests all three offline, adds sample servers with metrics (tools/seed_metrics.py), and serves the built web UI (web/dist) on 127.0.0.1:<port> (default 8777).
The admin password is the fixed test password below; the browser test changes it on first sign-in.
"""
import contextlib, dataclasses, datetime, json, os, random, shutil, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [ROOT, os.path.join(ROOT, 'tests'), os.path.join(ROOT, 'tools')]

import uvicorn  # noqa: E402

import logs_mini  # noqa: E402
import seed_metrics  # noqa: E402
from monishield.domain import config_model, log_formats, retention, services  # noqa: E402
from monishield.infrastructure import config, db, ingest  # noqa: E402
from monishield.interfaces.api import app as appmod  # noqa: E402

PASSWORD = 'smoke-test-first-password'


CADDY = open(os.path.join(ROOT, 'tests', 'fixtures', 'formats', 'caddy-json.log'), encoding='utf-8').read()
POSTGRES = '\n'.join(f'2026-01-02 10:0{i}:00.123 UTC [1] LOG:  checkpoint complete: wrote {40 + i} buffers' for i in range(6)) + '\n2026-01-02 10:09:00.000 UTC [1] LOG:  database system is ready\n'

# A Collector-like day (stage 62): Caddy's JSON access log and a JSON application log, with or without a request ID in both, so that every
# analysis page shows its new state (Availability, Root Causes, Request Tracing, Containers, Business).
ENDPOINTS = [('GET', '/api/v1/servers', 212), ('POST', '/api/v1/collector/logs', 186), ('GET', '/api/v1/overview', 61), ('POST', '/api/v1/auth/login', 23),
             ('GET', '/login', 23), ('POST', '/api/v1/collectors', 3), ('GET', '/wp-login.php', 3), ('POST', '/api/v1/notify/test', 2)]


def day_logs(day, ids):
    """-> (Caddy access log text, application log text) for the date `day` (a date), about 650 requests. `ids`: both logs carry a request ID."""
    rnd = random.Random(day.toordinal())
    base = datetime.datetime(day.year, day.month, day.day, tzinfo=datetime.timezone.utc)
    web, app, n = [], [], 0
    for method, path, count in ENDPOINTS:
        for _ in range(count):
            n += 1
            t = base + datetime.timedelta(seconds=rnd.randrange(0, 86400))
            status, dur = 200, rnd.uniform(0.004, 0.09)
            if path == '/api/v1/auth/login' and rnd.random() < 0.3: status = 401
            if path == '/login' and rnd.random() < 0.25: status = 404
            if path == '/wp-login.php': status = 404
            if path == '/api/v1/collector/logs' and n % 47 == 0: status, dur = 502, rnd.uniform(1.8, 2.4)
            if path == '/api/v1/overview' and n % 31 == 0: status, dur = 504, rnd.uniform(1.2, 1.6)
            if rnd.random() < 0.02: dur = rnd.uniform(0.3, 0.5)
            rid = f'{rnd.getrandbits(64):016x}' if ids else None
            entry = {'level': 'info', 'ts': t.timestamp(), 'logger': 'http.log.access.log0', 'msg': 'handled request', 'duration': round(dur, 4), 'size': 512, 'status': status,
                     'request': {'remote_ip': '172.18.0.1', 'client_ip': f'203.0.113.{rnd.randrange(2, 12)}', 'method': method, 'host': 'example.com', 'uri': path,
                                 'headers': {'User-Agent': ['smoke/1.0']}}}
            if rid: entry['request_id'] = rid
            web.append((t, json.dumps(entry)))
            if status >= 500 or rnd.random() < 0.04:
                msg = 'Timeout after %d ms reading %s' % (rnd.choice((30, 45, 60)), path) if status >= 500 else 'order saved'
                a = {'time': t.strftime('%Y-%m-%dT%H:%M:%SZ'), 'level': 'error' if status >= 500 else 'info', 'msg': msg}
                if rid: a['request_id'] = rid
                app.append((t, json.dumps(a)))
    for hh, msg in ((8, 'S3 sync failed: bucket not reachable (code 7)'), (13, 'S3 sync failed: bucket not reachable (code 9)')):
        t = base + datetime.timedelta(hours=hh, minutes=5)
        app.append((t, json.dumps({'time': t.strftime('%Y-%m-%dT%H:%M:%SZ'), 'level': 'error', 'msg': msg})))
    web.append((base, json.dumps({'level': 'info', 'ts': base.timestamp(), 'logger': 'tls', 'msg': 'certificate obtained successfully'})))
    text = lambda rows: '\n'.join(line for _t, line in sorted(rows)) + '\n'
    return text(web), text(app)


def today_logs(cfg, logs, inbox):
    """Today's folder for the Log Formats page (its services are the last 7 days) and the analysis pages: on a collector host a Caddy access log
    and an application log (JSON), a text log the built-in reading does not fit, plus an S3 service. Yesterday's collector folder carries a request
    ID in both logs, today's does not. The rules file reads the Caddy and the JSON log with their formats."""
    today = retention.today_local(datetime.datetime.now(datetime.timezone.utc))
    host = lambda day: os.path.join(inbox, 'collector', day.isoformat(), 'docker-host-01')
    for day, ids in ((today, False), (today - datetime.timedelta(days=1), True)):
        web, app = day_logs(day, ids)
        for svc, text in (('monishield-https-1', web), ('monishield-app-1', app), ('monishield-postgres-1', POSTGRES)):
            logs_mini.write(os.path.join(host(day), svc, f'log_{svc}_p1_{day.isoformat()}-00-00.log'), text)
    today = today.isoformat()
    logs_mini.write(logs_mini.log_path(logs, today, 'production', 'auth-service', 'pod-a'), logs_mini.lines('auth-service'))
    # today is the newest folder, so the pages open on it: it needs the service the smoke test opens (services/event-api) in the S3 source (the collector
    # source has none: its service page then opens the Overview, and its Business page shows the state of a source without business metrics)
    logs_mini.write(logs_mini.log_path(logs, today, 'tenant', 'event-api', 'pod-s'), logs_mini.lines('event-api'))
    os.makedirs(cfg.state_dir, exist_ok=True)
    rules = (log_formats.Rule('docker-host-01/monishield-https-1', 'caddy-json', 'http'), log_formats.Rule('docker-host-01/monishield-app-1', 'json', 'app'),
             *log_formats.default_rules(services.from_config(cfg)))
    with open(cfg.log_formats_file or os.path.join(cfg.state_dir, 'log-formats.toml'), 'w', encoding='utf-8') as fh: fh.write(log_formats.dumps(rules))
    log_formats.use(rules)


def main(work, port=8777):
    os.makedirs(work, exist_ok=True)
    logs = logs_mini.build(os.path.join(work, 'logs'))
    inbox = os.path.join(work, 'inbox')
    for source in ('kafka', 'collector'): shutil.copytree(os.path.join(logs, '2026-01-02'), os.path.join(inbox, source, '2026-01-02'))
    cfg = dataclasses.replace(config.Config(), log_dir=logs, data_dir=os.path.join(work, 'data'), state_dir=os.path.join(work, 'state'),
                              inbox_dir=inbox, cache_dir=os.path.join(work, 'cache'), offline=True, ingest_on_start=False,
                              cookie_secure=False, admin_user='admin', admin_password=PASSWORD, job_token='smoke-test-machine-token-0001',
                              jwt_secret='smoke-test-jwt-secret-at-least-32-characters', auth_database_url='',
                              kafka_brokers='', backup_enabled=False, analysis_file=os.path.join(work, 'state', 'analysis.toml'), log_formats_file=os.path.join(work, 'state', 'log-formats.toml'), bind=f'127.0.0.1:{port}')
    os.makedirs(cfg.data_dir, exist_ok=True)
    today_logs(cfg, logs, inbox)
    for c in (cfg, config_model.kafka_config(cfg), config_model.collector_config(cfg)):
        con = db.open(c.db_path); ingest.run(c, con, workers=0)
        # offline there is no IP location database: give the test IPs sample places so the maps (home page too) have dots
        con.execute("""UPDATE ip_info SET lat = [-6.2, -7.25, 1.29, 3.59][k], lon = [106.82, 112.75, 103.85, 98.67][k],
                              city = ['Jakarta', 'Surabaya', 'Singapore', 'Medan'][k], country = ['ID', 'ID', 'SG', 'ID'][k]
                       FROM (SELECT ip AS kip, (hash(ip) % 4 + 1)::INT AS k FROM ip_info) WHERE ip = kip AND NOT coalesce(is_private, false)""")
        con.close()
    app = appmod.create_app(cfg)
    start_up = app.router.lifespan_context

    @contextlib.asynccontextmanager
    async def lifespan(a):
        async with start_up(a):
            seed_metrics.seed(a)       # sample servers for the Servers page, before the first request is served
            yield
    app.router.lifespan_context = lifespan
    uvicorn.run(app, host='127.0.0.1', port=int(port), log_level='warning')


if __name__ == '__main__':
    main(sys.argv[1], *(sys.argv[2:3]))
