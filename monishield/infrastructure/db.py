"""Satu-satunya tempat DuckDB dibuka (TRD K1: satu proses pemilik file)."""
import builtins, os

import duckdb

SCHEMA = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'schema.sql')


def open(path, memory_limit='1GB'):  # noqa: A001  (dipanggil sebagai db.open)
    """Buka database dan terapkan skema (aman diulang). path ':memory:' untuk uji."""
    if path != ':memory:':
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        _rename_old(path)
    con = duckdb.connect(path)
    con.execute(f"SET memory_limit = '{memory_limit}'")
    with builtins.open(SCHEMA, encoding='utf-8') as fh: con.execute(fh.read())
    return con


OLD_NAME = 'simpel4.duckdb'   # nama berkas sebelum 2026-10-07 (nama aplikasi lama)


def _rename_old(path):
    """Berkas lama data/simpel4.duckdb (+ .wal) dipindah ke nama baru sekali, agar data tidak perlu di-ingest ulang."""
    old = os.path.join(os.path.dirname(os.path.abspath(path)), OLD_NAME)
    if os.path.basename(path) != OLD_NAME and not os.path.exists(path) and os.path.exists(old):
        os.replace(old, path)
        if os.path.exists(old + '.wal'): os.replace(old + '.wal', path + '.wal')


SNAPSHOT_STORAGE = 'v1.2.0'   # format file salinan: terbaca DuckDB >= 1.2 (DbGate 6.6 memakai 1.2.1)


def snapshot_path(cfg): return os.path.join(cfg.data_dir, 'snapshot', 'monishield.duckdb')


def snapshot(con, cfg):
    """Salinan baca seluruh database untuk penampil luar (DbGate di docker compose). DuckDB hanya boleh dibuka satu proses
    (K1), jadi penampil membuka SALINAN ini, bukan file milik server. Ditulis ke .tmp lalu diganti atomik; penampil yang
    sedang membuka salinan lama tetap membaca versi lamanya sampai tersambung ulang. -> path salinan."""
    path = snapshot_path(cfg)
    tmp = path + '.tmp'
    os.makedirs(os.path.dirname(path), exist_ok=True)
    for p in (tmp, tmp + '.wal'):
        if os.path.exists(p): os.remove(p)
    main = con.execute('SELECT current_database()').fetchone()[0]
    con.execute(f"ATTACH '{tmp}' AS snapshot_baca (STORAGE_VERSION '{SNAPSHOT_STORAGE}')")
    try: con.execute(f'COPY FROM DATABASE "{main}" TO snapshot_baca')
    finally: con.execute('DETACH snapshot_baca')
    if os.path.exists(path + '.wal'): os.remove(path + '.wal')   # WAL tulisan penampil atas salinan lama: jangan diputar ke salinan baru
    os.replace(tmp, path)
    return path
