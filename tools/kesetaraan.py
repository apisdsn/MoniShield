#!/usr/bin/env python3
"""Perbandingan angka v2 dengan sistem lama (TRD §9.3). Dipakai tests/test_equivalence.py dan laporan.

E1  setiap angka di docs/00-acuan.json (statistik MENTAH sistem lama, sebelum dipotong top-N) vs query agregat v2.
E3  pemilik jaringan tiap IP di dashboard.html lama vs tabel ip_info.
E4  daftar TERTUTUP selisih yang diharapkan (perbaikan definisi TRD §4.4 butir 1, 2, 3, 4, 9).

E2  isi tiap DAFTAR di dashboard.html lama vs respons API v2 (aplikasi sungguhan, di dalam proses).
"""
import collections, json, os, sys

V2 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, V2)
sys.path.insert(0, os.path.join(V2, 'tools'))

NG, FE, SL, AM, RP = 'nginx-ingress-controller', 'om-fe-inhouse', 'om-be-simpel-loop', 'om-be-appsmanager', 'om-be-report'
ONE = lambda con, sql, *p: con.execute(sql, list(p)).fetchone()[0]
MAP = lambda con, sql, *p: dict(con.execute(sql, list(p)).fetchall())

# --------------------------------------------------------------------------- E1
# key -> (fungsi(con, folder, service) -> nilai). Metrik yang hanya ada di nginx bernilai 0 di layanan lain,
# karena memang hanya nginx yang menghasilkannya (alur, serangan, pod, Uptime-Kuma, …).
SVC = {}


def svc_key(name):
    def deco(fn): SVC[name] = fn; return fn
    return deco


def _agg_service(con, f, s, col):
    r = con.execute(f'SELECT {col} FROM agg_service WHERE folder = ? AND service = ?', [f, s]).fetchone()
    return r[0] if r else 0


for _k, _c in (('lines', 'lines'), ('err', 'err'), ('warn', 'warn'), ('req', 'requests'), ('s4', 'n4xx'), ('s5', 'n5xx'), ('ip_unik', 'ip_unique')):
    SVC[_k] = (lambda c: lambda con, f, s: _agg_service(con, f, s, c))(_c)

SVC['jam'] = lambda con, f, s: ONE(con, 'SELECT count(*) FROM agg_hour WHERE folder = ? AND service = ? AND total > 0', f, s)
SVC['jam_total'] = lambda con, f, s: ONE(con, 'SELECT coalesce(sum(total), 0) FROM agg_hour WHERE folder = ? AND service = ?', f, s)
SVC['endpoint_unik'] = lambda con, f, s: ONE(con, 'SELECT count(*) FROM agg_endpoint WHERE folder = ? AND service = ?', f, s)
SVC['endpoint_min5'] = lambda con, f, s: ONE(con, 'SELECT count(*) FROM agg_endpoint WHERE folder = ? AND service = ? AND dur_n >= 5', f, s)
SVC['pesan_unik'] = lambda con, f, s: ONE(con, 'SELECT count(*) FROM agg_message WHERE folder = ? AND service = ?', f, s)
SVC['level'] = lambda con, f, s: MAP(con, 'SELECT level, n FROM agg_level WHERE folder = ? AND service = ?', f, s)
SVC['jwt'] = lambda con, f, s: MAP(con, 'SELECT bucket, n FROM agg_jwt WHERE folder = ? AND service = ?', f, s)
SVC['restart'] = lambda con, f, s: ONE(con, 'SELECT count(*) FROM v_restart WHERE folder = ? AND service = ?', f, s)

# --- hanya nginx ---
NGINX_ONLY = {
    'alur_ip': 'SELECT count(*) FROM (SELECT DISTINCT ip, upstream FROM agg_flow WHERE folder = ?)',
    'alur_ip_asal': 'SELECT count(DISTINCT ip) FROM agg_flow WHERE folder = ?',
    'serangan_req': 'SELECT coalesce(sum(hits), 0) FROM agg_attack_url WHERE folder = ?',
    'serangan_url': 'SELECT count(*) FROM agg_attack_url WHERE folder = ?',
    'serangan_ip': 'SELECT count(*) FROM agg_attack_ip WHERE folder = ?',
    'ip_4xx': "SELECT count(*) FROM agg_ip WHERE folder = ? AND service = 'nginx-ingress-controller' AND n4xx > 0",
    'klien_401': 'SELECT count(*) FROM agg_c401 WHERE folder = ?',
    'total_5xx_upstream': 'SELECT coalesce(sum(n5xx), 0) FROM agg_upstream WHERE folder = ?',
    'insiden_5xx': 'SELECT count(*) FROM agg_incident WHERE folder = ?',
    'pod_backend': 'SELECT count(*) FROM agg_pod WHERE folder = ?',
    'retry': 'SELECT coalesce(sum(n), 0) FROM agg_retry WHERE folder = ?',
    'error_koneksi_pod': 'SELECT count(*) FROM v_upstream_error WHERE folder = ?',
    'uptime_kuma': 'SELECT coalesce(sum(n), 0) FROM agg_uk_hour WHERE folder = ?',
    'uptime_kuma_gagal': 'SELECT coalesce(sum(fail), 0) FROM agg_uk_hour WHERE folder = ?',
}
for _k, _q in NGINX_ONLY.items():
    SVC[_k] = (lambda q: lambda con, f, s: ONE(con, q, f) if s == NG else 0)(_q)

SVC['serangan_kategori'] = lambda con, f, s: MAP(con, 'SELECT category, n::INT FROM v_attack_cat WHERE folder = ?', f) if s == NG else {}

# --- hanya simpel-loop ---
SL_ONLY = {
    'event_simpel_loop': 'SELECT count(*) FROM sl_event WHERE folder = ?',
    'lambat_1dtk': 'SELECT count(*) FROM agg_slow WHERE folder = ?',
    'email_notifikasi': 'SELECT coalesce(sum(n), 0) FROM agg_mail WHERE folder = ?',
    'aktivitas': 'SELECT coalesce(sum(n), 0) FROM agg_activity WHERE folder = ?',
}
for _k, _q in SL_ONLY.items():
    SVC[_k] = (lambda q: lambda con, f, s: ONE(con, q, f) if s == SL else 0)(_q)

SVC['bisnis'] = lambda con, f, s: MAP(con, 'SELECT metric, n FROM agg_biz WHERE folder = ?', f) if s == SL else {}
SVC['korelasi'] = lambda con, f, s: (list(con.execute('SELECT matched, total FROM agg_corr WHERE folder = ?', [f]).fetchone() or []) or None) if s == SL else None

# --- hanya appsmanager / report ---
# login_ip di acuan = SEMUA IP yang punya event login (gagal, reset, atau sukses); KPI 'IP dengan login gagal'
# yang hanya menghitung fail/lock ada di tampilan, diuji di Tahap 11.
for _k, _q in {'login_ip': 'SELECT count(*) FROM agg_login_ip WHERE folder = ?',
               'login_gagal': 'SELECT coalesce(sum(fail), 0) FROM agg_login_ip WHERE folder = ?',
               'login_reset': 'SELECT coalesce(sum(lock), 0) FROM agg_login_ip WHERE folder = ?',
               'login_sukses': 'SELECT coalesce(sum(ok), 0) FROM agg_login_ip WHERE folder = ?',
               'akun_dianalisis': 'SELECT count(*) FROM agg_account WHERE folder = ?'}.items():
    SVC[_k] = (lambda q: lambda con, f, s: ONE(con, q, f) if s == AM else 0)(_q)
for _k, _c in (('pdf_sukses', 'ok'), ('pdf_gagal', 'fail')):
    SVC[_k] = (lambda c: lambda con, f, s: (ONE(con, f'SELECT coalesce(sum({c}), 0) FROM agg_report WHERE folder = ?', f) if s == RP else 0))(_c)

# Dikecualikan dari E1 karena memang sengaja berbeda (E4) atau bukan angka tunggal.
E1_LEWATI = {'jejak', 'seharusnya', 'lama'}


def e1(con, acuan):
    """[(folder, layanan, kunci, lama, baru)] untuk SEMUA angka acuan; hanya yang berbeda yang perlu dilihat."""
    out = []
    for folder, v in acuan['days'].items():
        for svc, a in v.items():
            if svc == '_file':
                out.append((folder, '(file)', 'jumlah', a['jumlah'], ONE(con, 'SELECT count(*) FROM ingest_file WHERE folder = ?', folder)))
                out.append((folder, '(file)', 'kosong', a['kosong'], ONE(con, 'SELECT count(*) FROM ingest_file WHERE folder = ? AND lines = 0', folder)))
                continue
            for k, lama in a.items():
                if k in E1_LEWATI or k not in SVC: continue
                if k == 'level' and svc == SL: continue      # E4 butir 4
                out.append((folder, svc, k, lama, SVC[k](con, folder, svc)))
    return out


# --------------------------------------------------------------------------- E2
def klien_api():
    """Aplikasi v2 di dalam proses (TestClient) atas database nyata, sudah masuk sebagai admin. Akun di SQLite sementara."""
    import dataclasses, tempfile
    from fastapi.testclient import TestClient
    from monishield.infrastructure import auth, config
    from monishield.interfaces.api import app as appmod
    auth.SCRYPT = (10, 8, 1)   # hash murah: ini alat banding, bukan server
    pw, x = 'sandi-pembanding-pertama', {'X-Requested-With': 'kesetaraan'}
    # attack_rules='lama': kesetaraan dibuktikan dengan aturan serangan sistem lama (Tahap 21: tampilan memakai CRS)
    c = dataclasses.replace(config.load(), auth_database_url='sqlite:///' + os.path.join(tempfile.mkdtemp(), 'auth.db'), ingest_on_start=False, attack_rules='lama',
                            cookie_secure=False, admin_user='admin', admin_password=pw, jwt_secret='rahasia-sementara-alat-pembanding-kesetaraan')
    tc = TestClient(appmod.create_app(c)); tc.__enter__()
    assert tc.post('/api/auth/login', json=dict(username='admin', password=pw), headers=x).status_code == 200
    assert tc.post('/api/me/password', json=dict(old_password=pw, new_password=pw + '-2'), headers=x).status_code == 200
    return tc


def _beku(x):
    """Bentuk yang bisa dibandingkan dan dihitung: angka pecahan dibulatkan, dict diurutkan."""
    if isinstance(x, float): return round(x, 6)
    if isinstance(x, dict): return tuple(sorted((str(k), _beku(v)) for k, v in x.items()))
    if isinstance(x, (list, tuple)): return tuple(_beku(v) for v in x)
    return x


def _status(d): return ' '.join(f'{c}×{n}' for c, n in sorted(d.items()))   # bentuk teks lama: '200×3 401×1'


def e2(get, D):
    """[(folder, layanan, daftar, jumlah baris lama, masalah | None)] untuk setiap daftar di D['days'].

    Aturan: (1) setiap baris lama ada di daftar LENGKAP v2 dengan isi yang sama persis; (2) urutan nilai pengurut
    N baris pertama v2 sama dengan urutan lama. Jadi urutan boleh berbeda hanya di antara baris bernilai sama,
    dan daftar v2 boleh lebih panjang (tidak dipotong lagi, TRD K4).
    """
    out = []

    def semua(path):
        rows, off = [], 0
        while True:
            j = get(path + ('&' if '?' in path else '?') + f'limit=500&offset={off}')
            rows += j['rows']; off += 500
            if off >= j['matched']: return rows

    def daftar(folder, svc, nama, lama, baru, kunci=lambda r: r[1], urut=True):
        lama, baru = [_beku(r) for r in lama], [_beku(r) for r in baru]
        sisa, hilang = collections.Counter(baru), []
        for r in lama:
            if sisa[r] <= 0: hilang.append(r)
            sisa[r] -= 1
        masalah = None
        if hilang: masalah = f'{len(hilang)} baris lama tidak ada di v2, mis. {hilang[0]!r:.300}'
        elif urut and [kunci(r) for r in lama] != [kunci(r) for r in baru[:len(lama)]]: masalah = 'urutan nilai berbeda'
        out.append((folder, svc, nama, len(lama), masalah))

    def sama(folder, svc, nama, lama, baru):
        out.append((folder, svc, nama, len(lama) if hasattr(lama, '__len__') else 1, None if _beku(lama) == _beku(baru) else f'lama {lama!r:.200} vs baru {baru!r:.200}'))

    for folder, v in D['days'].items():
        F = f'/api/folders/{folder}'
        tab = lambda t, q='': semua(f'{F}/tables/{t}{q}')
        sama(folder, '(file)', 'files', sorted((f['svc'], f['pod'], f['ns'], f['lines'], f['err'], f['warn'], f['size']) for f in D['files'] if f['date'] == folder),
             sorted((f['service'], f['pod'], f['ns'], f['lines'], f['err'], f['warn'], f['size_bytes']) for f in get(F)['files']))
        for svc, s in v.items():
            q = f'?service={svc}'
            hal = get(f'{F}/services/{svc}')
            if not s['lines']:
                sama(folder, svc, 'kosong', False, hal['available']); continue
            sama(folder, svc, 'status', s['status'], hal['status'])
            sama(folder, svc, 'hour', s['hour'], [[h, n] for h, n, _ in hal['hour'] if n])
            if svc not in (NG, FE): sama(folder, svc, 'herr', s['herr'], {h: e for h, _, e in hal['hour'] if e})      # nginx/FE: E4 butir 2
            if svc != SL: sama(folder, svc, 'extra', dict(s['extra']), dict(hal['levels']))                           # simpel-loop: E4 butir 4
            daftar(folder, svc, 'msgs', s['msgs'], [(r['msg_key'], r['n'], r['sample']) for r in tab('messages', q)])
            if s['paths']: daftar(folder, svc, 'paths', s['paths'], [(r['key'], r['n']) for r in tab('endpoints', q)])
            if s['perr']: daftar(folder, svc, 'perr', s['perr'], [(f"{r['status']} {r['key']}", r['n']) for r in tab('endpoint-errors', q)])
            if s['ips']: daftar(folder, svc, 'ips', s['ips'], [(r['ip']['ip'], r['n']) for r in tab('ips', q)])
            if s['ep']: daftar(folder, svc, 'ep', s['ep'], [(r['key'], r['requests'], r['n4xx'], r['n5xx'], r['p50'], r['p95'], r['p99'], r['max'])
                                                         for r in tab('endpoint-perf', q + '&sort=requests')])
            if s['slow']: daftar(folder, svc, 'slow', s['slow'], [(r['duration_ms'], r['key'], str(r['status'])) for r in tab('slow', q)], kunci=lambda r: r[0])
            if s['restart']: sama(folder, svc, 'restart', s['restart'], [[r['time'], r['pod'], r['app'], r['seconds']] for r in tab('restarts') if r['service'] == svc])
            if s['jwt']:
                rc = get(f'{F}/rootcause')
                sama(folder, svc, 'jwt', s['jwt'], {**rc['jwt'].get(svc, {}), **({'Refresh Token Kedaluwarsa': rc['refresh_expired'][svc]} if svc in rc['refresh_expired'] else {})})
            if svc == 'coredns': daftar(folder, svc, 'paths (dns)', s['paths'], [(r['domain'], r['n']) for r in tab('dns')])
            if svc == NG:
                sec, av = get(f'{F}/security'), get(f'{F}/availability')
                daftar(folder, svc, 'up', s['up'], hal['upstreams'])
                daftar(folder, svc, 'ua', s['ua'], [(r['ua'], r['n']) for r in tab('user-agents', q)])
                daftar(folder, svc, 'atk', s['atk'], [(r['category'], r['method_path'], r['hits'], r['ip_count'], r['top_ip']['ip'], _status(r['status_counts']), r['sizes'],
                                                       r['upstreams'], r['ua'], r['first'], r['last']) for r in tab('attack-urls', '?sort=hits')], kunci=lambda r: r[2])
                daftar(folder, svc, 'atk_ip', s['atk_ip'], [(r['ip']['ip'], r['hits'], r['cats'], _status(r['status_counts']), r['ua'], r['first'], r['last']) for r in tab('attack-ips')])
                sama(folder, svc, 'atk_h', s['atk_h'], sec['by_hour'])
                sama(folder, svc, 'atk_cat', dict(s['atk_cat']), {c: n for c, n, _ in sec['by_category']})
                daftar(folder, svc, 'ip4', s['ip4'], [(r['ip']['ip'], r['n'], r['ua']) for r in tab('ip-4xx')])
                sama(folder, svc, 'incidents', s['incidents'], [[r['start'], r['end'], r['n'], r['upstreams'], r['statuses']] for r in tab('incidents')])
                sama(folder, svc, 'up5', s['up5'], dict(av['n5xx_by_upstream']))
                daftar(folder, svc, 'c401', s['c401'], [(r['client']['ip'], r['endpoint'], r['n'], r['peak_per_min'], r['first'], r['last']) for r in tab('c401')], kunci=lambda r: r[2])
                sama(folder, svc, 'uk', s['uk'], [[h, n] for h, n, _ in av['uptime_by_hour']])
                sama(folder, svc, 'ukf', s['ukf'], {h: g for h, _, g in av['uptime_by_hour'] if g})
                daftar(folder, svc, 'uk_t', s['uk_t'], [(r['target'], r['n']) for r in tab('uptime-targets')])
                pod = tab('backend-pods')
                sama(folder, svc, 'pod', s['pod'], [[r['upstream'], r['pod'], r['requests'], r['n5xx']] for r in pod])
                if len(s['retry']) < 30:     # daftar lama dipotong 30 (E4 butir 1): jumlah per pod hanya sebanding bila tidak terpotong
                    lama_retry = collections.Counter()
                    for up, a, _, n in s['retry']: lama_retry[f'{up} {a}'] += n
                    sama(folder, svc, 'retry per pod', dict(lama_retry), {f"{r['upstream']} {r['pod']}": r['retries'] for r in pod if r['retries']})
                daftar(folder, svc, 'uperr', s['uperr'], [(r['time'], r['kind'], r['pod'], r['request']) for r in tab('upstream-errors')], urut=False)
                # 3 pod teratas: yang bernilai sama boleh berbeda urutan, jadi yang dibandingkan jumlahnya
                daftar(folder, svc, 'flow', [(r[0], r[1], r[2], [n for _, n in r[3]]) for r in s['flow']],
                       [(r['src']['ip'], r['upstream'], r['requests'], [n for _, n in r['pods']]) for r in tab('flows')], kunci=lambda r: r[2])
            if svc == AM:
                sec, biz = get(f'{F}/security'), get(f'{F}/business')
                daftar(folder, svc, 'login', s['login'], [(r['ip']['ip'], r['fail'], r['lock'], r['ok'], r['accounts'], r['first'], r['last']) for r in tab('login-ips')],
                       kunci=lambda r: (r[2], r[1]))
                daftar(folder, svc, 'acct', s['acct'], [(r['account'], r['fail'], r['lock'], r['ok'], [c['ip'] for c in r['fail_ips']], [c['ip'] for c in r['ok_ips']], r['flags'],
                                                         r['first'], r['last'], r['notes']) for r in tab('accounts')],
                       kunci=lambda r: ('Sukses Dari IP Berbeda' in r[6], len(r[6]), r[1]))
                sama(folder, svc, 'login_h', s['login_h'], sec['login_by_hour'])
                sama(folder, svc, 'login_okh', s['login_okh'], biz['login_ok_by_hour'])
                sama(folder, svc, 'login_ok/users_ok', [s['login_ok'], s['users_ok']], [biz['login']['ok'], biz['login']['users']])
            if svc == RP and s['rep']:
                daftar(folder, svc, 'rep', s['rep'], [(r['template'], r['ok'], r['fail']) for r in tab('pdf-templates')], kunci=lambda r: (r[2], r[1]))
            if svc == SL:
                biz, tr = get(f'{F}/business'), get(f'{F}/tracing')
                sama(folder, svc, 'biz', s['biz'], biz['biz'])
                daftar(folder, svc, 'mail', s['mail'], biz['mail'])
                daftar(folder, svc, 'act', s['act'], [(r['key'], r['n']) for r in tab('activity')])
                sama(folder, svc, 'corr', s['corr'], [tr['corr']['matched'], tr['corr']['total']] if tr['available'] else None)
                if s['trace']: daftar(folder, svc, 'trace', s['trace'], [(r['client']['ip'], str(r['status']), r['error'], r['key'], r['n'], r['url'], r['upstream'], r['ua'],
                                                                         r['first'], r['last'], r['max_ms']) for r in tab('trace')], kunci=lambda r: r[4])
    return out


def cetak_e2(r2, keluar=None):
    p = lambda *a: print(*a, file=keluar or sys.stdout)
    beda = [r for r in r2 if r[4]]
    p(f'E2 isi daftar vs API: {len(r2)} daftar ({sum(r[3] for r in r2)} baris lama) dibandingkan, berbeda: {len(beda)}')
    for r in beda[:60]: p(f'   BEDA {r[0]} {r[1]} {r[2]}: {r[4]}')
    return not beda


# --------------------------------------------------------------------------- E3
def e3(con, D):
    """[(ip, lama, baru)] pemilik jaringan. Lokasi tidak dibandingkan: sumbernya kini GeoLite2 (TRD §3.6)."""
    baru = {r[0]: (r[1], r[2], r[3]) for r in con.execute('SELECT ip, asn, cc, org FROM ip_info').fetchall()}
    return [(ip, (v['asn'], v['cc'], v['org']), baru.get(ip)) for ip, v in D['ipinfo'].items()]


def e3_lokasi(con, D):
    """Ringkasan perbedaan lokasi DB-IP (lama) vs GeoLite2 (baru): bukan kegagalan, hanya dicatat."""
    baru = {r[0]: (r[1], r[2]) for r in con.execute('SELECT ip, city, country FROM ip_info WHERE lat IS NOT NULL').fetchall()}
    sama_negara = sama_kota = 0
    contoh = []
    for ip, g in D['geo'].items():
        if ip not in baru: continue
        kota, negara = baru[ip]
        sama_negara += g[2] == negara
        sama_kota += g[0] == kota
        if g[0] != kota and len(contoh) < 10: contoh.append((ip, g[0], kota))
    n = sum(1 for ip in D['geo'] if ip in baru)
    return dict(dibandingkan=n, negara_sama=sama_negara, kota_sama=sama_kota, tidak_ada_di_v2=len(D['geo']) - n, contoh=contoh)


# --------------------------------------------------------------------------- E4
def _trace_lama(D, folder, kunci):
    s = D['days'].get(folder, {}).get(SL) or {}
    return len(s.get('trace') or []) if kunci == 'n' else s


def e4(con, acuan, D):
    """[(folder, butir, ukuran, lama, baru, seharusnya, status)] — daftar TERTUTUP selisih yang diharapkan."""
    out = []

    def tambah(folder, butir, ukuran, lama, baru, seharusnya):
        if seharusnya is None: status = 'tidak dipotong lagi' if baru >= (lama or 0) else 'GAGAL'
        else: status = 'ok' if baru == seharusnya else 'GAGAL'
        out.append((folder, butir, ukuran, lama, baru, seharusnya, status))

    for folder, v in acuan['days'].items():
        d = D['days'].get(folder, {})
        n, sl = d.get(NG) or {}, d.get(SL) or {}
        a_ng, a_sl, a_am = v.get(NG) or {}, v.get(SL) or {}, v.get(AM) or {}
        if n:
            # butir 1: KPI yang di sistem lama dihitung dari daftar yang sudah dipotong
            tambah(folder, 1, 'error koneksi pod', len(n.get('uperr', [])), ONE(con, 'SELECT count(*) FROM v_upstream_error WHERE folder = ?', folder), a_ng.get('error_koneksi_pod'))
            tambah(folder, 1, 'retry ke pod lain', sum(r[3] for r in n.get('retry', [])), ONE(con, 'SELECT coalesce(sum(n), 0) FROM agg_retry WHERE folder = ?', folder), a_ng.get('retry'))
            tambah(folder, 1, 'IP sumber serangan', len(n.get('atk_ip', [])), ONE(con, 'SELECT count(*) FROM agg_attack_ip WHERE folder = ?', folder), a_ng.get('serangan_ip'))
            tambah(folder, 1, 'klien 401 berulang', len(n.get('c401', [])), ONE(con, 'SELECT count(*) FROM agg_c401 WHERE folder = ?', folder), a_ng.get('klien_401'))
            tambah(folder, 1, 'alur IP (peta)', len(n.get('flow', [])), ONE(con, 'SELECT count(*) FROM (SELECT DISTINCT ip, upstream FROM agg_flow WHERE folder = ?)', folder), a_ng.get('alur_ip'))
        if d.get(AM):
            # 'IP dengan login gagal' (batas 100) dan 'akun dianalisis' (batas 150) tidak pernah mencapai batas
            # pada data ini, jadi nilainya memang tidak berubah; tetap diperiksa agar ketahuan bila kelak tercapai.
            tambah(folder, 1, 'IP dengan login gagal', len(d[AM].get('login', [])), ONE(con, 'SELECT count(*) FROM agg_login_ip WHERE folder = ? AND (fail > 0 OR lock > 0)', folder), len(d[AM].get('login', [])) if len(d[AM].get('login', [])) < 100 else None)
            tambah(folder, 1, 'akun dianalisis', len(d[AM].get('acct', [])), ONE(con, 'SELECT count(*) FROM agg_account WHERE folder = ?', folder), a_am.get('akun_dianalisis'))
        if sl:
            tambah(folder, 1, 'baris jejak request', len(sl.get('trace', [])), ONE(con, 'SELECT count(*) FROM agg_trace WHERE folder = ?', folder), None)
        # butir 2: error per jam memuat baris error log, sehingga jumlahnya = KPI Error
        for svc in (NG, FE, AM, 'om-be-referensi', RP, 'coredns'):
            a = v.get(svc) or {}
            if not a or a.get('seharusnya', {}).get('herr_total') is None: continue
            tambah(folder, 2, f'Σ error per jam ({svc})', a['lama']['herr_total'],
                   ONE(con, 'SELECT coalesce(sum(err), 0) FROM agg_hour WHERE folder = ? AND service = ?', folder, svc), a['seharusnya']['herr_total'])
        # butir 4: distribusi level simpel-loop memakai tingkat efektif
        if a_sl.get('seharusnya', {}).get('level_error') is not None:
            lv = MAP(con, 'SELECT level, n FROM agg_level WHERE folder = ? AND service = ?', folder, SL)
            lama_lv = dict(sl.get('extra', []))
            for key, kolom in (('ERROR', 'level_error'), ('WARN', 'level_warn')):
                tambah(folder, 4, f'level simpel-loop {key}', lama_lv.get(key, 0), lv.get(key, 0), a_sl['seharusnya'][kolom])
            tambah(folder, 4, 'level simpel-loop (total)', sum(lama_lv.values()), sum(lv.values()), sum(lama_lv.values()))
        # butir 9: 'lambat >= 5 dtk' memuat jejak lambat berstatus apa pun yang tidak gagal
        if sl and a_sl.get('seharusnya'):
            tambah(folder, 9, 'request lambat ≥ 5 dtk', a_sl['lama']['lambat_5dtk'],
                   ONE(con, "SELECT coalesce(sum(n), 0) FROM agg_trace WHERE folder = ? AND error LIKE 'Lambat%'", folder), a_sl['seharusnya']['lambat_5dtk'])
    # butir 3: crit di frontend dihitung error (lama: warning). Tidak ada baris crit pada data ini.
    crit = ONE(con, "SELECT count(*) FROM nginx_error WHERE service = 'om-fe-inhouse' AND level IN ('crit', 'alert', 'emerg')")
    out.append(('(semua)', 3, 'baris crit/alert/emerg di frontend', 0, crit, 0, 'ok' if crit == 0 else 'ADA SELISIH: periksa'))
    return out


# --------------------------------------------------------------------------- laporan
def jalankan(db_path=None, acuan_path=None):
    import duckdb
    import ekstrak_dashboard
    acuan = json.load(open(acuan_path or os.path.join(V2, 'docs', '00-acuan.json'), encoding='utf-8'))
    con = duckdb.connect(db_path or os.path.join(V2, 'data', 'monishield.duckdb'), read_only=True)
    D = ekstrak_dashboard.load()
    return acuan, con, D, e1(con, acuan), e3(con, D), e4(con, acuan, D)


def cetak(acuan, con, D, r1, r3, r4, keluar=None):
    p = lambda *a: print(*a, file=keluar or sys.stdout)  # dibaca saat dipanggil, bukan saat impor
    beda1 = [r for r in r1 if r[3] != r[4]]
    p(f"E1 angka acuan: {len(r1)} angka dibandingkan ({len(acuan['days'])} folder), berbeda: {len(beda1)}")
    for r in beda1[:40]: p(f'   BEDA {r[0]} {r[1]} {r[2]}: lama {r[3]} vs baru {r[4]}')
    beda3 = [r for r in r3 if r[1] != r[2]]
    p(f'E3 pemilik jaringan IP: {len(r3)} IP dibandingkan, berbeda: {len(beda3)}')
    for r in beda3[:10]: p(f'   BEDA {r[0]}: lama {r[1]} vs baru {r[2]}')
    lok = e3_lokasi(con, D)
    p(f"   lokasi (sumber berganti DB-IP -> GeoLite2, bukan kegagalan): {lok['dibandingkan']} IP, negara sama "
      f"{lok['negara_sama']} ({round(100 * lok['negara_sama'] / max(lok['dibandingkan'], 1))}%), kota sama {lok['kota_sama']}")
    for ip, a, b in lok['contoh'][:5]: p(f'      {ip}: DB-IP {a} -> GeoLite2 {b}')
    gagal4 = [r for r in r4 if 'GAGAL' in r[6] or 'periksa' in r[6]]
    p(f'E4 selisih yang diharapkan: {len(r4)} pemeriksaan, tidak sesuai: {len(gagal4)}')
    for butir in (1, 2, 3, 4, 9):
        rows = [r for r in r4 if r[1] == butir and r[3] != r[4]]
        if rows:
            p(f'   butir {butir}: {len(rows)} ukuran berubah; contoh:')
            for r in rows[:4]: p(f'      {r[0]} {r[2]}: lama {r[3]} -> baru {r[4]} (seharusnya {r[5]}) [{r[6]}]')
    for r in gagal4: p(f'   TIDAK SESUAI {r[0]} butir {r[1]} {r[2]}: lama {r[3]} baru {r[4]} seharusnya {r[5]}')
    return not beda1 and not beda3 and not gagal4


if __name__ == '__main__':
    hasil = jalankan()
    ok = cetak(*hasil)
    hasil[1].close()                      # E2 membuka database lewat aplikasi: lepaskan dulu koneksi baca
    tc = klien_api()
    ok2 = cetak_e2(e2(lambda path: tc.get(path).json(), hasil[2]))
    tc.__exit__(None, None, None)
    sys.exit(0 if ok and ok2 else 1)
