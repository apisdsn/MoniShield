"""Kerangka dashboard: kesehatan, daftar folder + konfigurasi tampilan, ringkasan satu folder (TRD §5.2)."""
from fastapi import APIRouter, Depends, Request

from .. import __version__, refdata
from .common import cursor, folder_param, public, require_user_ready, wib

router = APIRouter(prefix='/api')


@router.get('/health', dependencies=[Depends(public)])
def health(): return dict(ok=True)   # tanpa data, tanpa sesi


@router.get('/meta')
def meta(request: Request, user=Depends(require_user_ready), cur=Depends(cursor)):
    cfg = request.app.state.cfg
    folders = [dict(folder=str(f), range_start=wib(a), range_end=wib(b), lines=lines, services=svc, files=files, files_empty=empty, files_corrupt=corrupt)
               for f, a, b, lines, files, empty, corrupt, svc in cur.execute(
                   """SELECT s.folder, s.range_start_utc, s.range_end_utc, s.lines, s.files, s.files_empty, s.files_corrupt,
                             (SELECT count(*) FROM agg_service a WHERE a.folder = s.folder)
                      FROM folder_state s ORDER BY s.folder DESC""").fetchall()]
    kota, prov, cc, lat, lon = cfg.server_fallback
    g = cur.execute('SELECT city, region, country, lat, lon FROM ip_info WHERE ip = ?', [cfg.server_ip]).fetchone()
    if g and g[3] is not None:   # GeoLite2 sering memberi koordinat tanpa nama kota untuk IP server: nama dari server_fallback
        kota, prov, cc, lat, lon = g[0] or kota, g[1] or prov, g[2] or cc, g[3], g[4]
    owner, located = cur.execute('SELECT count(*) FILTER (WHERE org IS NOT NULL), count(*) FILTER (WHERE lat IS NOT NULL) FROM ip_info').fetchone()
    st = request.app.state.ingest.state
    return dict(version=__version__, folders=folders, hosts=cfg.hosts,
                server=dict(ip=cfg.server_ip, city=kota, region=prov, cc=cc, lat=lat, lon=lon), dns_upstream=cfg.dns_upstream,
                ip_data=dict(owner=owner > 0, location=located > 0, map=refdata.map_ready(cfg)), attribution=refdata.ATTRIBUTION,
                ingest=dict(running=st['running'], phase=st['phase'], last_status=(st['last'] or {}).get('status'), error=st['error']))


@router.get('/folders/{folder}')
def folder_summary(folder: str = Depends(folder_param), user=Depends(require_user_ready), cur=Depends(cursor)):
    prev = cur.execute('SELECT max(folder) FROM folder_state WHERE folder < ?', [folder]).fetchone()[0]
    lama = {r[0]: dict(lines=r[1], err=r[2], warn=r[3]) for r in cur.execute('SELECT service, lines, err, warn FROM agg_service WHERE folder = ?', [prev]).fetchall()} if prev else {}
    # urutan layanan = urutan file pertama tiap layanan (urutan baca sistem lama)
    services = [dict(service=s, lines=lines, err=err, warn=warn, err_http=eh, err_log=el, files=files, files_empty=fe, files_corrupt=fc,
                     requests=req, n4xx=n4, n5xx=n5, ip_unique=ipu, prev=lama.get(s))
                for s, lines, err, warn, eh, el, files, fe, fc, req, n4, n5, ipu in cur.execute(
                    """SELECT a.service, a.lines, a.err, a.warn, a.err_http, a.err_log, a.files, a.files_empty, a.files_corrupt, a.requests, a.n4xx, a.n5xx, a.ip_unique
                       FROM agg_service a JOIN (SELECT service, min(relpath) AS first FROM ingest_file WHERE folder = $f GROUP BY service) o USING (service)
                       WHERE a.folder = $f ORDER BY o.first""", {'f': folder}).fetchall()]
    files = [dict(service=s, pod=pod, ns=ns, lines=lines, err=err, warn=warn, size_bytes=size, status=status)
             for s, pod, ns, lines, err, warn, size, status in cur.execute(
                 'SELECT service, pod, ns, lines, err, warn, size_bytes, status FROM ingest_file WHERE folder = ? ORDER BY relpath', [folder]).fetchall()]
    r = cur.execute('SELECT range_start_utc, range_end_utc FROM folder_state WHERE folder = ?', [folder]).fetchone()
    return dict(folder=folder, prev_folder=str(prev) if prev else None, range_start=wib(r[0]), range_end=wib(r[1]),
                attack_ip_count=cur.execute('SELECT count(*) FROM agg_attack_ip WHERE folder = ?', [folder]).fetchone()[0],
                services=services, files=files)
