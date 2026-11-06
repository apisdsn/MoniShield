"""Servers page API (interfaces/api/servers.py, infrastructure/queries/servers.py): roles, ranges, buckets, unusual values."""
import datetime

import pytest
from fastapi.testclient import TestClient

from test_api import X, as_user, cfg, error_code, make_user   # noqa: F401  (fixtures and helpers of the API tests)
from test_metrics_receiver import make                          # noqa: F401  (fixture)

UTC = datetime.timezone.utc
MB = 1024 * 1024
NOW = HOUR = None


@pytest.fixture(autouse=True)
def clock():
    """The test's own "now" (a module constant would be minutes old by the time a late test runs in a long suite)."""
    global NOW, HOUR
    NOW = datetime.datetime.now(UTC).replace(microsecond=0)
    HOUR = NOW.replace(minute=0, second=0)


def post_servers(c, rng=None): return c.post('/api/v1/servers', json={} if rng is None else dict(range=rng), headers=X)


def post_host(c, cid, host, rng=None): return c.post('/api/v1/servers/host', json=dict(cid=cid, host=host, **({} if rng is None else dict(range=rng))), headers=X)


def ago(**kw): return NOW - datetime.timedelta(**kw)


def series(host, ctr, name, start, count, value, every=30, dim=''):
    return [(host, ctr, name, dim, start + datetime.timedelta(seconds=every * i), value(i) if callable(value) else value) for i in range(count)]


def seed_hours(store, cid, host, ctr, name, values, dim=''):
    """One hourly row for the current hour of the day on each of the earlier days (value = the day's average)."""
    for k, v in enumerate(values, 1):
        store.rows('INSERT INTO metric_hour VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) RETURNING 1', [cid, host, ctr, name, dim, (HOUR - datetime.timedelta(days=k)).replace(tzinfo=None), v, v, 120])


@pytest.fixture
def world(make):
    tc, key, store = make()
    cid = tc.get('/api/v1/admin/collectors').json()['rows'][0]['id']
    return tc, cid, store


def seed_basic(store, cid):
    pts = (series('web-01', '', 'cpu', ago(minutes=30), 60, 12.0) + series('web-01', '', 'mem_used', ago(minutes=30), 60, 2000.0 * MB)
           + series('web-01', '', 'mem_total', ago(minutes=30), 60, 8000.0 * MB) + series('web-01', '', 'load1', ago(minutes=30), 60, 0.5)
           + series('web-01', '', 'net_rx', ago(minutes=30), 60, 1000.0) + series('web-01', '', 'net_tx', ago(minutes=30), 60, 500.0)
           + series('web-01', '', 'disk_used', ago(minutes=30), 60, 50.0, dim='/') + series('web-01', '', 'disk_total', ago(minutes=30), 60, 100.0, dim='/')
           + series('web-01', '', 'disk_used', ago(minutes=30), 60, 95.0, dim='/data') + series('web-01', '', 'disk_total', ago(minutes=30), 60, 100.0, dim='/data')
           + series('web-01', 'api', 'cpu', ago(minutes=30), 60, 30.0) + series('web-01', 'api', 'mem_used', ago(minutes=30), 60, 300.0 * MB)
           + series('web-01', 'api', 'mem_limit', ago(minutes=30), 60, 1000.0 * MB) + series('web-01', 'api', 'restarts', ago(minutes=30), 60, 2.0)
           + series('web-01', 'api', 'net_rx', ago(minutes=30), 60, 10.0) + series('web-01', 'api', 'net_tx', ago(minutes=30), 60, 20.0)
           + series('web-01', 'old', 'cpu', ago(hours=5), 4, 1.0))
    store.add(cid, pts, {('web-01', ''): dict(os='Ubuntu 24.04', image=None), ('web-01', 'api'): dict(os=None, image='repo/api:1'), ('web-01', 'old'): dict(os=None, image='repo/old:1')}, NOW)
    store.rows("UPDATE metric_target SET last_seen = ? WHERE ctr = 'old' RETURNING 1", [(ago(hours=5)).replace(tzinfo=None)])


# Roles and parameters
def test_roles_and_bad_parameters(world, cfg):
    tc, cid, store = world
    anon = TestClient(tc.app)
    assert post_servers(anon).status_code == 401 and post_host(anon, cid, 'web-01').status_code == 401
    make_user(tc, 'rina')
    user = as_user(tc, 'rina', 'rina-initial-password-123')
    assert post_servers(user).status_code == 200                              # like the Pods page: every signed-in user
    assert tc.get('/api/v1/servers?range=24h').status_code in (404, 405) and tc.get('/api/v1/servers/host?cid=1&host=web-01').status_code in (404, 405)   # no GET form: a host name never stands in a URL
    for rng in ('2h', '', '1H'): assert error_code(post_servers(tc, rng)) == 'invalid_parameter', rng
    seed_basic(store, cid)
    assert post_host(tc, cid, 'web-01').status_code == 200
    assert error_code(post_host(tc, cid, 'web-01', '9d')) == 'invalid_parameter'
    for c, h in ((cid, 'nope'), (cid + 50, 'web-01'), (cid, '../web-01'), (cid, 'web-01\n'), (cid, 'x' * 300)):
        r = post_host(tc, c, h)
        assert r.status_code in (404, 400) and r.json()['error']['code'] in ('not_found', 'invalid_parameter'), (c, h)
    for body in (dict(host='web-01'), dict(cid=cid), dict(cid='abc', host='x'), dict(cid=0, host='x')):
        assert tc.post('/api/v1/servers/host', json=body, headers=X).status_code == 400, body


def test_no_metrics_is_an_empty_page(world):
    tc, cid, store = world
    assert post_servers(tc).json() == dict(range='24h', hosts=[], unusual=[], disk_full=[])


def test_a_collector_that_never_enrolled_is_left_out(world):
    tc, cid, store = world
    tc.post('/api/v1/admin/collectors', json=dict(name='web-02', platform='linux'), headers=X)
    seed_basic(store, cid)
    assert [h['collector'] for h in post_servers(tc).json()['hosts']] == ['web-01']


# Overview
def test_overview_has_current_values_disks_and_collector_status(world):
    tc, cid, store = world
    seed_basic(store, cid)
    out = post_servers(tc, '7d').json()
    assert out['range'] == '7d' and out['unusual'] == []
    (h,) = out['hosts']
    assert (h['cid'], h['collector'], h['platform'], h['status'], h['host'], h['os'], h['containers']) == (cid, 'web-01', 'linux', 'online', 'web-01', 'Ubuntu 24.04', 2)
    assert (h['cpu'], h['mem_used'], h['mem_total'], h['load1'], h['net_rx'], h['net_tx']) == (12.0, 2000.0 * MB, 8000.0 * MB, 0.5, 1000.0, 500.0)
    assert [(d['mount'], d['pct']) for d in h['disks']] == [('/', 50.0), ('/data', 95.0)] and h['last_seen'].endswith('Z')
    assert out['disk_full'] == [dict(cid=cid, collector='web-01', host='web-01', mount='/data', pct=95.0)]


def test_values_older_than_an_hour_are_not_current(world):
    tc, cid, store = world
    store.add(cid, series('web-01', '', 'cpu', ago(hours=3), 10, 50.0), {('web-01', ''): dict(os=None, image=None)}, ago(hours=3))
    (h,) = post_servers(tc).json()['hosts']
    assert h['cpu'] is None and h['mem_used'] is None and h['disks'] == []


def test_a_server_with_only_containers_is_listed(world):
    tc, cid, store = world
    store.add(cid, series('dock-1', 'redis', 'cpu', ago(minutes=5), 10, 3.0), {('dock-1', 'redis'): dict(os=None, image='redis:7'), ('dock-1', ''): dict(os=None, image=None)}, NOW)
    (h,) = post_servers(tc).json()['hosts']
    assert (h['host'], h['containers'], h['cpu']) == ('dock-1', 1, None)


def test_a_deleted_collector_takes_its_metrics_along(world):
    tc, cid, store = world
    seed_basic(store, cid)
    assert tc.post(f'/api/v1/admin/collectors/{cid}/revoke', headers=X).status_code == 200
    assert post_servers(tc).json()['hosts'][0]['status'] == 'revoked'
    assert tc.delete(f'/api/v1/admin/collectors/{cid}', headers=X).status_code == 200
    assert store.rows('SELECT count(*) FROM metric_point') == [(0,)] and store.rows('SELECT count(*) FROM metric_target') == [(0,)]


# Unusual values
def test_a_server_far_above_its_usual_hour_is_unusual_and_says_when_it_started(world):
    tc, cid, store = world
    seed_hours(store, cid, 'web-01', '', 'cpu', [10, 12, 8, 11, 9, 10, 10])
    seed_hours(store, cid, 'web-01', '', 'mem_used', [2000.0 * MB] * 7)
    seed_hours(store, cid, 'web-01', 'api', 'mem_used', [300.0 * MB] * 7)
    pts = (series('web-01', '', 'cpu', ago(hours=3), 360, lambda i: 10.0 if i < 240 else 80.0)                         # normal for two hours, then 80 %
           + series('web-01', '', 'mem_used', ago(hours=3), 360, 2050.0 * MB) + series('web-01', '', 'mem_total', ago(hours=3), 360, 8000.0 * MB)
           + series('web-01', 'api', 'mem_used', ago(hours=3), 360, lambda i: 300.0 * MB if i < 300 else 900.0 * MB) + series('web-01', 'api', 'mem_limit', ago(hours=3), 360, 1000.0 * MB))
    store.add(cid, pts, {('web-01', ''): dict(os=None, image=None), ('web-01', 'api'): dict(os=None, image='x')}, NOW)
    out = post_servers(tc).json()
    kinds = [(u['kind'], u['ctr'], u['name']) for u in out['unusual']]
    assert kinds == [('container', 'api', 'mem_used'), ('host', '', 'cpu')] or kinds == [('host', '', 'cpu'), ('container', 'api', 'mem_used')]
    assert [u['z'] for u in out['unusual']] == sorted((u['z'] for u in out['unusual']), reverse=True)           # worst first
    cpu = next(u for u in out['unusual'] if u['name'] == 'cpu')
    assert cpu['host'] == 'web-01' and cpu['collector'] == 'web-01' and cpu['z'] > 3 and cpu['current'] == 80.0
    assert 8 <= cpu['low'] < cpu['high'] <= 14 and cpu['started'] is not None
    started = datetime.datetime.strptime(cpu['started'], '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=UTC)
    assert abs((started - ago(hours=1)).total_seconds()) <= 600                                                      # the jump was an hour ago (the 5-minute bucket)
    mem = next(u for u in out['unusual'] if u['ctr'] == 'api')
    assert mem['current'] == 900.0 * MB and mem['started'] is not None
    assert not any(u['name'] == 'mem_used' and u['ctr'] == '' for u in out['unusual'])                              # +50 MB on 2 GB is normal


def test_fewer_than_five_earlier_days_give_no_verdict(world):
    tc, cid, store = world
    seed_hours(store, cid, 'web-01', '', 'cpu', [10, 12, 8, 11])
    store.add(cid, series('web-01', '', 'cpu', ago(minutes=20), 40, 90.0), {('web-01', ''): dict(os=None, image=None)}, NOW)
    assert post_servers(tc).json()['unusual'] == []


def test_a_day_with_too_few_points_does_not_count(world):
    tc, cid, store = world
    seed_hours(store, cid, 'web-01', '', 'cpu', [10, 12, 8, 11, 9, 10, 10])
    store.rows("UPDATE metric_hour SET n = 5 WHERE t IN (SELECT t FROM metric_hour ORDER BY t LIMIT 3) RETURNING 1")          # 3 days have a stub of an hour
    store.add(cid, series('web-01', '', 'cpu', ago(minutes=20), 40, 90.0), {('web-01', ''): dict(os=None, image=None)}, NOW)
    assert post_servers(tc).json()['unusual'] == []


def test_an_old_spike_that_is_over_is_not_reported(world):
    tc, cid, store = world
    seed_hours(store, cid, 'web-01', '', 'cpu', [10, 12, 8, 11, 9, 10, 10])
    pts = series('web-01', '', 'cpu', ago(hours=2), 240, lambda i: 90.0 if i < 100 else 10.0)
    store.add(cid, pts, {('web-01', ''): dict(os=None, image=None)}, NOW)
    assert post_servers(tc).json()['unusual'] == []


# One server
def test_host_detail_one_hour_is_the_raw_points(world):
    tc, cid, store = world
    seed_basic(store, cid)
    out = post_host(tc, cid, 'web-01', '1h').json()
    assert (out['cid'], out['collector'], out['platform'], out['status'], out['host'], out['os'], out['range'], out['bucket_seconds']) == (cid, 'web-01', 'linux', 'online', 'web-01', 'Ubuntu 24.04', '1h', None)
    s = out['series']
    assert len(s['cpu']) == 60 and s['cpu'][0][1] == 12.0 and s['cpu'][0][0].endswith('Z') and [p[0] for p in s['cpu']] == sorted(p[0] for p in s['cpu'])
    assert len(s['mem_used']) == 60 and len(s['mem_total']) == 60 and len(s['net_rx']) == 60 and len(s['net_tx']) == 60
    assert s['disk_mount'] == '/' and len(s['disk_used']) == 60 and s['disk_used'][0][1] == 50.0 and s['disk_total'][0][1] == 100.0
    assert [d['mount'] for d in out['disks']] == ['/', '/data'] and out['current']['cpu'] == 12.0


def test_host_detail_buckets_by_range(world):
    tc, cid, store = world
    start = (HOUR - datetime.timedelta(days=9))
    store.add(cid, series('web-01', '', 'cpu', start, 120 * 24 * 9 + 40, lambda i: float(i % 100)), {('web-01', ''): dict(os=None, image=None)}, NOW)
    store.rollup(NOW)
    sizes = {}
    for rng, step in (('24h', 1800), ('7d', 3 * 3600), ('30d', 12 * 3600)):
        out = post_host(tc, cid, 'web-01', rng).json()
        pts = out['series']['cpu']
        times = [datetime.datetime.strptime(t, '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=UTC).timestamp() for t, _ in pts]
        assert out['bucket_seconds'] == step and all(t % step == 0 for t in times) and len(set(times)) == len(times), rng
        assert all(0 <= v < 100 for _, v in pts)
        sizes[rng] = len(pts)
    assert 48 <= sizes['24h'] <= 49 and 56 <= sizes['7d'] <= 57 and 18 <= sizes['30d'] <= 19          # 7 d / 3 h = 56, 9 d of data / 12 h = 18


def test_seven_days_reads_hours_and_adds_the_hour_in_progress(world):
    tc, cid, store = world
    store.add(cid, series('web-01', '', 'cpu', HOUR - datetime.timedelta(hours=5), 120 * 5, 10.0) + series('web-01', '', 'cpu', HOUR, 4, 70.0),
              {('web-01', ''): dict(os=None, image=None)}, NOW)
    store.rollup(NOW)
    store.rows("DELETE FROM metric_point WHERE t < ? RETURNING 1", [(HOUR).replace(tzinfo=None)])           # only the hours remain for the finished part
    pts = dict(post_host(tc, cid, 'web-01', '7d').json()['series']['cpu'])
    size = 3 * 3600
    last = datetime.datetime.fromtimestamp(HOUR.timestamp() // size * size, UTC).strftime('%Y-%m-%dT%H:%M:%SZ')    # the 3-hour bucket of the current hour
    earlier = int((HOUR.timestamp() - HOUR.timestamp() // size * size) // 3600)                                    # finished hours in that bucket
    assert pts[last] == pytest.approx((earlier * 120 * 10.0 + 4 * 70.0) / (earlier * 120 + 4))                      # weighted by the points of each hour
    assert len(pts) >= 2


def test_containers_say_whether_they_have_log_lines_today(world):
    """`logs_today`: the container's name is a service with log lines in today's folder of the collector source (what the sidebar lists)."""
    from monishield.domain import timezone
    tc, cid, store = world
    seed_basic(store, cid)
    store.add(cid, series('web-01', 'api', 'mem_used', HOUR - datetime.timedelta(hours=3), 120 * 3, 400.0 * MB), {('web-01', 'api'): dict(os=None, image='repo/api:1')}, NOW)
    flags = lambda: {c['name']: c['logs_today'] for c in post_host(tc, cid, 'web-01', '24h').json()['containers']}   # noqa: E731
    assert flags() == {'api': False, 'old': False}                                  # nothing ingested for today yet
    con = tc.app.state.sources['collector'].con
    today = timezone.current().today(datetime.datetime.now(UTC))
    con.execute('INSERT INTO agg_service (folder, service, lines) VALUES (?, ?, ?), (?, ?, ?)', [today, 'api', 12, today, 'old', 0])
    assert flags() == {'api': True, 'old': False}                                   # a service with no lines does not count
    con.execute('DELETE FROM agg_service')
    con.execute('INSERT INTO agg_service (folder, service, lines) VALUES (?, ?, ?)', [today - datetime.timedelta(days=1), 'api', 12])
    assert flags() == {'api': False, 'old': False}                                  # yesterday's lines are not today's


def test_host_detail_containers(world):
    tc, cid, store = world
    seed_basic(store, cid)
    store.add(cid, series('web-01', 'api', 'mem_used', HOUR - datetime.timedelta(hours=3), 120 * 3, 400.0 * MB), {('web-01', 'api'): dict(os=None, image='repo/api:1')}, NOW)
    cs = post_host(tc, cid, 'web-01', '24h').json()['containers']
    assert [c['name'] for c in cs] == ['api', 'old']                      # running first
    api, old = cs
    assert (api['image'], api['running'], api['cpu'], api['mem_used'], api['mem_limit'], api['net_rx'], api['net_tx'], api['restarts']) == ('repo/api:1', True, 30.0, 300.0 * MB, 1000.0 * MB, 10.0, 20.0, 2.0)
    assert len(api['spark']) == 24 and any(v is not None for v in api['spark']) and api['last_seen'].endswith('Z')
    assert old['running'] is False and old['cpu'] is None and len(old['spark']) == 24
    # a container that was last seen two days ago is not on a 24 hour view, but is on a 7 day view
    store.rows("UPDATE metric_target SET last_seen = ? WHERE ctr = 'old' RETURNING 1", [(ago(days=2)).replace(tzinfo=None)])
    assert [c['name'] for c in post_host(tc, cid, 'web-01', '24h').json()['containers']] == ['api']
    assert [c['name'] for c in post_host(tc, cid, 'web-01', '7d').json()['containers']] == ['api', 'old']


def test_disk_chart_falls_back_to_the_first_mount_point(world):
    tc, cid, store = world
    store.add(cid, series('win-01', '', 'disk_used', ago(minutes=10), 5, 10.0, dim='D:\\') + series('win-01', '', 'disk_total', ago(minutes=10), 5, 20.0, dim='D:\\')
              + series('win-01', '', 'disk_used', ago(minutes=10), 5, 30.0, dim='C:\\') + series('win-01', '', 'disk_total', ago(minutes=10), 5, 40.0, dim='C:\\'),
              {('win-01', ''): dict(os=None, image=None)}, NOW)
    s = post_host(tc, cid, 'win-01', '1h').json()['series']
    assert s['disk_mount'] == 'C:\\' and s['disk_used'][0][1] == 30.0
    assert post_host(tc, cid, 'win-01').json()['series']['cpu'] == []
