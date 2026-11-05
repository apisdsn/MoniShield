"""Collector as the third data source (docs/12-collector.md, step 4): own database and folders, ingest of what the receiver
wrote, catch-up after a restart, retention, backup, the ?source= guard and the source list of the page."""
import argparse, dataclasses, datetime, gzip, os, shutil, threading, time, types

import duckdb
import pytest
from fastapi.testclient import TestClient

from monishield.application import alert_service, sources
from monishield.domain import accounts, alerts, config_model, retention
from monishield.interfaces import cli
from monishield.interfaces.api import app as appmod
from monishield.infrastructure import db, ingest
from test_api import X, admin, cfg   # noqa: F401  (fixtures and helpers of the API tests)
from test_collector_receiver import HOST, K8S, post, sample
from test_collectors import add, enroll

DAY = '2026-11-05'   # the folder of the sample payloads (their time is 2026-11-04 16:55 WIB)


def src(tc, name): return tc.app.state.sources[name]


def known(tc, name): return src(tc, name).warehouse.known_folders()


def send_samples(tc, key):
    for name in ('k8s', 'host_file'): assert post(tc, key, sample(name)).status_code == 200


def wait_for(fn, seconds=60):
    end = time.time() + seconds
    while time.time() < end:
        if fn(): return True
        time.sleep(0.1)
    return False


# The source itself
def test_the_source_is_registered_with_its_own_paths(cfg):
    assert sources.SOURCES == ('s3', 'kafka', 'collector') and sources.LABEL['collector'] == 'Collector' and sources.valid('collector')
    c = config_model.collector_config(cfg)
    assert (c.log_dir, c.inbox_dir, c.db_path, c.duckdb_snapshot) == ('', cfg.collector_inbox, cfg.collector_db_path, False)
    assert cfg.collector_db_path == os.path.join(cfg.data_dir, 'collector', 'monishield.duckdb')
    assert len({cfg.db_path, cfg.kafka_db_path, cfg.collector_db_path}) == 3
    assert cfg.collector_ingest_seconds == 300


def test_cli_source_choice(cfg):
    pick = lambda s: cli._source_config(cfg, argparse.Namespace(source=s))
    assert pick('s3') is cfg and pick('kafka').db_path == cfg.kafka_db_path and pick('collector').db_path == cfg.collector_db_path
    assert pick('collector').inbox_dir == cfg.collector_inbox


def test_notifications_and_reports_name_the_source():
    named = alert_service.Notifier._named(types.SimpleNamespace(source='collector'), 'spike:x', 'Spike')
    assert named == ('spike:x@collector', 'Spike (Collector)')
    today = datetime.date(2026, 11, 5)
    both = ['2026-11-05', '2026-11-06']                                                  # the folder dated tomorrow is still filling up
    assert alerts.report_target(None, [], today, both) == ('2026-11-05', 'collector')
    assert alerts.report_target(None, ['2026-11-04'], today, both) == ('2026-11-04', 'kafka')
    assert alerts.report_target('2026-11-03', ['2026-11-04'], today, both) == ('2026-11-03', 's3')
    assert alerts.report_target(None, [], today, ['2026-11-06']) is None and alerts.report_target(None, [], today) is None


# The harness
@pytest.fixture
def boot(cfg, auth_url, tmp_path, monkeypatch):
    """boot(prefill=callable(collector inbox), s3=False, register=True, **settings) -> (admin client, collector key, collector inbox). Every
    test has its own data and inbox folders, so the databases of the sources start empty (s3=True: with the sample S3 days)."""
    monkeypatch.setattr(accounts, 'SCRYPT', (10, 8, 1))
    clients = []

    def start(prefill=None, s3=False, register=True, **over):
        c = dataclasses.replace(cfg, auth_database_url=auth_url, inbox_dir=str(tmp_path / 'inbox'), data_dir=str(tmp_path / 'data'),
                                state_dir=str(tmp_path / 'state'), collector_min_free_mb=0, collector_max_age_hours=0, **over)
        if s3:
            con = db.open(c.db_path); ingest.run(dataclasses.replace(c, retention_days=0, retention_inbox_days=0), con, workers=0); con.close()   # keeps every day
        if prefill: prefill(c.collector_inbox)
        tc = TestClient(appmod.create_app(c)); tc.__enter__(); clients.append(tc)
        admin(tc)
        key = enroll(TestClient(tc.app), add(tc)['enroll_token']).json()['key'] if register else None
        return tc, key, c.collector_inbox

    start.close = lambda tc: (clients.remove(tc), tc.__exit__(None, None, None))
    yield start
    for tc in clients: tc.__exit__(None, None, None)


def lay_down(inbox):
    for rel, lines in {**K8S, **HOST}.items():
        path = os.path.join(inbox, *rel.split('/'))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as fh: fh.write('\n'.join(lines) + '\n')


# Ingest of the inbox
def test_receiver_to_database_and_pages(boot):
    tc, key, root = boot()
    send_samples(tc, key)
    feed = tc.app.state.collector_feed
    assert feed.status()['pending'] == [DAY] and known(tc, 'collector') == set()
    assert feed.ingest_pending(force=True) == [DAY]
    assert feed.status()['pending'] == [] and feed.status()['last_ingest_at']
    assert known(tc, 'collector') == {DAY}
    assert DAY not in known(tc, 's3') and known(tc, 'kafka') == set()                          # the other sources do not know the day
    assert os.path.exists(tc.app.state.cfg.collector_db_path)
    meta = tc.get('/api/v1/meta?source=collector', headers=X).json()
    assert meta['source'] == 'collector' and [(f['folder'], f['source']) for f in meta['folders']] == [(DAY, 'collector')]
    ov = tc.get(f'/api/v1/folders/{DAY}/overview?source=collector', headers=X)
    assert ov.status_code == 200, ov.text
    names = {s['service'] for s in tc.get(f'/api/v1/folders/{DAY}?source=collector', headers=X).json()['services']}
    assert {'orders-api', 'payments', 'app'} <= names
    sv = tc.get(f'/api/v1/folders/{DAY}/services/payments?source=collector', headers=X)
    assert sv.status_code == 200, sv.text
    raw = tc.get(f'/api/v1/folders/{DAY}/raw', params=dict(q='charged', source='collector'), headers=X).json()
    assert raw['total'] == 1 and raw['rows'][0]['service'] == 'payments'
    assert tc.get(f'/api/v1/folders/{DAY}?source=s3', headers=X).status_code == 404               # S3 has no such day
    rows = tc.get('/api/v1/admin/folders?source=collector', headers=X).json()['rows']
    assert [(r['folder'], r['source'], r['in_db']) for r in rows] == [(DAY, 'collector', True)]
    assert DAY not in {r['folder'] for r in tc.get('/api/v1/admin/folders', headers=X).json()['rows']}   # the S3 side does not list it


def test_second_batch_is_read_again_and_the_interval_is_kept(boot):
    tc, key, root = boot(collector_ingest_seconds=300)
    feed = tc.app.state.collector_feed
    t0 = feed._last = time.monotonic()                                                          # as if an ingest had just run
    assert post(tc, key, sample('k8s')).status_code == 200
    assert feed.ingest_pending(now=t0 + 301) == [DAY]
    count = lambda: src(tc, 'collector').con.cursor().execute('SELECT count(*) FROM ingest_file WHERE folder = ?', [DAY]).fetchone()[0]
    first = count()
    assert post(tc, key, sample('host_file')).status_code == 200
    assert feed.ingest_pending(now=t0 + 400) == [] and feed.status()['pending'] == [DAY]        # 99 s later: not due
    assert feed.ingest_pending(now=t0 + 602) == [DAY] and count() > first
    assert feed.ingest_pending(now=t0 + 9999) == []                                             # nothing pending


def test_pending_is_kept_when_the_ingest_fails(boot, monkeypatch):
    tc, key, root = boot()
    send_samples(tc, key)
    feed, ing = tc.app.state.collector_feed, src(tc, 'collector').ingest

    def boom(*a, **k): raise RuntimeError('disk error')
    with monkeypatch.context() as m:
        m.setattr(ing, 'run_blocking', boom)
        assert feed.ingest_pending(force=True) == [] and feed.status()['pending'] == [DAY] and known(tc, 'collector') == set()
    assert feed.ingest_pending(force=True) == [DAY] and feed.status()['pending'] == [] and known(tc, 'collector') == {DAY}


def test_a_running_ingest_is_not_waited_for(boot):
    tc, key, root = boot()
    send_samples(tc, key)
    ing = src(tc, 'collector').ingest
    ing.state['running'] = True
    try: assert tc.app.state.collector_feed.ingest_pending(force=True) == [] and tc.app.state.collector_feed.status()['pending'] == [DAY]
    finally: ing.state['running'] = False


def test_the_ingest_error_does_not_leak_into_the_other_sources(boot, monkeypatch):
    tc, key, root = boot()
    send_samples(tc, key)
    monkeypatch.setattr(src(tc, 'collector').warehouse, 'ingest', lambda *a, **k: (_ for _ in ()).throw(RuntimeError('x')))
    assert tc.app.state.collector_feed.ingest_pending(force=True) == []
    assert src(tc, 'collector').ingest.state['error'].startswith('RuntimeError') and src(tc, 'kafka').ingest.state['error'] is None
    assert tc.app.state.ingest.state['error'] is None


# catch-up and the thread
def test_catch_up_ingests_folders_the_database_does_not_know(boot):
    tc, key, root = boot(prefill=lay_down)
    assert wait_for(lambda: known(tc, 'collector') == {DAY})
    assert tc.app.state.collector_feed.status()['pending'] == [] and tc.app.state.collector_feed.running()
    assert tc.get(f'/api/v1/folders/{DAY}?source=collector', headers=X).status_code == 200


def test_catch_up_skips_known_and_expired_folders(boot, tmp_path, monkeypatch):
    monkeypatch.setattr(retention, 'today_local', lambda now: datetime.date(2026, 12, 30))
    tc, key, root = boot(prefill=lay_down, retention_days=10)                                             # the sample day is past the keeping period
    time.sleep(1.5)
    feed = tc.app.state.collector_feed
    assert known(tc, 'collector') == set() and feed.catch_up() == [] and feed.status()['pending'] == []


def test_the_thread_ingests_on_its_own_and_stops_with_the_app(boot):
    tc, key, root = boot(collector_ingest_seconds=1)
    feed = tc.app.state.collector_feed
    assert feed.running() and any(t.name == 'collector-ingest' for t in threading.enumerate())
    time.sleep(1.2)                                                                              # the start counts as the last ingest
    assert post(tc, key, sample('k8s')).status_code == 200
    assert wait_for(lambda: known(tc, 'collector') == {DAY}) and feed.status()['pending'] == []
    boot.close(tc)
    assert not feed.running() and not any(t.name == 'collector-ingest' for t in threading.enumerate())


# The guard, the source list, retention, backup
def test_source_guard_names_all_three_sources(boot):
    tc, key, root = boot(register=False)
    for path in ('/api/v1/meta', '/api/v1/admin/folders', '/api/v1/admin/ingest', '/api/v1/admin/retention'):
        r = tc.get(path + '?source=bogus', headers=X)
        assert r.status_code == 400 and r.json()['error']['code'] == 'invalid_parameter'
        assert all(s in r.json()['error']['message'] for s in ('s3', 'kafka', 'collector'))
        assert tc.get(path + '?source=collector', headers=X).status_code == 200


def test_meta_offers_the_collector_once_one_exists(boot):
    tc, key, root = boot(register=False)
    assert tc.get('/api/v1/meta', headers=X).json()['sources'] == ['s3']
    add(tc)
    assert tc.get('/api/v1/meta', headers=X).json()['sources'] == ['s3', 'collector']


def test_meta_offers_the_collector_when_its_database_knows_a_day(boot):
    tc, key, root = boot()
    send_samples(tc, key)
    tc.app.state.collector_feed.ingest_pending(force=True)
    cid = tc.get('/api/v1/admin/collectors').json()['rows'][0]['id']
    assert tc.post(f'/api/v1/admin/collectors/{cid}/revoke', headers=X).status_code == 200 and tc.delete(f'/api/v1/admin/collectors/{cid}', headers=X).status_code == 200
    assert tc.app.state.auth.collector_list() == [] and tc.get('/api/v1/meta', headers=X).json()['sources'] == ['s3', 'collector']


def test_retention_cleans_the_collector_source_only(boot, cfg, monkeypatch):
    monkeypatch.setattr(retention, 'today_local', lambda now: datetime.date(2026, 11, 30))
    tc, key, root = boot(s3=True)
    st = tc.app.state
    send_samples(tc, key)
    kafka_day = os.path.join(st.cfg.kafka_inbox, '2026-11-02')                                  # a Kafka folder, also past the keeping period
    shutil.copytree(os.path.join(cfg.log_dir, '2026-01-02'), kafka_day)
    st.collector_feed.ingest_pending(force=True)
    k = src(tc, 'kafka'); k.ingest.start('2026-11-02', by='test'); k.ingest.wait(60)
    s3_before = known(tc, 's3')
    assert s3_before and known(tc, 'kafka') == {'2026-11-02'} and known(tc, 'collector') == {DAY}
    st.cfg.retention_days = st.cfg.retention_inbox_days = 10                                    # the settings are live; every source reads them
    v = tc.get('/api/v1/admin/retention?source=collector', headers=X).json()
    assert v['db'] == [DAY] and v['inbox'] == [DAY]
    assert tc.post('/api/v1/admin/retention/run?source=collector', headers=X).status_code == 200
    assert known(tc, 'collector') == set() and not os.path.exists(os.path.join(root, DAY))
    assert known(tc, 's3') == s3_before and known(tc, 'kafka') == {'2026-11-02'} and os.path.isdir(kafka_day)
    assert not st.collector_feed.status()['pending']


def test_backup_includes_the_collector_database(boot, tmp_path):
    tc, key, root = boot()
    send_samples(tc, key)
    tc.app.state.collector_feed.ingest_pending(force=True)
    r = tc.post('/api/v1/admin/backup/run', headers=X)
    assert r.status_code == 200, r.text
    folder = os.path.join(tc.app.state.cfg.backup_path, r.json()['last']['day'])
    assert 'collector.duckdb.gz' in os.listdir(folder)
    plain = str(tmp_path / 'restored.duckdb')
    with gzip.open(os.path.join(folder, 'collector.duckdb.gz'), 'rb') as a, open(plain, 'wb') as b: shutil.copyfileobj(a, b)
    con = duckdb.connect(plain, read_only=True)
    try: assert [r[0] for r in con.execute('SELECT folder::VARCHAR FROM folder_state').fetchall()] == [DAY]
    finally: con.close()


def test_start_ingests_new_lines_of_a_known_folder_without_a_new_batch(cfg, auth_url, tmp_path, monkeypatch):
    monkeypatch.setattr(accounts, 'SCRYPT', (10, 8, 1))
    c = dataclasses.replace(cfg, auth_database_url=auth_url, inbox_dir=str(tmp_path / 'inbox'), data_dir=str(tmp_path / 'data'),
                            state_dir=str(tmp_path / 'state'), collector_min_free_mb=0, collector_max_age_hours=0)
    lay_down(c.collector_inbox)
    lines = lambda tc: src(tc, 'collector').con.cursor().execute('SELECT coalesce(sum(lines), 0) FROM ingest_file WHERE folder = ?', [DAY]).fetchone()[0]
    with TestClient(appmod.create_app(c)) as tc:
        assert wait_for(lambda: known(tc, 'collector') == {DAY}) and wait_for(lambda: lines(tc) > 0)
        before = lines(tc)
    # the server is down: a collector's last lines land in a folder the database already knows
    with open(os.path.join(c.collector_inbox, *next(k for k in HOST if '/payments/' in k).split('/')), 'a', encoding='utf-8') as fh: fh.write('late line 1\nlate line 2\n')
    with TestClient(appmod.create_app(c)) as tc:
        assert wait_for(lambda: lines(tc) == before + 2), (before, lines(tc))
        assert tc.app.state.collector_feed.status()['pending'] == []
