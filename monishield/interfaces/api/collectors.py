"""Collector registry (docs/12-collector.md, step 2). Admin routes manage collectors; the enrollment route is for the collector
itself (no session): it exchanges the one-time token for the collector's key. Responses that carry a secret are never cached."""
from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel

from .common import _check_csrf, client_ip, public, require_admin

router = APIRouter(prefix='/api')


class NewCollector(BaseModel):
    name: str = ''
    platform: str = ''


class Enroll(BaseModel):
    token: str = ''


def _secret(response: Response): response.headers['Cache-Control'] = 'no-store'


def _svc(request: Request): return request.app.state.collectors


@router.get('/admin/collectors')
def list_collectors(request: Request, admin=Depends(require_admin)): return dict(rows=_svc(request).list())


@router.post('/admin/collectors', status_code=201)
def add_collector(body: NewCollector, request: Request, response: Response, admin=Depends(require_admin)):
    info, token, expires = _svc(request).add(body.name[:100], body.platform[:30], admin, client_ip(request))
    _secret(response)
    return dict(collector=info, enroll_token=token, expires=expires)


@router.post('/admin/collectors/{cid}/token')
def new_token(cid: int, request: Request, response: Response, admin=Depends(require_admin)):
    token, expires = _svc(request).new_token(cid, admin, client_ip(request))
    _secret(response)
    return dict(enroll_token=token, expires=expires)


@router.post('/admin/collectors/{cid}/rotate')
def rotate(cid: int, request: Request, response: Response, admin=Depends(require_admin)):
    key, until = _svc(request).rotate(cid, admin, client_ip(request))
    _secret(response)
    return dict(key=key, previous_valid_until=until)


@router.post('/admin/collectors/{cid}/revoke')
def revoke(cid: int, request: Request, admin=Depends(require_admin)):
    return dict(collector=_svc(request).revoke(cid, admin, client_ip(request)))


@router.delete('/admin/collectors/{cid}')
def delete(cid: int, request: Request, admin=Depends(require_admin)):
    _svc(request).delete(cid, admin, client_ip(request))
    return dict(ok=True)


@router.post('/collector/enroll', dependencies=[Depends(public)])
def enroll(body: Enroll, request: Request, response: Response):
    """The install script sends `X-Requested-With: monishield-collector`; the CSRF guard stays as for every other POST."""
    _check_csrf(request)
    info, key = _svc(request).enroll(body.token[:100], client_ip(request), request.headers.get('user-agent'))
    _secret(response)
    return dict(collector=dict(id=info['id'], name=info['name'], platform=info['platform']), key=key)
