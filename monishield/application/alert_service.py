"""Notifications: when they are sent and where to (rules + texts in monishield/domain/alerts.py, channels in
monishield/infrastructure/notify_channels.py). Called by the ingest / import services after a job finishes, and by a
scheduler every 10 minutes (folder not arrived, the daily report from its hour on). All sending happens in a background thread: ingest and the page never wait for Telegram/SMTP.

PROJECT RULE: user IP addresses must not be sent to third-party services — texts are cleaned with `alerts.scrub` here,
right before being handed to the channel.
"""
import datetime, threading, time

from monishield.application import settings_service, sources
from monishield.domain import alerts, timezone
from monishield.domain.alerts import AlertFail, AlertUnconfirmed
from monishield.domain.errors import Fail


def deliver(ctx, cfg, key, event, title, text, channels=None, force=False, notes=None):
    """Send to all enabled channels (or `channels`). Already succeeded for `key` -> skipped (unless force).
    -> {channel: None (success) | error message}. Errors never contain credentials. A send the channel received but did not
    confirm counts as success (sending again made duplicates); its note goes to the history and to `notes` when given."""
    auth = ctx.auth
    if not force and auth.alert_seen(key): return {}
    title, text = alerts.scrub(title), alerts.scrub(text)
    out = {}
    for name, ch in cfg['channels'].items():
        if (channels and name not in channels) or (not channels and not ch['enabled']): continue
        note = None
        try: ctx.channels.send(name, dict(ch, lang=cfg['lang'], dashboard_url=cfg.get('dashboard_url')) if name == 'email' else ch, title, text); out[name] = None
        except AlertUnconfirmed as e: out[name], note = None, str(e)
        except AlertFail as e: out[name] = str(e)
        except Exception as e: out[name] = type(e).__name__   # noqa: BLE001
        if note and notes is not None: notes[name] = note
        auth.alert_add(key, event, name, out[name] is None, summary=title, error=out[name] or note)
    return out


# ------------------------------------------------------------------ page (admin)
def view(ctx):
    try: services = ctx.warehouse.services()
    except Exception: services = []   # noqa: BLE001  database not open yet
    try: folders = ctx.alerts.report_folders()
    except Exception: folders = []   # noqa: BLE001
    return dict(alerts.public(alerts.load(ctx.cfg)), events_all=list(alerts.EVENTS), spike_all=list(alerts.SPIKE), services=services,
                history=ctx.auth.alert_list(30), report_folders=folders)


def update(ctx, body):
    """Merge page input (empty credential = unchanged, `clear` = erase), validate, write to .env. -> new settings."""
    try: cfg = alerts.merge(alerts.load(ctx.cfg), body)
    except (TypeError, ValueError): raise Fail('invalid_parameter', 'Invalid notification settings.', 400) from None
    settings_service.write_alerts(ctx, cfg)
    return cfg


def send_test(ctx, channel):
    """Test message to one channel using the SAVED settings. Send failure -> Fail 502 (answered as 424)."""
    if channel not in ctx.channels.names: raise Fail('invalid_parameter', 'Unknown channel.', 400)
    cfg = alerts.load(ctx.cfg)
    alerts.validate(cfg)
    ch = cfg['channels'][channel]
    if not all(ch[k] for k in alerts.TEST_NEEDS[channel]): raise Fail('alert_not_configured', "Fill in and save this channel's settings first.", 400)
    notes = {}
    r = deliver(ctx, cfg, f'test:{channel}:{time.time()}', 'test', alerts._t(cfg, 'test'), alerts._t(cfg, 'test_text'), channels=[channel], force=True,
                notes=notes)
    if r.get(channel): raise Fail('alert_send_failed', f'Failed to send to {channel}: {r[channel]}.', 502)
    return dict(sent=True, channel=channel, note=notes.get(channel))


REPORT_PENDING = 7   # "send the reports not sent yet": the latest 7 folders at most


def send_report(ctx, folder=None, source=sources.S3, pending=False):
    """Daily report on request (page buttons): one folder, sent again even when it already went out, or with `pending`
    every folder among the latest REPORT_PENDING whose report has not gone out yet (oldest first).
    -> dict(sent=[dict(folder, source)], failed=[dict(folder, source, errors={channel: message})])."""
    if not sources.valid(source): raise Fail('invalid_parameter', 'Unknown source.', 400)
    cfg = alerts.load(ctx.cfg)
    alerts.validate(cfg)
    if not alerts.active(cfg): raise Fail('alert_not_configured', 'Turn on and save at least one channel first.', 400)
    n = ctx.alerts
    if pending:
        rows = n.report_folders(REPORT_PENDING)
        main = sources.S3 if any(r['source'] == sources.S3 for r in rows) else sources.KAFKA
        todo = [(r['folder'], r['source']) for r in rows if r['source'] == main and not r['sent']][::-1]
    else:
        if folder not in n.folders(source): raise Fail('not_found', 'Log folder not found.', 404)
        todo = [(folder, source)]
    out = dict(sent=[], failed=[])
    with n._lock:   # not at the same time as the background notifications
        for f, s in todo:
            r = n.send_report(f, s, force=not pending, cfg=cfg)
            errs = {ch: e for ch, e in r.items() if e}
            if len(errs) < len(r): out['sent'].append(dict(folder=f, source=s))   # at least one channel got it
            if errs: out['failed'].append(dict(folder=f, source=s, errors=errs))
    return out


def _local(now_utc=None): return (now_utc or datetime.datetime.now(datetime.timezone.utc)) + timezone.current().delta   # S4_TIMEZONE_OFFSET


# ------------------------------------------------------------------ automatic
class Notifier:
    RETRY = 3600   # a scheduled report that failed on every channel is tried again after an hour, not every 10 minutes

    def __init__(self, ctx):
        self.ctx, self._lock, self._tried = ctx, threading.Lock(), {}

    def _cfg(self): return alerts.load(self.ctx.cfg)

    def _bg(self, fn, *a):
        threading.Thread(target=self._safe, args=(fn, *a), name='alerts', daemon=True).start()

    def _safe(self, fn, *a):
        with self._lock:
            try: fn(*a)
            except Exception: pass   # noqa: BLE001  notifications must not bring the server down; send errors are recorded in alert_log

    def after_ingest(self, result, error=None, src=None): self._bg(self._after_ingest, result, error, src or self.ctx)

    @staticmethod
    def _named(src, key, title):
        """Notifications come from both sources (owner request 2026-10-23): the title names the source, and the Kafka key is its
        own so S3 and Kafka never silence each other. S3 keys stay as they were (no repeats of what was already sent)."""
        return (key if src.source == sources.S3 else f'{key}@{src.source}'), f'{title} ({sources.LABEL[src.source]})'

    def _after_ingest(self, result, error, src):
        cfg = self._cfg()
        if not alerts.active(cfg): return
        if ev := alerts.ingest_failed(cfg, result, error):
            key, title = self._named(src, ev[0], ev[1])
            deliver(self.ctx, cfg, key, 'ingest_failed', title, ev[2])
        if error or not result: return
        changed = sorted(result.get('folders_changed') or [])
        if not changed: return
        w = src.warehouse
        newest = w.newest_folder()
        # S3: the newest three folders. Kafka: only the day in progress, so its first ingest does not announce old days
        floor = newest if src.source != sources.S3 else (datetime.date.fromisoformat(newest) - datetime.timedelta(days=2)).isoformat()
        crs = self.ctx.cfg.attack_rules == 'crs'
        for f in (x for x in changed if x >= floor):   # old folders that are re-ingested do not trigger notifications
            facts = w.folder_facts(f, crs)
            for ev, key, title, text in alerts.folder_events(cfg, f, facts, src.source):
                key, title = self._named(src, key, title)
                deliver(self.ctx, cfg, key, ev, title, text)
        # a new folder after the report hour gets its daily report right away (before it: at the report hour)
        if src.source == sources.S3: self.daily_report(seconds=result.get('seconds'))

    # ------------------------------------------------------------------ daily report
    def _src(self, source): return (getattr(self.ctx, 'sources', None) or {}).get(source) or self.ctx

    def _has(self, source): return source == sources.S3 or source in (getattr(self.ctx, 'sources', None) or {})

    def folders(self, source):
        """Folders a daily report can be sent for, newest first. Kafka: complete ones only (the folder dated tomorrow is filling up)."""
        if not self._has(source): return []
        try: fs = sorted(self._src(source).warehouse.folder_table()[0], reverse=True)
        except Exception: return []   # noqa: BLE001  database not open
        if source == sources.KAFKA: fs = [f for f in fs if f <= _local().date().isoformat()]
        return fs

    def report_folders(self, limit=14):
        """Latest folders of each source with whether their daily report already went out (page list)."""
        out = []
        for s in sources.SOURCES:
            for f in self.folders(s)[:limit]:
                out.append(dict(folder=f, source=s, sent=self.ctx.auth.alert_seen(self._named(self._src(s), alerts.summary_key(f), '')[0])))
        return out

    def send_report(self, folder, source=sources.S3, force=False, cfg=None, seconds=None):
        """Daily report of one folder to the enabled channels. Already sent and not `force` -> {} (nothing sent)."""
        cfg = cfg or self._cfg()
        src = self._src(source)
        if not force and self.ctx.auth.alert_seen(self._named(src, alerts.summary_key(folder), '')[0]): return {}
        facts = src.warehouse.folder_facts(folder, self.ctx.cfg.attack_rules == 'crs')
        on = dict(cfg, events=dict(cfg['events'], summary=True))   # a report asked for on the page goes out even with the event off
        key, title, text = alerts.summary(on, folder, facts, self._report_extra(folder, seconds, source), source)
        key, title = self._named(src, key, title)
        return deliver(self.ctx, cfg, key, 'summary', title, text, force=force)

    def daily_report(self, now_utc=None, seconds=None):
        """Scheduled daily report: from the report hour (local time) on, the newest complete folder, once per folder."""
        cfg = self._cfg()
        local = _local(now_utc)
        if not alerts.active(cfg) or not alerts.report_due(cfg, local): return None
        kafka = self.folders(sources.KAFKA) if self._has(sources.KAFKA) else []
        target = alerts.report_target(self.ctx.warehouse.newest_folder(), kafka, local.date())
        if not target: return None
        key = self._named(self._src(target[1]), alerts.summary_key(target[0]), '')[0]
        if time.monotonic() - self._tried.get(key, -self.RETRY) < self.RETRY: return None
        r = self.send_report(*target, cfg=cfg, seconds=seconds)
        if r and all(r.values()): self._tried[key] = time.monotonic()   # failed on every channel: next try in an hour
        return r

    def _report_extra(self, folder, seconds=None, source=sources.S3):
        """Ingest, Kafka, backup and S3 sync facts for the daily report (alerts.summary). Missing parts are left out."""
        ctx, out = self.ctx, dict(seconds=seconds)
        try:
            k = ctx.kafka.status()
            if k.get('configured') and source == sources.S3:
                out['kafka_state'] = k.get('state') if k.get('enabled') else 'off'
                kctx = (getattr(ctx, 'sources', None) or {}).get(sources.KAFKA)
                out['kafka'] = kctx.warehouse.folder_totals(folder) if kctx else None
        except Exception: pass   # noqa: BLE001  the report goes out without the Kafka part
        try:
            last = ctx.backup.last
            if last: out['backup'] = dict(ok=bool(last.get('ok')), day=last.get('day'), bytes=last.get('bytes'))
            elif (done := ctx.backups.list()): out['backup'] = dict(ok=True, day=done[0]['day'], bytes=done[0]['bytes'])
        except Exception: pass   # noqa: BLE001
        try:
            wc, last = ctx.imports.watch_config(), ctx.imports.watch.get('last')
            out['sync'] = dict(enabled=bool(wc.get('enabled') and wc.get('minutes')),
                               ok=None if not last else not (last.get('errors') or last.get('failed')))
        except Exception: pass   # noqa: BLE001
        return out

    def after_sync(self, res): self._bg(self._after_sync, res)

    def _after_sync(self, res):
        cfg = self._cfg()
        if alerts.active(cfg) and (ev := alerts.sync_failed(cfg, res)): deliver(self.ctx, cfg, ev[0], 'sync_failed', ev[1], ev[2])

    def check_missing(self, now_utc=None):
        """Folder dated today (local time) still missing after `missing_hour` -> once per day."""
        cfg = self._cfg()
        if not alerts.active(cfg) or not cfg['events']['folder_missing']: return None
        local = _local(now_utc)
        if local.hour < int(cfg['missing_hour']): return None
        ev = alerts.folder_missing(cfg, local, self.ctx.warehouse.newest_folder())
        return ev and deliver(self.ctx, cfg, ev[0], 'folder_missing', ev[1], ev[2])

    def start(self):
        self._stop = threading.Event()
        def loop():
            while not self._stop.wait(600):
                self._safe(self.check_missing)
                self._safe(self.daily_report)
        threading.Thread(target=loop, name='alerts-schedule', daemon=True).start()

    def stop(self):
        if getattr(self, '_stop', None): self._stop.set()
