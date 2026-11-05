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
