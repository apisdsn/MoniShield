"""Server and container metrics in their own DuckDB file `<data dir>/metrics.duckdb` (docs/13-metrics.md).

    metric_point(cid, host, ctr, name, dim, t, v)         every value as it arrived (about every 30 s), kept S4_METRICS_RAW_DAYS
    metric_hour(cid, host, ctr, name, dim, t, avg, max, n) the same per finished hour, kept S4_METRICS_HOUR_DAYS
    metric_target(cid, host, ctr, os, image, first_seen, last_seen)  one row per server (ctr '') and per container

`cid` is the collector's id, `ctr` is '' for the server itself, `dim` is a mount point for the disk values and '' otherwise.
Times are UTC (TIMESTAMP without zone). One connection and one lock: a request inserts a few hundred rows at once, the
background job (monishield/application/metrics_service.py) rolls up and prunes. The file is opened on first use, so a test or
a CLI call needs no start-up step.
"""
import datetime, os, shutil, threading

import duckdb

from monishield.infrastructure import db

SCHEMA = '''
CREATE TABLE IF NOT EXISTS metric_point (cid BIGINT, host VARCHAR, ctr VARCHAR, name VARCHAR, dim VARCHAR, t TIMESTAMP, v DOUBLE);
CREATE TABLE IF NOT EXISTS metric_hour (cid BIGINT, host VARCHAR, ctr VARCHAR, name VARCHAR, dim VARCHAR, t TIMESTAMP,
    avg DOUBLE, max DOUBLE, n INTEGER, PRIMARY KEY (cid, host, ctr, name, dim, t));
CREATE TABLE IF NOT EXISTS metric_target (cid BIGINT, host VARCHAR, ctr VARCHAR, os VARCHAR, image VARCHAR,
    first_seen TIMESTAMP, last_seen TIMESTAMP, PRIMARY KEY (cid, host, ctr));
'''


REDO = datetime.timedelta(hours=25)   # rolled up again on each run: late points of the last day are counted


def naive(t):
    """Aware time -> UTC time without zone, as stored."""
    return t.astimezone(datetime.timezone.utc).replace(tzinfo=None) if t.tzinfo else t


class MetricsStore:
    def __init__(self, path, memory_limit='256MB'):
        self.path, self.memory_limit = path, memory_limit
        self.lock, self.con = threading.RLock(), None

    # connection
    def open(self):
        with self.lock:
            if self.con is None:
                os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
                con = duckdb.connect(self.path)
                con.execute(f"SET memory_limit = '{self.memory_limit}'")
                con.execute(SCHEMA)
                self.con = con
            return self.con

    def close(self):
        with self.lock:
            if self.con is not None: self.con.close()
            self.con = None

    def free_bytes(self):
        """Free space of the disk the file is on (its nearest existing parent while the folder is not created yet)."""
        p = os.path.dirname(os.path.abspath(self.path))
        while not os.path.exists(p) and os.path.dirname(p) != p: p = os.path.dirname(p)
        return shutil.disk_usage(p).free

    # writing
    def add(self, cid, points, targets, now):
        """Store the points `(host, ctr, name, dim, t, v)` of one request and note the servers and containers they belong to.
        `targets` = {(host, ctr): dict(os, image)}; `t` and `now` are aware UTC times."""
        with self.lock:
            con = self.open()
            if points:
                db.insert_rows(con, 'metric_point', [[cid, h, c, n, d, naive(t).strftime('%Y-%m-%d %H:%M:%S'), v] for h, c, n, d, t, v in points])
            if targets:
                seen = naive(now)
                rows = [[cid, host, ctr, info.get('os'), info.get('image'), seen, seen] for (host, ctr), info in targets.items()]
                con.execute(f'''INSERT INTO metric_target (cid, host, ctr, os, image, first_seen, last_seen) VALUES {', '.join(['(?, ?, ?, ?, ?, ?, ?)'] * len(rows))}
                               ON CONFLICT (cid, host, ctr) DO UPDATE SET os = COALESCE(excluded.os, os), image = COALESCE(excluded.image, image),
                               last_seen = excluded.last_seen''', [v for r in rows for v in r])

    def forget(self, cid):
        """Remove everything of a collector that is deleted (its id may be given to a new one)."""
        with self.lock:
            con = self.open()
            for table in ('metric_point', 'metric_hour', 'metric_target'): con.execute(f'DELETE FROM {table} WHERE cid = ?', [cid])

    # roll-up and retention (application/metrics_service.py runs these every few minutes)
    def rollup(self, now):
        """Hourly average, maximum and count of every series for the finished hours. Idempotent: an hour that is rolled up again gets
        the same numbers plus late points. Starts a little before the newest hour already rolled up, so points that arrived late
        (a collector that was offline and sent its queue) are counted; at most S4_COLLECTOR_MAX_AGE_HOURS late, so REDO covers it.
        -> the number of hour rows written."""
        with self.lock:
            con = self.open()
            end = naive(now).replace(minute=0, second=0, microsecond=0)
            first = con.execute('SELECT min(t) FROM metric_point').fetchone()[0]
            if first is None: return 0
            last = con.execute('SELECT max(t) FROM metric_hour').fetchone()[0]
            start = first.replace(minute=0, second=0, microsecond=0)
            if last is not None: start = max(start, last - REDO)
            if start >= end: return 0
            con.execute('''INSERT INTO metric_hour (cid, host, ctr, name, dim, t, avg, max, n)
                           SELECT cid, host, ctr, name, dim, date_trunc('hour', t), avg(v), max(v), count(*) FROM metric_point
                           WHERE t >= ? AND t < ? GROUP BY ALL
                           ON CONFLICT (cid, host, ctr, name, dim, t) DO UPDATE SET avg = excluded.avg, max = excluded.max, n = excluded.n''', [start, end])
            return con.execute('SELECT count(*) FROM metric_hour WHERE t >= ? AND t < ?', [start, end]).fetchone()[0]

    def prune(self, now, raw_days, hour_days):
        """Delete points older than `raw_days`, hours and targets older than `hour_days`. -> (points, hours, targets) deleted."""
        with self.lock:
            con = self.open()
            n = naive(now)
            out = []
            for table, col, days in (('metric_point', 't', raw_days), ('metric_hour', 't', hour_days), ('metric_target', 'last_seen', hour_days)):
                cut = n - datetime.timedelta(days=days)
                out.append(con.execute(f'SELECT count(*) FROM {table} WHERE {col} < ?', [cut]).fetchone()[0])
                if out[-1]: con.execute(f'DELETE FROM {table} WHERE {col} < ?', [cut])
            if any(out):
                try: con.execute('CHECKPOINT')      # give the freed space back to the file
                except duckdb.Error: pass           # a reader is busy: the next round does it
            return tuple(out)

    # reading
    def cursor(self):
        """A cursor for the read side (queries run beside a write; the caller closes it)."""
        return self.open().cursor()

    def rows(self, sql, params=()):
        with self.lock: return self.open().execute(sql, list(params)).fetchall()
