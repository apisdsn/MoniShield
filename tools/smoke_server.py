"""Server for the browser smoke test (tools/smoke_browser.cjs, CI job "Browser smoke test").

    python tools/smoke_server.py <empty work dir> [port]

Builds the small synthetic log folders of tests/logs_mini.py as the S3 source, copies the second day into the Kafka inbox
as the Kafka source, ingests both offline, and serves the built web UI (web/dist) on 127.0.0.1:<port> (default 8777).
The admin password is the fixed test password below; the browser test changes it on first sign-in.
"""
import dataclasses, os, shutil, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [ROOT, os.path.join(ROOT, 'tests')]

import uvicorn  # noqa: E402

import logs_mini  # noqa: E402
from monishield.domain import config_model  # noqa: E402
from monishield.infrastructure import config, db, ingest  # noqa: E402
from monishield.interfaces.api import app as appmod  # noqa: E402

PASSWORD = 'smoke-test-first-password'


def main(work, port=8777):
    os.makedirs(work, exist_ok=True)
    logs = logs_mini.build(os.path.join(work, 'logs'))
    inbox = os.path.join(work, 'inbox')
    shutil.copytree(os.path.join(logs, '2026-01-02'), os.path.join(inbox, 'kafka', '2026-01-02'))
    cfg = dataclasses.replace(config.Config(), log_dir=logs, data_dir=os.path.join(work, 'data'), state_dir=os.path.join(work, 'state'),
                              inbox_dir=inbox, cache_dir=os.path.join(work, 'cache'), offline=True, ingest_on_start=False,
                              cookie_secure=False, admin_user='admin', admin_password=PASSWORD, job_token='smoke-test-machine-token-0001',
                              jwt_secret='smoke-test-jwt-secret-at-least-32-characters', auth_database_url='',
                              kafka_brokers='', backup_enabled=False, bind=f'127.0.0.1:{port}')
    os.makedirs(cfg.data_dir, exist_ok=True)
    for c in (cfg, config_model.kafka_config(cfg)):
        con = db.open(c.db_path); ingest.run(c, con, workers=0)
        # offline there is no IP location database: give the test IPs sample places so the maps (home page too) have dots
        con.execute("""UPDATE ip_info SET lat = [-6.2, -7.25, 1.29, 3.59][k], lon = [106.82, 112.75, 103.85, 98.67][k],
                              city = ['Jakarta', 'Surabaya', 'Singapore', 'Medan'][k], country = ['ID', 'ID', 'SG', 'ID'][k]
                       FROM (SELECT ip AS kip, (hash(ip) % 4 + 1)::INT AS k FROM ip_info) WHERE ip = kip AND NOT coalesce(is_private, false)""")
        con.close()
    uvicorn.run(appmod.create_app(cfg), host='127.0.0.1', port=int(port), log_level='warning')


if __name__ == '__main__':
    main(sys.argv[1], *(sys.argv[2:3]))
