"""Pemicu ingest, penurunan ulang, dan penghapusan folder (TRD §5.5). Ingest berjalan DI DALAM proses API (K1)."""
import json
import threading
import time
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel

from .. import importer, ingest
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

    def run_blocking(self, folder, by, wait_seconds=1800):
        """Jalankan ingest satu folder di thread pemanggil (impor S3), setelah ingest lain selesai. -> ringkasan."""
        t0 = time.time()
        while True:
            with self._lock:
                if not self.state['running']:
                    self.state.update(running=True, phase='pindai', done=0, total=0, folder=folder, started_by=by, error=None); break
            if time.time() - t0 > wait_seconds: raise ApiError(409, 'ingest_running', 'Ingest lain tidak selesai-selesai.')
            time.sleep(1)
        self._run(folder, False)
        if self.state['error']: raise RuntimeError(self.state['error'])
        return self.state['last']

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


# ------------------------------------------------------------------ impor S3 (TRD §3.8, Tahap 19)
class ImportManager:
    """Satu impor pada satu waktu, di thread latar: unduh (importer) lalu ingest folder itu. Rencana objek per job disimpan di memori."""

    def __init__(self, app):
        self.app, self._lock = app, threading.Lock()
        self.creds = importer.Credentials(app.state.cfg)
        self.state = dict(running=False, job_id=None, phase=None, done=0, total=0)
        self.plans, self.thread = {}, None   # job_id -> hasil importer.run (dibatasi 20 terakhir)

    def start(self, url, dry_run, by):
        cfg = self.app.state.cfg
        try: bucket, prefix, folder = importer.parse_url(cfg, url)          # tautan diperiksa sebelum ada koneksi ke AWS
        except importer.ImportFail as e: raise ApiError(e.status, e.code, e.message) from None
        if not self.creds.get()[0]: raise ApiError(400, 'no_credentials', importer.NO_CREDENTIALS)
        with self._lock:
            if self.state['running']: raise ApiError(409, 'import_running', 'Impor lain sedang berjalan; tunggu sampai selesai.')
            self.state.update(running=True, job_id=None, phase='daftar', done=0, total=0)
        try: job = self.app.state.auth.job_create(by, bucket, prefix, folder, 'coba' if dry_run else 'berjalan')
        except BaseException: self.state.update(running=False, phase=None); raise
        self.state['job_id'] = job
        self.thread = threading.Thread(target=self._run, args=(job, url, dry_run, by), name='import', daemon=True)
        self.thread.start()
        return job

    def _progress(self, phase, **k): self.state.update(phase=phase, **{x: k[x] for x in ('done', 'total') if x in k})

    def _run(self, job, url, dry_run, by):
        auth, cfg = self.app.state.auth, self.app.state.cfg
        try:
            r = importer.run(cfg, url, self.creds, dry_run=dry_run, progress=self._progress)
            msg = f"{r['take']} objek {'akan diambil' if dry_run else 'diambil'}, {r['skipped']} dilewati"
            if not dry_run:
                self.state['phase'] = 'ingest'
                ing = self.app.state.ingest.run_blocking(r['folder'], f'impor #{job}')
                r['ingest'] = {k: ing[k] for k in ('run_id', 'status', 'files_changed', 'files_failed')}
                msg += f"; ingest #{ing['run_id']}: {ing['files_changed']} file berubah"
            msg += ''.join(f'; {w}' for w in r['warnings'])
            self._keep(job, r)
            auth.job_finish(job, 'coba' if dry_run else 'selesai', r['bytes'] if dry_run else r['downloaded_bytes'],
                            r['take'] if dry_run else r['downloaded'], r['skipped'], msg)
        except importer.ImportFail as e:
            self._keep(job, dict(error=dict(code=e.code, message=e.message)))
            auth.job_finish(job, 'gagal', message=e.message)
        except Exception as e:  # noqa: BLE001  galat dilaporkan lewat status job; tanpa rahasia (pesan boto tidak memuat kunci)
            self._keep(job, dict(error=dict(code='import_failed', message=f'{type(e).__name__}: {e}'[:500])))
            auth.job_finish(job, 'gagal', message=f'{type(e).__name__}: {e}'[:500])
        finally:
            self.state.update(running=False, phase=None)

    def _keep(self, job, r):
        self.plans[job] = r
        for old in sorted(self.plans)[:-20]: self.plans.pop(old, None)

    def wait(self, timeout=None):
        if self.thread: self.thread.join(timeout)


class ImportBody(BaseModel):
    url: str = ''
    dry_run: bool = False


class CredBody(BaseModel):
    access_key_id: str = ''
    secret_access_key: str = ''
    session_token: str = ''


def _import_view(request):
    m, cfg = request.app.state.imports, request.app.state.cfg
    return dict(enabled=bool(cfg.import_buckets), allowed=importer.allowed_examples(cfg), region=cfg.import_region,
                credentials=m.creds.status(), running=m.state['running'], state=m.state)


@router.post('/import', status_code=202)
def start_import(request: Request, body: ImportBody = ImportBody(), who=Depends(require_admin_or_job)):
    job = request.app.state.imports.start(body.url, body.dry_run, who['username'])
    _audit(request, who, 'import.start', f"#{job} {body.url[:300]}{' (coba)' if body.dry_run else ''}")
    return dict(job_id=job)


@router.get('/import')
def import_overview(request: Request, limit: int = Query(20, ge=1, le=100), admin=Depends(require_admin)):
    return dict(_import_view(request), jobs=request.app.state.auth.job_list(limit))


@router.get('/import/{job_id}')
def import_job(job_id: int, request: Request, who=Depends(require_admin_or_job)):
    m = request.app.state.imports
    j = request.app.state.auth.job_get(job_id)
    if not j: raise ApiError(404, 'not_found', 'Job impor tidak ditemukan.')
    live = m.state if m.state['job_id'] == job_id and m.state['running'] else None
    return dict(j, running=bool(live), progress=live, result=m.plans.get(job_id))


@router.post('/import/credentials')
def set_credentials(body: CredBody, request: Request, admin=Depends(require_admin)):
    """Hanya admin bersesi (bukan token mesin). Nilai disimpan di memori proses saja dan tidak pernah dikembalikan."""
    try: request.app.state.imports.creds.set(body.access_key_id, body.secret_access_key, body.session_token)
    except importer.ImportFail as e: raise ApiError(e.status, e.code, e.message) from None
    _audit(request, admin, 'import.credentials.set', 'kredensial sementara ditempel (memori)')
    return dict(credentials=request.app.state.imports.creds.status())


@router.delete('/import/credentials')
def clear_credentials(request: Request, admin=Depends(require_admin)):
    request.app.state.imports.creds.clear()
    _audit(request, admin, 'import.credentials.clear', 'kredensial sementara dihapus')
    return dict(credentials=request.app.state.imports.creds.status())
