"""Derives one folder's aggregates from the raw tables (TRD §3.4, §4.3).

Each NN_<name>.sql file holds "delete this folder's rows; insert the SELECT result for this folder" statements with
parameter $f = folder (and $fe, $sl, $am, $rp: service names of the site profile; $tz: minutes of the local time zone). Run in order inside the ingest transaction. Changing an aggregate definition needs no
re-parse: just run it again (the `derive` command).

Equivalence rules with the old system kept in this SQL:
- local time = UTC + the site's offset (S4_TIMEZONE_OFFSET, default +7 h); minute/hour = truncation (date_trunc), like
  the old wib() which dropped seconds. Columns named *_wib hold this local time.
- "the first" = smallest by (file relpath, line_no) = the old system's read order.
- endpoint key = 'METHOD path_key'; frontend exception in agg_endpoint_error (no method), as before.
- percentile = element min(n-1, floor(q*n)) of the sorted durations (old pct()), not DuckDB's built-in quantile.
"""
import glob, os, re, time

from monishield.domain import detect, services, timezone
from monishield.infrastructure.derive import steps

HERE = os.path.dirname(os.path.abspath(__file__))


def statements():
    """[(file name, SQL statement)] in order."""
    out = []
    for path in sorted(glob.glob(os.path.join(HERE, '[0-9][0-9]_*.sql'))):
        sql = '\n'.join(l for l in open(path, encoding='utf-8').read().splitlines() if not l.lstrip().startswith('--'))
        out += [(os.path.basename(path), s.strip()) for s in sql.split(';\n') if s.strip().rstrip(';')]
    return out


def _params(sql, folder):
    """$f = folder; $fe/$sl/$am/$rp = the site's frontend, events, auth and report services (domain/services.py).
    Only the ones the statement uses: DuckDB refuses extra parameters."""
    p = services.current()
    allp = dict(f=folder, fe=p.frontend, sl=p.events, am=p.auth, rp=p.report, tz=timezone.current().minutes)
    return {k: v for k, v in allp.items() if re.search(r'\$' + k + r'\b', sql)}


def run(con, folder, now, rules_version):
    """Derive all aggregates of one folder. Called inside the caller's transaction."""
    timings = {}   # seconds per SQL file / step, so a slow ingest shows where the time went (owner request 2026-10-27)
    for name, sql in statements():
        t = time.perf_counter()
        try: con.execute(sql.rstrip(';'), _params(sql, folder))
        except Exception as e: raise RuntimeError(f'derive/{name}: {e}') from e
        timings[name] = timings.get(name, 0) + time.perf_counter() - t
    for step in steps.STEPS:
        t = time.perf_counter()
        try: step(con, folder)
        except Exception as e: raise RuntimeError(f'derive/steps.{step.__name__}: {e}') from e
        timings[f'steps.{step.__name__}'] = time.perf_counter() - t
    rng = con.execute("""SELECT min(a), max(b) FROM (
        SELECT min(ts_utc) a, max(ts_utc) b FROM nginx_access WHERE folder = $f UNION ALL
        SELECT min(ts_utc), max(ts_utc) FROM fe_access WHERE folder = $f UNION ALL
        SELECT min(ts_utc), max(ts_utc) FROM spring_line WHERE folder = $f)""", {'f': folder}).fetchone()
    con.execute('DELETE FROM folder_state WHERE folder = ?', [folder])
    con.execute("""INSERT INTO folder_state (folder, derived_at, rules_version, range_start_utc, range_end_utc, lines, files, files_empty, files_corrupt, crs_version, tz_minutes)
        SELECT $f, $now, $v, $a, $b, coalesce(sum(lines), 0), count(*),
               count(*) FILTER (WHERE lines = 0), count(*) FILTER (WHERE status = 'corrupt'), $crs, $tz
        FROM ingest_file WHERE folder = $f HAVING count(*) > 0""", {'f': folder, 'now': now, 'v': rules_version, 'a': rng[0], 'b': rng[1], 'crs': detect.version_key(),
                                                        'tz': timezone.current().minutes})
    return timings


def folders(con): return [str(r[0]) for r in con.execute('SELECT DISTINCT folder FROM ingest_file ORDER BY 1').fetchall()]
