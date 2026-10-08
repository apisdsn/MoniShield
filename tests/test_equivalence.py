"""Equivalence tests v2 vs the old system over REAL log folders (TRD §9.3, PRD §6.2).

E1 reference numbers, E2 list contents vs API, E3 IP network owners, E4 closed list of expected differences.
Needs: data/monishield.duckdb from ingest, ../dashboard.html, and docs/00-reference.json (created by
`python3 tools/acuan_lama.py`). If any is missing, the tests are skipped with an explanation.
"""
import json, os, sys

import pytest

V2 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(V2, 'tools'))
DB = os.path.join(V2, 'data', 'monishield.duckdb')
ACUAN = os.path.join(V2, 'docs', '00-reference.json')
LAMA = os.path.join(os.path.dirname(V2), 'dashboard.html')


@pytest.fixture(scope='module')
def bahan():
    import duckdb
    for path, pesan in ((DB, 'no database yet; run: python -m monishield ingest'),
                        (LAMA, 'the old system\'s dashboard.html is missing'),
                        (ACUAN, 'docs/00-reference.json not created yet; run: python3 tools/acuan_lama.py')):
        if not os.path.exists(path): pytest.skip(pesan)
    import ekstrak_dashboard, kesetaraan
    acuan = json.load(open(ACUAN, encoding='utf-8'))
    con = duckdb.connect(DB, read_only=True)
    folder_db = {str(r[0]) for r in con.execute('SELECT DISTINCT folder FROM ingest_file').fetchall()}
    if folder_db != set(acuan['days']):
        pytest.skip(f'reference and database do not match ({len(acuan["days"])} vs {len(folder_db)} folder); '
                    'run tools/acuan_lama.py and python -m monishield ingest again')
    return kesetaraan, acuan, con, ekstrak_dashboard.load()


def test_e1_angka_acuan_sama_persis(bahan):
    """Every raw statistic number of the old system, per folder x service, is exactly the same in v2."""
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
    """Every IP that has an owner in the old dashboard has exactly the same owner in v2."""
    kesetaraan, _, con, D = bahan
    hasil = kesetaraan.e3(con, D)
    beda = [r for r in hasil if r[1] != r[2]]
    assert len(hasil) >= 1700 and beda == [], '\n'.join(f'{r[0]}: lama {r[1]} vs baru {r[2]}' for r in beda[:10])


def test_e3_lokasi_hanya_dicatat_bukan_dibandingkan(bahan):
    """Location source switched to GeoLite2 (TRD §3.6): countries must mostly match, cities may differ."""
    kesetaraan, _, con, D = bahan
    lok = kesetaraan.e3_lokasi(con, D)
    assert lok['dibandingkan'] >= 1600 and lok['tidak_ada_di_v2'] == 0
    assert lok['negara_sama'] / lok['dibandingkan'] > 0.95


def test_e4_hanya_selisih_yang_terdaftar(bahan):
    """Every expected difference has the right value, and there are no items outside the closed list."""
    kesetaraan, acuan, con, D = bahan
    hasil = kesetaraan.e4(con, acuan, D)
    gagal = [r for r in hasil if 'GAGAL' in r[6] or 'periksa' in r[6]]
    assert gagal == [], '\n'.join(f'{r[0]} butir {r[1]} {r[2]}: lama {r[3]} baru {r[4]} seharusnya {r[5]}' for r in gagal)
    assert {r[1] for r in hasil} <= {1, 2, 3, 4, 9}, 'butir di luar daftar tertutup TRD §4.4'
    berubah = {r[1] for r in hasil if r[3] != r[4]}
    assert berubah == {1, 2, 4, 9}, f'butir yang berubah: {berubah} (butir 3 tidak berubah: tidak ada baris crit)'


@pytest.mark.parametrize('folder, ukuran, lama, baru', [
    ('2026-09-30', 'error koneksi pod', 200, 1200),          # KPI from the list truncated at 200
    ('2026-09-29', 'klien 401 berulang', 30, 653),
    ('2026-09-29', 'Σ error per jam (nginx-ingress-controller)', 59, 94),   # now includes error log lines
    ('2026-09-29', 'request lambat ≥ 5 dtk', 15, 24),        # now includes non-2xx slow traces
])
def test_e4_contoh_yang_disebut_di_dokumen(bahan, folder, ukuran, lama, baru):
    kesetaraan, acuan, con, D = bahan
    hasil = {(r[0], r[2]): r for r in kesetaraan.e4(con, acuan, D)}
    r = hasil[folder, ukuran]
    assert (r[3], r[4]) == (lama, baru) and r[6] == 'ok', r


def test_e4_level_simpel_loop_error_sama_dengan_kpi(bahan):
    """Item 4: the level donut uses the effective level, so ERROR/WARN = that service's Error/Warning KPI."""
    kesetaraan, acuan, con, _ = bahan
    for folder, v in acuan['days'].items():
        a = v.get('om-be-simpel-loop')
        if not a or not a['lines']: continue
        lv = dict(con.execute("SELECT level, n FROM agg_level WHERE folder = ? AND service = 'om-be-simpel-loop'", [folder]).fetchall())
        assert lv.get('ERROR', 0) == a['err'] and lv.get('WARN', 0) == a['warn'], folder


def test_e4_error_per_jam_sama_dengan_kpi(bahan):
    """Item 2: errors per hour sum = Error KPI for timestamped services."""
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


# ------------------------------------------------------------------ E2: old dashboard list contents vs API response
@pytest.fixture(scope='module')
def e2(bahan):
    kesetaraan, _, con, D = bahan
    import duckdb
    con.close()                                   # the app opens the database read-write: release this test's read connection
    try: tc = kesetaraan.klien_api()
    except duckdb.IOException: pytest.skip('database is in use by another process (is the server running?)')
    try: yield kesetaraan.e2(lambda path: tc.get(path).json(), D), tc
    finally: tc.__exit__(None, None, None)


def test_e2_isi_daftar_sama(e2):
    """Every list in the old dashboard (top-N, tables, hourly series) has the same contents as the API response; order may differ only among equal values."""
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
    ('/api/folders/2026-09-29/tracing', lambda j: j['kpi']['slow_requests'], 24),                 # E4 item 9
])
def test_e2_angka_yang_disebut_di_rencana(e2, path, ambil, nilai):
    _, tc = e2
    assert ambil(tc.get(path).json()) == nilai


def test_e2_halaman_data_nyata_kecil_dan_cepat(e2):
    """PRD §5.1/§5.2 on the largest folder: every page endpoint <= 500 KB and <= 300 ms."""
    import time
    _, tc = e2
    f = '2026-09-29'
    svc = [s['service'] for s in tc.get(f'/api/folders/{f}').json()['services']]
    for u in [f'/api/folders/{f}'] + [f'/api/folders/{f}/{h}' for h in ('overview', 'map', 'security', 'rootcause', 'availability', 'pods', 'business', 'tracing')] + \
             [f'/api/folders/{f}/services/{s}' for s in svc] + ['/api/trends?last=all', '/api/meta']:
        ms = 1e9
        for _ in range(3):                       # best of 3: other tests running concurrently must not fail this measurement
            t0 = time.perf_counter(); r = tc.get(u); ms = min(ms, (time.perf_counter() - t0) * 1000)
        assert r.status_code == 200 and len(r.content) <= 500_000 and ms <= 300, f'{u}: {r.status_code} {len(r.content)} byte {ms:.0f} ms'
