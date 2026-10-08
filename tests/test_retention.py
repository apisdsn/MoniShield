"""Data retention (owner request 2026-10-08): folders past S4_RETENTION_DAYS leave the database and do not come back;
inbox folders past S4_RETENTION_INBOX_DAYS are deleted from disk; log files in the main log folder are never touched."""
import dataclasses, datetime, os

import pytest
from fastapi.testclient import TestClient

import logs_mini
from monishield.domain import accounts, retention
from monishield.infrastructure import config, db, ingest
from monishield.interfaces.api import app as appmod
from conftest import JWT_SECRET

X = {'X-Requested-With': 'uji'}
PW, PW2 = 'sandi-admin-pertama', 'sandi-admin-sesudah-diganti'
TODAY = datetime.date(2026, 1, 12)   # cut-off with 10 days = 2026-01-02: folder 01-01 is past it, 01-02 is kept


def test_rules():
    assert retention.cutoff(TODAY, 0) is None and retention.cutoff(TODAY, 10) == '2026-01-02'
    assert retention.expired('2026-01-01', '2026-01-02') and not retention.expired('2026-01-02', '2026-01-02')
    assert not retention.expired('2000-01-01', None)
    p = retention.plan({'2026-01-01', '2026-01-05'}, {'2025-12-30', '2026-01-11'}, TODAY, 10, 3)
    assert (p['db'], p['inbox'], p['cutoff_inbox']) == (['2026-01-01'], ['2025-12-30'], '2026-01-09')
    assert retention.watch_days(30, 0) == 30 and retention.watch_days(30, 10) == 10 and retention.watch_days(0, 10) == 10
    assert retention.validate(0, 0) is None and retention.validate(8, 2) is None
    assert 'Database retention' in retention.validate(7, 0) and 'Inbox retention' in retention.validate(0, 1)
    assert retention.today_wib(datetime.datetime(2026, 1, 11, 18, 0)) == TODAY   # 18:00 UTC = 01:00 WIB the next day


@pytest.fixture
def tc(tmp_path, auth_url, monkeypatch):
    monkeypatch.setattr(accounts, 'SCRYPT', (10, 8, 1))
    monkeypatch.setattr(retention, 'today_wib', lambda now: TODAY)
    c = dataclasses.replace(config.Config(), log_dir=logs_mini.build(tmp_path / 'logs'), data_dir=str(tmp_path / 'data'), state_dir=str(tmp_path / 'state'),
                            inbox_dir=str(tmp_path / 'inbox'), cache_dir=str(tmp_path / 'cache'), offline=True, ingest_on_start=False, cookie_secure=False,
                            admin_user='admin', admin_password=PW, jwt_secret=JWT_SECRET, auth_database_url=auth_url)
    con = db.open(c.db_path); ingest.run(c, con, workers=0); con.close()
    with TestClient(appmod.create_app(c)) as client:
        assert client.post('/api/auth/login', json=dict(username='admin', password=PW), headers=X).status_code == 200
        assert client.post('/api/me/password', json=dict(old_password=PW, new_password=PW2), headers=X).status_code == 200
        yield client


def test_cleanup_removes_old_folders_for_good(tc):
    st = tc.app.state
    old_inbox = os.path.join(st.cfg.inbox_dir, '2025-12-20', 'ns', 'svc')
    os.makedirs(old_inbox); open(os.path.join(old_inbox, 'a.log'), 'w').write('x\n')
    assert tc.get('/api/admin/retention', headers=X).json()['db'] == []          # 0 = keep forever
    r = tc.put('/api/admin/config', json=dict(retention_days='10', retention_inbox_days='5'), headers=X)
    assert r.status_code == 200, r.text
    assert 'S4_RETENTION_DAYS=10' in open(st.env.path).read()
    v = tc.get('/api/admin/retention', headers=X).json()
    assert (v['db'], v['inbox'], v['cutoff_db']) == (['2026-01-01'], ['2025-12-20'], '2026-01-02')
    r = tc.post('/api/admin/retention/run', headers=X)
    assert r.status_code == 200, r.text
    assert r.json()['last']['db'] == ['2026-01-01'] and r.json()['last']['inbox'] == ['2025-12-20'] and r.json()['db'] == []
    assert st.warehouse.known_folders() == {'2026-01-02'}
    assert not os.path.exists(os.path.dirname(old_inbox))
    assert os.path.isdir(os.path.join(st.cfg.log_dir, '2026-01-01'))              # main log folder untouched
    assert 'retention.run' in tc.get('/api/admin/audit', headers=X).text
    # the log files are still there, but ingest and the "new folders" badge skip them
    st.ingest.start(by='uji'); st.ingest.wait(60)
    assert st.warehouse.known_folders() == {'2026-01-02'}
    assert tc.get('/api/admin/ingest/status', headers=X).json()['new_folders'] == []


@pytest.mark.parametrize('body', [dict(retention_days='7'), dict(retention_inbox_days='1'), dict(retention_days='abc')])
def test_invalid_settings_refused(tc, body):
    r = tc.put('/api/admin/config', json=body, headers=X)
    assert r.status_code == 400
    path = tc.app.state.env.path
    assert not os.path.exists(path) or 'S4_RETENTION' not in open(path).read()
