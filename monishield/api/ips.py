"""Profil IP dan daftar IP penyerang (Tahap 24 butir 4).

GET /api/folders/{folder}/ips/{ip}          satu IP: pemilik & lokasi (database offline), angka di folder ini, jejaknya di
                                            semua folder, dan request-nya di folder ini (ingress nginx, paling banyak 1.000).
GET /api/folders/{folder}/security/attack-ips.csv   IP sumber serangan folder ini sebagai CSV (untuk daftar blokir WAF).
Tidak ada yang dikirim ke layanan pihak ketiga: lokasi dan pemilik dari tabel ip_info.
"""
import csv, io, re
from urllib.parse import unquote_plus

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response

from .. import detect
from .common import ApiError, cursor, folder_param, require_user_ready, _all
from .tables import NG, SEV_SQL, T, UTC

MAX_REQ = 1000
router = APIRouter(prefix='/api', dependencies=[Depends(require_user_ready)])


def _ip(ip):
    if not re.fullmatch(r'[0-9A-Fa-f.:]{2,45}', ip or ''): raise ApiError(400, 'invalid_parameter', 'Parameter tidak sah: ip.')
    return ip


def _schema(request):
    return request.app.state.cfg.attack_rules == 'crs'


@router.get('/folders/{folder}/ips/{ip}')
def ip_profile(ip: str, request: Request, folder: str = Depends(folder_param), cur=Depends(cursor)):
    ip, crs = _ip(ip), _schema(request)
    I = 'agg_crs_ip' if crs else 'agg_attack_ip'
    info = cur.execute('SELECT asn, cc, org, is_private, city, region, country FROM ip_info WHERE ip = ?', [ip]).fetchone()
    # jejak di semua folder: request ingress, request serangan, login gagal/sukses
    days = {}
    for f, n in _all(cur, 'SELECT folder::VARCHAR, requests FROM agg_ip WHERE ip = ? AND service = ?', ip, NG): days.setdefault(f, {})['requests'] = n
    for f, n in _all(cur, f'SELECT folder::VARCHAR, hits FROM {I} WHERE ip = ?', ip): days.setdefault(f, {})['attacks'] = n
    for f, a, b in _all(cur, 'SELECT folder::VARCHAR, fail, ok FROM agg_login_ip WHERE ip = ?', ip): days.setdefault(f, {}).update(login_fail=a, login_ok=b)
    for f, n in _all(cur, 'SELECT folder::VARCHAR, sum(n) FROM agg_trace WHERE ip = ? GROUP BY 1', ip): days.setdefault(f, {})['traced'] = int(n)
    if not days and not info: raise ApiError(404, 'not_found', 'IP tidak ditemukan di data mana pun.')
    folders = [dict(folder=f, requests=d.get('requests', 0), attacks=d.get('attacks', 0), login_fail=d.get('login_fail', 0),
                    login_ok=d.get('login_ok', 0), traced=d.get('traced', 0)) for f, d in sorted(days.items(), reverse=True)]

    cat = "CASE WHEN capec IS NULL THEN NULL ELSE capec || '/' || crs_attack END" if crs else 'attack_cat'
    sev = 'crs_severity' if crs else SEV_SQL.replace('category', 'attack_cat')
    k = cur.execute(f"""SELECT count(*), count(*) FILTER (WHERE status BETWEEN 400 AND 499), count(*) FILTER (WHERE status >= 500),
                               count(*) FILTER (WHERE {cat} IS NOT NULL), count(DISTINCT path_key), count(DISTINCT ua),
                               {UTC.format('min(ts_utc)')}, {UTC.format('max(ts_utc)')}
                        FROM nginx_access WHERE folder = ? AND ip = ?""", [folder, ip]).fetchone()
    rows = [dict(time=t, method=m, path=unquote_plus(p)[:300], status=s, bytes=b, ua=u[:160], upstream=up, request_id=rid,
                 category=c, severity=sv if c else None, rules=list(r or []))
            for t, m, p, s, b, u, up, rid, c, sv, r in cur.execute(f"""
                SELECT {UTC.format('ts_utc')}, method, path, status, bytes, ua, upstream, request_id, {cat}, {sev},
                       {'crs_rules' if crs else '[]::INTEGER[]'}
                FROM nginx_access WHERE folder = ? AND ip = ? ORDER BY ts_utc, file_id, line_no LIMIT {MAX_REQ}""", [folder, ip]).fetchall()]
    login = cur.execute(f"""SELECT fail, lock, ok, list_sort(accounts), {T.format('first_wib')}, {T.format('last_wib')}
                            FROM agg_login_ip WHERE folder = ? AND ip = ?""", [folder, ip]).fetchone()
    return dict(
        ip=ip, scheme='crs' if crs else 'lama',
        info=dict(asn=info[0], cc=info[1], org=info[2], private=bool(info[3]), city=info[4], region=info[5], country=info[6]) if info else None,
        kpi=dict(requests=k[0], n4xx=k[1], n5xx=k[2], attacks=k[3], endpoints=k[4], user_agents=k[5], first=k[6], last=k[7],
                 login_fail=login[0] if login else 0, resets=login[1] if login else 0, login_ok=login[2] if login else 0),
        accounts=login[3] if login else [], folders=folders, requests=rows, truncated=k[0] > MAX_REQ,
        rule_msgs=detect.rule_msgs(i for r in rows for i in r['rules']) if crs else {})


def _safe(v):
    """Sel CSV aman dibuka di spreadsheet: teks yang diawali = + - @ diberi petik (cegah injeksi rumus)."""
    s = '' if v is None else str(v)
    return "'" + s if s[:1] in ('=', '+', '-', '@', '\t', '\r') else s


@router.get('/folders/{folder}/security/attack-ips.csv')
def attack_ips_csv(request: Request, folder: str = Depends(folder_param), cur=Depends(cursor)):
    crs = _schema(request)
    I = 'agg_crs_ip' if crs else 'agg_attack_ip'
    msev = 'a.max_severity' if crs else f"list_max(list_transform(map_keys(a.cats), category -> {SEV_SQL}))"
    rows = _all(cur, f"""SELECT a.ip, a.hits, array_to_string(list_sort(map_keys(a.cats)), ' | '), {msev}, i.country, i.asn, i.org,
                                {T.format('a.first_wib')}, {T.format('a.last_wib')}
                         FROM {I} a LEFT JOIN ip_info i USING (ip) WHERE a.folder = ? ORDER BY a.hits DESC, a.ip""", folder)
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator='\n')
    w.writerow(['ip', 'request_serangan', 'kategori', 'keparahan_maks', 'negara', 'asn', 'pemilik_jaringan', 'pertama_wib', 'terakhir_wib'])
    for r in rows: w.writerow([_safe(v) for v in r])
    return Response(buf.getvalue(), media_type='text/csv; charset=utf-8',
                    headers={'Content-Disposition': f'attachment; filename="ip-serangan-{folder}.csv"', 'Cache-Control': 'no-store'})
