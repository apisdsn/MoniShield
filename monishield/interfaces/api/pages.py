"""Page routers (TRD §5.3–§5.4): one read endpoint per page. The router only checks role and parameters,
then calls the read-side query in monishield/infrastructure/queries/<page>.py, which returns plain data."""
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response

from monishield.infrastructure.queries import (availability as q_availability, business as q_business, command as q_command, ips as q_ips,
                                               map as q_map, overview as q_overview, pods as q_pods, rootcause as q_rootcause, search as q_search,
                                               security as q_security, service as q_service, tables as q_tables, tracing as q_tracing, trends as q_trends)
from .common import cursor, folder_param, require_user_ready

router = APIRouter(prefix='/api', dependencies=[Depends(require_user_ready)])


def _cfg(request): return request.app.state.cfg


def _file(r):
    """A query result that is a download file -> attachment response; otherwise plain JSON."""
    if 'file' not in r: return r
    return Response(r['file'], media_type=r['media_type'],
                    headers={'Content-Disposition': f'attachment; filename="{r["filename"]}"', 'Cache-Control': 'no-store'})


@router.get('/folders/{folder}/overview')
def overview(folder: str = Depends(folder_param), cur=Depends(cursor)): return q_overview.overview(cur, folder)


@router.get('/folders/{folder}/command')
def command(request: Request, folder: str = Depends(folder_param), cur=Depends(cursor)):
    return q_command.command(cur, folder, _cfg(request), request.query_params.get('module'))


@router.get('/folders/{folder}/ips/{ip}')
def ip_profile(ip: str, request: Request, folder: str = Depends(folder_param), cur=Depends(cursor)):
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


@router.get('/folders/{folder}/map')
def ipmap(request: Request, folder: str = Depends(folder_param), cur=Depends(cursor)):
    return q_map.ipmap(cur, folder, request.query_params.get('module'))


@router.get('/trends')
def trends(request: Request, cur=Depends(cursor)): return q_trends.trends(cur, _cfg(request), request.query_params)


@router.get('/folders/{folder}/security')
def security(request: Request, folder: str = Depends(folder_param), cur=Depends(cursor)):
    return q_security.security(cur, folder, _cfg(request))


@router.get('/folders/{folder}/rootcause')
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
