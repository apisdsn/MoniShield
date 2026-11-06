"""Server for the browser smoke test (tools/smoke_browser.cjs, CI job "Browser smoke test").

    python tools/smoke_server.py <empty work dir> [port]

Builds the small synthetic log folders of tests/logs_mini.py as the S3 source, copies the second day into the Kafka inbox
as the Kafka source and into the collector inbox as the collector source, ingests all three offline, adds sample servers with metrics (tools/seed_metrics.py), and serves the built web UI (web/dist) on 127.0.0.1:<port> (default 8777).
The admin password is the fixed test password below; the browser test changes it on first sign-in.
"""
import contextlib, dataclasses, datetime, os, shutil, sys

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
UVICORN = '\n'.join(f'INFO:     172.18.0.4:5123{i} - "GET /api/v1/me HTTP/1.1" 200 OK' for i in range(6)) + '\nINFO:     Application startup complete.\n'


def today_logs(cfg, logs, inbox):
    """Today's folder for the Log Formats page (its services are the last 7 days): a Caddy access log and a service whose lines the built-in
    reading does not fit, on a collector host, plus an S3 service; the rules file reads the Caddy one with caddy-json."""
    today = retention.today_local(datetime.datetime.now(datetime.timezone.utc)).isoformat()
    host = os.path.join(inbox, 'collector', today, 'docker-host-01')
    for svc, text in (('monishield-https-1', CADDY), ('monishield-app-1', UVICORN)):
        logs_mini.write(os.path.join(host, svc, f'log_{svc}_p1_{today}-00-00.log'), text)
    logs_mini.write(logs_mini.log_path(logs, today, 'production', 'auth-service', 'pod-a'), logs_mini.lines('auth-service'))
    # today is the newest folder, so the pages open on it: it needs the service the smoke test opens (services/event-api) in both sources
    logs_mini.write(logs_mini.log_path(logs, today, 'tenant', 'event-api', 'pod-s'), logs_mini.lines('event-api'))
    logs_mini.write(logs_mini.log_path(os.path.join(inbox, 'collector'), today, 'tenant', 'event-api', 'pod-s'), logs_mini.lines('event-api'))
    os.makedirs(cfg.state_dir, exist_ok=True)
    rules = (log_formats.Rule('docker-host-01/monishield-https-1', 'caddy-json', 'http'), *log_formats.default_rules(services.from_config(cfg)))
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
                              kafka_brokers='', backup_enabled=False, log_formats_file=os.path.join(work, 'state', 'log-formats.toml'), bind=f'127.0.0.1:{port}')
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
