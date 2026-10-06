"""Pemicu ingest, penurunan ulang, dan penghapusan folder (TRD §5.5). Ingest berjalan DI DALAM proses API (K1)."""
import json
import threading
from typing import Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from .. import ingest
from .common import DATE, ApiError, client_ip, require_admin, require_admin_or_job

router = APIRouter(prefix='/api/admin')


class IngestManager:
    """Menjalankan ingest di thread latar atas kursor DuckDB milik proses ini; satu pada satu waktu."""

    def __init__(self, app):
        self.app, self._lock, self.thread = app, threading.Lock(), None
        self.state = dict(running=False, phase=None, done=0, total=0, folder=None, started_by=None, last=None, error=None)

    def start(self, folder=None, force=False, by=None):
        with self._lock:
            if self.state['running']: raise ApiError(409, 'ingest_running', 'Ingest sedang berjalan.')
            self.state.update(running=True, phase='pindai', done=0, total=0, folder=folder, started_by=by, error=None)
        self.thread = threading.Thread(target=self._run, args=(folder, force), name='ingest', daemon=True)
        self.thread.start()

    def _progress(self, phase, **k): self.state.update(phase=phase, **{x: k[x] for x in ('done', 'total', 'folder') if x in k})

    def _run(self, folder, force):
        cur = self.app.state.con.cursor()
        try:
            r = ingest.run(self.app.state.cfg, cur, folder=folder, force=force, progress=self._progress)
            self.state['last'] = {k: r[k] for k in ('run_id', 'status', 'files_seen', 'files_changed', 'files_parsed', 'files_removed', 'files_failed',
                                                    'folders_changed', 'folders_recorrelated', 'warnings', 'seconds')}
        except ingest.Busy: self.state['error'] = 'Ingest lain sedang berjalan.'
        except Exception as e:  # noqa: BLE001  galat dilaporkan lewat status, proses API tetap hidup
            self.state['error'] = f'{type(e).__name__}: {e}'
        finally:
            cur.close(); self.state.update(running=False, phase=None)

    def wait(self, timeout=None):
        if self.thread: self.thread.join(timeout)


class IngestBody(BaseModel):
    folder: Optional[str] = None
    force: bool = False


class FolderBody(BaseModel):
    folder: Optional[str] = None


def _folder(value, required=False):
    if value is None and not required: return None
    if not isinstance(value, str) or not DATE.fullmatch(value): raise ApiError(400, 'invalid_parameter', 'folder harus berbentuk YYYY-MM-DD.')
    return value


def _audit(request, who, action, detail):
    request.app.state.auth.audit(action, getattr(request.state, 'user', None), f"{detail or ''} oleh {who['username']}".strip(), client_ip(request))


@router.post('/ingest', status_code=202)
def start_ingest(request: Request, body: IngestBody = IngestBody(), who=Depends(require_admin_or_job)):
    folder = _folder(body.folder)
    request.app.state.ingest.start(folder, body.force, who['username'])
    _audit(request, who, 'ingest.start', f"folder={folder or 'semua'} force={body.force}")
    return dict(started=True)


@router.get('/ingest/status')
def ingest_status(request: Request, who=Depends(require_admin_or_job)):
    """Status di memori + ingest terakhir yang selesai dari database (bertahan setelah server dimulai ulang; waktu UTC)."""
    cur = request.app.state.con.cursor()
    try:
        r = cur.execute("""SELECT started_at, finished_at, status, files_seen, files_changed, message FROM ingest_run
                          WHERE finished_at IS NOT NULL ORDER BY run_id DESC LIMIT 1""").fetchone()
    finally: cur.close()
    last_run = r and dict(started_at=str(r[0].replace(microsecond=0)), finished_at=str(r[1].replace(microsecond=0)), status=r[2], files_seen=r[3], files_changed=r[4],
                          warnings=json.loads(r[5]) if r[5] else [])
    return dict(request.app.state.ingest.state, last_run=last_run)


def _exclusive(request, fn):
    """derive/forget tidak boleh berjalan bersamaan dengan ingest."""
    if request.app.state.ingest.state['running'] or not ingest._lock.acquire(blocking=False):
        raise ApiError(409, 'ingest_running', 'Ingest sedang berjalan; coba lagi setelah selesai.')
    cur = request.app.state.con.cursor()
    try: return fn(cur)
    finally: cur.close(); ingest._lock.release()


@router.post('/derive')
def derive(request: Request, body: FolderBody = FolderBody(), admin=Depends(require_admin)):
    folder = _folder(body.folder)
    done = _exclusive(request, lambda cur: ingest.derive_all(cur, folder))
    _audit(request, admin, 'derive', f"folder={folder or 'semua'}")
    return dict(folders=done)


@router.post('/forget')
def forget(body: FolderBody, request: Request, admin=Depends(require_admin)):
    folder = _folder(body.folder, required=True)
    n = _exclusive(request, lambda cur: ingest.forget(cur, folder))
    if not n: raise ApiError(404, 'not_found', 'Folder tidak ditemukan.')
    _audit(request, admin, 'forget', f'folder={folder} ({n} file)')
    return dict(folder=folder, files=n)
