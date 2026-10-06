"""Uji kesetaraan v2 vs sistem lama atas folder log NYATA (TRD §9.3, PRD §6.2).

E1 angka acuan, E2 isi daftar vs API, E3 pemilik jaringan IP, E4 daftar tertutup selisih yang diharapkan.
Butuh: data/simpel4.duckdb hasil ingest, ../dashboard.html, dan docs/00-acuan.json (dibuat
`python3 tools/acuan_lama.py`). Bila salah satu tidak ada, uji dilewati dengan keterangan.
"""
import json, os, sys

import pytest

V2 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(V2, 'tools'))
DB = os.path.join(V2, 'data', 'simpel4.duckdb')
ACUAN = os.path.join(V2, 'docs', '00-acuan.json')
LAMA = os.path.join(os.path.dirname(V2), 'dashboard.html')


@pytest.fixture(scope='module')
def bahan():
    import duckdb
    for path, pesan in ((DB, 'database belum ada; jalankan: python -m simpel4 ingest'),
                        (LAMA, 'dashboard.html sistem lama tidak ada'),
                        (ACUAN, 'docs/00-acuan.json belum dibuat; jalankan: python3 tools/acuan_lama.py')):
        if not os.path.exists(path): pytest.skip(pesan)
    import ekstrak_dashboard, kesetaraan
    acuan = json.load(open(ACUAN, encoding='utf-8'))
    con = duckdb.connect(DB, read_only=True)
    folder_db = {str(r[0]) for r in con.execute('SELECT DISTINCT folder FROM ingest_file').fetchall()}
    if folder_db != set(acuan['days']):
        pytest.skip(f'acuan dan database tidak sepadan ({len(acuan["days"])} vs {len(folder_db)} folder); '
                    'jalankan ulang tools/acuan_lama.py dan python -m simpel4 ingest')
    return kesetaraan, acuan, con, ekstrak_dashboard.load()


def test_e1_angka_acuan_sama_persis(bahan):
    """Setiap angka statistik mentah sistem lama, per folder x layanan, sama persis di v2."""
    kesetaraan, acuan, con, _ = bahan
    hasil = kesetaraan.e1(con, acuan)
    beda = [r for r in hasil if r[3] != r[4]]
    assert len(hasil) > 2500, f'cakupan terlalu sedikit: {len(hasil)} angka'
    assert beda == [], '\n'.join(f'{r[0]} {r[1]} {r[2]}: lama {r[3]} vs baru {r[4]}' for r in beda[:20])


def test_e1_mencakup_semua_folder_dan_layanan(bahan):
    kesetaraan, acuan, con, _ = bahan
    hasil = kesetaraan.e1(con, acuan)
    assert {r[0] for r in hasil} == set(acuan['days'])
    kunci = {r[2] for r in hasil}
    for k in ('lines', 'err', 'warn', 'req', 's4', 's5', 'ip_unik', 'alur_ip', 'serangan_req', 'korelasi', 'bisnis',
              'jwt', 'pdf_sukses', 'login_gagal', 'akun_dianalisis', 'insiden_5xx', 'retry', 'uptime_kuma'):
        assert k in kunci, k


def test_e3_pemilik_jaringan_ip_sama(bahan):
    """Semua IP yang punya pemilik di dashboard lama punya pemilik yang sama persis di v2."""
    kesetaraan, _, con, D = bahan
    hasil = kesetaraan.e3(con, D)
    beda = [r for r in hasil if r[1] != r[2]]
    assert len(hasil) >= 1700 and beda == [], '\n'.join(f'{r[0]}: lama {r[1]} vs baru {r[2]}' for r in beda[:10])


def test_e3_lokasi_hanya_dicatat_bukan_dibandingkan(bahan):
    """Sumber lokasi berganti ke GeoLite2 (TRD §3.6): negara harus sebagian besar sama, kota boleh berbeda."""
    kesetaraan, _, con, D = bahan
    lok = kesetaraan.e3_lokasi(con, D)
    assert lok['dibandingkan'] >= 1600 and lok['tidak_ada_di_v2'] == 0
    assert lok['negara_sama'] / lok['dibandingkan'] > 0.95


def test_e4_hanya_selisih_yang_terdaftar(bahan):
    """Setiap selisih yang diharapkan bernilai sesuai, dan tidak ada butir di luar daftar tertutup."""
    kesetaraan, acuan, con, D = bahan
    hasil = kesetaraan.e4(con, acuan, D)
    gagal = [r for r in hasil if 'GAGAL' in r[6] or 'periksa' in r[6]]
    assert gagal == [], '\n'.join(f'{r[0]} butir {r[1]} {r[2]}: lama {r[3]} baru {r[4]} seharusnya {r[5]}' for r in gagal)
    assert {r[1] for r in hasil} <= {1, 2, 3, 4, 9}, 'butir di luar daftar tertutup TRD §4.4'
    berubah = {r[1] for r in hasil if r[3] != r[4]}
    assert berubah == {1, 2, 4, 9}, f'butir yang berubah: {berubah} (butir 3 tidak berubah: tidak ada baris crit)'


@pytest.mark.parametrize('folder, ukuran, lama, baru', [
    ('2026-09-30', 'error koneksi pod', 200, 1200),          # KPI dari daftar yang dipotong 200
    ('2026-09-29', 'klien 401 berulang', 30, 653),
    ('2026-09-29', 'Σ error per jam (nginx-ingress-controller)', 59, 94),   # kini memuat baris error log
    ('2026-09-29', 'request lambat ≥ 5 dtk', 15, 24),        # kini memuat jejak lambat non-2xx
])
def test_e4_contoh_yang_disebut_di_dokumen(bahan, folder, ukuran, lama, baru):
    kesetaraan, acuan, con, D = bahan
    hasil = {(r[0], r[2]): r for r in kesetaraan.e4(con, acuan, D)}
    r = hasil[folder, ukuran]
    assert (r[3], r[4]) == (lama, baru) and r[6] == 'ok', r


def test_e4_level_simpel_loop_error_sama_dengan_kpi(bahan):
    """Butir 4: donat level memakai tingkat efektif, jadi ERROR/WARN = KPI Error/Warning layanan itu."""
    kesetaraan, acuan, con, _ = bahan
    for folder, v in acuan['days'].items():
        a = v.get('om-be-simpel-loop')
        if not a or not a['lines']: continue
        lv = dict(con.execute("SELECT level, n FROM agg_level WHERE folder = ? AND service = 'om-be-simpel-loop'", [folder]).fetchall())
        assert lv.get('ERROR', 0) == a['err'] and lv.get('WARN', 0) == a['warn'], folder


def test_e4_error_per_jam_sama_dengan_kpi(bahan):
    """Butir 2: jumlah error per jam = KPI Error untuk layanan yang bercap waktu."""
    kesetaraan, acuan, con, _ = bahan
    for folder, v in acuan['days'].items():
        for svc, a in v.items():
            if svc == '_file' or svc == 'om-be-simpel-loop' or not a['lines'] or svc == 'coredns': continue
            n = con.execute('SELECT coalesce(sum(err), 0) FROM agg_hour WHERE folder = ? AND service = ?', [folder, svc]).fetchone()[0]
            assert n == a['err'], f'{folder} {svc}: per jam {n} vs KPI {a["err"]}'


def test_laporan_berjalan_dan_lulus(bahan, capsys):
    kesetaraan, acuan, con, D = bahan
    ok = kesetaraan.cetak(acuan, con, D, kesetaraan.e1(con, acuan), kesetaraan.e3(con, D), kesetaraan.e4(con, acuan, D))
    keluaran = capsys.readouterr().out
    assert ok and 'berbeda: 0' in keluaran and 'tidak sesuai: 0' in keluaran


# ------------------------------------------------------------------ E2: isi daftar dashboard lama vs respons API
@pytest.fixture(scope='module')
def e2(bahan):
    kesetaraan, _, con, D = bahan
    import duckdb
    con.close()                                   # aplikasi membuka database baca-tulis: lepaskan koneksi baca uji ini
    try: tc = kesetaraan.klien_api()
    except duckdb.IOException: pytest.skip('database sedang dipakai proses lain (server berjalan?)')
    try: yield kesetaraan.e2(lambda path: tc.get(path).json(), D), tc
    finally: tc.__exit__(None, None, None)


def test_e2_isi_daftar_sama(e2):
    """Tiap daftar di dashboard lama (top-N, tabel, seri per jam) sama isinya dengan respons API; urutan hanya boleh beda di antara nilai sama."""
    hasil, _ = e2
    beda = [r for r in hasil if r[4]]
    assert len(hasil) >= 550 and sum(r[3] for r in hasil) >= 9000, f'cakupan terlalu sedikit: {len(hasil)} daftar'
    assert beda == [], '\n'.join(f'{r[0]} {r[1]} {r[2]}: {r[4]}' for r in beda[:20])


def test_e2_mencakup_semua_jenis_daftar(e2):
    hasil, _ = e2
    jenis = {r[2] for r in hasil}
    for k in ('files', 'status', 'hour', 'herr', 'extra', 'msgs', 'paths', 'perr', 'ips', 'ep', 'slow', 'up', 'ua', 'atk', 'atk_ip', 'atk_h', 'atk_cat', 'ip4', 'incidents',
              'up5', 'c401', 'uk', 'ukf', 'uk_t', 'pod', 'retry per pod', 'uperr', 'flow', 'login', 'acct', 'login_h', 'login_okh', 'rep', 'biz', 'mail', 'act', 'corr',
              'trace', 'jwt', 'restart'):
        assert k in jenis, k


@pytest.mark.parametrize('path, ambil, nilai', [
    ('/api/folders/2026-10-06/security', lambda j: (j['kpi']['attack_requests'], j['kpi']['attack_ips']), (88, 14)),
    ('/api/folders/2026-09-30/availability', lambda j: j['kpi']['upstream_errors'], 1200),
    ('/api/folders/2026-09-28/map', lambda j: (j['available'], j['reason']), (False, 'no_nginx')),
    ('/api/folders/2026-09-29/tables/c401?limit=5&q=count', lambda j: (j['total'], len(j['rows']) <= 5, j['matched'] <= 653), (653, True, True)),
    ('/api/folders/2026-09-29/tracing', lambda j: j['kpi']['slow_requests'], 24),                 # E4 butir 9
])
def test_e2_angka_yang_disebut_di_rencana(e2, path, ambil, nilai):
    _, tc = e2
    assert ambil(tc.get(path).json()) == nilai


def test_e2_halaman_data_nyata_kecil_dan_cepat(e2):
    """PRD §5.1/§5.2 pada folder terbesar: tiap endpoint halaman <= 500 KB dan <= 300 ms."""
    import time
    _, tc = e2
    f = '2026-09-29'
    svc = [s['service'] for s in tc.get(f'/api/folders/{f}').json()['services']]
    for u in [f'/api/folders/{f}'] + [f'/api/folders/{f}/{h}' for h in ('overview', 'map', 'security', 'rootcause', 'availability', 'pods', 'business', 'tracing')] + \
             [f'/api/folders/{f}/services/{s}' for s in svc] + ['/api/trends?last=all', '/api/meta']:
        tc.get(u); t0 = time.perf_counter(); r = tc.get(u); ms = (time.perf_counter() - t0) * 1000
        assert r.status_code == 200 and len(r.content) <= 500_000 and ms <= 300, f'{u}: {r.status_code} {len(r.content)} byte {ms:.0f} ms'
