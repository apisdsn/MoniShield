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
