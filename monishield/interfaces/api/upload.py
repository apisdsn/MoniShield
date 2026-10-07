"""Unggah folder log dari browser (monishield/application/upload_service.py). Admin saja (bukan token mesin), CSRF
seperti rute ubah lain.
  POST   /api/admin/upload                rencana: daftar {path, size} -> file yang diterima / dilewati + upload_id
  PUT    /api/admin/upload/{id}/{i}       isi satu file (badan mentah, dialirkan ke disk, ukuran harus sama dengan rencana)
  POST   /api/admin/upload/{id}/finish    pindah ke kotak masuk, lalu ingest folder-folder itu di latar
  DELETE /api/admin/upload/{id}           batalkan
"""
import os

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from monishield.application import upload_service
from .admin import _audit
from .common import ApiError, require_admin

router = APIRouter(prefix='/api/admin/upload')


class PlanBody(BaseModel):
    files: list = []
    folder: str = ''


@router.post('', status_code=201)
def create(body: PlanBody, request: Request, admin=Depends(require_admin)):
    return upload_service.plan(request.app.state, body.files, body.folder, admin['username'])


@router.put('/{uid}/{i}')
async def put_file(uid: str, i: int, request: Request, admin=Depends(require_admin)):
    """Badan permintaan dialirkan langsung ke disk (bagian HTTP, bukan aturan): ukuran harus sama dengan rencana."""
    m = request.app.state.uploads
    e, path = m.target(uid, admin['username'], i)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    n, fh = 0, await run_in_threadpool(open, path + '.part', 'wb')
    try:
        async for chunk in request.stream():
            n += len(chunk)
            if n > e['size']: raise ApiError(413, 'size_mismatch', f'{e["rel"]} lebih besar dari yang direncanakan.')
            await run_in_threadpool(fh.write, chunk)
    finally:
        fh.close()
    if n != e['size']:
        os.remove(path + '.part')
        raise ApiError(400, 'size_mismatch', f'{e["rel"]}: diterima {n} byte, direncanakan {e["size"]}.')
    os.replace(path + '.part', path)
    m.received(uid, i)
    return dict(i=i, bytes=n)


@router.post('/{uid}/finish', status_code=202)
def finish(uid: str, request: Request, admin=Depends(require_admin)):
    r = upload_service.finish(request.app.state, uid, admin['username'])
    _audit(request, admin, 'upload.finish', f"{r['files']} file, {r['bytes']} byte ke kotak masuk: {', '.join(r['folders'])}")
    return r


@router.delete('/{uid}')
def cancel(uid: str, request: Request, admin=Depends(require_admin)):
    return upload_service.cancel(request.app.state, uid, admin['username'])
