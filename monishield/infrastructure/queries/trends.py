"""Halaman Tren (TRD §5.3). Tahap 24: kelengkapan data (tanggal tanpa folder, file rusak/kosong, ingest terakhir) dan
heatmap jam × hari (request ingress, error semua layanan)."""
import datetime


from monishield.infrastructure.queries.sql import wib, _all, reject
from .tables import NG

TREND_BIZ = ('Laporan Dibuat', 'Registrasi Laporan', 'File Diunggah', 'Email Terkirim', 'OTP Diminta')


def trends(cur, cfg, params):
    last = params.get('last', '30')
    if last not in ('14', '30', '90', 'all'): raise reject(400, 'invalid_parameter', 'Parameter tidak sah: last.')
    folders = [str(r[0]) for r in _all(cur, 'SELECT folder FROM folder_state ORDER BY folder')]
    if last != 'all': folders = folders[-int(last):]
    if not folders: return dict(folders=[], services=[], lines={}, err={}, warn={}, http={}, security={}, business={}, file_status={},
                                completeness=None, heat=None)
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
    atk = 'agg_crs_url' if cfg.attack_rules == 'crs' else 'agg_attack_url'   # Tahap 21: aturan deteksi yang dipakai
    for f, n in _all(cur, f'SELECT folder::VARCHAR, sum(hits) FROM {atk} WHERE folder >= ? GROUP BY 1', lo): sec['attack_requests'][pos[f]] = int(n)
    # lama: Σ login[*][1] dan [2] = hanya IP yang punya gagal/reset; sama dengan jumlah semua baris
    for f, a, b in _all(cur, 'SELECT folder::VARCHAR, sum(fail), sum(lock) FROM agg_login_ip WHERE folder >= ? GROUP BY 1', lo):
        sec['login_fail'][pos[f]], sec['resets'][pos[f]] = int(a), int(b)
    biz = {k: kosong(0) for k in TREND_BIZ}
    for f, m, n in _all(cur, f"SELECT folder::VARCHAR, metric, n FROM agg_biz WHERE folder >= ? AND metric IN ({', '.join('?' * len(TREND_BIZ))})", lo, *TREND_BIZ): biz[m][pos[f]] = n
    return dict(folders=folders, services=names, **out, http=http, security=sec, business=biz,
                completeness=_completeness(cur, folders), heat=_heat(cur, lo))


def _completeness(cur, folders):
    """Tanggal di rentang yang tidak punya folder log, file rusak/kosong per folder, ingest terakhir yang selesai."""
    ada = {datetime.date.fromisoformat(f) for f in folders}
    a, b = min(ada), max(ada)
    missing = [str(a + datetime.timedelta(days=i)) for i in range((b - a).days + 1) if a + datetime.timedelta(days=i) not in ada]
    st = {str(f): (c, e) for f, c, e in _all(cur, 'SELECT folder, files_corrupt, files_empty FROM folder_state WHERE folder >= ?', folders[0])}
    run = cur.execute('SELECT finished_at, status, files_changed FROM ingest_run WHERE finished_at IS NOT NULL ORDER BY run_id DESC LIMIT 1').fetchone()
    return dict(missing=missing, corrupt=[st.get(f, (0, 0))[0] for f in folders], empty=[st.get(f, (0, 0))[1] for f in folders],
                last_ingest=dict(time=wib(run[0]), status=run[1], files_changed=run[2]) if run else None)


def _heat(cur, lo):
    """Jam (WIB) × tanggal: request ingress nginx dan error semua layanan, dari agg_hour."""
    rows = _all(cur, f"""SELECT strftime(hour_wib, '%Y-%m-%d'), hour(hour_wib)::INTEGER, coalesce(sum(total) FILTER (WHERE service = '{NG}'), 0), sum(err)
                          FROM agg_hour WHERE folder >= ? GROUP BY 1, 2 ORDER BY 1, 2""", lo)
    days = sorted({r[0] for r in rows})
    pos = {d: i for i, d in enumerate(days)}
    req, err = [[0] * 24 for _ in days], [[0] * 24 for _ in days]
    for d, h, n, e in rows: req[pos[d]][h], err[pos[d]][h] = int(n), int(e)
    return dict(days=days, requests=req, errors=err)
