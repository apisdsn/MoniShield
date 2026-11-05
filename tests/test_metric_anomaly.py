"""Unusual values (domain/metric_anomaly.py): enough and too few days, the floors, the band, when it started, disks."""
import datetime, statistics

import pytest

from monishield.domain import metric_anomaly as ma

MB = 1024 * 1024


def test_a_value_far_above_the_usual_is_unusual():
    v = ma.verdict('cpu', 40.0, [10, 12, 8, 11, 9, 10, 10])
    assert v['unusual'] and v['z'] >= 3
    assert v['mean'] == pytest.approx(10.0) and v['std'] == pytest.approx(statistics.stdev([10, 12, 8, 11, 9, 10, 10]))
    assert v['low'] == pytest.approx(10 - v['spread']) and v['high'] == pytest.approx(10 + v['spread'])
    assert v['limit'] == pytest.approx(10 + 3 * v['spread'])


def test_only_higher_than_usual_counts():
    v = ma.verdict('cpu', 0.0, [50, 55, 45, 52, 48, 50, 51])
    assert v['z'] < -3 and v['unusual'] is False
    assert ma.verdict('cpu', 10.0, [10, 12, 8, 11, 9])['unusual'] is False


def test_five_days_are_needed_and_a_missing_value_gives_no_verdict():
    base = [10, 12, 8, 11, 9, 10, 10]
    assert ma.verdict('cpu', 99.0, base[:4]) is None and ma.verdict('cpu', 99.0, []) is None
    assert ma.verdict('cpu', 99.0, base[:5]) is not None and ma.verdict('cpu', 99.0, base[:6]) is not None
    assert ma.verdict('cpu', None, base) is None


def test_a_very_steady_server_needs_a_real_jump_cpu_floor():
    steady = [5.0] * 7                                           # std 0: the floor of 2 points decides
    assert ma.verdict('cpu', 9.0, steady)['unusual'] is False and ma.verdict('cpu', 9.0, steady)['z'] == pytest.approx(2.0)
    assert ma.verdict('cpu', 11.0, steady)['unusual'] is True and ma.verdict('cpu', 11.0, steady)['z'] == pytest.approx(3.0)


def test_memory_floor_is_two_percent_of_the_total_but_at_least_50_mb():
    steady = [1000.0 * MB] * 7
    assert ma.floor('mem_used', 16000 * MB) == pytest.approx(320 * MB) and ma.floor('mem_used', 1000 * MB) == 50 * MB and ma.floor('mem_used', None) == 50 * MB
    assert ma.verdict('mem_used', 1000 * MB + 200 * MB, steady, 16000 * MB)['unusual'] is False       # +200 MB on a 16 GB server: normal wobble
    assert ma.verdict('mem_used', 1000 * MB + 1000 * MB, steady, 16000 * MB)['unusual'] is True
    assert ma.verdict('mem_used', 1000 * MB + 200 * MB, steady, 1000 * MB)['unusual'] is True         # the same on a 1 GB limit: 50 MB floor


def test_the_band_does_not_go_below_zero():
    assert ma.verdict('cpu', 1.0, [0.5, 0.0, 0.2, 0.1, 0.3])['low'] == 0.0


def test_started_is_the_first_bucket_after_which_everything_stayed_above():
    t = lambda m: datetime.datetime(2026, 11, 5, 10, 0) + datetime.timedelta(minutes=m)           # noqa: E731
    seq = [10, 10, 80, 12, 90, 95, 99, 97]
    assert ma.started([(t(5 * i), v) for i, v in enumerate(seq)], 50) == t(20)                    # the jump at 10 minutes went back down: not the start
    assert ma.started([(t(5 * i), v) for i, v in enumerate([10, 10, 80, 12, 90, 95, 99, 20])], 50) is None      # already back to normal
    assert ma.started([(t(5 * i), v) for i, v in enumerate([90, 91, 92])], 50) == t(0)
    assert ma.started([(t(0), None), (t(5), 90), (t(10), None), (t(15), 90)], 50) == t(15)       # an empty bucket breaks the run
    assert ma.started([], 50) is None


def test_disks_are_almost_full_at_ninety_percent():
    assert ma.percent(90, 100) == 90.0 and ma.percent(1, 0) is None and ma.percent(None, 5) is None
    assert ma.almost_full(90, 100) and ma.almost_full(99.9, 100) and not ma.almost_full(89.9, 100) and not ma.almost_full(5, 0)
