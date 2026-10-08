"""Admin routes: ingest, re-derive, folder management (TRD §5.5) and S3 import (TRD §3.8). The work happens in the
application layer (monishield/application/ingest_service.py, import_service.py); these routes check role + parameters, then
write the audit log."""
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel

from monishield.application import ingest_service
from .common import DATE, ApiError, client_ip, require_admin, require_admin_or_job

router = APIRouter(prefix='/api/admin')


class IngestBody(BaseModel):
    folder: Optional[str] = None
    force: bool = False


class FolderBody(BaseModel):
    folder: Optional[str] = None


def _folder(value, required=False):
    if value is None and not required: return None
    if not isinstance(value, str) or not DATE.fullmatch(value): raise ApiError(400, 'invalid_parameter', 'folder must be in YYYY-MM-DD form.')
    return value


def _audit(request, who, action, detail):
    request.app.state.auth.audit(action, getattr(request.state, 'user', None), f"{detail or ''} by {who['username']}".strip(), client_ip(request))


@router.post('/ingest', status_code=202)
def start_ingest(request: Request, body: IngestBody = IngestBody(), who=Depends(require_admin_or_job)):
    folder = _folder(body.folder)
    request.app.state.ingest.start(folder, body.force, who['username'])
    _audit(request, who, 'ingest.start', f"folder={folder or 'all'} force={body.force}")
    return dict(started=True)


@router.get('/ingest/status')
def ingest_status(request: Request, who=Depends(require_admin_or_job)):
    return request.app.state.ingest.status()


@router.post('/derive')
def derive(request: Request, body: FolderBody = FolderBody(), admin=Depends(require_admin)):
    folder = _folder(body.folder)
    done = ingest_service.derive(request.app.state, folder)
    _audit(request, admin, 'derive', f"folder={folder or 'all'}")
    return dict(folders=done)


class DeleteBody(BaseModel):
    delete_inbox: bool = True   # also delete the log files in the inbox (from S3 import); the main log folder is never deleted


@router.get('/folders')
def folders_list(request: Request, admin=Depends(require_admin)):
    """Folder management (owner request 2026-10-07): every folder known to the dashboard, on disk, or ignored."""
    return ingest_service.folders(request.app.state)


@router.post('/folders/{folder}/delete')
def folder_delete(folder: str, request: Request, body: DeleteBody = DeleteBody(), admin=Depends(require_admin)):
    r = ingest_service.delete_folder(request.app.state, _folder(folder, required=True), body.delete_inbox, admin['username'])
    _audit(request, admin, 'folder.delete', f"folder={folder} ({r['files']} data files{'; inbox deleted' if r['inbox_deleted'] else ''}{'; ignored' if r['ignored'] else ''})")
    return r


@router.post('/folders/{folder}/restore')
def folder_restore(folder: str, request: Request, admin=Depends(require_admin)):
    r = ingest_service.restore_folder(request.app.state, _folder(folder, required=True))
    _audit(request, admin, 'folder.restore', f'folder={folder}')
    return r


@router.post('/forget')
def forget(body: FolderBody, request: Request, admin=Depends(require_admin)):
    folder = _folder(body.folder, required=True)
    n = ingest_service.forget(request.app.state, folder)
    _audit(request, admin, 'forget', f'folder={folder} ({n} files)')
    return dict(folder=folder, files=n)


# ------------------------------------------------------------------ S3 import (TRD §3.8, Stage 19)
class WatchBody(BaseModel):
    url: str = ''
    minutes: int = 60
    enabled: bool = True


class ImportBody(BaseModel):
    url: str = ''
    dry_run: bool = False


class CredBody(BaseModel):
    access_key_id: str = ''
    secret_access_key: str = ''
    session_token: str = ''


@router.post('/import', status_code=202)
def start_import(request: Request, body: ImportBody = ImportBody(), who=Depends(require_admin_or_job)):
    job = request.app.state.imports.start(body.url, body.dry_run, who['username'])
    _audit(request, who, 'import.start', f"#{job} {body.url[:300]}{' (dry run)' if body.dry_run else ''}")
    return dict(job_id=job)


@router.put('/import/watch')
def set_watch(body: WatchBody, request: Request, admin=Depends(require_admin)):
    """Set up automatic S3 sync from the UI: S3 parent folder address (s3://bucket/prefix/), interval, on/off. Admin only."""
    m = request.app.state.imports
    w = m.set_watch(body.url, body.minutes, body.enabled)
    _audit(request, admin, 'import.watch', f"{'on' if w['enabled'] else 'off'}: {w['url'][:300]} every {w['minutes']} minutes")
    return m.view()['watch']


@router.post('/import/sync', status_code=202)
def sync_s3(request: Request, who=Depends(require_admin_or_job)):
    """Check the S4_S3_WATCH prefix now ("Check S3 now" button, or cron with the machine token)."""
    request.app.state.imports.sync(who['username'])
    _audit(request, who, 'import.sync', 'check S3 for new folders')
    return dict(started=True)


@router.get('/import')
def import_overview(request: Request, limit: int = Query(20, ge=1, le=100), admin=Depends(require_admin)):
    return dict(request.app.state.imports.view(), jobs=request.app.state.auth.job_list(limit))


@router.get('/import/{job_id}')
def import_job(job_id: int, request: Request, who=Depends(require_admin_or_job)):
    return request.app.state.imports.job(job_id)


@router.post('/import/credentials')
def set_credentials(body: CredBody, request: Request, admin=Depends(require_admin)):
    """Only an admin with a session (not the machine token). Values are kept in process memory only and never returned."""
    creds = request.app.state.imports.creds
    creds.set(body.access_key_id, body.secret_access_key, body.session_token)
    _audit(request, admin, 'import.credentials.set', 'temporary credentials pasted (memory)')
    return dict(credentials=creds.status())


@router.delete('/import/credentials')
def clear_credentials(request: Request, admin=Depends(require_admin)):
    creds = request.app.state.imports.creds
    creds.clear()
    _audit(request, admin, 'import.credentials.clear', 'temporary credentials removed')
    return dict(credentials=creds.status())
