"""Roll-up and retention of the metrics store (docs/13-metrics.md), from a small background thread started and stopped in the app's
`lifespan` like the collector ingest: every 5 minutes the finished hours are rolled up (hourly average, maximum, count; an hour that
is rolled up again just gets the same numbers plus late points), then points older than S4_METRICS_RAW_DAYS and hours older than
S4_METRICS_HOUR_DAYS are deleted. Roll-up always comes before the delete, so a raw point is never removed before it is in its hour."""
import datetime, threading

EVERY = 300   # seconds between two rounds


def _now(): return datetime.datetime.now(datetime.timezone.utc)


class MetricsService:
    def __init__(self, ctx):
        self.ctx, self.thread, self._stop = ctx, None, threading.Event()
        self.last = None   # result of the last round: dict(at, hours, deleted) or dict(at, error)

    def run(self, now=None):
        """One round. -> dict(at, hours rolled up, deleted=(points, hours, targets))."""
        now, cfg, store = now or _now(), self.ctx.cfg, self.ctx.metrics
        hours = store.rollup(now)
        deleted = store.prune(now, cfg.metrics_raw_days, cfg.metrics_hour_days)
        self.last = dict(at=now.isoformat(timespec='seconds'), hours=hours, deleted=deleted)
        return self.last

    def start(self, every=EVERY, first=30):
        if self.running(): return
        self._stop = threading.Event()
        self.thread = threading.Thread(target=self._loop, args=(every, first), name='metrics-rollup', daemon=True)
        self.thread.start()

    def stop(self, timeout=60):
        self._stop.set()
        if self.thread: self.thread.join(timeout)
        self.thread = None

    def running(self): return bool(self.thread and self.thread.is_alive())

    def _loop(self, every, first):
        wait = first
        while not self._stop.wait(wait):
            wait = every
            try: self.run()
            except Exception as e:   # noqa: BLE001  the thread must not die; the next round tries again
                self.last = dict(at=_now().isoformat(timespec='seconds'), error=type(e).__name__)
