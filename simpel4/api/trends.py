"""Halaman Tren (TRD §5.3)."""
from fastapi import APIRouter, Depends, Request

from .common import ApiError, cursor, require_user_ready, _all
from .tables import NG

TREND_BIZ = ('Laporan Dibuat', 'Registrasi Laporan', 'File Diunggah', 'Email Terkirim', 'OTP Diminta')

router = APIRouter(prefix='/api', dependencies=[Depends(require_user_ready)])


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
    # urutan layanan = urutan kemunculan pertama (folder terlama dulu, lalu urutan file di folder itu), sama dengan lama
    names = [r[0] for r in _all(cur, """WITH f AS (SELECT service, min(folder) AS f FROM agg_service WHERE folder >= ? GROUP BY service)
                                     SELECT f.service FROM f JOIN ingest_file i ON i.service = f.service AND i.folder = f.f
                                     GROUP BY f.service, f.f ORDER BY f.f, min(i.relpath)""", lo)]
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
