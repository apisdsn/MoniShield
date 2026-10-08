"""Notifications: when they are sent and where to (rules + texts in monishield/domain/alerts.py, channels in
monishield/infrastructure/notify_channels.py). Called by the ingest / import services after a job finishes, and by the hourly
scheduler (folder not arrived). All sending happens in a background thread: ingest and the page never wait for Telegram/SMTP.

PROJECT RULE: user IP addresses must not be sent to third-party services — texts are cleaned with `alerts.scrub` here,
right before being handed to the channel.
"""
import datetime, threading, time

from monishield.application import settings_service
from monishield.domain import alerts
from monishield.domain.alerts import AlertFail
from monishield.domain.errors import Fail


def deliver(ctx, cfg, key, event, title, text, channels=None, force=False):
    """Send to all enabled channels (or `channels`). Already succeeded for `key` -> skipped (unless force).
    -> {channel: None (success) | error message}. Errors never contain credentials."""
    auth = ctx.auth
    if not force and auth.alert_seen(key): return {}
    title, text = alerts.scrub(title), alerts.scrub(text)
    out = {}
    for name, ch in cfg['channels'].items():
        if (channels and name not in channels) or (not channels and not ch['enabled']): continue
        try: ctx.channels.send(name, ch, title, text); out[name] = None
        except AlertFail as e: out[name] = str(e)
        except Exception as e: out[name] = type(e).__name__   # noqa: BLE001
        auth.alert_add(key, event, name, out[name] is None, summary=title, error=out[name])
    return out


# ------------------------------------------------------------------ page (admin)
def view(ctx):
    try: services = ctx.warehouse.services()
    except Exception: services = []   # noqa: BLE001  database not open yet
    return dict(alerts.public(alerts.load(ctx.cfg)), events_all=list(alerts.EVENTS), spike_all=list(alerts.SPIKE), services=services,
                history=ctx.auth.alert_list(30))


def update(ctx, body):
    """Merge page input (empty credential = unchanged, `clear` = erase), validate, write to .env. -> new settings."""
    try: cfg = alerts.merge(alerts.load(ctx.cfg), body)
    except (TypeError, ValueError): raise Fail('invalid_parameter', 'Invalid notification settings.', 400) from None
    settings_service.write_alerts(ctx, cfg)
    return cfg


def send_test(ctx, channel):
    """Test message to one channel using the SAVED settings. Send failure -> Fail 502."""
    if channel not in ctx.channels.names: raise Fail('invalid_parameter', 'Unknown channel.', 400)
    cfg = alerts.load(ctx.cfg)
    alerts.validate(cfg)
    ch = cfg['channels'][channel]
    if not all(ch[k] for k in alerts.TEST_NEEDS[channel]): raise Fail('alert_not_configured', "Fill in and save this channel's settings first.", 400)
    r = deliver(ctx, cfg, f'test:{channel}:{time.time()}', 'test', alerts._t(cfg, 'test'), alerts._t(cfg, 'test_text'), channels=[channel], force=True)
    if r.get(channel): raise Fail('alert_send_failed', f'Failed to send to {channel}: {r[channel]}.', 502)
    return dict(sent=True, channel=channel)


# ------------------------------------------------------------------ automatic
class Notifier:
    def __init__(self, ctx):
        self.ctx, self._lock = ctx, threading.Lock()

    def _cfg(self): return alerts.load(self.ctx.cfg)

    def _bg(self, fn, *a):
        threading.Thread(target=self._safe, args=(fn, *a), name='alerts', daemon=True).start()

    def _safe(self, fn, *a):
        with self._lock:
            try: fn(*a)
            except Exception: pass   # noqa: BLE001  notifications must not bring the server down; send errors are recorded in alert_log

    def after_ingest(self, result, error=None): self._bg(self._after_ingest, result, error)

    def _after_ingest(self, result, error):
        cfg = self._cfg()
        if not alerts.active(cfg): return
        if ev := alerts.ingest_failed(cfg, result, error): deliver(self.ctx, cfg, ev[0], 'ingest_failed', ev[1], ev[2])
        if error or not result: return
        changed = sorted(result.get('folders_changed') or [])
        if not changed: return
        w = self.ctx.warehouse
        newest = w.newest_folder()
        floor = (datetime.date.fromisoformat(newest) - datetime.timedelta(days=2)).isoformat()
        crs = self.ctx.cfg.attack_rules == 'crs'
        for f in (x for x in changed if x >= floor):   # old folders that are re-ingested do not trigger notifications
            for ev, key, title, text in alerts.folder_events(cfg, f, w.folder_facts(f, crs)): deliver(self.ctx, cfg, key, ev, title, text)

    def after_sync(self, res): self._bg(self._after_sync, res)

    def _after_sync(self, res):
        cfg = self._cfg()
        if alerts.active(cfg) and (ev := alerts.sync_failed(cfg, res)): deliver(self.ctx, cfg, ev[0], 'sync_failed', ev[1], ev[2])

    def check_missing(self, now_utc=None):
        """Folder dated today (WIB) still missing after `missing_hour` -> once per day."""
        cfg = self._cfg()
        if not alerts.active(cfg) or not cfg['events']['folder_missing']: return None
        wib = (now_utc or datetime.datetime.now(datetime.timezone.utc)) + datetime.timedelta(hours=7)
        if wib.hour < int(cfg['missing_hour']): return None
        ev = alerts.folder_missing(cfg, wib, self.ctx.warehouse.newest_folder())
        return ev and deliver(self.ctx, cfg, ev[0], 'folder_missing', ev[1], ev[2])

    def start(self):
        self._stop = threading.Event()
        def loop():
            while not self._stop.wait(3600):
                self._safe(self.check_missing)
        threading.Thread(target=loop, name='alerts-hourly', daemon=True).start()

    def stop(self):
        if getattr(self, '_stop', None): self._stop.set()
