"""Logs-from-Kafka service: consumer in a background thread (KafkaFeed) + realtime map events (LiveHub). Adapters: Kafka
client monishield/infrastructure/kafka_client.py, inbox monishield/infrastructure/inbox.py; message rules
monishield/domain/kafka_message.py.

Logs from Kafka (owner request 2026-10-07: can it work like the existing logging?).

Rancher (cluster logging -> Kafka, fluentd) sends one JSON message per container log line:
    {"log": "<original line>", "stream": "stdout", "tag": "kubernetes.var.log.containers.<pod>_<ns>_<container>-<id>.log",
     "docker": {"container_id": …}, "kubernetes": {"container_name": …, "namespace_name": …, "pod_name": …}, "time": 1515680329}
The content is the same as the logs in S3: `log` = one file line, while the namespace/service/pod that S3 has in the folder/file
names are taken from `kubernetes.*`. This consumer rewrites the messages into the SAME folder layout as the S3 export:
    <inbox>/<date>/<namespace>/<service>/log_<service>_<pod>_<date>-00-00.log
then periodic ingest (S4_KAFKA_INGEST_MINUTES) processes the grown files — every dashboard page works right away.

Folder date follows the existing S3 export: folder D holds logs from (D-1 00:00, D 00:00] WIB, so today's events land in
the folder dated TOMORROW (that folder is "filling up" until midnight).

Kafka is its own data source (owner request 2026-10-23): this feed runs in the context of the Kafka source, so it writes to
<inbox>/kafka and its periodic ingest fills the Kafka database. S3 has its own folders and database: a date is never a mix
of both, and the dashboard shows one source at a time.

Delivery: offsets are committed AFTER the lines are written to disk (at-least-once). If the server dies in between, some
lines may be written twice; rare and small.

Realtime (map animation): nginx-ingress lines are forwarded to `LiveHub` (application/live_map.py) -> SSE /api/v1/live/map. Only location coordinates
(from the local/offline IP database, ip_info table) + module are sent to the browser, NOT IP addresses. IPs not yet known
(never ingested) are not drawn until the next ingest fills in their location.
"""
import collections, datetime, threading, time

from monishield.application.live_map import LiveHub
from monishield.domain import parse
from monishield.domain.errors import Busy, Fail
from monishield.domain.kafka_message import configured, folder_of, parse_message

FLUSH_SECONDS, FLUSH_LINES = 5, 20000
RECENT = 50


# Consumer
class KafkaFeed:
    """Consumer in a background thread of the server process (ingest stays the single DuckDB owner, TRD K1)."""

    def __init__(self, ctx):
        self.ctx, self.thread, self._stop = ctx, None, threading.Event()
        self.live = LiveHub(ctx)
        self.recent = collections.deque(maxlen=RECENT)
        self._reset_stats()

    def _reset_stats(self):
        self.stats = dict(state='off', since=None, received=0, written=0, skipped=0, last_message_at=None, last_ingest_at=None,
                          error=None, last_skip=None, per_service={}, folders={})
        self.pending = set()   # folders grown since the last ingest

    # Control
    def start(self):
        cfg = self.ctx.cfg
        if not (cfg.kafka_enabled and configured(cfg)): self.stats['state'] = 'off'; return
        kc = self.ctx.kafka_client
        if not kc.library_ok(): self.stats.update(state='error', error=kc.no_library); return
        if self.thread and self.thread.is_alive(): return
        self._stop = threading.Event()
        self.thread = threading.Thread(target=self._loop, name='kafka', daemon=True)
        self.thread.start()

    def stop(self, timeout=15):
        self._stop.set()
        if self.thread: self.thread.join(timeout)
        self.thread = None

    def restart(self):
        self.stop(); self._reset_stats(); self.start()

    def running(self): return bool(self.thread and self.thread.is_alive())

    def peek(self, n=10):
        """"Check messages": the LAST n messages of the topic (no consumer group; does not move the read position)."""
        return self.ctx.kafka_client.peek(self.ctx.cfg, n)

    def ingest_now(self):
        if not self.pending: raise Fail('kafka_nothing', 'No new lines from Kafka since the last ingest.', 400)
        if not self.maybe_ingest(force=True): raise Busy('Another ingest is running; try again shortly.')

    def live_folder(self): return folder_of(datetime.datetime.now(datetime.timezone.utc))

    def status(self):
        cfg = self.ctx.cfg
        return dict(configured=configured(cfg), enabled=cfg.kafka_enabled, library=self.ctx.kafka_client.library_ok(), brokers=cfg.kafka_brokers, topic=cfg.kafka_topic,
                    group=cfg.kafka_group, security=cfg.kafka_security, ingest_minutes=cfg.kafka_ingest_minutes, live_folder=self.live_folder(),
                    pending=sorted(self.pending), recent=list(self.recent)[::-1], **self.stats)

    # Core (testable without a broker)
    def handle(self, records, spool):
        """records: [(value, timestamp_ms, partition, offset)]."""
        prefix = self.ctx.cfg.upstream_prefix
        for value, ts, part, off in records:
            self.stats['received'] += 1
            rec, why = parse_message(value, ts)
            if not rec:
                self.stats['skipped'] += 1
                self.stats['last_skip'] = dict(reason=why, sample=(value or b'')[:300].decode('utf-8', 'replace') if isinstance(value, bytes) else str(value)[:300])
                continue
            f = spool.add(rec)
            key = f"{rec['ns']}/{rec['svc']}"
            self.stats['per_service'][key] = self.stats['per_service'].get(key, 0) + 1
            self.stats['last_message_at'] = rec['t'].astimezone(datetime.timezone.utc).replace(tzinfo=None).isoformat(timespec='seconds')
            self.recent.append(dict(at=self.stats['last_message_at'], folder=f, ns=rec['ns'], svc=rec['svc'], pod=rec['pod'], line=rec['line'][:400],
                                    partition=part, offset=off))
            if rec['svc'] == parse.NGINX_SVC: self.live.nginx_line(rec['line'], prefix)

    def flush(self, spool):
        wrote = spool.flush()
        for f, n in wrote.items():
            self.stats['written'] += n
            self.stats['folders'][f] = self.stats['folders'].get(f, 0) + n
            self.pending.add(f)
        return wrote

    def maybe_ingest(self, now=None, force=False):
        """Periodic ingest of grown folders (through IngestManager: single DuckDB owner). -> True when started."""
        now = now or time.time()
        last = getattr(self, '_last_ingest', 0)
        if not self.pending or (not force and now - last < self.ctx.cfg.kafka_ingest_minutes * 60): return False
        ing = self.ctx.ingest
        if ing.state['running']: return False
        folders = sorted(self.pending)
        try: ing.start(folders[0] if len(folders) == 1 else None, False, '(kafka)')
        except Exception: return False   # noqa: BLE001  another ingest just started: try next round
        self._last_ingest = now
        self.pending.clear()
        self.stats['last_ingest_at'] = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None).isoformat(timespec='seconds')
        self.live.refresh()
        return True

    # Thread
    def _loop(self):
        cfg, kc, wait = self.ctx.cfg, self.ctx.kafka_client, 5
        spool = self.ctx.inbox(cfg.inbox_dir)
        while not self._stop.is_set():
            c = None
            try:
                self.stats.update(state='connecting', error=None)
                c = kc.consumer(cfg)
                self.stats.update(state='running', since=datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None).isoformat(timespec='seconds'))
                wait, last_flush = 5, time.time()
                while not self._stop.is_set():
                    for recs in c.poll(timeout_ms=1000): self.handle(recs, spool)
                    if spool.n and (spool.n >= FLUSH_LINES or time.time() - last_flush >= FLUSH_SECONDS):
                        self.flush(spool); c.commit(); last_flush = time.time()
                    elif not spool.n: last_flush = time.time()
                    self.maybe_ingest()
                if spool.n: self.flush(spool); c.commit()
            except Exception as e:   # noqa: BLE001  broker down / wrong password: status + periodic retry
                f = kc.error(e)
                self.stats.update(state='error', error=f'[{f.code}] {f.message}')
                self._stop.wait(wait); wait = min(wait * 2, 120)
            finally:
                if c is not None:
                    try: c.close()
                    except Exception: pass   # noqa: BLE001
        self.stats['state'] = 'off'
