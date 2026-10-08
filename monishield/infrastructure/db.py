"""The only place DuckDB is opened (TRD K1: one process owns the file)."""
import builtins, os

import duckdb

SCHEMA = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'schema.sql')


def open(path, memory_limit='1GB'):  # noqa: A001  (called as db.open)
    """Open the database and apply the schema (safe to repeat). path ':memory:' for tests."""
    if path != ':memory:':
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        _rename_old(path)
    con = duckdb.connect(path)
    con.execute(f"SET memory_limit = '{memory_limit}'")
    with builtins.open(SCHEMA, encoding='utf-8') as fh: con.execute(fh.read())
    _english_status(con)
    return con


# Status values were Indonesian before 2026-10-08; rewritten once in place (cheap no-op afterwards).
RUN_STATUS = {'berjalan': 'running', 'gagal': 'failed'}
FILE_STATUS = {'kosong': 'empty', 'rusak': 'corrupt', 'gagal': 'failed'}


def _english_status(con):
    for table, m in (('ingest_run', RUN_STATUS), ('ingest_file', FILE_STATUS)):
        case = ' '.join(f"WHEN '{a}' THEN '{b}'" for a, b in m.items())
        con.execute(f"UPDATE {table} SET status = CASE status {case} END WHERE status IN ({', '.join(repr(a) for a in m)})")


OLD_NAME = 'simpel4.duckdb'   # file name before 2026-10-07 (old application name)


def _rename_old(path):
    """The old file data/simpel4.duckdb (+ .wal) is moved to the new name once, so the data need not be re-ingested."""
    old = os.path.join(os.path.dirname(os.path.abspath(path)), OLD_NAME)
    if os.path.basename(path) != OLD_NAME and not os.path.exists(path) and os.path.exists(old):
        os.replace(old, path)
        if os.path.exists(old + '.wal'): os.replace(old + '.wal', path + '.wal')


SNAPSHOT_STORAGE = 'v1.2.0'   # copy file format: readable by DuckDB >= 1.2 (DbGate 6.6 uses 1.2.1)


def snapshot_path(cfg): return os.path.join(cfg.data_dir, 'snapshot', 'monishield.duckdb')


def snapshot(con, cfg):
    """Read-only copy of the whole database for an external viewer (DbGate in docker compose). DuckDB may be opened by only one
    process (K1), so the viewer opens this COPY, not the server's file. Written to .tmp then replaced atomically; a viewer
    that has the old copy open keeps reading the old version until it reconnects. -> copy path."""
    path = snapshot_path(cfg)
    tmp = path + '.tmp'
    os.makedirs(os.path.dirname(path), exist_ok=True)
    for p in (tmp, tmp + '.wal'):
        if os.path.exists(p): os.remove(p)
    main = con.execute('SELECT current_database()').fetchone()[0]
    con.execute(f"ATTACH '{tmp}' AS snapshot_baca (STORAGE_VERSION '{SNAPSHOT_STORAGE}')")
    try: con.execute(f'COPY FROM DATABASE "{main}" TO snapshot_baca')
    finally: con.execute('DETACH snapshot_baca')
    if os.path.exists(path + '.wal'): os.remove(path + '.wal')   # WAL of viewer writes on the old copy: must not be replayed onto the new copy
    os.replace(tmp, path)
    return path
