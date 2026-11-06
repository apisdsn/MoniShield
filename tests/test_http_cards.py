"""HTTP cards from any access log (stage 59): Command Center, volume band numbers (meta), folder summary and Trends use the ingress
when the folder has its lines (the numbers stay as they were) and otherwise the access-log service with the most requests."""
import dataclasses, os

import pytest
from fastapi.testclient import TestClient

import logs_mini
from conftest import JWT_SECRET
from monishield.domain import accounts, log_formats as lf
from monishield.infrastructure import config, db, ingest
from monishield.interfaces.api import app as appmod
from test_log_formats_page import sample
from test_wire import PW, PW2, Browser

NGINX_DAY, CADDY_DAY, APP_DAY = '2026-01-02', '2026-03-01', '2026-03-03'


@pytest.fixture
def tc(tmp_path, auth_url, monkeypatch):
    monkeypatch.setattr(accounts, 'SCRYPT', (10, 8, 1))
    root = logs_mini.build(tmp_path / 'logs')
    caddy = '\n'.join(sample('caddy-json.log')) + '\n'
    logs_mini.write(logs_mini.log_path(root, CADDY_DAY, 'host1', 'monishield-https-1', 'p1'), caddy)
    logs_mini.write(logs_mini.log_path(root, APP_DAY, 'host1', 'auth-service', 'p1'), logs_mini.lines('auth-service'))
    cfg = dataclasses.replace(config.Config(), log_dir=root, data_dir=str(tmp_path / 'data'), state_dir=str(tmp_path / 'state'), inbox_dir=str(tmp_path / 'inbox'),
                              cache_dir=str(tmp_path / 'cache'), offline=True, ingest_on_start=False, cookie_secure=False, admin_user='admin',
                              admin_password=PW, jwt_secret=JWT_SECRET, auth_database_url=auth_url)
    cfg.log_formats_file = str(tmp_path / 'state' / 'log-formats.toml')
    os.makedirs(cfg.state_dir)
    from monishield.domain import services
    rules = (lf.Rule('monishield-https-1', 'caddy-json', 'http'), *lf.default_rules(services.from_config(cfg)))
    open(cfg.log_formats_file, 'w').write(lf.dumps(rules))
    lf.use(rules)
    con = db.open(cfg.db_path); ingest.run(cfg, con, workers=0); con.close()
    with TestClient(appmod.create_app(cfg)) as c:
        b = Browser(c)
        assert b.call('POST', '/api/v1/auth/login', dict(username='admin', password=PW)).status_code == 200
        assert b.call('POST', '/api/v1/me/password', dict(old_password=PW, new_password=PW2)).status_code == 200
        c.b = b
        yield c
    lf.use(None)


def get(tc, path): return tc.b.json(tc.b.call('GET', path), 'GET', path)


def test_a_folder_with_the_ingress_keeps_its_numbers(tc):
    d = get(tc, f'/api/v1/folders/{NGINX_DAY}/command-center')
    assert d['http_service'] == 'nginx-ingress-controller' and d['kpi']['requests'] == 7 and sum(d['by_hour']['requests']) == 7
    assert get(tc, f'/api/v1/folders/{NGINX_DAY}')['http_service'] == 'nginx-ingress-controller'


def test_a_folder_with_only_a_caddy_log_uses_it(tc):
    d = get(tc, f'/api/v1/folders/{CADDY_DAY}/command-center')
    assert d['http_service'] == 'monishield-https-1' and d['kpi']['requests'] == 3 and sum(d['by_hour']['requests']) == 3
    assert get(tc, f'/api/v1/folders/{CADDY_DAY}')['http_service'] == 'monishield-https-1'
    folders = {f['folder']: f for f in get(tc, '/api/v1/meta')['folders']}
    assert (folders[CADDY_DAY]['requests'], folders[CADDY_DAY]['http_service']) == (3, 'monishield-https-1')
    assert (folders[NGINX_DAY]['requests'], folders[NGINX_DAY]['http_service']) == (7, 'nginx-ingress-controller')


def test_a_folder_without_an_access_log_has_no_http_numbers(tc):
    d = get(tc, f'/api/v1/folders/{APP_DAY}/command-center')
    assert d['http_service'] is None and d['kpi']['requests'] is None and d['kpi']['n5xx'] is None and sum(d['by_hour']['requests']) == 0
    assert get(tc, f'/api/v1/folders/{APP_DAY}')['http_service'] is None
    assert {f['folder']: f['requests'] for f in get(tc, '/api/v1/meta')['folders']}[APP_DAY] is None


def test_trends_count_each_folders_access_log(tc):
    t = get(tc, '/api/v1/trends?last=all')
    per = dict(zip(t['folders'], t['http']['total']))
    assert per[NGINX_DAY] == 7 and per[CADDY_DAY] == 3 and per[APP_DAY] == 0
    assert per['2026-01-01'] == 2 and sum(map(sum, t['heat']['requests'])) == 12   # the frontend's folder counts its frontend
