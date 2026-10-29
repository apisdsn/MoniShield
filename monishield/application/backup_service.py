"""Daily backup (owner request 2026-10-27): both DuckDB databases (S3 and Kafka sources) and the account database, kept for
S4_BACKUP_KEEP days, optionally copied to object storage. The files are written by the Backups adapter
(monishield/infrastructure/backup.py). A failure is notified (event 'backup_failed') and shown on the Ingest & import page.
"""
import datetime, threading

from monishield.domain import alerts, retention
from monishield.domain.errors import Fail


def _now(): return datetime.datetime.now(datetime.timezone.utc)


class BackupService:
    def __init__(self, ctx):
        self.ctx, self.last, self.running = ctx, None, False

    def status(self):
        cfg = self.ctx.cfg
        nxt = retention.next_daily(_now(), cfg.backup_hour) if cfg.backup_enabled else None
        return dict(enabled=cfg.backup_enabled, hour=cfg.backup_hour, keep=cfg.backup_keep, dir=cfg.backup_path, s3=cfg.backup_s3 or None,
                    next=nxt and nxt.replace(tzinfo=None, microsecond=0).isoformat(sep=' '), running=self.running, last=self.last,
                    backups=self.ctx.backups.list())

    def run(self, by):
        """Make today's backup (WIB date), copy it to object storage when set, delete the oldest. -> result dict.
        Raises Fail (and notifies) when it fails."""
        if self.running: raise Fail('backup_busy', 'A backup is already running.', 409)
        self.running = True
        day = retention.today_local(_now()).isoformat()
        res = dict(at=str(_now().replace(tzinfo=None, microsecond=0)), by=by, day=day, ok=False, uploaded=None, pruned=[], error=None)
        try:
            cons = {name: ctx.con for name, ctx in self.ctx.sources.items()}
            man = self.ctx.backups.make(cons, self.ctx.auth, day)
            res['bytes'] = sum(f['bytes'] for f in man['files'].values())
            res['uploaded'] = self.ctx.backups.upload(day)
            res['pruned'] = self.ctx.backups.prune(self.ctx.cfg.backup_keep)
            res['ok'] = True
            self.ctx.auth.audit('backup.run', None, f"{day}: {res['bytes']} bytes{'; copied to ' + res['uploaded'] if res['uploaded'] else ''} by {by}")
            return res
        except Fail as e:
            res['error'] = e.message; self._notify(day, e.message); raise
        except Exception as e:   # noqa: BLE001  disk full, permissions, ...: reported, the server stays up
            res['error'] = f'{type(e).__name__}: {e}'; self._notify(day, res['error'])
            raise Fail('backup_failed', f"The backup failed: {res['error']}", 500) from None
        finally:
            self.last, self.running = res, False

    def _notify(self, day, error):
        try:
            from monishield.application.alert_service import deliver
            cfg = alerts.load(self.ctx.cfg)
            if alerts.active(cfg) and (ev := alerts.backup_failed(cfg, day, error)): deliver(self.ctx, cfg, ev[0], 'backup_failed', ev[1], ev[2])
        except Exception: pass   # noqa: BLE001  a notification problem must not hide the backup error

    # -------------------------------------------------------------- daily
    def start(self):
        self._stop = threading.Event()

        def loop():
            while True:
                wait = (retention.next_daily(_now(), self.ctx.cfg.backup_hour) - _now()).total_seconds()
                if self._stop.wait(max(60, wait)): return
                if not self.ctx.cfg.backup_enabled: continue
                try: self.run('(daily)')
                except Exception: pass   # noqa: BLE001  recorded in .last and notified; tried again tomorrow
        threading.Thread(target=loop, name='backup', daemon=True).start()

    def stop(self):
        if getattr(self, '_stop', None): self._stop.set()

