"""Public home page map (owner request 2026-10-28): coarse cells, small cells dropped, no IP addresses, can be turned off."""
import dataclasses, json, re, time

import pytest
from fastapi.testclient import TestClient

import logs_mini
from monishield.application import kafka_service
from monishield.domain import accounts, public_map
from monishield.infrastructure import config, db, ingest
from monishield.interfaces.api import app as appmod
from conftest import JWT_SECRET

PW, PW2 = 'sandi-admin-pertama', 'sandi-admin-sesudah-diganti'
X = {'X-Requested-With': 'uji'}
IP = re.compile(r'\b\d{1,3}(?:\.\d{1,3}){3}\b')


def test_points_are_rounded_and_small_ones_dropped():
    rows = [(-6.21, 106.85, 40, 'Jakarta', 'ID'), (-6.24, 106.99, 5, 'Bekasi', 'ID'), (-6.4, 106.9, 2, None, 'ID'),
            (-33.87, 151.21, 2, 'Sydney', 'AU'), (None, None, 9, None, None)]
    pts = public_map.coarse(rows)
    assert pts == [dict(lat=-6.0, lon=107.0, requests=45, city='Jakarta', cc='ID')]   # Sydney and the unnamed cell (2 requests) left out
    assert public_map.coarse(rows, 1)[0] == dict(lat=-34.0, lon=151.0, requests=2, city='Sydney', cc='AU')
    assert public_map.totals(pts) == dict(requests=45, places=1, countries=1)
    assert public_map.cell(-6.26) == -6.5 and public_map.cell(106.74) == 106.5 and public_map.cell(106.76) == 107.0


def test_live_window_sums_the_last_minutes(monkeypatch):
    class W:
        def ip_locations(self): return {'203.0.113.5': (-6.2, 106.8, 'Jakarta', 'ID'), '198.51.100.7': (1.29, 103.85, 'Singapore', 'SG')}
    hub = kafka_service.LiveHub(type('Ctx', (), {'warehouse': W()})())
    clock = [1_000_000.0]
    monkeypatch.setattr(kafka_service.time, 'time', lambda: clock[0])
    line = lambda ip: f'{ip} - - [28/Oct/2026:08:00:00 +0700] "GET / HTTP/1.1" 200 1 "-" "-" 10 0.01 [ns-svc-80] [] 10.0.0.1:80 1 0.01 200 x'
    for _ in range(3): hub.nginx_line(line('203.0.113.5'), 'ns-')
    clock[0] += 1
    hub.nginx_line(line('198.51.100.7'), 'ns-')
    clock[0] += 1
    assert sorted(hub.window(60)) == [(-6.2, 106.8, 3, 'Jakarta', 'ID'), (1.29, 103.85, 1, 'Singapore', 'SG')]
    clock[0] += 61
    assert hub.window(60) == []


@pytest.fixture
def client(tmp_path, auth_url, monkeypatch):
    monkeypatch.setattr(accounts, 'SCRYPT', (10, 8, 1))
    c = dataclasses.replace(config.Config(), log_dir=logs_mini.build(tmp_path / 'logs'), data_dir=str(tmp_path / 'data'), state_dir=str(tmp_path / 'state'),
                            inbox_dir=str(tmp_path / 'inbox'), cache_dir=str(tmp_path / 'cache'), offline=True, ingest_on_start=False, cookie_secure=False,
                            admin_user='admin', admin_password=PW, jwt_secret=JWT_SECRET, auth_database_url=auth_url)
    con = db.open(c.db_path)
    ingest.run(c, con, workers=0)
    con.execute("UPDATE ip_info SET lat = -6.2, lon = 106.8, city = 'Jakarta', country = 'ID' WHERE NOT coalesce(is_private, false)")
    con.close()
    with TestClient(appmod.create_app(c)) as tc:
        yield tc


def test_public_map_without_sign_in_or_ips(client):
    r = client.get('/api/public/map')
    assert r.status_code == 200 and r.headers['cache-control'] == 'no-store'
    m = r.json()
    assert m['enabled'] is True and m['mode'] == 'day' and m['day'] == '2026-01-01'       # Kafka off: the newest folder (logs of 1 Jan)
    assert m['points'] == [dict(lat=-6.0, lon=107.0, requests=7, city='Jakarta', cc='ID')] and m['totals'] == dict(requests=7, places=1, countries=1)
    assert set(m['server']) == {'lat', 'lon', 'city', 'cc'}                                 # no server IP
    assert not IP.search(r.text)
    # the admin turns it off on the Configuration page
    client.post('/api/auth/login', json=dict(username='admin', password=PW), headers=X)
    client.post('/api/me/password', json=dict(old_password=PW, new_password=PW2), headers=X)
    r = client.put('/api/admin/config', json=dict(public_map='false'), headers=X)
    assert r.status_code == 200 and r.json()['public']['public_map']['value'] is False
    time.sleep(0.01)
    assert client.get('/api/public/map').json() == dict(enabled=False)
    assert 'S4_PUBLIC_MAP=false' in open(client.app.state.env.path).read()
    assert json.loads(client.get('/api/admin/config').text)['public']['public_map']['value'] is False


def test_live_animation_does_not_reveal_small_areas():
    """Security review: the live pulses must not show a cell that the map leaves out (under MIN_REQUESTS)."""
    from monishield.application import public_map_service

    class Live:
        def window(self, seconds):
            big = [(-6.2, 106.8, 40 if seconds > 10 else 4, 'Jakarta', 'ID')]
            return big + [(-33.87, 151.21, 1, 'Sydney', 'AU')]          # one request: below the minimum
    class Feed:
        live = Live()
        def running(self): return True
    cfg = type('Cfg', (), {'public_map': True, 'server_fallback': ['Jakarta', 'DKI Jakarta', 'ID', -6.2, 106.8]})()
    m = public_map_service.PublicMap(type('Ctx', (), {'cfg': cfg, 'kafka': Feed()})()).snapshot()
    assert m['mode'] == 'live' and [(p['lat'], p['lon']) for p in m['points']] == [(-6.0, 107.0)]
    assert m['pulses'] == [dict(lat=-6.0, lon=107.0, n=4)] and 'Sydney' not in str(m)


def test_empty_newest_folder_uses_the_previous_one():
    """Owner report 2026-10-28: the home page map was empty because the newest folder had no located requests yet."""
    from monishield.application import public_map_service

    class Wh:
        def folder_table(self):
            return ({'2026-10-28': dict(lines=10), '2026-10-27': dict(lines=500), '2026-10-26': dict(lines=400),
                     '2026-10-29': dict(lines=0), 'uji-lama': dict(lines=9), '2026-10-30': dict(lines=7)}, {'2026-10-30': dict(by='admin', at=None)})
        def request_origins(self, folder):
            return {'2026-10-27': [(-6.2, 106.8, 40, 'Jakarta', 'ID')], '2026-10-26': [(3.6, 98.7, 9, 'Medan', 'ID')]}.get(folder, [])

    class Cfg: public_map, server_fallback = True, ('Jakarta', 'DKI', 'ID', -6.2, 106.8)

    class Ctx: cfg, warehouse, source, kafka, sources = Cfg, Wh(), 's3', None, {}

    m = public_map_service.PublicMap(Ctx).snapshot()
    assert m['mode'] == 'day' and m['day'] == '2026-10-26'   # folder 2026-10-27 (logs of the 26th); empty, ignored and odd names skipped
    assert [(p['lat'], p['lon'], p['requests']) for p in m['points']] == [(-6.0, 107.0, 40)]
