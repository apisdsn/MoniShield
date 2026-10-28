"""Daily backup (owner request 2026-10-27): both DuckDB databases + the account database, private files, kept N days,
optional copy to object storage, notified when it fails, and restorable."""
import dataclasses, datetime, gzip, json, os, shutil, stat

import duckdb
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

import logs_mini
from monishield.domain import accounts, retention
from monishield.domain.errors import Fail
from monishield.infrastructure import backup, config, db, ingest
from monishield.infrastructure.auth import Base
from monishield.interfaces.api import app as appmod
from conftest import JWT_SECRET

X = {'X-Requested-With': 'uji'}
PW, PW2 = 'sandi-admin-pertama', 'sandi-admin-sesudah-diganti'
JOB = 'token-mesin-untuk-uji-backup-0001'


@pytest.fixture
def cfg(tmp_path, auth_url):
    c = dataclasses.replace(config.Config(), log_dir=logs_mini.build(tmp_path / 'logs'), data_dir=str(tmp_path / 'data'), state_dir=str(tmp_path / 'state'),
                            inbox_dir=str(tmp_path / 'inbox'), cache_dir=str(tmp_path / 'cache'), offline=True, ingest_on_start=False, cookie_secure=False,
                            admin_user='admin', admin_password=PW, jwt_secret=JWT_SECRET, auth_database_url=auth_url, job_token=JOB, backup_keep=2)
    os.makedirs(c.data_dir)
    con = db.open(c.db_path); ingest.run(c, con, workers=0); con.close()
    return c


@pytest.fixture
def client(cfg, monkeypatch):
    monkeypatch.setattr(accounts, 'SCRYPT', (10, 8, 1))
    with TestClient(appmod.create_app(cfg)) as tc:
        assert tc.post('/api/auth/login', json=dict(username='admin', password=PW), headers=X).status_code == 200
        assert tc.post('/api/me/password', json=dict(old_password=PW, new_password=PW2), headers=X).status_code == 200
        yield tc


def test_next_daily_run_is_the_next_hour_in_wib():
    utc = lambda *a: datetime.datetime(*a, tzinfo=datetime.timezone.utc)
    assert retention.next_daily(utc(2026, 10, 27, 18, 0), 2) == utc(2026, 10, 27, 19, 0)    # 01:00 WIB -> 02:00 WIB the same night
    assert retention.next_daily(utc(2026, 10, 27, 19, 0), 2) == utc(2026, 10, 28, 19, 0)    # exactly 02:00 WIB -> tomorrow
    assert retention.next_daily(utc(2026, 10, 27, 3, 0), 23) == utc(2026, 10, 27, 16, 0)


def test_backup_now_writes_private_copies_of_both_databases_and_the_accounts(client, cfg):
    r = client.post('/api/admin/backup/run', headers=X)
    assert r.status_code == 200, r.text
    s = r.json()
    day = s['last']['day']
    assert s['last']['ok'] and s['backups'][0]['day'] == day and s['next']
    folder = os.path.join(cfg.backup_path, day)
    assert sorted(os.listdir(folder)) == ['accounts.json.gz', 'kafka.duckdb.gz', 'manifest.json', 's3.duckdb.gz']
    assert stat.S_IMODE(os.stat(folder).st_mode) == 0o700
    assert all(stat.S_IMODE(os.stat(os.path.join(folder, f)).st_mode) == 0o600 for f in os.listdir(folder))   # password hashes, IPs
    man = json.load(open(os.path.join(folder, 'manifest.json')))
    assert all(backup._sha256(os.path.join(folder, f)) == v['sha256'] for f, v in man['files'].items())
    copy = str(cfg.data_dir) + '/check.duckdb'
    with gzip.open(os.path.join(folder, 's3.duckdb.gz'), 'rb') as a, open(copy, 'wb') as b: shutil.copyfileobj(a, b)
    live = client.app.state.con.cursor().execute('SELECT folder::VARCHAR, lines FROM folder_state ORDER BY 1').fetchall()
    c = duckdb.connect(copy, read_only=True)
    assert c.execute('SELECT folder::VARCHAR, lines FROM folder_state ORDER BY 1').fetchall() == live and live
    c.close()
    acc = json.load(gzip.open(os.path.join(folder, 'accounts.json.gz'), 'rt'))['tables']
    assert [u['username'] for u in acc['app_user']] == ['admin'] and acc['app_user'][0]['password_hash']


def test_machine_token_can_start_a_backup_and_old_ones_are_pruned(client, cfg):
    for d in ('2026-01-01', '2026-01-02', '2026-01-03'):   # older backups
        os.makedirs(os.path.join(cfg.backup_path, d))
        json.dump(dict(day=d, files={'s3.duckdb.gz': dict(bytes=1, sha256='x')}), open(os.path.join(cfg.backup_path, d, 'manifest.json'), 'w'))
    r = client.post('/api/admin/backup/run', headers={'Authorization': f'Bearer {JOB}'})
    assert r.status_code == 200, r.text
    assert [b['day'] for b in r.json()['backups']] == [r.json()['last']['day'], '2026-01-03']   # backup_keep=2
    assert r.json()['last']['pruned'] == ['2026-01-02', '2026-01-01']


def test_copy_to_object_storage_uses_the_bucket_and_prefix(cfg, tmp_path):
    b = backup.Backups(dataclasses.replace(cfg, backup_s3='s3://ms-backup/monishield'))
    os.makedirs(os.path.join(cfg.backup_path, '2026-10-27'))
    for f in ('manifest.json', 's3.duckdb.gz'): open(os.path.join(cfg.backup_path, '2026-10-27', f), 'w').write('x')
    calls = []
    client = type('C', (), {'upload_file': lambda self, path, bucket, key: calls.append((os.path.basename(path), bucket, key))})()
    assert b.upload('2026-10-27', client) == 's3://ms-backup/monishield/2026-10-27/'
    assert calls == [('manifest.json', 'ms-backup', 'monishield/2026-10-27/manifest.json'), ('s3.duckdb.gz', 'ms-backup', 'monishield/2026-10-27/s3.duckdb.gz')]
    denied = type('C', (), {'upload_file': lambda self, *a: (_ for _ in ()).throw(PermissionError('AccessDenied'))})()
    with pytest.raises(Fail) as e: b.upload('2026-10-27', denied)
    assert e.value.code == 'backup_upload' and 'AccessDenied' in e.value.message
    with pytest.raises(Fail): backup.Backups(dataclasses.replace(cfg, backup_s3='s3://x/', storage_provider='azure')).upload('2026-10-27', client)
    assert backup.Backups(cfg).upload('2026-10-27', client) is None                        # no S4_BACKUP_S3: nothing to copy


def test_a_failed_backup_is_reported_and_notified(client, monkeypatch):
    sent = []
    monkeypatch.setattr('monishield.application.alert_service.deliver', lambda ctx, cfg, key, ev, title, text, **k: sent.append((key, ev, title, text)))
    monkeypatch.setattr('monishield.domain.alerts.active', lambda cfg: True)
    def boom(*a, **k): raise OSError(28, 'No space left on device')
    monkeypatch.setattr(client.app.state.backups, 'make', boom)
    r = client.post('/api/admin/backup/run', headers=X)
    assert r.status_code == 500 and 'No space left on device' in r.json()['error']['message']
    last = client.get('/api/admin/backup', headers=X).json()['last']
    assert last['ok'] is False and 'No space left' in last['error']
    assert sent and sent[0][1] == 'backup_failed' and sent[0][0].startswith('backup_failed:') and 'No space left' in sent[0][3]


def test_restore_puts_databases_back_and_refills_an_empty_account_database(client, cfg, tmp_path):
    day = client.post('/api/admin/backup/run', headers=X).json()['last']['day']
    folder = os.path.join(cfg.backup_path, day)
    client.__exit__(None, None, None)   # server stopped: DuckDB has one owner
    live = duckdb.connect(cfg.db_path); live.execute('DELETE FROM folder_state'); live.close()   # an accident after the backup
    engine = create_engine('sqlite:///' + str(tmp_path / 'new-auth.db')); Base.metadata.create_all(engine)
    r = backup.restore(cfg, folder, engine, Base.metadata)
    assert r['accounts']['app_user'] == 1 and r['s3'] == cfg.db_path and os.path.exists(cfg.db_path + '.before-restore')
    c = duckdb.connect(cfg.db_path, read_only=True); assert c.execute('SELECT count(*) FROM folder_state').fetchone()[0] > 0; c.close()
    with engine.connect() as k: assert k.exec_driver_sql('SELECT username FROM app_user').fetchall() == [('admin',)]
    with pytest.raises(Fail) as e: backup.restore(cfg, folder, engine, Base.metadata, databases=False)   # not empty any more
    assert e.value.code == 'restore_not_empty'
    open(os.path.join(folder, 's3.duckdb.gz'), 'ab').write(b'x')                                           # damaged file
    with pytest.raises(Fail) as e: backup.restore(cfg, folder, create_engine('sqlite://'), Base.metadata)
    assert e.value.code == 'restore_corrupt'
