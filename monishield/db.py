"""Satu-satunya tempat DuckDB dibuka (TRD K1: satu proses pemilik file)."""
import builtins, os

import duckdb

SCHEMA = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'schema.sql')


def open(path, memory_limit='1GB'):  # noqa: A001  (dipanggil sebagai db.open)
    """Buka database dan terapkan skema (aman diulang). path ':memory:' untuk uji."""
    if path != ':memory:': os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    con = duckdb.connect(path)
    con.execute(f"SET memory_limit = '{memory_limit}'")
    with builtins.open(SCHEMA, encoding='utf-8') as fh: con.execute(fh.read())
    return con


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
