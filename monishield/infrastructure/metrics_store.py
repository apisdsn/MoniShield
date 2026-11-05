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
            seen = naive(now)
            for (host, ctr), info in targets.items():
                con.execute('''INSERT INTO metric_target (cid, host, ctr, os, image, first_seen, last_seen) VALUES (?, ?, ?, ?, ?, ?, ?)
                               ON CONFLICT (cid, host, ctr) DO UPDATE SET os = COALESCE(excluded.os, os), image = COALESCE(excluded.image, image),
                               last_seen = excluded.last_seen''', [cid, host, ctr, info.get('os'), info.get('image'), seen, seen])

    # reading (tests and the read side)
    def rows(self, sql, params=()):
        with self.lock: return self.open().execute(sql, list(params)).fetchall()
