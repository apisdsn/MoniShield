"""Halaman Layanan (TRD §5.3)."""
from fastapi import APIRouter, Depends

from .common import ApiError, cursor, folder_param, require_user_ready, SL, H, _all, _no
from .map import MOD
from .tables import NG, first

router = APIRouter(prefix='/api', dependencies=[Depends(require_user_ready)])


@router.get('/folders/{folder}/services/{service}')
def service_page(service: str, folder: str = Depends(folder_param), cur=Depends(cursor)):
    r = cur.execute("""SELECT lines, err, warn, err_http, err_log, files, files_empty, files_corrupt, requests, n4xx, n5xx, ip_unique
                       FROM agg_service WHERE folder = ? AND service = ?""", [folder, service]).fetchone()
    if not r: raise ApiError(404, 'not_found', 'Layanan tidak ditemukan.')
    kpi = dict(zip(('lines', 'err', 'warn', 'err_http', 'err_log', 'files', 'files_empty', 'files_corrupt', 'requests', 'n4xx', 'n5xx', 'ip_unique'), r))
    if not r[0]: return dict(**_no('empty'), service=service, kpi=kpi)
    corr = cur.execute('SELECT matched, total FROM agg_corr WHERE folder = ?', [folder]).fetchone() if service == SL else None
    tabel = {t: first(cur, t, folder, service=service) for t in ('endpoints', 'endpoint-errors', 'endpoint-perf', 'endpoint-error-rate', 'slow', 'ips', 'user-agents', 'messages')}
    return dict(
        available=True, service=service, kpi=kpi, corr=dict(matched=corr[0], total=corr[1]) if corr else None,
        hour=_all(cur, f"SELECT {H.format('hour_wib')}, total, err FROM agg_hour WHERE folder = ? AND service = ? ORDER BY hour_wib", folder, service),
        status=_all(cur, 'SELECT status::VARCHAR, n FROM agg_status WHERE folder = ? AND service = ? ORDER BY 1', folder, service),
        upstreams=_all(cur, 'SELECT upstream, requests FROM agg_upstream WHERE folder = ? ORDER BY requests DESC, upstream LIMIT 12', folder) if service == NG else [],
        levels=_all(cur, 'SELECT level, n FROM agg_level WHERE folder = ? AND service = ? ORDER BY n DESC, level', folder, service),
        # peta di halaman layanan (Tahap 20): ingress = semua alur; modul di belakang ingress = alur modul itu (lama: flowsOf)
        has_flows=bool(cur.execute(f"SELECT 1 FROM agg_flow WHERE folder = ? AND (? = ? OR {MOD} = ?) LIMIT 1", [folder, service, NG, service]).fetchone()),
        tables={t: v for t, v in tabel.items() if v['total']})   # kartu yang datanya kosong tidak dikirim (inv. §2.10)
