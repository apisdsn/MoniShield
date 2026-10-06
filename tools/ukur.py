#!/usr/bin/env python3
"""Gerbang ukuran dan kinerja (TRD §9.7, PRD §5.1–§5.3).

  python3 tools/ukur.py [data/sim.duckdb] [--ingest] [--scrypt]

Mengukur: ukuran berkas dan per tabel; waktu query yang akan dipakai tiap halaman dashboard; (opsional)
waktu ingest satu folder tambahan dan ingest tanpa perubahan; (opsional) biaya hash sandi.
Query di bawah adalah yang akan dipakai API Tahap 11: semuanya membaca tabel agregat, bukan tabel mentah.
"""
import argparse, os, statistics, sys, time

V2 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, V2)

TARGET = dict(ukuran_gb=10, halaman_ms=200, tren_ms=500, ingest_folder_dtk=60, ingest_kosong_dtk=5)

# (nama halaman, SQL). $f = folder. Satu halaman di API memanggil beberapa query ini; yang diukur jumlahnya.
HALAMAN = [
    ('Overview: layanan', 'SELECT * FROM agg_service WHERE folder = $f'),
    ('Overview: error per jam', 'SELECT service, hour_wib, err FROM agg_hour WHERE folder = $f AND err > 0'),
    ('Overview: pesan lintas layanan', 'SELECT service, msg_key, level, n FROM agg_message WHERE folder = $f ORDER BY n DESC LIMIT 25'),
    ('Overview: file', 'SELECT service, pod, lines, err, warn, size_bytes, status FROM ingest_file WHERE folder = $f'),
    ('Layanan: endpoint', "SELECT key, requests, n4xx, n5xx FROM agg_endpoint WHERE folder = $f AND service = 'nginx-ingress-controller' ORDER BY requests DESC LIMIT 20"),
    ('Layanan: kinerja endpoint', "SELECT key, requests, p50, p95, p99, dur_max FROM agg_endpoint WHERE folder = $f AND service = 'nginx-ingress-controller' AND dur_n >= 5 ORDER BY p95 DESC LIMIT 25"),
    ('Layanan: IP klien', "SELECT ip, requests FROM agg_ip WHERE folder = $f AND service = 'nginx-ingress-controller' ORDER BY requests DESC LIMIT 15"),
    ('Layanan: pesan', "SELECT msg_key, level, n, sample_raw FROM agg_message WHERE folder = $f AND service = 'om-be-appsmanager' ORDER BY n DESC LIMIT 40"),
    ('Keamanan: KPI', """SELECT (SELECT coalesce(sum(hits), 0) FROM agg_attack_url WHERE folder = $f), (SELECT count(*) FROM agg_attack_ip WHERE folder = $f),
                                (SELECT count(*) FROM agg_login_ip WHERE folder = $f AND (fail > 0 OR lock > 0)), (SELECT count(*) FROM agg_account WHERE folder = $f)"""),
    ('Keamanan: URL serangan', 'SELECT * FROM agg_attack_url WHERE folder = $f ORDER BY hits DESC LIMIT 300'),
    ('Keamanan: IP penyerang + pemilik', 'SELECT a.*, i.asn, i.cc, i.org FROM agg_attack_ip a LEFT JOIN ip_info i USING (ip) WHERE a.folder = $f ORDER BY a.hits DESC LIMIT 100'),
    ('Keamanan: analisis akun', 'SELECT * FROM agg_account WHERE folder = $f ORDER BY fail DESC LIMIT 150'),
    ('Akar masalah: 401', 'SELECT * FROM agg_c401 WHERE folder = $f ORDER BY n DESC LIMIT 30'),
    ('Akar masalah: JWT', 'SELECT service, bucket, n FROM agg_jwt WHERE folder = $f'),
    ('Ketersediaan: insiden', 'SELECT * FROM agg_incident WHERE folder = $f ORDER BY seq'),
    ('Ketersediaan: error koneksi pod', 'SELECT * FROM v_upstream_error WHERE folder = $f ORDER BY ts_utc DESC LIMIT 200'),
    ('Pod: sebaran traffic', 'SELECT p.*, coalesce(r.n, 0) FROM agg_pod p LEFT JOIN (SELECT upstream, addr_first, sum(n) n FROM agg_retry WHERE folder = $f GROUP BY ALL) r ON r.upstream = p.upstream AND r.addr_first = p.addr WHERE p.folder = $f'),
    ('Bisnis: ringkasan', 'SELECT (SELECT list(struct_pack(m := metric, n := n)) FROM agg_biz WHERE folder = $f), (SELECT list(struct_pack(k := kind, n := n)) FROM agg_mail WHERE folder = $f)'),
    ('Pelacakan: jejak', 'SELECT * FROM agg_trace WHERE folder = $f ORDER BY n DESC LIMIT 300'),
    ('Peta: titik', """SELECT i.lat, i.lon, i.city, i.region, i.country, count(DISTINCT f.ip), sum(f.n) FROM agg_flow f JOIN ip_info i USING (ip)
                       WHERE f.folder = $f AND i.lat IS NOT NULL GROUP BY 1, 2, 3, 4, 5"""),
    ('Peta: tabel alur', """SELECT f.ip, i.org, i.city, f.upstream, list(struct_pack(pod := f.pod, n := f.n) ORDER BY f.n DESC)[:3], sum(f.n) AS total
                            FROM agg_flow f LEFT JOIN ip_info i USING (ip) WHERE f.folder = $f GROUP BY 1, 2, 3, 4 ORDER BY total DESC LIMIT 100"""),
]
TREN = [
    ('Tren: baris/error/warning per hari', 'SELECT folder, service, lines, err, warn FROM agg_service ORDER BY folder'),
    ('Tren: HTTP per hari', "SELECT folder, sum(n) FILTER (WHERE status BETWEEN 400 AND 499), sum(n) FILTER (WHERE status BETWEEN 500 AND 599), sum(n) FROM agg_status WHERE service = 'nginx-ingress-controller' GROUP BY folder ORDER BY folder"),
    ('Tren: keamanan per hari', """SELECT folder, (SELECT coalesce(sum(hits), 0) FROM agg_attack_url a WHERE a.folder = s.folder),
                                          (SELECT coalesce(sum(fail), 0) FROM agg_login_ip l WHERE l.folder = s.folder) FROM folder_state s ORDER BY folder"""),
    ('Tren: bisnis per hari', 'SELECT folder, metric, n FROM agg_biz ORDER BY folder'),
    ('Daftar folder', 'SELECT folder, range_start_utc, range_end_utc, lines, files, files_empty, files_corrupt FROM folder_state ORDER BY folder DESC'),
]


def waktu(con, sql, params, ulang=5):
    con.execute(sql, params).fetchall()  # pemanasan: cache berkas, bukan hasil query
    t = []
    for _ in range(ulang):
        a = time.perf_counter(); con.execute(sql, params).fetchall(); t.append((time.perf_counter() - a) * 1000)
    return min(t), statistics.median(t)


def ukuran_tabel(con):
    blok = con.execute('SELECT block_size FROM pragma_database_size()').fetchone()[0]
    out = {}
    for (t,) in con.execute("SELECT table_name FROM duckdb_tables() WHERE database_name = current_database()").fetchall():
        n = con.execute(f"SELECT count(DISTINCT block_id) FROM pragma_storage_info('{t}') WHERE block_id IS NOT NULL").fetchone()[0]
        baris = con.execute(f'SELECT count(*) FROM {t}').fetchone()[0]
        out[t] = (baris, n * blok)
    return out


def main():
    import duckdb
    ap = argparse.ArgumentParser()
    ap.add_argument('db', nargs='?', default=os.path.join(V2, 'data', 'sim.duckdb'))
    ap.add_argument('--ingest', action='store_true', help='ukur juga waktu ingest (memakai database nyata)')
    ap.add_argument('--scrypt', action='store_true', help='ukur biaya hash sandi')
    a = ap.parse_args()
    con = duckdb.connect(a.db, read_only=True)
    folders = [str(r[0]) for r in con.execute('SELECT folder FROM folder_state ORDER BY folder').fetchall()]
    n = len(folders)
    byte = os.path.getsize(a.db)
    print(f'# Ukuran dan kinerja — {os.path.basename(a.db)}')
    print(f'\nFolder: {n}; berkas {byte / 2**30:.2f} GB ({byte / n / 2**20:.1f} MB per folder)')
    if n != 365: print(f'Ekstrapolasi ke 365 folder: {byte / n * 365 / 2**30:.2f} GB')
    gb365 = byte / n * 365 / 2**30
    print(f"Target ≤ {TARGET['ukuran_gb']} GB: {'LULUS' if gb365 <= TARGET['ukuran_gb'] else 'GAGAL'}")

    print('\n## Ukuran per tabel (10 terbesar, perkiraan dari blok)')
    tab = sorted(ukuran_tabel(con).items(), key=lambda kv: -kv[1][1])
    for t, (baris, b) in tab[:10]: print(f'  {t:22} {baris:>12,} baris  {b / 2**20:>8.1f} MB')
    print(f'  {"(agregat saja)":22} {sum(v[0] for k, v in tab if k.startswith("agg_")):>12,} baris  {sum(v[1] for k, v in tab if k.startswith("agg_")) / 2**20:>8.1f} MB')

    print(f'\n## Waktu query per halaman (folder terakhir; min / median dari 5, ms); target ≤ {TARGET["halaman_ms"]} ms')
    f = folders[-1]
    total, lambat = 0, []
    for nama, sql in HALAMAN:
        mn, md = waktu(con, sql, {'f': f})
        total += md
        if md > TARGET['halaman_ms']: lambat.append((nama, md))
        print(f'  {nama:38} {mn:7.1f} / {md:7.1f}')
    print(f'  {"JUMLAH semua query halaman":38} {"":7}   {total:7.1f}')
    print(f'\n## Tren (semua {n} folder); target ≤ {TARGET["tren_ms"]} ms')
    tren_total = 0
    for nama, sql in TREN:
        mn, md = waktu(con, sql, {})
        tren_total += md
        print(f'  {nama:38} {mn:7.1f} / {md:7.1f}')
    print(f'  {"JUMLAH query tab Tren":38} {"":7}   {tren_total:7.1f}')
    if n != 365: print(f'  perkiraan pada 365 folder: {tren_total * 365 / n:.1f} ms')
    print(f'\nHalaman di atas target: {lambat or "tidak ada"}')

    if a.scrypt:
        import hashlib, secrets
        print('\n## Biaya hash sandi (scrypt)')
        for nlog, r, p in ((14, 8, 1), (15, 8, 1), (16, 8, 1)):
            t0 = time.perf_counter(); hashlib.scrypt(b'sandi-contoh-panjang', salt=secrets.token_bytes(16), n=2**nlog, r=r, p=p, maxmem=2**30); ms = (time.perf_counter() - t0) * 1000
            print(f'  n=2^{nlog} r={r} p={p}: {ms:.0f} ms')

    if a.ingest:
        import subprocess
        print('\n## Waktu ingest (database nyata)')
        for label, args in (('tanpa perubahan', ['ingest']), ('satu folder dipaksa ulang', ['ingest', '--folder', '2026-09-29', '--force'])):
            t0 = time.perf_counter()
            subprocess.run([sys.executable, '-m', 'simpel4', *args], cwd=V2, capture_output=True, check=True)
            print(f'  {label:28} {time.perf_counter() - t0:.1f} dtk')
    con.close()


if __name__ == '__main__':
    main()
