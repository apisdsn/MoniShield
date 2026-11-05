"""OTLP/HTTP JSON metrics (domain/otlp_metrics.py, docs/13-metrics.md).

tests/fixtures/otlp_metrics_hostmetrics*.json are two real requests of otelcol-contrib 0.163.2 (the generated Linux configuration,
host metrics on, scrapes 30 s apart) as they reached the receiver.
tests/fixtures/otlp_metrics_docker_stats.json is the output of the real `docker_stats` receiver of 0.163.2 through the generated Docker
configuration, but fed by a stand-in for the Docker Engine API (no Docker runs in the build sandbox): the container name, image, restart
count and the numbers are made up; the metric names, units, attributes and the resource are what the receiver wrote."""
import copy, datetime, json, os

import pytest

from monishield.domain import otlp_metrics as om

FIX = os.path.join(os.path.dirname(__file__), 'fixtures')
UTC = datetime.timezone.utc
T2 = datetime.datetime.fromtimestamp(1793880383, UTC)                  # the second host scrape, to the second
NOW = T2 + datetime.timedelta(seconds=20)


def fixture(name):
    with open(os.path.join(FIX, f'otlp_metrics_{name}.json'), encoding='utf-8') as fh: return json.load(fh)


def parse(payload, now=NOW, max_age=None, collector='c1'): return om.parse_metrics(payload, collector, now, max_age)


def by(points, ctr='', host=None):
    out = {}
    for h, c, name, dim, t, v in points:
        if c == ctr and (host is None or h == host): out.setdefault((name, dim), []).append((t, v))
    return out


def attr(k, v): return {'key': k, 'value': {'stringValue': v}}


def request(metrics, resource=(('host.name', 'web-01'),)):
    return {'resourceMetrics': [{'resource': {'attributes': [attr(k, v) for k, v in resource]}, 'scopeMetrics': [{'metrics': metrics}]}]}


def gauge(name, v, t='1793880383000000000', attrs=(), key='asDouble'):
    return {'name': name, 'gauge': {'dataPoints': [{'attributes': [attr(k, x) for k, x in attrs], 'timeUnixNano': t, key: v}]}}


def total(name, points, temporality=2, start='1793877559000000000'):
    """points = [(value, time ns, attrs)]"""
    return {'name': name, 'sum': {'aggregationTemporality': temporality, 'isMonotonic': True, 'dataPoints': [
        {'attributes': [attr(k, x) for k, x in a], 'startTimeUnixNano': start, 'timeUnixNano': t, 'asInt': str(v)} for v, t, a in points]}}


# Real requests
def test_host_scrape_of_the_real_collector():
    points, counters, targets, rejected, ignored = parse(fixture('hostmetrics'))
    assert rejected == {} and ignored == 0
    host = by(points)
    assert set(host) == {('cpu', ''), ('mem_used', ''), ('mem_total', ''), ('load1', ''), ('disk_used', '/'), ('disk_total', '/'),
                         ('disk_used', '/opt/claude-code'), ('disk_total', '/opt/claude-code'), ('disk_used', '/opt/env-runner'), ('disk_total', '/opt/env-runner')}
    assert all(h == 'vm' for h, *_ in points) and all(t == T2 for _, _, _, _, t, _ in points)
    cpu = host[('cpu', '')][0][1]
    assert 0 <= cpu < 5 and cpu == pytest.approx(100 * (1 - 0.9966664720277629))      # 100 x (1 - idle share), one value per scrape
    assert host[('mem_used', '')][0][1] == 734887936 and host[('mem_total', '')][0][1] == 16867418112     # the limit metric
    assert host[('load1', '')][0][1] == 0.16
    assert host[('disk_used', '/')][0][1] == 24628260864 and host[('disk_total', '/')][0][1] == 24628260864 + 17195597824   # used + free, like df: not the reserved blocks
    assert 0.55 < host[('disk_used', '/')][0][1] / host[('disk_total', '/')][0][1] < 0.6
    assert targets == {('vm', ''): dict(os='Ubuntu 24.04.5 LTS (Noble Numbat) (Linux vm 6.18.44-fc-v236 #1 SMP PREEMPT_DYNAMIC @0 x86_64)', image=None)}
    assert {(c['name'], c['dim']) for c in counters} == {(n, d) for n in ('net_rx', 'net_tx') for d in ('ifb0', 'ifb1', 'eth0')}


def test_network_rate_from_two_real_scrapes():
    rates = om.Rates()
    first = parse(fixture('hostmetrics_first'), now=T2)
    assert om.rate_points(first[1], rates, scope=7) == []                              # the first sample has no rate
    second = parse(fixture('hostmetrics'))
    got = by(om.rate_points(second[1], rates, scope=7))
    assert set(got) == {('net_rx', ''), ('net_tx', '')}
    (t, rx), = got[('net_rx', '')]
    assert t == T2 and 0 <= rx < 50_000_000                                            # bytes per second, summed over the devices
    # the same request again (a retry whose answer was lost) gives nothing new
    assert om.rate_points(second[1], rates, scope=7) == []
    # another collector has its own series
    assert om.rate_points(second[1], rates, scope=8) == []


def test_container_scrape_from_the_docker_stats_receiver():
    points, counters, targets, rejected, ignored = parse(fixture('docker_stats'), now=datetime.datetime.fromtimestamp(1793880498 + 5, UTC))
    assert rejected == {} and ignored == 0
    ctr = by(points, 'web-1')
    assert {k: v[0][1] for k, v in ctr.items()} == {('cpu', ''): pytest.approx(2.8), ('mem_used', ''): 260_000_000, ('mem_limit', ''): 2_000_000_000, ('restarts', ''): 3}
    assert targets[('vm', 'web-1')] == dict(os=None, image='nginx:1.27') and ('vm', '') in targets
    assert {(c['ctr'], c['name'], c['dim']) for c in counters if c['ctr']} == {('web-1', 'net_rx', 'eth0'), ('web-1', 'net_tx', 'eth0')}
    assert ('cpu', '') in by(points, '') and ('mem_total', '') in by(points, '')      # the host's own values arrive in the same request


# What is ignored, what is rejected
def test_other_metrics_are_ignored_not_rejected():
    hist = {'name': 'system.cpu.utilization', 'histogram': {'dataPoints': []}}
    p = request([gauge('process.cpu.time', 1), gauge('system.disk.io', 3), hist, gauge('container.cpu.utilization', 1.0)])      # a container metric on a server
    points, counters, targets, rejected, ignored = parse(p)
    assert (points, counters, rejected, ignored) == ([], [], {}, 4)


def test_secrets_and_ids_are_not_kept():
    res = (('host.name', 'web-01'), ('container.name', 'api'), ('container.id', 'f' * 64), ('container.hostname', 'x'), ('host.ip', '10.9.8.7'),
           ('process.command_line', 'secret --token=1'), ('container.image.name', 'repo/api:1'))
    points, counters, targets, rejected, ignored = parse(request([gauge('container.cpu.utilization', 5.0)], res))
    assert points == [('web-1' if False else 'web-01', 'api', 'cpu', '', T2, 5.0)]
    assert targets[('web-01', 'api')] == dict(os=None, image='repo/api:1')
    assert '10.9.8.7' not in repr((points, targets)) and 'secret' not in repr((points, targets)) and 'f' * 64 not in repr((points, targets))


@pytest.mark.parametrize('metric,reason', [
    ({'name': 'system.cpu.load_average.1m', 'gauge': {'dataPoints': [{'timeUnixNano': '1793880383000000000'}]}}, 'malformed point'),                 # no value
    (gauge('system.cpu.load_average.1m', 'abc'), 'malformed point'),
    (gauge('system.cpu.load_average.1m', 'NaN'), 'malformed point'),
    (gauge('system.cpu.load_average.1m', float('inf')), 'malformed point'),
    (gauge('system.cpu.load_average.1m', True), 'malformed point'),
    (gauge('system.cpu.load_average.1m', 'x', key='asInt'), 'malformed point'),
    (gauge('system.cpu.load_average.1m', 1.0, t='abc'), 'invalid time'),
    (gauge('system.cpu.load_average.1m', 1.0, t='0'), 'invalid time'),
    (gauge('system.cpu.load_average.1m', 1.0, t='-5'), 'invalid time'),
    (gauge('system.cpu.load_average.1m', 1.0, t='9' * 30), 'invalid time'),
    ({'name': 'system.cpu.load_average.1m', 'gauge': {'dataPoints': ['x']}}, 'malformed point'),
    ({'name': 'system.cpu.load_average.1m', 'gauge': {'dataPoints': [{'attributes': 'x', 'timeUnixNano': '1793880383000000000', 'asDouble': 1}]}}, 'malformed attributes'),
    ({'name': 'system.cpu.load_average.1m', 'gauge': {'dataPoints': 'x'}}, 'malformed request'),
    ({'name': 'system.network.io', 'sum': {'aggregationTemporality': 9, 'dataPoints': []}}, 'malformed request'),
    (total('system.network.io', [(5, '1793880383000000000', [('direction', 'sideways')])]), 'malformed point'),
])
def test_broken_points_are_rejected_with_a_reason(metric, reason):
    points, counters, targets, rejected, ignored = parse(request([metric]))
    assert rejected == {reason: 1} and points == [] and counters == []


def test_a_broken_point_does_not_take_the_good_ones_with_it():
    p = request([gauge('system.cpu.load_average.1m', 'abc'), gauge('system.cpu.load_average.1m', 0.5)])
    points, _, _, rejected, _ = parse(p)
    assert rejected == {'malformed point': 1} and [v for *_, v in points] == [0.5]
    assert om.partial_success(rejected) == {'partialSuccess': {'rejectedDataPoints': '1', 'errorMessage': '1 data points rejected: malformed point (1)'}}
    assert om.partial_success({}) == {}


def test_too_old_uses_the_same_limit_as_the_logs():
    old = gauge('system.cpu.load_average.1m', 1.0, t='1793700000000000000')       # about two days before NOW
    assert parse(request([old]))[3] == {}
    points, _, _, rejected, _ = parse(request([old]), max_age=datetime.timedelta(hours=24))
    assert points == [] and rejected == {'too old': 1}


def test_a_time_in_the_future_becomes_the_receive_time():
    points, *_ = parse(request([gauge('system.cpu.load_average.1m', 1.0, t='1893880383000000000')]))
    assert points[0][4] == NOW.replace(microsecond=0)


@pytest.mark.parametrize('payload', [[], 'x', {'resourceMetrics': 'x'}, {'resourceMetrics': ['x']}, {'resourceMetrics': [{'resource': 'x'}]},
                                     {'resourceMetrics': [{'scopeMetrics': 'x'}]}, {'resourceMetrics': [{'scopeMetrics': ['x']}]},
                                     {'resourceMetrics': [{'scopeMetrics': [{'metrics': 'x'}]}]}, {'resourceMetrics': [{'scopeMetrics': [{'metrics': ['x']}]}]},
                                     {'resourceMetrics': [{'resource': {'attributes': [{'key': 1}]}}]}])
def test_a_malformed_request_is_counted_never_raised(payload):
    points, _, _, rejected, _ = parse(payload)
    assert points == [] and sum(rejected.values()) >= 1 and set(rejected) <= {'malformed request', 'malformed attributes'}


def test_empty_request_is_fine():
    assert parse({}) == ([], [], {}, {}, 0) and parse({'resourceMetrics': []}) == ([], [], {}, {}, 0)


def test_a_bad_host_name_rejects_its_points():
    p = request([gauge('system.cpu.load_average.1m', 1.0)], (('host.name', 'bad\nname'),))
    p['resourceMetrics'][0]['resource']['attributes'].append(attr('k8s.node.name', 'x' * 300))
    points, _, _, rejected, _ = parse(p, collector='')
    assert points == [] and rejected == {'invalid name': 1}


def test_too_many_points_in_one_request_are_cut(monkeypatch):
    monkeypatch.setattr(om, 'MAX_POINTS', 5)
    p = request([gauge('system.cpu.load_average.1m', float(i)) for i in range(8)])
    points, _, _, rejected, _ = parse(p)
    assert len(points) == 5 and rejected == {'too many points': 3}


# Names and joins
def test_host_name_rules():
    one = lambda res, collector='c1': parse(request([gauge('system.cpu.load_average.1m', 1.0)], res), collector=collector)[0][0][0]
    assert one((('host.name', 'web-01'),)) == 'web-01'
    assert one((('host.name', 'pod-abc'), ('k8s.node.name', 'node-1'))) == 'node-1'      # the pod's own name is not the server
    assert one(()) == 'c1'                                                               # no name at all: the collector's
    assert one((('host.name', 'My Server'),)) == 'My-Server'                             # like the log host name


def test_cpu_is_one_minus_the_mean_idle_share_also_without_the_metric_transform():
    def cpu(per):
        m = {'name': 'system.cpu.utilization', 'gauge': {'dataPoints': [
            {'attributes': [attr('cpu', f'cpu{i}'), attr('state', 'idle')], 'timeUnixNano': '1793880383000000000', 'asDouble': v} for i, v in enumerate(per)] +
            [{'attributes': [attr('cpu', 'cpu0'), attr('state', 'user')], 'timeUnixNano': '1793880383000000000', 'asDouble': 0.5}]}}
        return by(parse(request([m]))[0])[('cpu', '')][0][1]
    assert cpu([0.9, 0.7]) == pytest.approx(20.0) and cpu([1.0]) == 0.0 and cpu([0.0]) == 100.0


def test_total_memory_is_the_limit_or_the_sum_of_the_states_but_inactive():
    states = [('used', 400), ('free', 300), ('cached', 200), ('inactive', 9999)]
    usage = total('system.memory.usage', [(v, '1793880383000000000', [('state', s)]) for s, v in states])
    got = by(parse(request([usage]))[0])
    assert got[('mem_used', '')][0][1] == 400 and got[('mem_total', '')][0][1] == 900
    limit = {'name': 'system.memory.limit', 'sum': {'aggregationTemporality': 2, 'dataPoints': [{'timeUnixNano': '1793880383000000000', 'asInt': '1000'}]}}
    assert by(parse(request([usage, limit]))[0])[('mem_total', '')][0][1] == 1000
    assert by(parse(request([limit]))[0])[('mem_total', '')][0][1] == 1000 and ('mem_used', '') not in by(parse(request([limit]))[0])


def test_at_most_ten_mount_points_and_the_root_first():
    mounts = ['/z'] + [f'/m{i}' for i in range(14)] + ['/']
    pts = [(1000, '1793880383000000000', [('mountpoint', m), ('state', s)]) for m in mounts for s in ('used', 'free', 'reserved')]
    pts = [(10 if a[1][1] == 'used' else 90, t, a) for _, t, a in pts]
    got = by(parse(request([total('system.filesystem.usage', pts)]))[0])
    dims = sorted({d for (n, d) in got if n == 'disk_used'})
    assert len(dims) == 10 and '/' in dims and '/z' not in dims and got[('disk_total', '/')][0][1] == 100
    # a mount point with only one of the states is skipped
    only = total('system.filesystem.usage', [(10, '1793880383000000000', [('mountpoint', '/x'), ('state', 'used')])])
    assert by(parse(request([only]))[0]) == {}


def test_windows_style_mount_points_and_load():
    pts = [(5, '1793880383000000000', [('mountpoint', 'C:\\'), ('state', 'used')]), (5, '1793880383000000000', [('mountpoint', 'C:\\'), ('state', 'free')])]
    assert by(parse(request([total('system.filesystem.usage', pts)]))[0])[('disk_total', 'C:\\')][0][1] == 10


# Rates
def counter_request(v, t_ns, devices=('eth0',), start='1793877559000000000', temporality=2):
    pts = [(v, t_ns, [('device', d), ('direction', dr)]) for d in devices for dr in ('receive', 'transmit')]
    return request([total('system.network.io', pts, temporality, start)])


def rate(rates, req, now=NOW + datetime.timedelta(hours=1)):
    pts = om.rate_points(parse(req, now=now)[1], rates, 1)
    return {n: v for _, _, n, _, _, v in pts}


def test_rates_need_a_previous_sample_and_follow_resets_and_gaps():
    r, ns = om.Rates(), 10 ** 9
    base = 1793880000
    assert rate(r, counter_request(1000, f'{base * ns}')) == {}                                                       # first sample
    assert rate(r, counter_request(4000, f'{(base + 30) * ns}')) == {'net_rx': 100.0, 'net_tx': 100.0}                # 3000 bytes / 30 s
    assert rate(r, counter_request(100, f'{(base + 60) * ns}')) == {}                                                 # value went down: reset
    assert rate(r, counter_request(400, f'{(base + 90) * ns}')) == {'net_rx': 10.0, 'net_tx': 10.0}                   # rebased on the reset sample
    assert rate(r, counter_request(500, f'{(base + 120) * ns}', start=f'{(base + 100) * ns}')) == {}                  # the start time changed: restart
    assert rate(r, counter_request(900, f'{(base + 150) * ns}', start=f'{(base + 100) * ns}')) == {'net_rx': pytest.approx(400 / 30), 'net_tx': pytest.approx(400 / 30)}
    assert rate(r, counter_request(2000, f'{(base + 150 + 301) * ns}', start=f'{(base + 100) * ns}')) == {}           # a gap over five minutes
    assert rate(r, counter_request(2300, f'{(base + 150 + 331) * ns}', start=f'{(base + 100) * ns}')) == {'net_rx': 10.0, 'net_tx': 10.0}
    assert rate(r, counter_request(2300, f'{(base + 150 + 300) * ns}', start=f'{(base + 100) * ns}')) == {}           # an older sample is not used


def test_rates_are_summed_over_devices_and_a_new_device_does_not_spike():
    r, ns, base = om.Rates(), 10 ** 9, 1793880000
    rate(r, counter_request(1000, f'{base * ns}', ('eth0', 'eth1')))
    assert rate(r, counter_request(2000, f'{(base + 10) * ns}', ('eth0', 'eth1'))) == {'net_rx': 200.0, 'net_tx': 200.0}
    got = rate(r, counter_request(3000, f'{(base + 20) * ns}', ('eth0', 'eth1', 'eth2')))      # eth2 appears with a big counter: no rate for it
    assert got == {'net_rx': 200.0, 'net_tx': 200.0}
    assert rate(r, counter_request(4000, f'{(base + 30) * ns}', ('eth0', 'eth2'))) == {'net_rx': 200.0, 'net_tx': 200.0}          # eth1 is gone


def test_a_delta_counter_is_a_rate_over_its_own_interval():
    r, ns, base = om.Rates(), 10 ** 9, 1793880000
    got = rate(r, counter_request(600, f'{(base + 30) * ns}', start=f'{base * ns}', temporality=1))
    assert got == {'net_rx': 20.0, 'net_tx': 20.0}
    assert rate(r, counter_request(600, f'{(base + 30) * ns}', start=f'{(base - 1000) * ns}', temporality=1)) == {}          # longer than the gap limit
    assert rate(r, counter_request(600, f'{(base + 30) * ns}', start='0', temporality=1)) == {}


def test_container_rates_are_per_container_and_do_not_mix_with_the_host():
    def req(v, t, name):
        return request([total('container.network.io.usage.rx_bytes', [(v, t, [('interface', 'eth0')])])], (('host.name', 'h'), ('container.name', name)))
    r, ns, base = om.Rates(), 10 ** 9, 1793880000
    for name in ('a', 'b'): om.rate_points(parse(req(100, f'{base * ns}', name))[1], r, 1)
    pa = om.rate_points(parse(req(400, f'{(base + 30) * ns}', 'a'))[1], r, 1)
    pb = om.rate_points(parse(req(700, f'{(base + 30) * ns}', 'b'))[1], r, 1)
    assert [(c, n, v) for _, c, n, _, _, v in pa] == [('a', 'net_rx', 10.0)] and [(c, n, v) for _, c, n, _, _, v in pb] == [('b', 'net_rx', 20.0)]


def test_old_series_are_forgotten():
    r = om.Rates()
    r.update(('k',), None, T2 - datetime.timedelta(hours=3), 1)
    r.update(('new',), None, T2, 1)
    r.prune(T2)
    assert list(r.last) == [('new',)]
