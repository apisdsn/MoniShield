"""Import of log folders from S3 (TRD §3.8, Stage 19) and automatic sync from the S3 parent folder (owner request
2026-10-07). One import at a time, in a background thread: download (ctx.s3) then ingest that folder (ctx.ingest)."""
import datetime, threading

from monishield.application import settings_service
from monishield.application.ingest_service import now
from monishield.domain import s3_import
from monishield.domain.errors import Busy, Fail
from monishield.domain.s3_import import ImportFail

WATCH_MINUTES = (5, 15, 30, 60, 180, 360, 720, 1440)
SYNC_BY = '(automatic S3 sync)'


class ImportService:
    """Object plans per job are kept in memory (last 20); job history is in the account database (ctx.auth)."""

    def __init__(self, ctx):
        self.ctx, self._lock = ctx, threading.Lock()
        self.state = dict(running=False, job_id=None, phase=None, done=0, total=0, mode=None)   # mode: 'manual' (link) / 'sync' (automatic)
        self.plans, self.thread = {}, None   # job_id -> download result
        self.watch = dict(last=None, next_check=None)   # automatic sync: last round result, next schedule (UTC)

    @property
    def creds(self): return self.ctx.s3.creds   # credentials pasted by an admin (process memory) + .env

    def _claim(self, phase, mode):
        with self._lock:
            if self.state['running']: raise Busy('Another import is running; wait until it finishes.', 'import_running')
            self.state.update(running=True, job_id=None, phase=phase, done=0, total=0, mode=mode)

    # -------------------------------------------------------------- import one link
    def start(self, url, dry_run, by):
        bucket, prefix, folder = s3_import.parse_url(self.ctx.cfg, url)   # the link is checked before any connection to AWS
        self.ctx.s3.ready()
        self._claim('list', 'manual')
        try: job = self.ctx.auth.job_create(by, bucket, prefix, folder, 'dry_run' if dry_run else 'running')
        except BaseException: self.state.update(running=False, phase=None); raise
        self.state['job_id'] = job
        self.thread = threading.Thread(target=self._run, args=(job, url, dry_run), name='import', daemon=True)
        self.thread.start()
        return job

    def _progress(self, phase, **k): self.state.update(phase=phase, **{x: k[x] for x in ('done', 'total') if x in k})

    def _run(self, job, url, dry_run):
        try: self._job(job, url, dry_run)
        finally: self.state.update(running=False, phase=None)

    def _job(self, job, url, dry_run):
        """One import job (download then ingest that folder). -> True when finished without error; errors are recorded in the job."""
        auth = self.ctx.auth
        try:
            r = self.ctx.s3.run(url, dry_run=dry_run, progress=self._progress)
            msg = f"{r['take']} objects {'would be fetched' if dry_run else 'fetched'}, {r['skipped']} skipped"
            if r.get('extracted'): msg += f", {r['extracted']} .gz extracted to .log"
            if not dry_run:
                self.state['phase'] = 'ingest'
                ing = self.ctx.ingest.run_blocking(r['folder'], f'import #{job}')
                r['ingest'] = {k: ing[k] for k in ('run_id', 'status', 'files_changed', 'files_failed')}
                msg += f"; ingest #{ing['run_id']}: {ing['files_changed']} files changed"
            msg += ''.join(f'; {w}' for w in r['warnings'])
            self._keep(job, r)
            auth.job_finish(job, 'dry_run' if dry_run else 'done', r['bytes'] if dry_run else r['downloaded_bytes'],
                            r['take'] if dry_run else r['downloaded'], r['skipped'], msg)
            return True
        except ImportFail as e:
            self._keep(job, dict(error=dict(code=e.code, message=e.message)))
            auth.job_finish(job, 'failed', message=f'[{e.code}] {e.message}')   # code in front: the UI translates it (EN)
        except Exception as e:  # noqa: BLE001  error reported through the job status; no secrets (boto messages contain no keys)
            self._keep(job, dict(error=dict(code='import_failed', message=f'{type(e).__name__}: {e}'[:500])))
            auth.job_finish(job, 'failed', message=f'[import_failed] {type(e).__name__}: {e}'[:500])
        return False

    def _keep(self, job, r):
        self.plans[job] = r
        for old in sorted(self.plans)[:-20]: self.plans.pop(old, None)

    def job(self, job_id):
        j = self.ctx.auth.job_get(job_id)
        if not j: raise Fail('not_found', 'Import job not found.', 404)
        live = self.state if self.state['job_id'] == job_id and self.state['running'] else None
        return dict(j, running=bool(live), progress=live, result=self.plans.get(job_id))

    # -------------------------------------------------------------- automatic sync from the S3 parent prefix (S4_S3_WATCH)
    def watch_config(self):
        """Sync settings in effect (.env: S4_S3_WATCH, S4_S3_WATCH_MINUTES, S4_S3_WATCH_ENABLED; the page writes there).
        -> dict(url, minutes, enabled, source='file'|'environment'|None)"""
        cfg = self.ctx.cfg
        return dict(url=cfg.s3_watch, minutes=cfg.s3_watch_minutes, enabled=cfg.s3_watch_enabled and bool(cfg.s3_watch),
                    source=settings_service.source(self.ctx, 's3_watch'))

    def watch_sources(self):
        """-> (list of watched s3://…, configuration error (ImportFail) or None). Empty when sync is off."""
        w = self.watch_config()
        if not w['enabled']: return [], None
        try: return [f's3://{b}/{p}' for b, p in s3_import.parse_watch(self.ctx.cfg, w['url'])], None
        except ImportFail as e: return [], e

    def set_watch(self, url, minutes, enabled):
        """Save settings from the page (first checked against the allowlist, no network) then wake the scheduler:
        when on, the first check runs a few seconds later."""
        url = (url or '').strip()
        if enabled:
            if not url: raise Fail('invalid_watch', 'Enter the S3 parent folder address, e.g. s3://bucket-name/k8s-logs/.', 400)
            try: s3_import.parse_watch(self.ctx.cfg, url)
            except ImportFail as e: raise Fail(e.code, e.message, 400) from None
        if minutes not in WATCH_MINUTES: raise Fail('invalid_parameter', f'Interval must be one of {", ".join(map(str, WATCH_MINUTES))} minutes.', 400)
        settings_service.write_watch(self.ctx, url, minutes, enabled)
        self._kick_loop()
        return self.watch_config()

    def sync(self, by):
        """Check the S3 parent folder now, in a background thread: unknown date folders are imported + ingested."""
        w = self.watch_config()
        try: sources = s3_import.parse_watch(self.ctx.cfg, w['url']) if w['enabled'] else []
        except ImportFail as e: raise Fail(e.code, e.message, 400) from None
        if not sources: raise Fail('watch_disabled', 'Automatic S3 sync is not on: enter the S3 parent folder address in the Import from S3 card (e.g. s3://bucket-name/k8s-logs/).', 400)
        self.ctx.s3.ready()
        self._claim('check', 'sync')
        self.thread = threading.Thread(target=self._sync, args=(sources, by), name='s3-sync', daemon=True)
        self.thread.start()

    def _known(self):
        """Folders already known (database, ignored, log folder, inbox) and inbox folders that came from S3."""
        w, lf = self.ctx.warehouse, self.ctx.logfolders
        known, ign = w.known_folders(), w.ignored()
        in_log, in_inbox = lf.dates()
        from_s3 = lf.from_s3(in_inbox) - ign - in_log
        return known | ign | in_log | in_inbox, from_s3

    def _sync(self, sources, by):
        cfg, auth, s3 = self.ctx.cfg, self.ctx.auth, self.ctx.s3
        res = dict(at=now(), by=by, sources=[], imported=[], rechecked=[], failed=[], waiting=0, errors=[])
        try:
            known, from_s3 = self._known()
            today = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=7)).date()   # folder date = WIB
            seen, todo = set(), []
            for bucket, base in sources:
                try: folders = [f for f in s3.list_folders(bucket, base) if f not in seen]
                except Exception as e:  # noqa: BLE001
                    x = s3.error(e); res['errors'].append(dict(code=x.code, where=f's3://{bucket}/{base}', message=x.message)); continue
                seen.update(folders)
                take, again, waiting = s3_import.pick(folders, known, from_s3, today, cfg.s3_watch_days, cfg.s3_watch_recheck_days, cfg.s3_watch_max_folders)
                res['sources'].append(dict(source=f's3://{bucket}/{base}', folders=len(folders), new=len(take) + waiting))
                res['waiting'] += waiting
                todo += [(bucket, base, f, False) for f in take]
                for f in again:   # recent sync results: downloaded again only when there are new/changed objects
                    try: p = s3.run(f's3://{bucket}/{base}{f}/', dry_run=True)
                    except ImportFail as e: res['errors'].append(dict(code=e.code, where=f, message=e.message)); continue
                    if p['take'] or any(o.get('extract_local') for o in p['objects']): todo.append((bucket, base, f, True))
            for i, (bucket, base, f, again) in enumerate(todo):
                self.state.update(phase='download', done=i, total=len(todo))
                job = auth.job_create(by, bucket, f'{base}{f}/', f, 'running')
                self.state['job_id'] = job
                ok = self._job(job, f's3://{bucket}/{base}{f}/', False)
                (res['failed'] if not ok else res['rechecked'] if again else res['imported']).append(f)
        except Exception as e:  # noqa: BLE001
            x = s3.error(e)
            res['errors'].append(dict(code=x.code, where=None, message=x.message))
        finally:
            self.watch['last'] = res
            self.state.update(running=False, phase=None, job_id=None)
            self.ctx.alerts.after_sync(res)

    def start_watch(self, first=60):
        """Scheduler (always alive; reads the settings every round): first check `first` seconds after server start,
        then every `minutes`. Settings changed from the page -> woken up, next check in ±5 seconds."""
        self._kick, self._stopped = threading.Event(), False
        threading.Thread(target=self._watch_loop, args=(first,), name='s3-watch', daemon=True).start()

    def _kick_loop(self):
        if getattr(self, '_kick', None): self._kick.set()

    def _watch_loop(self, delay):
        while not self._stopped:
            w = self.watch_config()
            if not w['enabled'] or w['minutes'] <= 0:
                self.watch['next_check'] = None
                self._kick.wait(300); self._kick.clear(); delay = 5
                continue
            self.watch['next_check'] = now(delay)
            if self._kick.wait(delay):   # settings changed / server stopping
                self._kick.clear(); delay = 5
                continue
            delay = w['minutes'] * 60
            try: self.sync(SYNC_BY)
            except Fail as e:
                if e.status == 409: delay = 300   # manual import running: try again in 5 minutes
                else: self.watch['last'] = dict(at=now(), by=SYNC_BY, sources=[], imported=[], rechecked=[], failed=[], waiting=0,
                                                errors=[dict(code=e.code, where=None, message=e.message)])

    def stop_watch(self):
        self._stopped = True
        self._kick_loop()

    def wait(self, timeout=None):
        if self.thread: self.thread.join(timeout)

    # -------------------------------------------------------------- import card view
    def view(self):
        cfg = self.ctx.cfg
        sources, problem = self.watch_sources()
        w = self.watch_config()
        watch = dict(enabled=bool(sources), sources=sources, problem=problem and problem.message, problem_code=problem and problem.code, url=w['url'], minutes=w['minutes'], source=w['source'],
                     minute_options=WATCH_MINUTES, days=cfg.s3_watch_days, max_folders=cfg.s3_watch_max_folders, **self.watch)
        return dict(enabled=bool(cfg.import_buckets), library=self.ctx.s3.library_ok(), allowed=s3_import.allowed_examples(cfg), region=cfg.import_region,
                    credentials=self.creds.status(), running=self.state['running'], state=self.state, watch=watch)
