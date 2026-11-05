"""Metrics store (infrastructure/metrics_store.py, docs/13-metrics.md): tables, inserts, targets."""
import datetime, os

import pytest

from monishield.infrastructure.metrics_store import MetricsStore

UTC = datetime.timezone.utc
T = datetime.datetime(2026, 11, 5, 10, 0, 30, tzinfo=UTC)


@pytest.fixture
def store(tmp_path):
    s = MetricsStore(str(tmp_path / 'sub' / 'metrics.duckdb'))
    yield s
    s.close()


def test_the_file_and_its_folder_are_made_on_first_use(store):
    assert not os.path.exists(store.path)
    assert store.rows('SELECT count(*) FROM metric_point') == [(0,)] and os.path.exists(store.path)
    assert {r[0] for r in store.rows('SHOW TABLES')} == {'metric_point', 'metric_hour', 'metric_target'}
    assert store.free_bytes() > 0


def test_points_are_stored_with_utc_times(store):
    local = datetime.timezone(datetime.timedelta(hours=7))
    store.add(3, [('h', '', 'cpu', '', T, 12.5), ('h', 'api', 'mem_used', '', T.astimezone(local), 100.0), ('h', '', 'disk_used', '/', T, 1.0)], {}, T)
    rows = store.rows('SELECT cid, host, ctr, name, dim, strftime(t, \'%Y-%m-%d %H:%M:%S\'), v FROM metric_point ORDER BY name')
    assert rows == [(3, 'h', '', 'cpu', '', '2026-11-05 10:00:30', 12.5), (3, 'h', '', 'disk_used', '/', '2026-11-05 10:00:30', 1.0),
                    (3, 'h', 'api', 'mem_used', '', '2026-11-05 10:00:30', 100.0)]


def test_targets_are_noted_and_updated_without_losing_what_is_known(store):
    store.add(1, [], {('h', ''): dict(os='Ubuntu', image=None), ('h', 'api'): dict(os=None, image='repo/api:1')}, T)
    later = T + datetime.timedelta(minutes=5)
    store.add(1, [], {('h', ''): dict(os=None, image=None), ('h', 'api'): dict(os=None, image='repo/api:2')}, later)
    rows = store.rows('SELECT host, ctr, os, image, first_seen, last_seen FROM metric_target ORDER BY ctr')
    assert rows[0][:4] == ('h', '', 'Ubuntu', None) and rows[1][:4] == ('h', 'api', None, 'repo/api:2')
    assert rows[0][4] == T.replace(tzinfo=None) and rows[0][5] == later.replace(tzinfo=None)
    store.add(2, [], {('h', ''): dict(os='Windows', image=None)}, T)          # another collector with the same host name is another target
    assert store.rows('SELECT count(*) FROM metric_target') == [(3,)]


def test_many_points_go_in_one_statement(store):
    pts = [('h', f'c{i % 20}', 'cpu', '', T + datetime.timedelta(seconds=30 * i), float(i)) for i in range(2000)]
    store.add(1, pts, {}, T)
    assert store.rows('SELECT count(*), max(v) FROM metric_point') == [(2000, 1999.0)]


def test_close_and_reopen_keeps_the_data(store):
    store.add(1, [('h', '', 'cpu', '', T, 1.0)], {}, T)
    store.close()
    assert store.rows('SELECT count(*) FROM metric_point') == [(1,)]


# Roll-up and retention
def points(host, name, start, count, value, every=30, dim='', ctr=''):
    return [(host, ctr, name, dim, start + datetime.timedelta(seconds=every * i), value(i) if callable(value) else value) for i in range(count)]


def hours(store, where=''):
    return store.rows(f"SELECT cid, host, ctr, name, dim, strftime(t, '%H:%M'), avg, max, n FROM metric_hour {where} ORDER BY cid, host, ctr, name, dim, t")


def test_finished_hours_are_rolled_up_and_the_hour_in_progress_is_not(store):
    start = datetime.datetime(2026, 11, 5, 8, 0, 0, tzinfo=UTC)
    store.add(1, points('h', 'cpu', start, 240, lambda i: float(i)), {}, start)            # 08:00 to 09:59:30
    store.add(1, points('h', 'cpu', start + datetime.timedelta(hours=2), 10, 100.0), {}, start)       # 10:00 to 10:04:30
    assert store.rollup(start + datetime.timedelta(hours=2, minutes=5)) == 2
    assert hours(store) == [(1, 'h', '', 'cpu', '', '08:00', pytest.approx(59.5), 119.0, 120), (1, 'h', '', 'cpu', '', '09:00', pytest.approx(179.5), 239.0, 120)]


def test_roll_up_is_idempotent_and_counts_late_points(store):
    start = datetime.datetime(2026, 11, 5, 8, 0, 0, tzinfo=UTC)
    now = start + datetime.timedelta(hours=3)
    store.add(1, points('h', 'cpu', start, 120, 10.0), {}, start)
    assert store.rollup(now) == 1 and store.rollup(now) == 1 and store.rollup(now) == 1
    assert hours(store) == [(1, 'h', '', 'cpu', '', '08:00', 10.0, 10.0, 120)]
    store.add(1, points('h', 'cpu', start + datetime.timedelta(minutes=30), 60, 40.0, every=30)[:20], {}, start)         # points that arrived late
    store.rollup(now)
    (row,) = hours(store)
    assert row[8] == 140 and row[6] == pytest.approx((120 * 10 + 20 * 40) / 140) and row[7] == 40.0
    store.add(1, points('h', 'cpu', start + datetime.timedelta(hours=1), 120, 20.0), {}, start)           # the next hour joins
    store.rollup(now)
    assert [r[5] for r in hours(store)] == ['08:00', '09:00']


def test_series_are_kept_apart_in_the_hours(store):
    start = datetime.datetime(2026, 11, 5, 8, 0, 0, tzinfo=UTC)
    pts = points('h', 'cpu', start, 4, 1.0) + points('h', 'disk_used', start, 4, 5.0, dim='/') + points('h', 'disk_used', start, 4, 7.0, dim='/data') + points('h', 'cpu', start, 4, 9.0, ctr='api')
    store.add(1, pts, {}, start)
    store.add(2, points('h', 'cpu', start, 4, 3.0), {}, start)
    assert store.rollup(start + datetime.timedelta(hours=2)) == 5
    assert [(r[0], r[2], r[3], r[4], r[6]) for r in hours(store)] == [(1, '', 'cpu', '', 1.0), (1, '', 'disk_used', '/', 5.0), (1, '', 'disk_used', '/data', 7.0), (1, 'api', 'cpu', '', 9.0), (2, '', 'cpu', '', 3.0)]


def test_nothing_to_roll_up(store):
    assert store.rollup(T) == 0
    store.add(1, points('h', 'cpu', T, 3, 1.0), {}, T)
    assert store.rollup(T + datetime.timedelta(minutes=10)) == 0 and hours(store) == []            # still the same hour


def test_prune_deletes_by_age_after_roll_up(store):
    now = datetime.datetime(2026, 11, 20, 12, 5, tzinfo=UTC)
    old, mid, new = now - datetime.timedelta(days=8), now - datetime.timedelta(days=3), now - datetime.timedelta(minutes=30)
    store.add(1, points('h', 'cpu', old, 120, 1.0) + points('h', 'cpu', mid, 120, 2.0) + points('h', 'cpu', new, 10, 3.0), {('h', ''): dict(os='x', image=None)}, old)
    store.add(1, [], {('gone', ''): dict(os='x', image=None)}, now - datetime.timedelta(days=100))
    store.rollup(now)
    assert store.prune(now, 7, 90) == (120, 0, 1)
    assert sorted({str(t.date()) for (t,) in store.rows('SELECT t FROM metric_point')}) == ['2026-11-17', '2026-11-20']
    assert len(hours(store)) >= 2 and store.rows('SELECT host FROM metric_target') == [('h',)]       # the old hours are kept: 90 days
    assert store.prune(now, 7, 90) == (0, 0, 0)
    assert store.prune(now + datetime.timedelta(days=95), 7, 90)[1] >= 2                              # and go when they are 90 days old
    assert store.rows('SELECT count(*) FROM metric_hour') == [(0,)]


def test_a_point_is_never_deleted_before_it_is_in_its_hour(store):
    now = datetime.datetime(2026, 11, 20, 12, 5, tzinfo=UTC)
    old = now - datetime.timedelta(days=9)
    store.add(1, points('h', 'cpu', old, 10, 5.0), {}, old)
    store.rollup(now); store.prune(now, 7, 90)
    assert store.rows('SELECT count(*) FROM metric_point') == [(0,)] and len(hours(store)) == 1 and hours(store)[0][6] == 5.0


def test_forget_removes_a_collector_everywhere(store):
    store.add(1, points('h', 'cpu', T, 3, 1.0), {('h', ''): dict(os=None, image=None)}, T)
    store.add(2, points('h', 'cpu', T, 3, 1.0), {('h', ''): dict(os=None, image=None)}, T)
    store.rollup(T + datetime.timedelta(hours=2))
    store.forget(1)
    for table in ('metric_point', 'metric_hour', 'metric_target'):
        assert {c for (c,) in store.rows(f'SELECT DISTINCT cid FROM {table}')} == {2}, table


def test_the_service_runs_a_round_and_a_thread_that_stops(store):
    import types
    from monishield.application.metrics_service import MetricsService
    ctx = types.SimpleNamespace(metrics=store, cfg=types.SimpleNamespace(metrics_raw_days=7, metrics_hour_days=90))
    old = datetime.datetime.now(UTC) - datetime.timedelta(days=2)
    store.add(1, points('h', 'cpu', old, 120, 4.0), {}, old)
    svc = MetricsService(ctx)
    out = svc.run()
    assert out['hours'] >= 1 and out['deleted'] == (0, 0, 0) and svc.last is out
    svc.start(every=1, first=0)
    assert svc.running()
    svc.stop(5)
    assert not svc.running()
