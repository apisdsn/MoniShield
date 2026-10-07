"""Rute admin: ingest, penurunan ulang, kelola folder (TRD §5.5) dan impor S3 (TRD §3.8). Pekerjaannya di lapisan
application (monishield/application/ingest_service.py, import_service.py); rute ini memeriksa peran + parameter, lalu
mencatat audit."""
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
    return request.app.state.ingest.status()


@router.post('/derive')
def derive(request: Request, body: FolderBody = FolderBody(), admin=Depends(require_admin)):
    folder = _folder(body.folder)
    done = ingest_service.derive(request.app.state, folder)
    _audit(request, admin, 'derive', f"folder={folder or 'semua'}")
    return dict(folders=done)


class DeleteBody(BaseModel):
    delete_inbox: bool = True   # hapus juga file log di kotak masuk (hasil impor S3); folder log utama tidak pernah dihapus


@router.get('/folders')
def folders_list(request: Request, admin=Depends(require_admin)):
    """Kelola folder (permintaan pemilik 2026-10-07): semua folder yang dikenal dashboard, di disk, atau diabaikan."""
    return ingest_service.folders(request.app.state)


@router.post('/folders/{folder}/delete')
def folder_delete(folder: str, request: Request, body: DeleteBody = DeleteBody(), admin=Depends(require_admin)):
    r = ingest_service.delete_folder(request.app.state, _folder(folder, required=True), body.delete_inbox, admin['username'])
    _audit(request, admin, 'folder.delete', f"folder={folder} ({r['files']} file data{'; kotak masuk dihapus' if r['inbox_deleted'] else ''}{'; diabaikan' if r['ignored'] else ''})")
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
    _audit(request, admin, 'forget', f'folder={folder} ({n} file)')
    return dict(folder=folder, files=n)


# ------------------------------------------------------------------ impor S3 (TRD §3.8, Tahap 19)
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
    _audit(request, who, 'import.start', f"#{job} {body.url[:300]}{' (coba)' if body.dry_run else ''}")
    return dict(job_id=job)


@router.put('/import/watch')
def set_watch(body: WatchBody, request: Request, admin=Depends(require_admin)):
    """Atur sinkron S3 otomatis dari layar: alamat folder induk (s3://bucket/awalan/), jeda, aktif/mati. Admin saja."""
    m = request.app.state.imports
    w = m.set_watch(body.url, body.minutes, body.enabled)
    _audit(request, admin, 'import.watch', f"{'aktif' if w['enabled'] else 'mati'}: {w['url'][:300]} tiap {w['minutes']} menit")
    return m.view()['watch']


@router.post('/import/sync', status_code=202)
def sync_s3(request: Request, who=Depends(require_admin_or_job)):
    """Periksa awalan S4_S3_WATCH sekarang (tombol "Periksa S3 sekarang", atau cron dengan token mesin)."""
    request.app.state.imports.sync(who['username'])
    _audit(request, who, 'import.sync', 'periksa folder baru di S3')
    return dict(started=True)


@router.get('/import')
def import_overview(request: Request, limit: int = Query(20, ge=1, le=100), admin=Depends(require_admin)):
    return dict(request.app.state.imports.view(), jobs=request.app.state.auth.job_list(limit))


@router.get('/import/{job_id}')
def import_job(job_id: int, request: Request, who=Depends(require_admin_or_job)):
    return request.app.state.imports.job(job_id)


@router.post('/import/credentials')
def set_credentials(body: CredBody, request: Request, admin=Depends(require_admin)):
    """Hanya admin bersesi (bukan token mesin). Nilai disimpan di memori proses saja dan tidak pernah dikembalikan."""
    creds = request.app.state.imports.creds
    creds.set(body.access_key_id, body.secret_access_key, body.session_token)
    _audit(request, admin, 'import.credentials.set', 'kredensial sementara ditempel (memori)')
    return dict(credentials=creds.status())


@router.delete('/import/credentials')
def clear_credentials(request: Request, admin=Depends(require_admin)):
    creds = request.app.state.imports.creds
    creds.clear()
    _audit(request, admin, 'import.credentials.clear', 'kredensial sementara dihapus')
    return dict(credentials=creds.status())
