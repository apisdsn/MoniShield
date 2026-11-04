"""Logs from collectors (docs/12-collector.md, step 3): a decoded OTLP request is read by monishield/domain/otlp_logs.py and
its lines are appended to the collector inbox (CollectorInbox port). Keeps counts per collector for the status page (step 6)
and the folders written since the last ingest (step 4 ingests those)."""
import threading

from monishield.domain import otlp_logs

MB = 1024 * 1024
MAX_REJECT_TEXT = 300


class CollectorFeed:
    def __init__(self, ctx):
        self.ctx, self._lock = ctx, threading.Lock()
        self.stats = {}          # collector id -> counts
        self.pending = set()     # folders written since the last ingest

    @property
    def inbox(self): return self.ctx.collector_inbox

    def space_low(self):
        """True when the disk is too full to take more: the receiver answers 503 and the collector keeps its queue."""
        return self.inbox.free_bytes() < self.ctx.cfg.collector_min_free_mb * MB

    def receive(self, collector, payload, now):
        """-> (OTLP answer, {folder: lines written}). The lines are on disk when this returns."""
        records, rejected = otlp_logs.parse_logs(payload, collector['name'], now)
        written = self.inbox.append(records) if records else {}
        answer = otlp_logs.partial_success(rejected)
        self._count(collector, len(records) + sum(rejected.values()), rejected, answer, written, now)
        return answer, written

    def _count(self, collector, received, rejected, answer, written, now):
        stamp = now.isoformat(timespec='seconds')   # text, so status() can go straight to JSON
        with self._lock:
            s = self.stats.setdefault(collector['id'], dict(name=collector['name'], received=0, rejected={}, written=0, last_batch_at=None, last_reject=None))
            s['name'], s['received'], s['last_batch_at'] = collector['name'], s['received'] + received, stamp
            s['written'] += sum(written.values())
            for why, n in rejected.items(): s['rejected'][why] = s['rejected'].get(why, 0) + n
            if rejected: s['last_reject'] = dict(at=stamp, text=answer['partialSuccess']['errorMessage'][:MAX_REJECT_TEXT])   # reasons only, no log text
            self.pending.update(written)

    def status(self):
        with self._lock:
            return dict(collectors={k: dict(v, rejected=dict(v['rejected'])) for k, v in self.stats.items()}, pending=sorted(self.pending))
