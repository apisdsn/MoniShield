"""Collector registry (docs/12-collector.md, step 2). Admin routes manage collectors; the enrollment route is for the collector
itself (no session): it exchanges the one-time token for the collector's key. Responses that carry a secret are never cached."""
from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from monishield.domain import collector_config
from monishield.domain.errors import Fail
from .common import ApiError, _check_csrf, client_ip, public, require_admin, require_collector

router = APIRouter(prefix='/api')


class NewCollector(BaseModel):
    name: str = ''
    platform: str = ''
    options: dict | None = None   # the log inputs (domain/collector_config.py); empty = the defaults of the platform
    group: str | None = None      # the section it is listed under; empty or missing = no group


class Options(BaseModel):
    """The update call: the inputs, the group, or both (what is missing stays as it is)."""
    options: dict | None = None
    group: str | None = None


class Enroll(BaseModel):
    token: str = ''


def _secret(response: Response): response.headers['Cache-Control'] = 'no-store'


def _svc(request: Request): return request.app.state.collectors


def receiver_url(request: Request):
    """The address collectors send to: S4_COLLECTOR_PUBLIC_URL, else the address this request used (the install script and the
    enrollment call come from the collector's own server, so that is the address it can reach)."""
    cfg = request.app.state.cfg
    if cfg.collector_public_url: return cfg.collector_public_url
    scheme = request.headers.get('x-forwarded-proto', '').split(',')[-1].strip() if cfg.trust_proxy else ''
    try: return collector_config.base_url(f"{scheme if scheme in ('http', 'https') else request.url.scheme}://{request.headers.get('host', '')}")
    except Fail: raise ApiError(400, 'invalid_host', 'The Host header is not a valid address; set S4_COLLECTOR_PUBLIC_URL.') from None


@router.get('/admin/collectors')
def list_collectors(request: Request, admin=Depends(require_admin)):
    stats = request.app.state.collector_feed.status()['collectors']   # counts of the receiver since the server started
    return dict(rows=[dict(c, stats=stats.get(c['id'])) for c in _svc(request).list()], groups=_svc(request).groups(),
                receiver=receiver_url(request), otel_version=request.app.state.cfg.collector_otel_version)


@router.get('/admin/collectors/{cid}/config')
def download_config(cid: int, request: Request, admin=Depends(require_admin)):
    """The configuration of this collector for download (Helm values for Kubernetes). It holds no key."""
    info = _svc(request).get(cid)
    name = 'values.yaml' if info['platform'] == 'kubernetes' else 'config.yaml'
    return PlainTextResponse(_svc(request).config(info, receiver_url(request)), media_type='text/yaml; charset=utf-8',
                             headers={'Cache-Control': 'no-store', 'Content-Disposition': f'attachment; filename="{name}"'})


@router.post('/admin/collectors', status_code=201)
def add_collector(body: NewCollector, request: Request, response: Response, admin=Depends(require_admin)):
    info, token, expires = _svc(request).add(body.name[:100], body.platform[:30], admin, client_ip(request), body.options, (body.group or '')[:100])
    _secret(response)
    return dict(collector=info, enroll_token=token, expires=expires)


@router.put('/admin/collectors/{cid}/options')
def set_options(cid: int, body: Options, request: Request, admin=Depends(require_admin)):
    svc, ip, info = _svc(request), client_ip(request), None
    if body.options is not None: info = svc.set_options(cid, body.options, admin, ip)
    if 'group' in body.model_fields_set: info = svc.set_group(cid, (body.group or '')[:100], admin, ip)
    if info is None: raise ApiError(400, 'invalid_body', 'Send options, a group, or both.')
    return dict(collector=info)


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
    config = _svc(request).config(info, receiver_url(request))
    out = dict(collector=dict(id=info['id'], name=info['name'], platform=info['platform']), key=key, config=config)
    if request.query_params.get('format') != 'install': return out
    # the install script reads this without a JSON parser: the configuration as text, the rest in headers
    return PlainTextResponse(config, headers={'Cache-Control': 'no-store', 'X-Collector-Key': key, 'X-Collector-Platform': info['platform'], 'X-Collector-Name': info['name']})


@router.get('/collector/config')
def current_config(request: Request, collector=Depends(require_collector)):
    """For a collector that is already running: the configuration after the admin changed its inputs (the key stays as it is)."""
    return PlainTextResponse(_svc(request).config(collector, receiver_url(request)), headers={'Cache-Control': 'no-store'})
