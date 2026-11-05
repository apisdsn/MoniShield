"""Unusual values of servers and containers (docs/13-metrics.md, "Unusual values"). Pure: numbers in, a verdict out.

For the CPU and the memory in use of every server and container:

* current  = the mean of the last 10 minutes;
* baseline = the hourly averages of the same hour of the day on each of the previous 7 days; at least 5 days are needed,
  otherwise there is no verdict (a new server is never called unusual);
* z        = (current - mean) / max(std, floor), with the sample standard deviation of the baseline and a floor so that a very steady
  server does not turn tiny changes into big numbers: CPU 2 percentage points, memory 2 % of the total (of the limit for a
  container) but at least 50 MB;
* unusual  = z >= 3 (only higher than usual is reported);
* the usual band is mean +- max(std, floor), shown as "usually a-b";
* "started" is the earliest 5-minute bucket of the last 6 hours after which every bucket stayed above mean + 3 x max(std, floor).

Disks have no z-score: a mount point that is 90 % full or more is "almost full".
"""
import statistics

MIN_DAYS = 5
Z_LIMIT = 3.0
CPU_FLOOR = 2.0                  # percentage points
MEM_FLOOR_SHARE, MEM_FLOOR_BYTES = 0.02, 50 * 1024 * 1024
DISK_FULL = 90.0                 # percent used
CHECKED = ('cpu', 'mem_used')


def floor(name, scale=None):
    """The smallest spread that counts, in the unit of the value. `scale` = the memory total (server) or limit (container), if known."""
    if name == 'cpu': return CPU_FLOOR
    return max(MEM_FLOOR_SHARE * scale if scale else 0.0, MEM_FLOOR_BYTES)


def verdict(name, current, baseline, scale=None):
    """-> None when there is no verdict (too few days, no current value), else
    dict(z, mean, std, low, high, limit, unusual): `baseline` = one average per earlier day (same hour of the day)."""
    if current is None or len(baseline) < MIN_DAYS: return None
    mean, std = statistics.fmean(baseline), statistics.stdev(baseline)
    spread = max(std, floor(name, scale))
    z = (current - mean) / spread
    return dict(z=z, mean=mean, std=std, spread=spread, low=max(0.0, mean - spread), high=mean + spread, limit=mean + Z_LIMIT * spread, unusual=z >= Z_LIMIT)


def started(buckets, limit):
    """`buckets` = [(time, mean)] of the last 6 hours, oldest first. -> the time of the earliest bucket after which every bucket was above
    `limit`, or None when the newest bucket is not above it (the value is already back to normal)."""
    since = None
    for t, v in buckets:
        if v is not None and v > limit:
            if since is None: since = t
        else: since = None
    return since


def percent(used, total): return 100.0 * used / total if total and total > 0 and used is not None else None


def almost_full(used, total):
    """True when a mount point is DISK_FULL percent used or more."""
    p = percent(used, total)
    return p is not None and p >= DISK_FULL
