#!/usr/bin/env python3
"""Buat database simulasi berisi N folder sebesar folder log terbesar, untuk gerbang ukuran & kinerja (TRD §9.7).

  python3 tools/simulasi_setahun.py [--folders 365] [--sumber 2026-09-29] [--out data/sim.duckdb]

Baris mentah folder sumber disalin ke N tanggal berurutan lewat query (tanpa parse ulang), lalu agregatnya
diturunkan seperti biasa. Request id diberi awalan per folder supaya korelasi tetap di dalam folder — sama
dengan data nyata, yang tidak punya kecocokan lintas folder. Database asli hanya dibaca.
"""
import argparse, datetime, os, shutil, sys, time

V2 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, V2)

from monishield import db, derive, ingest, parse  # noqa: E402

MENTAH = list(parse.TABLES)


def ruang_bebas_gb(path): return shutil.disk_usage(path).free / 2**30


def jalankan(sumber, n, out, src_db, log=print):
    if os.path.exists(out): os.remove(out)
    con = db.open(out, memory_limit='2GB')
    con.execute(f"ATTACH '{src_db}' AS asli (READ_ONLY)")  # ATTACH tidak menerima parameter terikat
    con.execute('INSERT INTO ip_info SELECT * FROM asli.ip_info')
    kolom = {t: [r[0] for r in con.execute(f"SELECT column_name FROM information_schema.columns WHERE table_name = '{t}' AND table_schema = 'main' AND table_catalog = current_database() ORDER BY ordinal_position").fetchall()] for t in MENTAH + ['ingest_file']}
    mulai = datetime.date.fromisoformat(sumber)
    t0 = time.time()
    for i in range(n):
        fd = (mulai + datetime.timedelta(days=i)).isoformat()
        con.execute('BEGIN')
        con.execute(f"""INSERT INTO ingest_file SELECT file_id + {i} * 1000, '{fd}/' || relpath, source_ext, DATE '{fd}', ns, service, pod,
                        size_bytes, mtime_ns, sha256, lines, err, warn, corrupt_lines, status, rules_version, ingested_at
                        FROM asli.ingest_file WHERE folder = ?""", [sumber])
        con.execute(f"""INSERT INTO file_counter SELECT file_id + {i} * 1000, kind, key, n FROM asli.file_counter
                        WHERE file_id IN (SELECT file_id FROM asli.ingest_file WHERE folder = ?)""", [sumber])
        for t in MENTAH:
            pilih = []
            for c in kolom[t]:
                if c == 'file_id': pilih.append(f'file_id + {i} * 1000')
                elif c == 'folder': pilih.append(f"DATE '{fd}'")
                # awalan per folder: request id tetap unik, kecocokan tetap di dalam folder (seperti data nyata)
                elif c == 'request_id': pilih.append(f"CASE WHEN request_id IS NULL THEN NULL ELSE printf('%03x', {i}) || substr(request_id, 4) END")
                else: pilih.append(c)
            con.execute(f'INSERT INTO {t} SELECT {", ".join(pilih)} FROM asli.{t} WHERE folder = ?', [sumber])
        con.execute('COMMIT')
        if (i + 1) % 10 == 0 or i + 1 == n:
            log(f'  salin {i + 1}/{n} folder, {round(time.time() - t0)} dtk, berkas {os.path.getsize(out) / 2**30:.2f} GB, sisa disk {ruang_bebas_gb(out):.1f} GB')
        if ruang_bebas_gb(out) < 3: raise SystemExit('disk hampir penuh; hentikan dan pakai --folders lebih kecil')
    t1 = time.time()
    log(f'salin selesai: {round(t1 - t0)} dtk')
    for j, fd in enumerate(derive.folders(con), 1):
        con.execute('BEGIN'); derive.run(con, fd, ingest.utcnow(), parse.RULES_VERSION); con.execute('COMMIT')
        if j % 10 == 0 or j == n: log(f'  derive {j}/{n} folder, {round(time.time() - t1)} dtk')
    con.execute('CHECKPOINT')
    log(f'derive selesai: {round(time.time() - t1)} dtk; total {round(time.time() - t0)} dtk')
    con.close()
    return dict(folder=n, detik_salin=round(t1 - t0, 1), detik_derive=round(time.time() - t1, 1), byte=os.path.getsize(out))


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--folders', type=int, default=365)
    ap.add_argument('--sumber', default='2026-09-29')
    ap.add_argument('--out', default=os.path.join(V2, 'data', 'sim.duckdb'))
    ap.add_argument('--db', default=os.path.join(V2, 'data', 'simpel4.duckdb'))
    a = ap.parse_args()
    r = jalankan(a.sumber, a.folders, a.out, a.db, log=lambda m: print(m, file=sys.stderr))
    print(f"{r['folder']} folder, {r['byte'] / 2**30:.2f} GB, salin {r['detik_salin']} dtk, derive {r['detik_derive']} dtk")
