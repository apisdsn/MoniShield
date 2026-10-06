"""Satu endpoint per halaman (TRD §5.3): KPI + seri chart + halaman pertama tiap tabel.

Semua angka dibaca dari tabel agregat lengkap (TRD K4), bukan dari daftar yang sudah dipotong.
Bila log yang dibutuhkan tidak ada: 200 dengan available=false + reason, bukan galat.
"""
import re

from fastapi import APIRouter, Depends, Request

from .common import ApiError, cursor, folder_param, require_user_ready
from .tables import NG, SEV, SEV_SQL, cells, first, services

SL, AM, RP = 'om-be-simpel-loop', 'om-be-appsmanager', 'om-be-report'
H = "strftime({}, '%Y-%m-%d %H')"   # jam WIB, format lama
MOD = "regexp_replace(upstream, '-\\d+$', '')"
CLOUD = re.compile(r'CLOUD|OCEAN|AMAZON|AWS|AZURE|MICROSOFT|HETZNER|OVH|LINODE|VULTR|ALIBABA|TENCENT|HOSTING|DATACENTER', re.I)  # lama: temuan 5
JWT_OLD = ('1–24 Jam', '1–7 Hari', '> 7 Hari')
TREND_BIZ = ('Laporan Dibuat', 'Registrasi Laporan', 'File Diunggah', 'Email Terkirim', 'OTP Diminta')

router = APIRouter(prefix='/api', dependencies=[Depends(require_user_ready)])


def _all(cur, sql, *p): return [list(r) for r in cur.execute(sql, list(p)).fetchall()]
def _one(cur, sql, *p): return cur.execute(sql, list(p)).fetchone()[0]
def _no(reason): return dict(available=False, reason=reason)
def _has(svc, name): return bool(svc.get(name))   # layanan ada DAN punya baris


# ------------------------------------------------------------------ Overview
@router.get('/folders/{folder}/overview')
def overview(folder: str = Depends(folder_param), cur=Depends(cursor)):
    a, b = cur.execute(f"SELECT {H.format('min(hour_wib)')}, {H.format('max(hour_wib)')} FROM agg_hour WHERE folder = ? AND total > 0", [folder]).fetchone()
    err = {}
    for s, h, n in _all(cur, f"SELECT service, {H.format('hour_wib')}, err FROM agg_hour WHERE folder = ? AND err > 0 ORDER BY service, hour_wib", folder):
        err.setdefault(s, []).append([h, n])
    return dict(available=True, period=dict(start=a, end=b), err_by_hour=err, tables=dict(messages=first(cur, 'messages', folder, limit=25)))


# ------------------------------------------------------------------ Peta IP
@router.get('/folders/{folder}/map')
def ipmap(request: Request, folder: str = Depends(folder_param), cur=Depends(cursor)):
    module = request.query_params.get('module') or None
    modules = [r[0] for r in _all(cur, f'SELECT DISTINCT {MOD} FROM agg_flow WHERE folder = ? ORDER BY 1', folder)]
    if not modules: return _no('no_nginx')
    if module is not None and module not in modules: raise ApiError(404, 'not_found', 'Modul tidak ditemukan.')
    src = f"""FROM agg_flow f LEFT JOIN ip_info i USING (ip) WHERE f.folder = $f AND (CAST($m AS VARCHAR) IS NULL OR {MOD} = $m)"""
    p = dict(f=folder, m=module)
    k = cur.execute(f"""SELECT count(DISTINCT f.ip), count(DISTINCT (i.lat, i.lon)) FILTER (WHERE i.lat IS NOT NULL), count(DISTINCT i.country) FILTER (WHERE i.lat IS NOT NULL),
                               count(DISTINCT {MOD}), count(DISTINCT f.pod), coalesce(sum(f.n), 0),
                               coalesce(sum(f.n) FILTER (WHERE i.lat IS NOT NULL AND i.country <> 'ID'), 0), coalesce(sum(f.n) FILTER (WHERE i.lat IS NULL), 0) {src}""", p).fetchone()
    loc = f"{src} AND i.lat IS NOT NULL GROUP BY ALL"
    points = {(lat, lon): dict(lat=lat, lon=lon, city=city, region=region, cc=cc, ips=ips, requests=n, modules={})
              for lat, lon, city, region, cc, ips, n in cur.execute(
                  f"SELECT i.lat, i.lon, any_value(i.city), any_value(i.region), any_value(i.country), count(DISTINCT f.ip), sum(f.n)::BIGINT {src} AND i.lat IS NOT NULL GROUP BY i.lat, i.lon", p).fetchall()}
    for lat, lon, m, n in cur.execute(f"SELECT i.lat, i.lon, {MOD}, sum(f.n)::BIGINT {loc}", p).fetchall(): points[lat, lon]['modules'][m] = n
    points = sorted(points.values(), key=lambda x: (x['requests'], x['lat'], x['lon']))   # terbesar digambar terakhir, seperti lama
    return dict(available=True, module=module, modules=modules,
                kpi=dict(source_ips=k[0], locations=k[1], countries=k[2], modules=k[3], dest_pods=k[4], requests=k[5]),
                abroad_requests=k[6], unlocated_requests=k[7], points=points, tables=dict(flows=first(cur, 'flows', folder, module=module)))


# ------------------------------------------------------------------ Tren
@router.get('/trends')
def trends(request: Request, cur=Depends(cursor)):
    last = request.query_params.get('last', '30')
    if last not in ('14', '30', '90', 'all'): raise ApiError(400, 'invalid_parameter', 'Parameter tidak sah: last.')
    folders = [str(r[0]) for r in _all(cur, 'SELECT folder FROM folder_state ORDER BY folder')]
    if last != 'all': folders = folders[-int(last):]
    if not folders: return dict(folders=[], services=[], lines={}, err={}, warn={}, http={}, security={}, business={}, file_status={})
    lo, pos = folders[0], {f: i for i, f in enumerate(folders)}
    kosong = lambda isi=None: [isi] * len(folders)
    rows = _all(cur, 'SELECT folder::VARCHAR, service, lines, err, warn, files_corrupt, requests, n4xx, n5xx FROM agg_service WHERE folder >= ? ORDER BY service', lo)
    names = list(dict.fromkeys(r[1] for r in rows))
    out = {k: {s: kosong() for s in names} for k in ('lines', 'err', 'warn', 'file_status')}   # None = layanan tidak ada di folder itu
    http = {k: kosong(0) for k in ('total', 'n4xx', 'n5xx')}
    for f, s, lines, err, warn, rusak, req, n4, n5 in rows:
        i = pos[f]
        out['lines'][s][i], out['err'][s][i], out['warn'][s][i] = lines, err, warn
        out['file_status'][s][i] = 'rusak' if rusak else 'kosong' if not lines else 'ok'
        if s == NG: http['total'][i], http['n4xx'][i], http['n5xx'][i] = req, n4, n5
    sec = {k: kosong(0) for k in ('attack_requests', 'login_fail', 'resets')}
    for f, n in _all(cur, 'SELECT folder::VARCHAR, sum(hits) FROM agg_attack_url WHERE folder >= ? GROUP BY 1', lo): sec['attack_requests'][pos[f]] = int(n)
    # lama: Σ login[*][1] dan [2] = hanya IP yang punya gagal/reset; sama dengan jumlah semua baris
    for f, a, b in _all(cur, 'SELECT folder::VARCHAR, sum(fail), sum(lock) FROM agg_login_ip WHERE folder >= ? GROUP BY 1', lo):
        sec['login_fail'][pos[f]], sec['resets'][pos[f]] = int(a), int(b)
    biz = {k: kosong(0) for k in TREND_BIZ}
    for f, m, n in _all(cur, f"SELECT folder::VARCHAR, metric, n FROM agg_biz WHERE folder >= ? AND metric IN ({', '.join('?' * len(TREND_BIZ))})", lo, *TREND_BIZ): biz[m][pos[f]] = n
    return dict(folders=folders, services=names, **out, http=http, security=sec, business=biz)


# ------------------------------------------------------------------ Keamanan
@router.get('/folders/{folder}/security')
def security(folder: str = Depends(folder_param), cur=Depends(cursor)):
    svc = services(cur, folder)
    atk = _all(cur, f'SELECT category, {SEV_SQL}, hits, top_ip, status_counts, upstreams FROM agg_attack_url WHERE folder = ?', folder)
    aip = _all(cur, 'SELECT a.ip, a.hits, a.cats, i.org FROM agg_attack_ip a LEFT JOIN ip_info i USING (ip) WHERE a.folder = ? ORDER BY a.hits DESC, a.ip', folder)
    login = _all(cur, """SELECT l.ip, l.fail, l.lock, l.accounts, i.org FROM agg_login_ip l LEFT JOIN ip_info i USING (ip)
                         WHERE l.folder = ? AND (l.fail > 0 OR l.lock > 0) ORDER BY l.lock DESC, l.fail DESC, l.ip""", folder)
    acct = _all(cur, 'SELECT account, flags FROM agg_account WHERE folder = ?', folder)
    ok2 = lambda st: any(c.startswith('2') for c in st)
    kategori = lambda c: [r for r in atk if r[0] == c]
    ringkas = lambda rs: dict(hits=sum(r[2] for r in rs), ips=sorted({r[3] for r in rs}), upstreams=sorted({u for r in rs for u in r[5]}),
                              statuses=sorted({c for r in rs for c in r[4]}))
    per_cat, per_org = {}, {}
    for r in atk: per_cat[r[0]] = per_cat.get(r[0], 0) + r[2]
    for ip, hits, cats, org in aip: per_org[org or 'Tidak diketahui'] = per_org.get(org or 'Tidak diketahui', 0) + hits
    urut = lambda d, n=None: [list(x) for x in sorted(d.items(), key=lambda kv: (-kv[1], kv[0]))[:n]]
    top = cells(cur, [dict(ip=ip, hits=hits, max_severity=max(SEV.get(c, 1) for c in cats)) for ip, hits, cats, org in aip[:10]], ('ip',))
    top_login = cells(cur, [dict(ip=r[0], fail=r[1]) for r in sorted(login, key=lambda r: (-r[1], r[0]))[:10] if r[1]], ('ip',))
    return dict(
        available=True, nginx=_has(svc, NG), appsmanager=_has(svc, AM),
        kpi=dict(attack_requests=sum(r[2] for r in atk), attack_ips=len(aip), critical_hits=sum(r[2] for r in atk if r[1] == 3),
                 attack_urls_2xx=sum(1 for r in atk if r[1] >= 2 and ok2(r[4])), login_fail_ips=len(login),
                 accounts_ok_after_fail=sum('Sukses Setelah ≥3 Gagal' in f for _, f in acct), accounts_ok_other_ip=sum('Sukses Dari IP Berbeda' in f for _, f in acct),
                 resets=sum(r[2] for r in login)),
        by_category=[[c, n, SEV.get(c, 1)] for c, n in urut(per_cat)],
        by_hour=_all(cur, f"SELECT {H.format('hour_wib')}, n FROM agg_attack_hour WHERE folder = ? ORDER BY hour_wib", folder),
        top_ips=top, by_owner=urut(per_org, 10),
        login_by_hour=_all(cur, f"SELECT {H.format('hour_wib')}, fail FROM agg_login_hour WHERE folder = ? AND fail > 0 ORDER BY hour_wib", folder),
        login_top_ips=[dict(**r['ip'], fail=r['fail']) for r in top_login],
        findings=dict(
            log4shell=ringkas(kategori('Log4Shell / RCE')) if kategori('Log4Shell / RCE') else None,
            by_critical_category=[dict(category=c, **ringkas(kategori(c))) for c in ('SQL Injection', 'XSS', 'Path Traversal / LFI') if kategori(c)],
            rancher_probe_hits=sum(r[2] for r in atk if r[1] >= 2 and any('rancher' in u for u in r[5])),
            cloud_owners=sorted({org for ip, hits, cats, org in aip if org and CLOUD.search(org) and any(SEV.get(c, 1) >= 2 for c in cats)}),
            ombudsman_login_ips=[r[0] for r in login if r[4] and 'OMBUDSMAN' in r[4].upper()],
            multi_account_ips=[r[0] for r in login if len({u.split('@')[0] for u in r[3]}) >= 3],
            accounts_other_ip=[a for a, f in acct if 'Sukses Dari IP Berbeda' in f]),
        tables={t: first(cur, t, folder) for t in ('attack-urls', 'attack-ips', 'accounts', 'login-ips', 'ip-4xx')})


# ------------------------------------------------------------------ Akar Masalah
@router.get('/folders/{folder}/rootcause')
def rootcause(folder: str = Depends(folder_param), cur=Depends(cursor)):
    jwt, refresh = {}, {}
    for s, b, n in _all(cur, 'SELECT service, bucket, n FROM agg_jwt WHERE folder = ? ORDER BY service', folder):
        if b == 'Refresh Token Kedaluwarsa': refresh[s] = n     # TRD §4.4 butir 10: kini ditampilkan
        else: jwt.setdefault(s, {})[b] = n
    pdf = cur.execute('SELECT coalesce(sum(ok), 0), coalesce(sum(fail), 0), count(*) FILTER (WHERE fail > 0) FROM agg_report WHERE folder = ?', [folder]).fetchone()
    return dict(
        available=True, sources=sorted(s for s, n in services(cur, folder).items() if n),
        jwt=jwt, jwt_total=sum(n for d in jwt.values() for n in d.values()), jwt_over_1h=sum(d.get(b, 0) for d in jwt.values() for b in JWT_OLD), refresh_expired=refresh,
        pdf=dict(ok=pdf[0], fail=pdf[1], templates_failed=pdf[2]),
        dns_total=_one(cur, 'SELECT coalesce(sum(n), 0) FROM v_dns WHERE folder = ?', folder),
        upstream_errors_total=_one(cur, 'SELECT count(*) FROM v_upstream_error WHERE folder = ?', folder),
        upstream_error_kinds=_all(cur, 'SELECT kind, count(*) FROM v_upstream_error WHERE folder = ? GROUP BY kind ORDER BY 2 DESC, 1', folder),
        tables={t: first(cur, t, folder) for t in ('c401', 'pdf-templates', 'dns')})


# ------------------------------------------------------------------ Ketersediaan
@router.get('/folders/{folder}/availability')
def availability(folder: str = Depends(folder_param), cur=Depends(cursor)):
    if not _has(services(cur, folder), NG): return _no('no_nginx')
    req, n5 = cur.execute('SELECT requests, n5xx FROM agg_service WHERE folder = ? AND service = ?', [folder, NG]).fetchone()
    uk = _all(cur, f"SELECT {H.format('hour_wib')}, n, fail FROM agg_uk_hour WHERE folder = ? ORDER BY hour_wib", folder)
    # ponytail: 5xx per jam dibaca dari tabel mentah (agg_hour.err memuat juga baris error log, butir 2); satu folder = satu rentang
    # berurutan, jadi hanya blok folder itu yang dibaca. Tambah kolom n5xx di agg_hour bila query ini terukur lambat.
    return dict(
        available=True,
        kpi=dict(requests=req, n5xx=n5, incidents=_one(cur, 'SELECT count(*) FROM agg_incident WHERE folder = ?', folder),
                 retries=_one(cur, 'SELECT coalesce(sum(n), 0) FROM agg_retry WHERE folder = ?', folder),
                 upstream_errors=_one(cur, 'SELECT count(*) FROM v_upstream_error WHERE folder = ?', folder),
                 uptime_checks=sum(r[1] for r in uk), uptime_failed=sum(r[2] for r in uk)),
        n5xx_by_hour=_all(cur, f"""SELECT {H.format("date_trunc('hour', ts_utc + INTERVAL 7 HOUR)")} AS h, count(*) FROM nginx_access
                                   WHERE folder = ? AND status BETWEEN 500 AND 599 GROUP BY h ORDER BY h""", folder),
        hours=[r[0] for r in _all(cur, f"SELECT {H.format('hour_wib')} FROM agg_hour WHERE folder = ? AND service = ? AND total > 0 ORDER BY hour_wib", folder, NG)],
        n5xx_by_upstream=_all(cur, 'SELECT upstream, n5xx FROM agg_upstream WHERE folder = ? AND n5xx > 0 ORDER BY n5xx DESC, upstream', folder),
        uptime_by_hour=uk,
        tables={t: first(cur, t, folder) for t in ('upstreams', 'incidents', 'upstream-errors', 'uptime-targets')})


# ------------------------------------------------------------------ Pod
@router.get('/folders/{folder}/pods')
def pods(folder: str = Depends(folder_param), cur=Depends(cursor)):
    files, empty = cur.execute('SELECT count(*), count(*) FILTER (WHERE lines = 0) FROM ingest_file WHERE folder = ?', [folder]).fetchone()
    return dict(
        available=True,
        kpi=dict(files=files, files_without_log=empty, backend_pods=_one(cur, 'SELECT count(*) FROM agg_pod WHERE folder = ?', folder),
                 pods_with_retry=_one(cur, 'SELECT count(*) FROM (SELECT DISTINCT upstream, addr_first FROM agg_retry WHERE folder = ?)', folder),
                 restarts=_one(cur, 'SELECT count(*) FROM v_restart WHERE folder = ?', folder)),
        tables={t: first(cur, t, folder) for t in ('backend-pods', 'restarts')})


# ------------------------------------------------------------------ Bisnis
@router.get('/folders/{folder}/business')
def business(folder: str = Depends(folder_param), cur=Depends(cursor)):
    svc = services(cur, folder)
    prev = _one(cur, 'SELECT max(folder) FROM folder_state WHERE folder < ?', folder)
    biz = lambda f: dict(cur.execute('SELECT metric, n FROM agg_biz WHERE folder = ?', [f]).fetchall())
    ada_lama = prev and _one(cur, 'SELECT count(*) FROM agg_service WHERE folder = ? AND service = ?', prev, SL)
    pdf = cur.execute('SELECT coalesce(sum(ok), 0), coalesce(sum(fail), 0) FROM agg_report WHERE folder = ?', [folder]).fetchone()
    return dict(
        available=True, sources=sorted(s for s, n in svc.items() if n), prev_folder=str(prev) if prev else None,
        biz=biz(folder), biz_prev=biz(prev) if ada_lama else None,     # None = simpel-loop tidak ada di folder sebelumnya
        pdf=dict(ok=pdf[0], fail=pdf[1]),
        login=dict(ok=_one(cur, 'SELECT coalesce(sum(ok), 0) FROM agg_login_ip WHERE folder = ?', folder),
                   users=_one(cur, 'SELECT coalesce(sum(users_ok), 0) FROM agg_service WHERE folder = ? AND service = ?', folder, AM)),
        mail=_all(cur, 'SELECT kind, n FROM agg_mail WHERE folder = ? ORDER BY n DESC, kind', folder),
        login_ok_by_hour=_all(cur, f"SELECT {H.format('hour_wib')}, ok FROM agg_login_hour WHERE folder = ? AND ok > 0 ORDER BY hour_wib", folder),
        tables={t: first(cur, t, folder) for t in ('activity', 'pdf-templates')})


# ------------------------------------------------------------------ Pelacakan
@router.get('/folders/{folder}/tracing')
def tracing(folder: str = Depends(folder_param), cur=Depends(cursor)):
    corr = cur.execute('SELECT matched, total FROM agg_corr WHERE folder = ?', [folder]).fetchone()
    if not corr: return _no('no_simpel_loop' if SL not in services(cur, folder) else 'no_correlation')
    gagal = 'folder = ? AND status BETWEEN 400 AND 599'
    by_ip = cells(cur, [dict(ip=ip, n=n) for ip, n in _all(cur, f'SELECT ip, sum(n)::BIGINT FROM agg_trace WHERE {gagal} GROUP BY ip ORDER BY 2 DESC, 1 LIMIT 10', folder)], ('ip',))
    return dict(
        available=True, corr=dict(matched=corr[0], total=corr[1]),
        kpi=dict(failed_requests=_one(cur, f'SELECT coalesce(sum(n), 0) FROM agg_trace WHERE {gagal}', folder),
                 failed_ips=_one(cur, f'SELECT count(DISTINCT ip) FROM agg_trace WHERE {gagal}', folder),
                 # TRD §4.4 butir 9: semua jejak lambat yang tidak gagal, apa pun statusnya
                 slow_requests=_one(cur, "SELECT coalesce(sum(n), 0) FROM agg_trace WHERE folder = ? AND error LIKE 'Lambat%'", folder)),
        by_ip=[dict(**r['ip'], n=r['n']) for r in by_ip],
        by_error=_all(cur, f"SELECT status || ' ' || error, sum(n)::BIGINT FROM agg_trace WHERE {gagal} GROUP BY 1 ORDER BY 2 DESC, 1 LIMIT 10", folder),
        tables=dict(trace=first(cur, 'trace', folder)))


# ------------------------------------------------------------------ Halaman layanan
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
        tables={t: v for t, v in tabel.items() if v['total']})   # kartu yang datanya kosong tidak dikirim (inv. §2.10)
