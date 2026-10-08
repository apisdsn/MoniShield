"""Dashboard server FOR TESTING the import page (Stage 19): small synthetic data (tests/logs_mini) + a local fake S3.

  .venv/bin/python tools/server_uji_impor.py <port> <work-directory>

Not for production: the S3 endpoint is redirected to the fake S3 (importer.ENDPOINT), something deliberately not
possible through configuration. Admin: 'admin' / 'sandi-awal-admin-uji-19' (must be changed at first login).
"""
import dataclasses, gzip, os, sys

V2 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [V2, os.path.join(V2, 'tests')]

import uvicorn  # noqa: E402

import logs_mini  # noqa: E402
from s3_tiruan import KEY_OK, S3Tiruan  # noqa: E402
from monishield.infrastructure import config, db, importer
from monishield.infrastructure import ingest  # noqa: E402
from monishield.interfaces.api import app as appmod  # noqa: E402

D = '2026-01-05'
SECRET = 'rahasiaTiruanUjiYangTidakBolehBocor0001'


def obj(service, pod, ns='ombudsman', ext='.log'): return f'k8s-logs/{D}/{ns}/{service}/log_{service}_{pod}_{D}-00-00{ext}'


def main(port, work):
    apps = logs_mini.lines('om-be-appsmanager').encode()
    isi = {obj('om-be-appsmanager', 'pod-a'): apps, obj('om-be-appsmanager', 'pod-a', ext='.log.gz'): gzip.compress(apps),
           obj('om-fe-inhouse', 'pod-f', ext='.log.gz'): gzip.compress(logs_mini.lines('om-fe-inhouse').encode()),
           f'k8s-logs/{D}/.DS_Store': b'x'}
    s3 = S3Tiruan({'simpel4-backup': isi})
    importer.ENDPOINT = s3.url
    cfg = dataclasses.replace(config.Config(), log_dir=logs_mini.build(os.path.join(work, 'logs')), data_dir=os.path.join(work, 'data'),
                              state_dir=os.path.join(work, 'state'), inbox_dir=os.path.join(work, 'inbox'), cache_dir=os.path.join(work, 'cache'),
                              offline=True, ingest_on_start=False, cookie_secure=False, admin_user='admin', admin_password='sandi-awal-admin-uji-19',
                              job_token='token-mesin-uji-19', jwt_secret='rahasia-jwt-server-uji-impor-minimal-32',
                              import_buckets={'simpel4-backup': ['k8s-logs/']}, aws_access_key_id=KEY_OK, aws_secret_access_key=SECRET,
                              bind=f'127.0.0.1:{port}')
    os.makedirs(cfg.data_dir, exist_ok=True)
    con = db.open(cfg.db_path); ingest.run(cfg, con, workers=0); con.close()
    uvicorn.run(appmod.create_app(cfg), host='127.0.0.1', port=int(port), log_level='warning')


if __name__ == '__main__':
    main(*sys.argv[1:3])
