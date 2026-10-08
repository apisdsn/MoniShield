"""Ingest and folder management (TRD §3, §5.5). Ingest runs INSIDE the server process (K1), one at a time, in a
background thread; derive/delete folder hold the same lock so they never run alongside ingest."""
import datetime, threading, time

from monishield.domain.errors import Busy, Fail


def now(after_seconds=0):
    """UTC time (no zone, whole seconds) for status, like other time fields in the API."""
    t = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None, microsecond=0) + datetime.timedelta(seconds=after_seconds)
    return str(t)


class IngestService:
    """Runs ingest (ctx.warehouse) in a background thread; one at a time. Afterwards: read-only copy + notifications."""

    def __init__(self, ctx):
        self.ctx, self._lock, self.thread = ctx, threading.Lock(), None
        self.state = dict(running=False, phase=None, done=0, total=0, folder=None, started_by=None, last=None, error=None)

    def start(self, folder=None, force=False, by=None):
        with self._lock:
            if self.state['running']: raise Busy('Ingest is running.')
            self.state.update(running=True, phase='scan', done=0, total=0, folder=folder, started_by=by, error=None)
        self.thread = threading.Thread(target=self._run, args=(folder, force), name='ingest', daemon=True)
        self.thread.start()

    def run_blocking(self, folder, by, wait_seconds=1800):
        """Run ingest of one folder in the caller's thread (S3 import, upload), after other ingests finish. -> summary."""
        t0 = time.time()
        while True:
            with self._lock:
                if not self.state['running']:
                    self.state.update(running=True, phase='scan', done=0, total=0, folder=folder, started_by=by, error=None); break
            if time.time() - t0 > wait_seconds: raise Busy('Another ingest is taking too long to finish.')
            time.sleep(1)
        self._run(folder, False)
        if self.state['error']: raise RuntimeError(self.state['error'])
        return self.state['last']

    def _progress(self, phase, **k): self.state.update(phase=phase, **{x: k[x] for x in ('done', 'total', 'folder') if x in k})

    def _run(self, folder, force):
        try:
            r = self.ctx.warehouse.ingest(folder, force, self._progress)
            self.state['last'] = {k: r[k] for k in ('run_id', 'status', 'files_seen', 'files_changed', 'files_parsed', 'files_removed', 'files_failed',
                                                    'folders_changed', 'folders_recorrelated', 'warnings', 'seconds')}
            self.snapshot()
            self.ctx.alerts.after_ingest(r)   # notifications (background thread; does not hold up ingest)
        except Busy: self.state['error'] = 'Another ingest is running.'
        except Exception as e:  # noqa: BLE001  error reported through the status, the server process stays alive
            self.state['error'] = f'{type(e).__name__}: {e}'
            self.ctx.alerts.after_ingest(None, self.state['error'])
        finally:
            self.state.update(running=False, phase=None)

    def snapshot(self, missing_only=False):
        """Refresh the DuckDB read-only copy for DbGate (when S4_DUCKDB_SNAPSHOT). Failure -> recorded in the status, ingest still succeeds."""
        w = self.ctx.warehouse
        if not w.snapshot_wanted(missing_only): return
        try: w.snapshot(); self.ctx.snapshot_error = None
        except Exception as e: self.ctx.snapshot_error = f'{type(e).__name__}: {e}'   # noqa: BLE001

    def wait(self, timeout=None):
        if self.thread: self.thread.join(timeout)

    def status(self):
        """In-memory status + last finished ingest (survives a server restart; UTC times) + new folders +
        S3 sync summary (for the Sync data button in the page header)."""
        m = self.ctx.imports
        last = m.watch.get('last') or {}
        s3 = dict(enabled=bool(m.watch_sources()[0]), running=bool(m.state['running'] and m.state.get('mode') == 'sync'), phase=m.state['phase'],
                  done=m.state['done'], total=m.state['total'], last_at=last.get('at'), last_imported=last.get('imported', []) + last.get('rechecked', []),
                  last_errors=last.get('errors', []))
        return dict(self.state, last_run=self.ctx.warehouse.last_run(), new_folders=new_folders(self.ctx),
                    snapshot_error=getattr(self.ctx, 'snapshot_error', None), s3=s3)


# ------------------------------------------------------------------ folders (owner request 2026-10-07: manage folders)
def new_folders(ctx):
    """Date folders in the log folder / inbox that are not yet in the database (and not ignored)."""
    w = ctx.warehouse
    return ctx.logfolders.new_folders(w.known_folders() | w.ignored())


def _exclusive(ctx):
    if ctx.ingest.state['running']: raise Busy('Ingest is running; try again after it finishes.')
    return ctx.warehouse.exclusive()


def derive(ctx, folder=None):
    with _exclusive(ctx) as w: return w.derive_all(folder)


def forget(ctx, folder):
    with _exclusive(ctx) as w: n = w.forget(folder)
    if not n: raise Fail('not_found', 'Folder not found.', 404)
    return n


def folders(ctx):
    """All folders known to the dashboard, present on disk, or ignored."""
    rows_db, ign = ctx.warehouse.folder_table()
    in_log, in_inbox = ctx.logfolders.dates()
    rows = []
    for f in sorted(set(rows_db) | set(ign) | in_log | in_inbox, reverse=True):
        log, inbox = ctx.logfolders.on_disk(f)
        if f not in rows_db and f not in ign and not (log or inbox): continue   # empty date folder on disk
        rows.append(dict(folder=f, in_db=f in rows_db, **(rows_db.get(f) or dict(lines=0, files=0, files_corrupt=0)), log=log, inbox=inbox,
                         ignored=f in ign, ignored_by=(ign.get(f) or {}).get('by'), ignored_at=(ign.get(f) or {}).get('at')))
    return dict(rows=rows, log_dir_readonly=True)


def delete_folder(ctx, folder, delete_inbox, by):
    """Delete a folder's data from the dashboard. Inbox files are deleted too when requested; the main log folder is read-only,
    so if its files are still there (or automatic S3 sync is on) the folder is recorded as "ignored" so ingest/sync
    does not bring it back."""
    lf = ctx.logfolders
    if not lf.inbox_ok(folder): raise Fail('invalid_parameter', 'invalid folder.', 400)
    with _exclusive(ctx) as w:
        n = w.forget(folder)
        inbox_deleted = bool(delete_inbox) and lf.remove_inbox(folder)
        # still on disk, or automatic S3 sync on (the folder would be downloaded again from S3): recorded as "ignored"
        ignored = any(lf.on_disk(folder)) or ctx.imports.watch_config()['enabled']
        if ignored: w.ignore(folder, by)
        ctx.ingest.snapshot()
    if not n and not inbox_deleted and not ignored: raise Fail('not_found', 'Folder not found.', 404)
    return dict(folder=folder, files=n, inbox_deleted=inbox_deleted, ignored=ignored)


def restore_folder(ctx, folder):
    """Undo "ignored": the next ingest/sync brings the folder in again."""
    if not ctx.warehouse.unignore(folder): raise Fail('not_found', 'Folder is not ignored.', 404)
    return dict(folder=folder, restored=True)
