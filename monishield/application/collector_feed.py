"""Logs from collectors (docs/12-collector.md, step 3): a decoded OTLP request is read by monishield/domain/otlp_logs.py and
its lines are appended to the collector inbox (CollectorInbox port). Keeps counts per collector for the status page (step 6)
and the folders written since the last ingest. Step 4: those folders are ingested into the collector source's own database
(`ctx.sources['collector']`) from a small background thread, at most every S4_COLLECTOR_INGEST_SECONDS, and folders in the
inbox that the database does not know yet are ingested once when the server starts (catch-up after a restart)."""
import threading, time

from monishield.application import ingest_service, sources
from monishield.domain import otlp_logs

MB = 1024 * 1024
MAX_REJECT_TEXT = 300
TICK = 1   # seconds between two looks at `pending`


class CollectorFeed:
    def __init__(self, ctx):
        self.ctx, self._lock = ctx, threading.Lock()
        self.stats = {}          # collector id -> counts
        self.pending = set()     # folders written since the last ingest (kept when that ingest fails)
        self.thread, self._stop = None, threading.Event()
        self._last, self.last_ingest_at = None, None   # monotonic time of the last ingest start; UTC text of the last success

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
            return dict(collectors={k: dict(v, rejected=dict(v['rejected'])) for k, v in self.stats.items()}, pending=sorted(self.pending),
                        ingest_seconds=self.ctx.cfg.collector_ingest_seconds, last_ingest_at=self.last_ingest_at, running=self.running())

    # Ingest into the collector source
    def source(self): return self.ctx.sources[sources.COLLECTOR]

    def catch_up(self):
        """Folders in the collector inbox that the collector database does not know yet (written before a restart, or while the
        server was down) join `pending`. -> the folders added. (The start-up ingest covers known folders too.)"""
        found = ingest_service.new_folders(self.source())
        with self._lock: self.pending.update(found)
        return found

    def ingest_pending(self, now=None, force=False, whole=False):
        """Ingest the folders written since the last ingest, at most every S4_COLLECTOR_INGEST_SECONDS (`force` ignores that).
        One folder is ingested alone, several by one ingest of the whole inbox (only changed files are read again), like Kafka.
        `whole` ingests the whole inbox even when nothing is pending (start-up catch-up). Folders whose ingest did not succeed
        stay in `pending`. -> the folders ingested ([] when nothing was due or it failed)."""
        now = time.monotonic() if now is None else now
        src = self.source()
        if src.ingest.state['running']: return []   # another run (page button): try again next round
        with self._lock:
            if (not self.pending and not whole) or (not force and self._last is not None and now - self._last < self.ctx.cfg.collector_ingest_seconds): return []
            folders = sorted(self.pending)
            self.pending.difference_update(folders)   # lines written during the ingest add their folder again
        self._last = now
        try: src.ingest.run_blocking(folders[0] if len(folders) == 1 and not whole else None, '(collector)')
        except Exception:   # noqa: BLE001  busy or failed (the reason is in the ingest status): the folders wait for the next round
            with self._lock: self.pending.update(folders)
            return []
        self.last_ingest_at = ingest_service.now()
        return folders

    def start(self):
        if self.running(): return
        self._stop = threading.Event()
        self.thread = threading.Thread(target=self._loop, name='collector-ingest', daemon=True)
        self.thread.start()

    def stop(self, timeout=600):
        self._stop.set()
        if self.thread: self.thread.join(timeout)
        self.thread = None

    def running(self): return bool(self.thread and self.thread.is_alive())

    def _loop(self):
        try:   # catch-up: one ingest of the whole inbox (only files that changed are read again), so lines written into a known
            # folder just before a restart reach the pages without waiting for a new batch
            self.catch_up()
            self.ingest_pending(force=True, whole=bool(self.source().logfolders.dates()[1]))
        except Exception: pass   # noqa: BLE001  database not readable now: folders show up again through the receiver
        if self._last is None: self._last = time.monotonic()   # then at most one ingest per interval, counted from the start
        while not self._stop.is_set():
            try: self.ingest_pending()
            except Exception: pass   # noqa: BLE001  the thread must not die; tried again next round
            self._stop.wait(TICK)
