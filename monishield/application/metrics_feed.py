"""Metrics from collectors (docs/13-metrics.md): a decoded OTLP metrics request is read by monishield/domain/otlp_metrics.py and its
points are stored through the MetricsStore port. Network counters become bytes per second here, because the previous sample of
each series is needed: it is kept in memory (`Rates`), so a restart of the server only loses one point per series.
Keeps counts per collector for the status page."""
import datetime, threading

from monishield.domain import otlp_metrics

MAX_REJECT_TEXT = 300


class MetricsFeed:
    def __init__(self, ctx):
        self.ctx, self._lock = ctx, threading.Lock()
        self.rates = otlp_metrics.Rates()
        self.stats = {}          # collector id -> counts

    @property
    def store(self): return self.ctx.metrics

    def space_low(self):
        """True when the disk is too full to take more: the receiver answers 503 and the collector keeps its queue."""
        return self.store.free_bytes() < self.ctx.cfg.collector_min_free_mb * 1024 * 1024

    def max_age(self):
        h = self.ctx.cfg.collector_max_age_hours
        return datetime.timedelta(hours=h) if h else None

    def receive(self, collector, payload, now):
        """-> the OTLP answer. The points are stored when this returns."""
        points, counters, targets, rejected, ignored = otlp_metrics.parse_metrics(payload, collector['name'], now, self.max_age())
        with self._lock: points = points + otlp_metrics.rate_points(counters, self.rates, collector['id'])
        if points or targets: self.store.add(collector['id'], points, targets, now)
        answer = otlp_metrics.partial_success(rejected)
        self._count(collector, len(points), rejected, ignored, answer, now)
        return answer

    def _count(self, collector, stored, rejected, ignored, answer, now):
        stamp = now.isoformat(timespec='seconds')
        with self._lock:
            s = self.stats.setdefault(collector['id'], dict(name=collector['name'], stored=0, rejected={}, ignored=0, last_batch_at=None, last_reject=None))
            s['name'], s['stored'], s['ignored'], s['last_batch_at'] = collector['name'], s['stored'] + stored, s['ignored'] + ignored, stamp
            for why, n in rejected.items(): s['rejected'][why] = s['rejected'].get(why, 0) + n
            if rejected: s['last_reject'] = dict(at=stamp, text=answer['partialSuccess']['errorMessage'][:MAX_REJECT_TEXT])   # reasons only

    def status(self):
        with self._lock: return dict(collectors={k: dict(v, rejected=dict(v['rejected'])) for k, v in self.stats.items()})
