"""The only place DuckDB is opened (TRD K1: one process owns the file)."""
import builtins, json, math, os, tempfile

import duckdb

SCHEMA = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'schema.sql')


def open(path, memory_limit='1GB'):  # noqa: A001  (called as db.open)
    """Open the database and apply the schema (safe to repeat). path ':memory:' for tests."""
    if path != ':memory:':
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    con = duckdb.connect(path)
    con.execute(f"SET memory_limit = '{memory_limit}'")
    with builtins.open(SCHEMA, encoding='utf-8') as fh: con.execute(fh.read())
    _english_status(con)
    return con


def insert_rows(con, table, rows):
    """Insert many rows (lists in the table's column order; a MAP column is a dict, a list column a list) in ONE statement.

    The DuckDB Python API's executemany costs 2-4 ms per row (measured 2026-10-27: a folder with 27,000 attack rows spent
    100 s in it); the engine reading one JSON-lines file costs about 0.01 ms per row. The file is private (mode 0600), lives
    only for this call and is removed at once. Values become what the column type says (DATE/TIMESTAMP from text, MAP from an
    object); a NaN/inf float becomes NULL (JSON has no NaN)."""
    if not rows: return
    cols = con.execute(f'DESCRIBE {table}').fetchall()
    names = [c[0] for c in cols]
    fd, path = tempfile.mkstemp(suffix='.jsonl')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as fh:
            for r in rows:
                try: line = json.dumps(dict(zip(names, r)), default=str, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
                except ValueError:   # NaN / inf somewhere in the row
                    line = json.dumps(dict(zip(names, [None if isinstance(v, float) and not math.isfinite(v) else v for v in r])),
                                      default=str, ensure_ascii=False, separators=(',', ':'))
                fh.write(line + '\n')
        spec = ', '.join(f"'{n}': '{t}'" for n, (_, t, *_x) in zip(names, cols))
        con.execute(f"INSERT INTO {table} SELECT * FROM read_json(?, format='newline_delimited', columns={{{spec}}})", [path])
    finally:
        try: os.remove(path)
        except FileNotFoundError: pass


# Status values were Indonesian before 2026-10-08; rewritten once in place (cheap no-op afterwards).
RUN_STATUS = {'berjalan': 'running', 'gagal': 'failed'}
FILE_STATUS = {'kosong': 'empty', 'rusak': 'corrupt', 'gagal': 'failed'}


# Business metric keys were Indonesian before 2026-10-28 (domain/services.py METRICS); rewritten once the same way.
BIZ_KEYS = {'Laporan Dibuat': 'reports_created', 'Registrasi Laporan': 'report_registrations', 'OTP Diminta': 'otp_requested',
            'OTP Terverifikasi': 'otp_verified', 'File Diunggah': 'files_uploaded', 'Lampiran Ditambahkan': 'attachments_added',
            'OTP Gagal': 'otp_failed', 'Upload Ditolak (Terlalu Besar)': 'uploads_rejected_too_large',
            'Upload Ditolak (Tipe File)': 'uploads_rejected_file_type', 'Email Terkirim': 'emails_sent', 'Email Gagal': 'emails_failed'}


def _rewrite(con, table, column, m, where=''):
    case = ' '.join(f"WHEN '{a}' THEN '{b}'" for a, b in m.items())
    con.execute(f"UPDATE {table} SET {column} = CASE {column} {case} END WHERE {column} IN ({', '.join(repr(a) for a in m)}){where}")


def _english_status(con):
    _rewrite(con, 'ingest_run', 'status', RUN_STATUS)
    _rewrite(con, 'ingest_file', 'status', FILE_STATUS)
    _rewrite(con, 'agg_biz', 'metric', BIZ_KEYS)
    _rewrite(con, 'file_counter', 'key', BIZ_KEYS, " AND kind = 'biz'")


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
