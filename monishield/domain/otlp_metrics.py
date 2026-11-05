"""OTLP/HTTP JSON metrics request (OpenTelemetry Collector `otlphttp`, encoding json) -> server and container points.

    {"resourceMetrics": [{"resource": {"attributes": [...]}, "scopeMetrics": [{"metrics": [
        {"name": "system.memory.usage", "sum": {"dataPoints": [{"attributes": [...], "timeUnixNano": "…", "asInt": "…"}]}}]}]}]}

Only the metrics MoniShield shows are read (the `hostmetrics` and `docker_stats` receivers, docs/13-metrics.md); any other
metric name, and histograms, summaries and exponential histograms, are ignored and only counted. A point that is broken is a
rejected point with a reason, never an exception. Nothing but the host name, the operating system, the container name and its
image name is kept from the resource: no IP address, no process or command line, no container id.

The output is a list of points `(host, ctr, name, dim, t, v)`; `ctr` is '' for the server itself, `dim` is a mount point for the
disk values and '' otherwise.

    host:       cpu (%, 100 x (1 - idle share)), mem_used, mem_total (bytes), disk_used, disk_total (bytes, dim = mount point),
                net_rx, net_tx (bytes per second), load1
    container:  cpu (% as Docker reports it, can pass 100 with several cores), mem_used, mem_limit (bytes), net_rx, net_tx
                (bytes per second), restarts (count)

Network values arrive as counters. `Rates` turns them into bytes per second from the previous sample of the same series, which
the caller keeps in memory (no rate for the first sample, after a counter reset or after a gap of more than 5 minutes).
Pure: standard library and monishield.domain only."""
import datetime, math, re

from monishield.domain import kafka_message
from monishield.domain.otlp_logs import EPOCH, FUTURE, Bad, _int, pairs

MAX_POINTS = 20000          # data points per request; a collector sends some tens to a few hundred
MAX_MOUNTS = 10             # file systems kept per server; '/' first
MAX_TEXT = 200
GAP = datetime.timedelta(minutes=5)       # between two samples of a counter; a longer gap gives no rate
AGGREGATION = {0: 'cumulative', 1: 'delta', 2: 'cumulative', 'AGGREGATION_TEMPORALITY_UNSPECIFIED': 'cumulative',
               'AGGREGATION_TEMPORALITY_DELTA': 'delta', 'AGGREGATION_TEMPORALITY_CUMULATIVE': 'cumulative'}

# metric name -> what it feeds
HOST_GAUGES = {'system.cpu.utilization', 'system.cpu.load_average.1m'}
HOST_SUMS = {'system.memory.usage', 'system.memory.limit', 'system.filesystem.usage', 'system.network.io'}
CONTAINER_GAUGES = {'container.cpu.utilization'}
CONTAINER_SUMS = {'container.memory.usage.total', 'container.memory.usage.limit', 'container.restarts',
                  'container.network.io.usage.rx_bytes', 'container.network.io.usage.tx_bytes'}
USED = {*HOST_GAUGES, *HOST_SUMS, *CONTAINER_GAUGES, *CONTAINER_SUMS}
COUNTERS = {'system.network.io', 'container.network.io.usage.rx_bytes', 'container.network.io.usage.tx_bytes'}
DIRECTION = {'receive': 'net_rx', 'transmit': 'net_tx'}


# Values
def _number(dp):
    """The point's value as a float; Bad when it is missing or not a finite number."""
    if 'asDouble' in dp:
        v = dp['asDouble']
        if isinstance(v, str) and re.fullmatch(r'-?\d+(\.\d+)?([eE][-+]?\d+)?', v): v = float(v)      # a double can travel as text
        if isinstance(v, bool) or not isinstance(v, (int, float)): raise Bad('malformed point')
        v = float(v)
    elif 'asInt' in dp:
        try: v = float(_int(dp['asInt']))
        except Bad: raise Bad('malformed point') from None
    else: raise Bad('malformed point')
    if not math.isfinite(v): raise Bad('malformed point')
    return v


def _time(v, now, max_age, required=True):
    """timeUnixNano (a JSON string) -> aware UTC time, whole seconds; a time further ahead than FUTURE becomes `now`."""
    try: n = _int(v) if v is not None else 0
    except Bad: raise Bad('invalid time') from None
    if n < 0 or (required and n == 0): raise Bad('invalid time')
    if not n: return None
    try: t = EPOCH + datetime.timedelta(microseconds=n // 1000)
    except OverflowError: raise Bad('invalid time') from None
    t = now if t > now + FUTURE else t
    if max_age and t < now - max_age: raise Bad('too old')
    return t.replace(microsecond=0)


def _text(v):
    v = v.strip() if isinstance(v, str) else ''
    return v if v and len(v) <= MAX_TEXT and not any(ord(c) < 32 or ord(c) == 127 for c in v) else None


def _name(v):
    """A host or container name as the logs name it (Raw Logs filters by it): spaces and slashes become hyphens."""
    v = _text(v)
    v = re.sub(r'[ /]', '-', v) if v else None
    return v if v and kafka_message.NAME.fullmatch(v) else None


# Resource
def who(attrs, collector):
    """-> (host, container or '', os text or None, image or None). The host is the node's name on Kubernetes (the pod's own host
    name is the pod's), else the host name, else the collector's name. Bad when a name is not usable."""
    host = _name(attrs.get('k8s.node.name')) or _name(attrs.get('host.name')) or _name(collector)
    if not host: raise Bad('invalid name')
    ctr = ''
    if 'container.name' in attrs:
        ctr = re.sub(r'[^A-Za-z0-9._-]+', '-', _text(attrs.get('container.name')) or '').strip('-._')
        if not ctr or not kafka_message.NAME.fullmatch(ctr): raise Bad('invalid name')
    os_type, os_desc = _text(attrs.get('os.type')), _text(attrs.get('os.description'))
    return host, ctr, (os_desc or os_type), _text(attrs.get('container.image.name'))


# Points of one metric
def _datapoints(metric):
    """-> (kind, aggregation, [dataPoints]) or None for a metric type that is not used (histogram, summary, …)."""
    for kind in ('gauge', 'sum'):
        body = metric.get(kind)
        if body is None: continue
        if not isinstance(body, dict) or not isinstance(body.get('dataPoints', []), list): raise Bad('malformed request')
        raw = body.get('aggregationTemporality', 0)
        agg = AGGREGATION.get(raw) if isinstance(raw, (int, str)) else None
        if kind == 'sum' and agg is None: raise Bad('malformed request')
        return kind, agg or 'cumulative', body.get('dataPoints', [])
    return None


class Reader:
    """Collects the readings of one request, then `finish()` joins the values that belong together."""

    def __init__(self, collector, now, max_age):
        self.collector, self.now, self.max_age = collector, now, max_age
        self.rejected, self.ignored, self.seen = {}, 0, 0
        self.targets = {}                  # (host, ctr) -> dict(os=…, image=…)
        self.counters = []                 # network counters, see Rates
        self.cpu_idle = {}                 # (host, t) -> [idle share, …]
        self.mem = {}                      # (host, t) -> {state: bytes}
        self.limit = {}                    # (host, t) -> bytes
        self.disk = {}                     # (host, t) -> {mount point: {state: bytes}}
        self.points = []

    def reject(self, reason, n=1): self.rejected[reason] = self.rejected.get(reason, 0) + n

    def room(self):
        """False once the request holds MAX_POINTS points; the rest is rejected without being read."""
        return self.seen < MAX_POINTS

    def add(self, host, ctr, name, dim, t, v): self.points.append((host, ctr, name, dim, t, v))

    # one data point
    def point(self, host, ctr, metric, kind, agg, dp):
        if not isinstance(dp, dict): raise Bad('malformed point')
        attrs = pairs(dp.get('attributes'))
        v, t = _number(dp), _time(dp.get('timeUnixNano'), self.now, self.max_age)
        if metric in COUNTERS:
            name = (DIRECTION.get(attrs.get('direction')) if metric == 'system.network.io' else 'net_rx' if metric.endswith('rx_bytes') else 'net_tx')
            if not name: raise Bad('malformed point')
            device = _text(attrs.get('device') or attrs.get('interface')) or ''
            start = _time(dp.get('startTimeUnixNano'), self.now, None, required=False)
            self.counters.append(dict(host=host, ctr=ctr, name=name, dim=device, t=t, start=start, v=v, delta=agg == 'delta'))
        elif metric == 'system.cpu.utilization':
            if attrs.get('state') == 'idle': self.cpu_idle.setdefault((host, t), []).append(v)
        elif metric == 'system.cpu.load_average.1m': self.add(host, '', 'load1', '', t, v)
        elif metric == 'system.memory.usage':
            state = attrs.get('state')
            if isinstance(state, str): self.mem.setdefault((host, t), {})[state] = v
        elif metric == 'system.memory.limit': self.limit[(host, t)] = v
        elif metric == 'system.filesystem.usage':
            mount, state = _text(attrs.get('mountpoint')), attrs.get('state')
            if mount and isinstance(state, str): self.disk.setdefault((host, t), {}).setdefault(mount, {})[state] = v
        elif metric == 'container.cpu.utilization': self.add(host, ctr, 'cpu', '', t, max(0.0, v))
        elif metric == 'container.memory.usage.total': self.add(host, ctr, 'mem_used', '', t, v)
        elif metric == 'container.memory.usage.limit': self.add(host, ctr, 'mem_limit', '', t, v)
        elif metric == 'container.restarts': self.add(host, ctr, 'restarts', '', t, v)

    def metric(self, host, ctr, metric):
        name = metric.get('name')
        if not isinstance(name, str) or name not in USED or (name.startswith('container.') != bool(ctr)):
            self.ignored += 1       # not a metric MoniShield uses (or a server metric on a container's resource)
            return
        found = _datapoints(metric)
        if found is None:
            self.ignored += 1       # a histogram or another type
            return
        kind, agg, dps = found
        for dp in dps:
            if not self.room():
                self.reject('too many points')
                continue
            self.seen += 1
            try: self.point(host, ctr, name, kind, agg, dp)
            except Bad as e: self.reject(str(e))

    def resource(self, res):
        if not isinstance(res, dict): raise Bad('malformed request')
        resource = {} if res.get('resource') is None else res['resource']
        if not isinstance(resource, dict): raise Bad('malformed request')
        attrs = pairs(resource.get('attributes'))
        scopes = res.get('scopeMetrics')
        if scopes is None: scopes = []
        if not isinstance(scopes, list): raise Bad('malformed request')
        try: host, ctr, os_text, image = who(attrs, self.collector)
        except Bad as e:
            self.reject(str(e), self._count(scopes) or 1)
            return
        info = self.targets.setdefault((host, ctr), dict(os=None, image=None))
        if ctr: info['image'] = image or info['image']
        else: info['os'] = os_text or info['os']
        if ctr and (host, '') not in self.targets: self.targets[(host, '')] = dict(os=os_text, image=None)     # the container's server is a target too
        for scope in scopes:
            try:
                if not isinstance(scope, dict): raise Bad('malformed request')
                metrics = scope.get('metrics')
                if metrics is None: metrics = []
                if not isinstance(metrics, list): raise Bad('malformed request')
            except Bad as e:
                self.reject(str(e))
                continue
            for m in metrics:
                try:
                    if not isinstance(m, dict): raise Bad('malformed request')
                    self.metric(host, ctr, m)
                except Bad as e: self.reject(str(e))

    @staticmethod
    def _count(scopes):
        """Data points of the metrics that would have been used (to count what a bad resource loses)."""
        n = 0
        for s in scopes:
            for m in (s.get('metrics') or []) if isinstance(s, dict) and isinstance(s.get('metrics') or [], list) else []:
                if isinstance(m, dict) and m.get('name') in USED:
                    for kind in ('gauge', 'sum'):
                        body = m.get(kind)
                        if isinstance(body, dict) and isinstance(body.get('dataPoints'), list): n += len(body['dataPoints'])
        return n

    # joins
    def finish(self):
        for (host, t), idle in self.cpu_idle.items():
            self.add(host, '', 'cpu', '', t, min(100.0, max(0.0, 100.0 * (1.0 - sum(idle) / len(idle)))))
        for (host, t), states in self.mem.items():
            if 'used' in states: self.add(host, '', 'mem_used', '', t, states['used'])
            total = self.limit.get((host, t))
            if total is None: total = sum(v for k, v in states.items() if k != 'inactive') or None
            if total: self.add(host, '', 'mem_total', '', t, total)
        for (host, t), total in self.limit.items():
            if (host, t) not in self.mem: self.add(host, '', 'mem_total', '', t, total)
        for (host, t), mounts in self.disk.items():
            for mount in sorted(mounts, key=lambda m: (m not in ('/',), m))[:MAX_MOUNTS]:
                s = mounts[mount]
                if 'used' not in s or 'free' not in s: continue
                self.add(host, '', 'disk_used', mount, t, s['used'])
                self.add(host, '', 'disk_total', mount, t, s['used'] + s['free'])     # like `df`: the reserved blocks are not counted


def parse_metrics(payload, collector, now, max_age=None):
    """Decoded OTLP metrics request -> (points, counters, targets, rejected, ignored).
    `points` = [(host, ctr, name, dim, t, v)]; `counters` = network counters for `rate_points`; `targets` = {(host, ctr): dict(os, image)};
    `rejected` maps a reason to the number of data points; `ignored` counts metrics that are not used."""
    r = Reader(collector, now, max_age)
    try:
        if not isinstance(payload, dict): raise Bad('malformed request')
        items = payload.get('resourceMetrics')
        if items is None: items = []
        if not isinstance(items, list): raise Bad('malformed request')
        for res in items:
            try: r.resource(res)
            except Bad as e: r.reject(str(e))
    except Bad as e:
        r.reject(str(e))
    r.finish()
    return r.points, r.counters, r.targets, r.rejected, r.ignored


# Rates
class Rates:
    """The last sample of every counter series, to turn the next one into bytes per second. In memory: a restart of the server only
    loses one point per series. Not thread safe on its own; the caller holds a lock."""
    MAX = 50000

    def __init__(self): self.last = {}      # key -> (start, t, value)

    def update(self, key, start, t, v):
        """-> bytes per second, or None for the first sample, a counter reset, a sample that is not newer, or a gap over 5 minutes."""
        prev = self.last.get(key)
        if prev is not None and t <= prev[1]: return None          # a batch sent twice, or an old one: keep what is newer
        self.last[key] = (start, t, v)
        if len(self.last) > self.MAX: self.prune(t)
        if prev is None: return None
        p_start, p_t, p_v = prev
        if start != p_start or v < p_v or t - p_t > GAP: return None
        return (v - p_v) / (t - p_t).total_seconds()

    def prune(self, now):
        """Forget series that have not been seen for an hour (a container that is gone)."""
        for k in [k for k, (_, t, _v) in self.last.items() if now - t > datetime.timedelta(hours=1)]: del self.last[k]


def rate_points(counters, rates, scope=None):
    """Network counters -> points: bytes per second of each device, summed per server or container and time."""
    sums = {}
    for c in counters:
        if c['delta']:
            dt = (c['t'] - c['start']).total_seconds() if c['start'] else 0
            rate = c['v'] / dt if 0 < dt <= GAP.total_seconds() and c['v'] >= 0 else None
        else: rate = rates.update((scope, c['host'], c['ctr'], c['name'], c['dim']), c['start'], c['t'], c['v'])
        if rate is not None: sums[(c['host'], c['ctr'], c['name'], c['t'])] = sums.get((c['host'], c['ctr'], c['name'], c['t']), 0.0) + rate
    return [(host, ctr, name, '', t, v) for (host, ctr, name, t), v in sums.items()]


def partial_success(rejected):
    """OTLP JSON answer: {} when everything was taken, else the number of rejected data points and why."""
    n = sum(rejected.values())
    if not n: return {}
    why = ', '.join(f'{r} ({c})' for r, c in sorted(rejected.items(), key=lambda x: -x[1]))
    return {'partialSuccess': {'rejectedDataPoints': str(n), 'errorMessage': f'{n} data points rejected: {why}'}}
