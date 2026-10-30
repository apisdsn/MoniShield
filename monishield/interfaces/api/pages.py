"""Page routers (TRD §5.3–§5.4): one read endpoint per page. The router only checks role and parameters,
then calls the read-side query in monishield/infrastructure/queries/<page>.py, which returns plain data.

Reads whose parameters can hold personal data (a search text, an IP, an email, a request ID, a file name) also have a POST
form with the parameters in the JSON body (owner request 2026-10-30): the web UI uses only that form, so its body is
encrypted (interfaces/api/wire.py) and nothing of it lands in URLs, proxy/CDN logs or the network panel. The GET forms
stay for Swagger, curl and scripts."""
from fastapi import APIRouter, Body, Depends, Query, Request
from fastapi.responses import Response

from monishield.infrastructure.queries import (availability as q_availability, business as q_business, command as q_command, ips as q_ips,
                                               map as q_map, overview as q_overview, pods as q_pods, rawlogs as q_rawlogs, rootcause as q_rootcause, search as q_search,
                                               security as q_security, service as q_service, tables as q_tables, tracing as q_tracing, trends as q_trends)
from .common import ApiError, client_ip, cursor, folder_param, require_user_ready, source_ctx

router = APIRouter(prefix='/api', dependencies=[Depends(require_user_ready)])


def _cfg(request): return request.app.state.cfg


def _params(body):
    """JSON body of a POST read -> the same flat text parameters as a query string (numbers become text, null is left out)."""
    if not isinstance(body, dict) or any(not isinstance(k, str) or isinstance(v, (dict, list)) for k, v in body.items()):
        raise ApiError(400, 'invalid_parameter', 'The body is an object of plain values.')
    return {k: ('true' if v is True else 'false' if v is False else str(v)) for k, v in body.items() if v is not None}


def _file(r):
    """A query result that is a download file -> attachment response; otherwise plain JSON."""
    if 'file' not in r: return r
    return Response(r['file'], media_type=r['media_type'],
                    headers={'Content-Disposition': f'attachment; filename="{r["filename"]}"', 'Cache-Control': 'no-store'})


@router.get('/folders/{folder}/overview')
def overview(folder: str = Depends(folder_param), cur=Depends(cursor)): return q_overview.overview(cur, folder)


@router.get('/folders/{folder}/command-center')
def command(request: Request, folder: str = Depends(folder_param), cur=Depends(cursor)):
    return q_command.command(cur, folder, _cfg(request), request.query_params.get('module'))


@router.get('/folders/{folder}/ips/{ip}')
def ip_profile(ip: str, request: Request, folder: str = Depends(folder_param), cur=Depends(cursor)):
    return q_ips.ip_profile(cur, folder, _cfg(request), ip)


@router.post('/folders/{folder}/ip-profile')
def ip_profile_post(request: Request, body: dict = Body(default={}), folder: str = Depends(folder_param), cur=Depends(cursor)):
    """The IP profile with the IP in the (encrypted) body: {"ip": "203.0.113.5"}."""
    ip = _params(body).get('ip')
    if not ip: raise ApiError(400, 'invalid_parameter', 'ip is required.')
    return q_ips.ip_profile(cur, folder, _cfg(request), ip)


@router.get('/folders/{folder}/security/blocklist')
def blocklist(request: Request, folder: str = Depends(folder_param), cur=Depends(cursor),
              format: str = Query('nginx'), days: int = Query(1, ge=1, le=90), min_severity: int = Query(1, ge=1, le=3),
              min_hits: int = Query(1, ge=1, le=100000), lang: str = Query('id')):
    return _file(q_ips.blocklist(cur, folder, _cfg(request), format, days, min_severity, min_hits, lang))


@router.get('/folders/{folder}/security/attack-ips.csv')
def attack_ips_csv(request: Request, folder: str = Depends(folder_param), cur=Depends(cursor)):
    return _file(q_ips.attack_ips_csv(cur, folder, _cfg(request)))


@router.get('/search')
def search(request: Request, cur=Depends(cursor)): return q_search.search(cur, request.query_params)


@router.post('/search')
def search_post(body: dict = Body(default={}), cur=Depends(cursor)): return q_search.search(cur, _params(body))


@router.get('/folders/{folder}/map')
def ipmap(request: Request, folder: str = Depends(folder_param), cur=Depends(cursor)):
    return q_map.ipmap(cur, folder, request.query_params.get('module'))


@router.get('/trends')
def trends(request: Request, cur=Depends(cursor)): return q_trends.trends(cur, _cfg(request), request.query_params)


@router.get('/folders/{folder}/security')
def security(request: Request, folder: str = Depends(folder_param), cur=Depends(cursor)):
    return q_security.security(cur, folder, _cfg(request))


@router.get('/folders/{folder}/root-causes')
def rootcause(folder: str = Depends(folder_param), cur=Depends(cursor)): return q_rootcause.rootcause(cur, folder)


@router.get('/folders/{folder}/availability')
def availability(folder: str = Depends(folder_param), cur=Depends(cursor)): return q_availability.availability(cur, folder)


@router.get('/folders/{folder}/pods')
def pods(folder: str = Depends(folder_param), cur=Depends(cursor)): return q_pods.pods(cur, folder)


@router.get('/folders/{folder}/business')
def business(folder: str = Depends(folder_param), cur=Depends(cursor)): return q_business.business(cur, folder)


@router.get('/folders/{folder}/tracing')
def tracing(folder: str = Depends(folder_param), cur=Depends(cursor)): return q_tracing.tracing(cur, folder)


@router.get('/folders/{folder}/services/{service}')
def service_page(service: str, folder: str = Depends(folder_param), cur=Depends(cursor)): return q_service.service_page(cur, folder, service)


@router.get('/folders/{folder}/tables/{table}')
def table_page(table: str, request: Request, folder: str = Depends(folder_param), cur=Depends(cursor)):
    return q_tables.table_page(cur, folder, _cfg(request), table, request.query_params)


@router.post('/folders/{folder}/tables/{table}')
def table_page_post(table: str, request: Request, body: dict = Body(default={}), folder: str = Depends(folder_param), cur=Depends(cursor)):
    return q_tables.table_page(cur, folder, _cfg(request), table, _params(body))


# ------------------------------------------------------------------ Raw Logs (owner request 2026-10-30)
# Every signed-in user (role-based access per module comes later); the text is shown as written (no masking). Each new
# search and each download is recorded in the audit log; paging through the same search and opening context are not.
def _raw_audit(request, action, folder, q, detail=''):
    src = source_ctx(request).source
    request.app.state.auth.audit(action, getattr(request.state, 'user', None),
                                 f'folder={folder} source={src} {q.describe()}{detail}', client_ip(request))


def _raw_search(request, folder, cur, params):
    r, q = q_rawlogs.search(cur, source_ctx(request).cfg, folder, params)
    if not r['offset']: _raw_audit(request, 'raw.search', folder, q, f' matches={r["total"]}')
    return r


@router.get('/folders/{folder}/raw')
def raw_search(request: Request, folder: str = Depends(folder_param), cur=Depends(cursor)):
    return _raw_search(request, folder, cur, request.query_params)


@router.post('/folders/{folder}/raw')
def raw_search_post(request: Request, body: dict = Body(default={}), folder: str = Depends(folder_param), cur=Depends(cursor)):
    return _raw_search(request, folder, cur, _params(body))


@router.get('/folders/{folder}/raw/context')
def raw_context(request: Request, folder: str = Depends(folder_param), cur=Depends(cursor)):
    return q_rawlogs.context(cur, source_ctx(request).cfg, folder, request.query_params)


@router.post('/folders/{folder}/raw/context')
def raw_context_post(request: Request, body: dict = Body(default={}), folder: str = Depends(folder_param), cur=Depends(cursor)):
    return q_rawlogs.context(cur, source_ctx(request).cfg, folder, _params(body))


@router.get('/folders/{folder}/raw/download')
def raw_download(request: Request, folder: str = Depends(folder_param), cur=Depends(cursor)):
    r, q, n = q_rawlogs.download(cur, source_ctx(request).cfg, folder, request.query_params)
    _raw_audit(request, 'raw.download', folder, q, f' entries={n}')
    return _file(r)


@router.post('/folders/{folder}/raw/download')
def raw_download_post(request: Request, body: dict = Body(default={}), folder: str = Depends(folder_param), cur=Depends(cursor)):
    """The same file as JSON {filename, text, entries}, so the web UI receives it encrypted and saves it itself."""
    r, q, n = q_rawlogs.download(cur, source_ctx(request).cfg, folder, _params(body))
    _raw_audit(request, 'raw.download', folder, q, f' entries={n}')
    return dict(filename=r['filename'], text=r['file'].decode('utf-8'), entries=n)
