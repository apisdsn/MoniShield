"""Derives one folder's aggregates from the raw tables (TRD §3.4, §4.3).

Each NN_<name>.sql file holds "delete this folder's rows; insert the SELECT result for this folder" statements with
parameter $f = folder. Run in order inside the ingest transaction. Changing an aggregate definition needs no
re-parse: just run it again (the `derive` command).

Equivalence rules with the old system kept in this SQL:
- WIB = UTC + 7 h; minute/hour = truncation (date_trunc), like the old wib() which dropped seconds.
- "the first" = smallest by (file relpath, line_no) = the old system's read order.
- endpoint key = 'METHOD path_key'; frontend exception in agg_endpoint_error (no method), as before.
- percentile = element min(n-1, floor(q*n)) of the sorted durations (old pct()), not DuckDB's built-in quantile.
"""
import glob, os

from monishield.domain import detect
from monishield.infrastructure.derive import steps

HERE = os.path.dirname(os.path.abspath(__file__))


def statements():
    """[(file name, SQL statement)] in order."""
    out = []
    for path in sorted(glob.glob(os.path.join(HERE, '[0-9][0-9]_*.sql'))):
        sql = '\n'.join(l for l in open(path, encoding='utf-8').read().splitlines() if not l.lstrip().startswith('--'))
        out += [(os.path.basename(path), s.strip()) for s in sql.split(';\n') if s.strip().rstrip(';')]
    return out


def run(con, folder, now, rules_version):
    """Derive all aggregates of one folder. Called inside the caller's transaction."""
    for name, sql in statements():
        try: con.execute(sql.rstrip(';'), {'f': folder})
        except Exception as e: raise RuntimeError(f'derive/{name}: {e}') from e
    for step in steps.STEPS:
        try: step(con, folder)
        except Exception as e: raise RuntimeError(f'derive/steps.{step.__name__}: {e}') from e
    rng = con.execute("""SELECT min(a), max(b) FROM (
        SELECT min(ts_utc) a, max(ts_utc) b FROM nginx_access WHERE folder = $f UNION ALL
        SELECT min(ts_utc), max(ts_utc) FROM fe_access WHERE folder = $f UNION ALL
        SELECT min(ts_utc), max(ts_utc) FROM spring_line WHERE folder = $f)""", {'f': folder}).fetchone()
    con.execute('DELETE FROM folder_state WHERE folder = ?', [folder])
    con.execute("""INSERT INTO folder_state (folder, derived_at, rules_version, range_start_utc, range_end_utc, lines, files, files_empty, files_corrupt, crs_version)
        SELECT $f, $now, $v, $a, $b, coalesce(sum(lines), 0), count(*),
               count(*) FILTER (WHERE lines = 0), count(*) FILTER (WHERE status = 'corrupt'), $crs
        FROM ingest_file WHERE folder = $f HAVING count(*) > 0""", {'f': folder, 'now': now, 'v': rules_version, 'a': rng[0], 'b': rng[1], 'crs': detect.version_key()})


def folders(con): return [str(r[0]) for r in con.execute('SELECT DISTINCT folder FROM ingest_file ORDER BY 1').fetchall()]
