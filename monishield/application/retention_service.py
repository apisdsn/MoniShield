"""Data retention (owner request 2026-10-08): removes folders past their keeping period from the database and old
inbox folders from disk. Rules: monishield/domain/retention.py. Runs once a day in the server (first check a few
minutes after start), and on demand from the Configuration page. Holds the ingest lock, like deleting a folder by hand.

Disk space: DuckDB reuses the space of deleted rows for new data; the database file itself does not shrink.
"""
import datetime, threading

from monishield.application import ingest_service
from monishield.domain import retention
from monishield.domain.errors import Busy


def _now(): return datetime.datetime.now(datetime.timezone.utc)


class RetentionService:
    def __init__(self, ctx):
        self.ctx, self._lock, self.last = ctx, threading.Lock(), None

    def plan(self):
        cfg, w = self.ctx.cfg, self.ctx.warehouse
        _, inbox = self.ctx.logfolders.dates()
        p = retention.plan(w.known_folders(), inbox, retention.today_wib(_now()), cfg.retention_days, cfg.retention_inbox_days)
        return dict(p, days=cfg.retention_days, inbox_days=cfg.retention_inbox_days)

    def view(self): return dict(self.plan(), last=self.last)

    def run(self, by):
        """Remove what the plan lists. -> dict(at, by, db=[folders removed], inbox=[folders deleted]). Ingest running -> Busy."""
        if not self._lock.acquire(blocking=False): raise Busy('Retention cleanup is already running.')
        try:
            ctx, p = self.ctx, self.plan()
            done = dict(at=str(_now().replace(tzinfo=None, microsecond=0)), by=by, db=[], inbox=[])
            if p['db'] or p['inbox']:
                with ingest_service._exclusive(ctx) as w:
                    for f in p['db']:
                        w.forget(f); done['db'].append(f)
                    for f in p['inbox']:
                        if ctx.logfolders.remove_inbox(f): done['inbox'].append(f)
                ctx.ingest.snapshot()
                ctx.auth.audit('retention.run', None, f"database: {len(done['db'])} folders, inbox: {len(done['inbox'])} folders by {by}")
            self.last = done
            return done
        finally:
            self._lock.release()

    # -------------------------------------------------------------- daily
    def start(self, first_delay=300, every=86400):
        self._stop = threading.Event()

        def loop():
            wait = first_delay
            while not self._stop.wait(wait):
                wait = every
                cfg = self.ctx.cfg
                if not (cfg.retention_days or cfg.retention_inbox_days): continue
                try: self.run('(daily)')
                except Busy: wait = 3600            # ingest running: try again in an hour
                except Exception: pass              # noqa: BLE001  cleanup must never stop the server; tried again tomorrow
        threading.Thread(target=loop, name='retention', daemon=True).start()

    def stop(self):
        if getattr(self, '_stop', None): self._stop.set()
