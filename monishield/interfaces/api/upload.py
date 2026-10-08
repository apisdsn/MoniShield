"""Upload log folders from the browser (monishield/application/upload_service.py). Admin only (not the machine token), CSRF
like the other changing routes.
  POST   /api/admin/upload                plan: list of {path, size} -> files accepted / skipped + upload_id
  PUT    /api/admin/upload/{id}/{i}       content of one file (raw body, streamed to disk, size must match the plan)
  POST   /api/admin/upload/{id}/finish    move to the inbox, then ingest those folders in the background
  DELETE /api/admin/upload/{id}           cancel
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
    """The request body is streamed straight to disk (the HTTP part, not rules): the size must match the plan."""
    m = request.app.state.uploads
    e, path = m.target(uid, admin['username'], i)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    n, fh = 0, await run_in_threadpool(open, path + '.part', 'wb')
    try:
        async for chunk in request.stream():
            n += len(chunk)
            if n > e['size']: raise ApiError(413, 'size_mismatch', f'{e["rel"]} is larger than planned.')
            await run_in_threadpool(fh.write, chunk)
    finally:
        fh.close()
    if n != e['size']:
        os.remove(path + '.part')
        raise ApiError(400, 'size_mismatch', f'{e["rel"]}: received {n} bytes, planned {e["size"]}.')
    os.replace(path + '.part', path)
    m.received(uid, i)
    return dict(i=i, bytes=n)


@router.post('/{uid}/finish', status_code=202)
def finish(uid: str, request: Request, admin=Depends(require_admin)):
    r = upload_service.finish(request.app.state, uid, admin['username'])
    _audit(request, admin, 'upload.finish', f"{r['files']} files, {r['bytes']} bytes to the inbox: {', '.join(r['folders'])}")
    return r


@router.delete('/{uid}')
def cancel(uid: str, request: Request, admin=Depends(require_admin)):
    return upload_service.cancel(request.app.state, uid, admin['username'])
