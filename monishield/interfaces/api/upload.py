"""Unggah folder log dari browser (aturan: monishield/domain/uploads.py, penyimpanan: monishield/infrastructure/uploads.py). Admin saja (bukan token mesin), CSRF seperti rute ubah lain.
  POST   /api/admin/upload                rencana: daftar {path, size} -> file yang diterima / dilewati + upload_id
  PUT    /api/admin/upload/{id}/{i}       isi satu file (badan mentah, dialirkan ke disk, ukuran harus sama dengan rencana)
  POST   /api/admin/upload/{id}/finish    pindah ke kotak masuk, lalu ingest folder-folder itu di latar
  DELETE /api/admin/upload/{id}           batalkan
"""
import os, threading

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from monishield.infrastructure import importer
from monishield.domain import uploads as upload
from .admin import _audit
from .common import ApiError, require_admin

router = APIRouter(prefix='/api/admin/upload')


class PlanBody(BaseModel):
    files: list = []
    folder: str = ''


def _m(request): return request.app.state.uploads


def _fail(e): return ApiError(e.status, e.code, e.message)


@router.post('', status_code=201)
def create(body: PlanBody, request: Request, admin=Depends(require_admin)):
    try:
        ok, skip = upload.plan(request.app.state.cfg, body.files, body.folder.strip())
        if not ok: raise importer.ImportFail('nothing_to_upload', 'Tidak ada file log yang bisa diunggah dari folder ini.' + (f' Contoh: {skip[0]["path"][:120]} — {skip[0]["reason"]}.' if skip else ''))
    except importer.ImportFail as e: raise _fail(e) from None
    uid = _m(request).create(admin['username'], ok)
    return dict(upload_id=uid, files=[dict(i=f['i'], rel=f['rel'], size=f['size']) for f in ok], skipped=skip[:200], skipped_count=len(skip),
                folders=sorted({f['folder'] for f in ok}), bytes=sum(f['size'] for f in ok))


@router.put('/{uid}/{i}')
async def put_file(uid: str, i: int, request: Request, admin=Depends(require_admin)):
    m = _m(request)
    try: e, path = m.target(uid, admin['username'], i)
    except importer.ImportFail as x: raise _fail(x) from None
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
        importer._rm(path + '.part')
        raise ApiError(400, 'size_mismatch', f'{e["rel"]}: diterima {n} byte, direncanakan {e["size"]}.')
    os.replace(path + '.part', path)
    m.received(uid, i)
    return dict(i=i, bytes=n)


@router.post('/{uid}/finish', status_code=202)
def finish(uid: str, request: Request, admin=Depends(require_admin)):
    try: r = _m(request).finish(uid, admin['username'])
    except importer.ImportFail as e: raise _fail(e) from None
    ing = request.app.state.ingest
    # ingest di latar (menunggu ingest lain selesai); hasilnya terlihat di status ingest seperti biasa
    def kerja():
        for f in r['folders']:
            try: ing.run_blocking(f, f"unggah oleh {admin['username']}")
            except Exception: pass   # noqa: BLE001  galat ingest tercatat di status ingest dan tabel ingest_run
    threading.Thread(target=kerja, name='upload-ingest', daemon=True).start()
    _audit(request, admin, 'upload.finish', f"{r['files']} file, {r['bytes']} byte ke kotak masuk: {', '.join(r['folders'])}")
    return r


@router.delete('/{uid}')
def cancel(uid: str, request: Request, admin=Depends(require_admin)):
    try: _m(request).get(uid, admin['username'])
    except importer.ImportFail as e: raise _fail(e) from None
    _m(request).drop(uid)
    return dict(cancelled=True)
