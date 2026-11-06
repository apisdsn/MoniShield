"""Realistic sample servers for the Servers page, for the browser smoke test and for screenshots.

    seed(app)      the app of monishield.interfaces.api.app.create_app: adds collectors in groups (and one without a group), enrols them
                   and writes 26 hours of 60-second points plus 30 days of hourly rows, so every range of the page has data. One
                   container's memory has jumped in the last quarter hour and one disk is almost full, so the banner shows.

Used by tools/smoke_server.py (run in-process, nothing is sent over the network). The names are made up.
"""
import datetime, math

UTC = datetime.timezone.utc
MB = 1024 * 1024
GB = 1024 * MB

# name, platform, group, host, os, containers [(name, image, cpu %, memory MB, limit MB, restarts, running)], cpu %, memory share %, disk share %, status
SERVERS = [
    ('web-01', 'linux', 'Client A', 'web-01', 'Ubuntu 24.04', [], 31, 52, 63, 'online'),
    ('web-02', 'linux', 'Client A', 'web-02', 'Ubuntu 24.04', [], 28, 49, 61, 'online'),
    ('db-01', 'linux', 'Client A', 'db-01', 'Debian 12', [], 12, 66, 92, 'late'),
    ('api-01', 'docker', 'Client B', 'api-01', 'Ubuntu 22.04', [('api', 'registry.example.com/api:4.2', 18, 420, 1024, 0, True), ('worker', 'registry.example.com/worker:4.2', 9, 260, 512, 1, True)],
     44, 58, 40, 'online'),
    ('win-erp', 'windows', 'Client B', 'WIN-ERP01', 'Windows Server 2022', [], 9, 71, 55, 'online'),
    ('monishield-docker', 'docker', 'Internal', 'docker-host-01', 'Ubuntu 24.04',
     [('monishield-app-1', 'monishield:2.0.0', 12, 1700, 2048, 0, True), ('monishield-https-1', 'caddy:2.10.2-alpine', 3, 48, 0, 0, True),
      ('monishield-postgres-1', 'postgres:17', 2, 210, 1024, 0, True), ('otel-test', 'busybox:1.37', 0, 2, 0, 3, False)], 23, 78, 41, 'online'),
    ('test-vm', 'linux', '', 'test-vm', 'Ubuntu 24.04', [], 4, 30, 20, 'offline'),
]
OLDER = {'web-02'}         # a collector configuration from before stage 61: no load 5/15, cores, uptime or disk traffic, so the page asks for the upgrade
SPIKE = 'monishield-app-1'     # its memory jumped in the last 15 minutes
HOURS = 26


def describe(os_text, host, platform):
    """The text the collector's resource detection sends as `os.description`."""
    if platform == 'windows': return f'Microsoft {os_text} Datacenter 10.0.20348 Build 20348'
    return f'{os_text} LTS (Noble Numbat) (Linux {host} 6.8.0-138-generic #1 SMP PREEMPT_DYNAMIC x86_64)'


def _wave(i, base, amp, seed):
    return max(0.0, base + amp * math.sin((i + seed) / 7.3) + amp * 0.4 * math.cos((i * (seed + 3)) / 11.1))


def _series(host, ctr, name, dim, start, count, step, fn):
    return [(host, ctr, name, dim, start + datetime.timedelta(seconds=step * i), fn(i)) for i in range(count)]


def _points(host, os_text, containers, cpu, mem, disk, start, count, now, older=False):
    seed = sum(map(ord, host)) % 17
    total_mem, total_disk = 8 * GB, 120 * GB
    pts = []
    add = lambda *a: pts.extend(_series(host, *a))   # noqa: E731
    add('', 'cpu', '', start, count, 60, lambda i: _wave(i, cpu, 3, seed))
    add('', 'mem_used', '', start, count, 60, lambda i: total_mem * _wave(i, mem, 2, seed) / 100)
    add('', 'mem_total', '', start, count, 60, lambda i: total_mem)
    add('', 'load1', '', start, count, 60, lambda i: _wave(i, cpu / 25, 0.3, seed))
    if not older:
        cores = 2 + 2 * (seed % 3)
        add('', 'load5', '', start, count, 60, lambda i: _wave(i, cpu / 25 * 0.9, 0.15, seed))
        add('', 'load15', '', start, count, 60, lambda i: _wave(i, cpu / 25 * 0.8, 0.06, seed))
        add('', 'cores', '', start, count, 60, lambda i: float(cores))
        add('', 'uptime', '', start, count, 60, lambda i: (12 * 86400 + 4 * 3600) + 60.0 * i)
        add('', 'disk_read', '', start, count, 60, lambda i: 1.2e6 * max(0.05, 1 + math.sin((i + seed) / 5) * 0.8))
        add('', 'disk_write', '', start, count, 60, lambda i: 0.4e6 * max(0.05, 1 + math.cos((i + seed) / 6) * 0.7))
    add('', 'net_rx', '', start, count, 60, lambda i: 1.5e6 * (1 + math.sin((i + seed) / 9) * 0.6))
    add('', 'net_tx', '', start, count, 60, lambda i: 0.9e6 * (1 + math.cos((i + seed) / 8) * 0.5))
    add('', 'disk_used', '/', start, count, 60, lambda i: total_disk * (disk + i * 0.0004) / 100)
    add('', 'disk_total', '/', start, count, 60, lambda i: total_disk)
    for name, _image, c_cpu, c_mem, c_limit, restarts, running in containers:
        n = count if running else 5 * 60           # a container that is not running stopped five hours ago
        s0 = start if running else now - datetime.timedelta(hours=5, minutes=n)
        spike = name == SPIKE
        add(name, 'cpu', '', s0, n, 60, lambda i, c=c_cpu: _wave(i, c, 1.5, seed))
        add(name, 'mem_used', '', s0, n, 60, lambda i, m=c_mem, n=n, spike=spike: (m * 0.5 if spike and i < n - 15 else m) * MB * (1 + 0.01 * math.sin(i / 5)))
        if c_limit: add(name, 'mem_limit', '', s0, n, 60, lambda i, m=c_limit: m * MB)
        add(name, 'net_rx', '', s0, n, 60, lambda i: 4e5 * (1 + math.sin(i / 6) * 0.5))
        add(name, 'net_tx', '', s0, n, 60, lambda i: 1.1e6 * (1 + math.cos(i / 6) * 0.5))
        add(name, 'restarts', '', s0, n, 60, lambda i, r=restarts: float(r))
    return pts


def seed(app, now=None):
    """Collectors, their metrics and (for the baseline of the unusual-value check) 30 days of hourly rows. -> {collector name: id}."""
    now = (now or datetime.datetime.now(UTC)).replace(second=0, microsecond=0)
    svc, store = app.state.collectors, app.state.metrics
    ids = {}
    start = now - datetime.timedelta(hours=HOURS)
    count = HOURS * 60
    for name, platform, group, host, os_text, containers, cpu, mem, disk, status in SERVERS:
        info, token, _exp = svc.add(name, platform, {'username': 'admin'}, None, None, group)
        ids[name] = cid = info['id']
        svc.enroll(token, '203.0.113.7', 'OpenTelemetry Collector Contrib/0.163.2 (linux/amd64)')
        older = name in OLDER
        os_text = describe(os_text, host, platform)
        targets = {(host, ''): dict(os=os_text, image=None), **{(host, c[0]): dict(os=None, image=c[1]) for c in containers}}
        if status == 'offline':       # it reported for the last time six days ago
            gone = now - datetime.timedelta(days=6)
            store.add(cid, _points(host, os_text, containers, cpu, mem, disk, gone - datetime.timedelta(hours=1), 60, gone, older), targets, gone)
        else:
            store.add(cid, _points(host, os_text, containers, cpu, mem, disk, start, count, now, older), targets, now)
            for c in containers:
                if not c[6]: store.rows('UPDATE metric_target SET last_seen = ? WHERE cid = ? AND ctr = ? RETURNING 1', [(now - datetime.timedelta(hours=5)).replace(tzinfo=None), cid, c[0]])
        # hourly rows for the 30 days before (the 26 hours above are rolled up by the background job later)
        rows = []
        for h in range(HOURS, 30 * 24):
            t = (now - datetime.timedelta(hours=h)).replace(minute=0).replace(tzinfo=None)
            seed_ = (h * 7 + len(host)) % 13
            base = [('', 'cpu', '', cpu), ('', 'mem_used', '', 8 * GB * mem / 100), ('', 'net_rx', '', 1.5e6), ('', 'net_tx', '', 0.9e6)]
            if not older: base += [('', 'load1', '', cpu / 25), ('', 'load5', '', cpu / 25 * 0.9), ('', 'load15', '', cpu / 25 * 0.8), ('', 'disk_read', '', 1.2e6), ('', 'disk_write', '', 0.4e6)]
            base += [(c[0], 'cpu', '', c[2]) for c in containers] + [(c[0], 'mem_used', '', c[3] * MB * (0.5 if c[0] == SPIKE else 1)) for c in containers]
            for ctr, metric, dim, v in base:
                v = v * (1 + 0.12 * math.sin(seed_))   # about 8 % spread between days, so only the real jump stands out
                rows.append([cid, host, ctr, metric, dim, t, v, v * 1.2, 120])
        if rows and status != 'offline':
            con = store.open()
            with store.lock:
                from monishield.infrastructure import db
                db.insert_rows(con, 'metric_hour', rows)
        if status != 'online': _set_seen(app, cid, now, status)
    return ids


def _set_seen(app, cid, now, status):
    """A collector that was last seen a while ago: 'late' (22 minutes) or 'offline' (6 days)."""
    from sqlalchemy import update
    from monishield.infrastructure.auth import Collector
    ago = datetime.timedelta(minutes=22) if status == 'late' else datetime.timedelta(days=6)
    with app.state.auth._tx() as s: s.execute(update(Collector).where(Collector.id == cid).values(last_seen=(now - ago).replace(tzinfo=None)))
