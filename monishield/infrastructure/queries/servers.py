"""Servers page (docs/13-metrics.md): what the collectors report about servers and containers, read from the metrics store.

The functions take a DuckDB cursor of the metrics store and plain data from the accounts side (the collectors, with their name,
platform and status), so this module never touches the account database. Times in the answers are ISO 8601 UTC with a Z; the
web UI shows them in the configured time zone. Nothing here is personal data: host and container names, numbers.
"""
import datetime

from monishield.domain import metric_anomaly

RANGES = {'1h': datetime.timedelta(hours=1), '24h': datetime.timedelta(hours=24), '7d': datetime.timedelta(days=7), '30d': datetime.timedelta(days=30)}
BUCKET = {'1h': 0, '24h': 1800, '7d': 3 * 3600, '30d': 12 * 3600}      # seconds; 0 = the points as they arrived (every 30 s)
FROM_HOURS = {'7d', '30d'}                                              # these ranges read the hourly rows
CURRENT = datetime.timedelta(hours=1)           # a value older than this is not "current"
RUNNING = datetime.timedelta(minutes=2)         # a container seen this recently is running
RECENT = datetime.timedelta(minutes=10)         # the mean for the unusual-value check
SINCE_BUCKETS = datetime.timedelta(hours=6)
MAX_UNUSUAL = 50
SPARK_POINTS = 24

HOST_CURRENT = ('cpu', 'mem_used', 'mem_total', 'load1', 'net_rx', 'net_tx')
CONTAINER_CURRENT = ('cpu', 'mem_used', 'mem_limit', 'net_rx', 'net_tx', 'restarts')


def _naive(t): return t.astimezone(datetime.timezone.utc).replace(tzinfo=None) if t.tzinfo else t


def iso(t): return t.strftime('%Y-%m-%dT%H:%M:%SZ') if t else None


def _marks(items): return ', '.join('?' * len(items))


def _num(v): return None if v is None else float(v)


# Latest values
def latest(cur, cids, since):
    """{(cid, host, ctr, name, dim): (value, time)} of the newest point of every series since `since`."""
    if not cids: return {}
    rows = cur.execute(f'SELECT cid, host, ctr, name, dim, arg_max(v, t), max(t) FROM metric_point WHERE t >= ? AND cid IN ({_marks(cids)}) GROUP BY ALL',
                       [since, *cids]).fetchall()
    return {(c, h, k, n, d): (v, t) for c, h, k, n, d, v, t in rows}


def targets(cur, cids):
    if not cids: return []
    return cur.execute(f'SELECT cid, host, ctr, os, image, first_seen, last_seen FROM metric_target WHERE cid IN ({_marks(cids)}) ORDER BY host, ctr', cids).fetchall()


def _disks(now_values, cid, host):
    """[{mount, used, total, pct}] of a server, '/' first."""
    used = {d: v for (c, h, k, n, d), (v, _t) in now_values.items() if (c, h, k, n) == (cid, host, '', 'disk_used')}
    total = {d: v for (c, h, k, n, d), (v, _t) in now_values.items() if (c, h, k, n) == (cid, host, '', 'disk_total')}
    out = [dict(mount=m, used=used[m], total=total[m], pct=metric_anomaly.percent(used[m], total[m])) for m in used if m in total]
    return sorted(out, key=lambda d: (d['mount'] != '/', d['mount']))


def value(values, cid, host, ctr, name):
    v = values.get((cid, host, ctr, name, ''))
    return _num(v[0]) if v else None


# Overview
def overview(cur, collectors, now, rng):
    """-> dict(range, hosts, unusual, disk_full). `collectors` = [dict(id, name, platform, status)] from the account side."""
    n = _naive(now)
    by_id = {c['id']: c for c in collectors}
    cids = sorted(by_id)
    values = latest(cur, cids, n - CURRENT)
    rows = targets(cur, cids)
    counts = {}
    for cid, host, ctr, *_ in rows:
        if ctr: counts[(cid, host)] = counts.get((cid, host), 0) + 1
    hosts, disk_full = [], []
    for cid, host, ctr, os_text, image, first, last in rows:
        if ctr: continue
        c = by_id[cid]
        disks = _disks(values, cid, host)
        hosts.append(dict(cid=cid, collector=c['name'], group=c.get('group') or '', platform=c['platform'], status=c['status'], host=host, os=os_text, last_seen=iso(last),
                          containers=counts.get((cid, host), 0), disks=disks,
                          **{k: value(values, cid, host, '', k) for k in HOST_CURRENT}))
        disk_full += [dict(cid=cid, collector=c['name'], host=host, mount=d['mount'], pct=d['pct']) for d in disks if metric_anomaly.almost_full(d['used'], d['total'])]
    return dict(range=rng, hosts=hosts, unusual=unusual(cur, by_id, n), disk_full=disk_full)


# Unusual values
def unusual(cur, by_id, n):
    """CPU and memory in use that are far above the same hour of the earlier days (domain/metric_anomaly.py), worst first."""
    cids = sorted(by_id)
    if not cids: return []
    recent = {(c, h, k, nm): (v, cnt) for c, h, k, nm, v, cnt in cur.execute(
        f"SELECT cid, host, ctr, name, avg(v), count(*) FROM metric_point WHERE t >= ? AND dim = '' AND name IN ('cpu', 'mem_used') AND cid IN ({_marks(cids)}) GROUP BY ALL",
        [n - RECENT, *cids]).fetchall() if cnt >= 4}
    if not recent: return []
    hour = n.replace(minute=0, second=0, microsecond=0)
    days = [hour - datetime.timedelta(days=k) for k in range(1, 8)]
    baseline = {}
    for c, h, k, nm, t, avg in cur.execute(
            f"SELECT cid, host, ctr, name, t, avg FROM metric_hour WHERE dim = '' AND name IN ('cpu', 'mem_used') AND n >= 30 AND t IN ({_marks(days)}) AND cid IN ({_marks(cids)})",
            [*days, *cids]).fetchall():
        baseline.setdefault((c, h, k, nm), []).append(avg)
    scale = {(c, h, k): v for c, h, k, nm, v in cur.execute(
        f"SELECT cid, host, ctr, name, arg_max(v, t) FROM metric_point WHERE t >= ? AND dim = '' AND name IN ('mem_total', 'mem_limit') AND cid IN ({_marks(cids)}) GROUP BY ALL",
        [n - CURRENT, *cids]).fetchall()}
    out = []
    for key, (current, _cnt) in recent.items():
        cid, host, ctr, name = key
        verdict = metric_anomaly.verdict(name, current, baseline.get(key, []), scale.get((cid, host, ctr)))
        if not verdict or not verdict['unusual']: continue
        buckets = cur.execute("SELECT time_bucket(INTERVAL 5 MINUTE, t), avg(v) FROM metric_point WHERE cid = ? AND host = ? AND ctr = ? AND name = ? AND dim = '' "
                              'AND t >= ? GROUP BY 1 ORDER BY 1', [cid, host, ctr, name, n - SINCE_BUCKETS]).fetchall()
        out.append(dict(kind='container' if ctr else 'host', cid=cid, collector=by_id[cid]['name'], host=host, ctr=ctr, name=name, z=round(verdict['z'], 2),
                        current=current, low=verdict['low'], high=verdict['high'], started=iso(metric_anomaly.started(buckets, verdict['limit']))))
    return sorted(out, key=lambda u: -u['z'])[:MAX_UNUSUAL]


# One server
def _series(cur, cid, host, ctr, names, since, until, rng):
    """{(name, dim): [[time, value], …]} for a chart: the points themselves (1 h), 30-minute averages of the points (24 h), or 3-hour /
    12-hour averages of the hourly rows (7 d / 30 d; the hour in progress is added from the points)."""
    size = BUCKET[rng]
    key, base = [cid, host, ctr, *names], f'cid = ? AND host = ? AND ctr = ? AND name IN ({_marks(names)})'
    if not size:
        rows = cur.execute(f'SELECT name, dim, t, v FROM metric_point WHERE {base} AND t >= ? AND t <= ? ORDER BY t', [*key, since, until]).fetchall()
    elif rng not in FROM_HOURS:
        rows = cur.execute(f'SELECT name, dim, make_timestamp((floor(epoch(t) / {size}) * {size})::BIGINT * 1000000), avg(v) FROM metric_point WHERE {base} AND t >= ? AND t <= ? '
                           'GROUP BY ALL ORDER BY 3', [*key, since, until]).fetchall()
    else:
        rows = cur.execute(f'''WITH h AS (
                SELECT name, dim, t, avg, n FROM metric_hour WHERE {base} AND t >= ? AND t <= ?
                UNION ALL
                SELECT name, dim, date_trunc('hour', t) AS t, avg(v), count(*) FROM metric_point WHERE {base} AND t >= ? AND t <= ?
                    AND date_trunc('hour', t) NOT IN (SELECT t FROM metric_hour WHERE {base}) GROUP BY ALL)
            SELECT name, dim, make_timestamp((floor(epoch(t) / {size}) * {size})::BIGINT * 1000000), sum(avg * n) / sum(n) FROM h GROUP BY ALL ORDER BY 3''',
                           [*key, since, until, *key, since, until, *key]).fetchall()
    out = {}
    for name, dim, t, v in rows: out.setdefault((name, dim), []).append([iso(t), _num(v)])
    return out


def _spark(cur, cid, host, ctr, n):
    """The memory in use of a container over the last 24 hours as 24 hourly averages, oldest first (None = no data in that hour)."""
    end = n.replace(minute=0, second=0, microsecond=0) + datetime.timedelta(hours=1)
    start = end - datetime.timedelta(hours=SPARK_POINTS)
    rows = cur.execute("SELECT date_trunc('hour', t), avg(v) FROM metric_point WHERE cid = ? AND host = ? AND ctr = ? AND name = 'mem_used' AND t >= ? GROUP BY 1",
                       [cid, host, ctr, start]).fetchall()
    got = {t: v for t, v in rows}
    return [_num(got.get(start + datetime.timedelta(hours=i))) for i in range(SPARK_POINTS)]


def host(cur, collector, name, now, rng):
    """-> dict for one server, or None when this collector never reported it. `collector` = dict(id, name, platform, status)."""
    n, cid = _naive(now), collector['id']
    rows = [r for r in targets(cur, [cid]) if r[1] == name]
    if not rows: return None
    values = latest(cur, [cid], n - CURRENT)
    me = next((r for r in rows if r[2] == ''), None)
    disks = _disks(values, cid, name)
    mount = next((d['mount'] for d in disks if d['mount'] == '/'), disks[0]['mount'] if disks else None)
    since = n - RANGES[rng]
    srv = _series(cur, cid, name, '', ('cpu', 'mem_used', 'mem_total', 'net_rx', 'net_tx', 'load1'), since, n, rng)
    disk = _series(cur, cid, name, '', ('disk_used', 'disk_total'), since, n, rng) if mount else {}
    window = n - max(RANGES[rng], RANGES['24h'])
    containers = []
    for cid_, h, ctr, os_text, image, first, last in rows:
        if not ctr or last < window: continue
        containers.append(dict(name=ctr, image=image, running=n - last <= RUNNING, last_seen=iso(last), spark=_spark(cur, cid, name, ctr, n),
                               **{k: value(values, cid, name, ctr, k) for k in CONTAINER_CURRENT}))
    containers.sort(key=lambda c: (not c['running'], c['name']))
    pick = lambda d, k, dim='': d.get((k, dim), [])    # noqa: E731
    return dict(
        cid=cid, collector=collector['name'], group=collector.get('group') or '', platform=collector['platform'], status=collector['status'], host=name, os=me[3] if me else None,
        last_seen=iso(me[6] if me else max(r[6] for r in rows)), range=rng, bucket_seconds=BUCKET[rng] or None,
        current={k: value(values, cid, name, '', k) for k in HOST_CURRENT}, disks=disks,
        series=dict(cpu=pick(srv, 'cpu'), mem_used=pick(srv, 'mem_used'), mem_total=pick(srv, 'mem_total'), load1=pick(srv, 'load1'),
                    disk_mount=mount, disk_used=pick(disk, 'disk_used', mount or ''), disk_total=pick(disk, 'disk_total', mount or ''),
                    net_rx=pick(srv, 'net_rx'), net_tx=pick(srv, 'net_tx')),
        containers=containers)
