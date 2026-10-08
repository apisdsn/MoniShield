"""Incremental, safely repeatable ingest (TRD §3.1–§3.3): scan -> fingerprint -> parse (subprocess) -> load CSV.

One transaction per folder (K7). Only the process owning DuckDB calls run(); subprocesses only parse.
Aggregates are derived via derive_folder(), filled in by a later stage.
"""
import concurrent.futures, datetime, json, multiprocessing, os, shutil, threading, time

from monishield.infrastructure import db, derive, logfiles, refdata
from monishield.domain import detect, parse, rules

RAW_TABLES = list(parse.TABLES)
_lock = threading.Lock()  # one ingest at a time (TRD §3.1)


def utcnow(): return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)  # all times in the database are UTC


class Busy(RuntimeError):
    """Another ingest is running."""


def scan(roots):
    """{logical relpath (without .gz): file info}. roots ordered by priority: the same folder in two roots -> the first root."""
    files, warnings, owner = {}, [], {}
    for root in roots:
        if not os.path.isdir(root): continue
        for top in sorted(os.listdir(root)):
            if not rules.DATE_DIR.fullmatch(top) or not os.path.isdir(os.path.join(root, top)): continue
            if owner.setdefault(top, root) != root:
                warnings.append(f'folder {top} is in {owner[top]} and {root}; the second one is ignored'); continue
            for d, _, names in os.walk(os.path.join(root, top)):
                have = set(names)
                for name in sorted(names):
                    # old rule: all *.log; *.log.gz only when its .log pair is absent
                    if not (name.endswith('.log') or (name.endswith('.log.gz') and name[:-3] not in have)): continue
                    path = os.path.join(d, name)
                    parts = rules.split_relpath(os.path.relpath(path, root))
                    if not parts: continue
                    folder, ns, service, base = parts
                    st = os.stat(path)
                    rel = os.path.relpath(path, root).removesuffix('.gz')
                    files[rel] = dict(relpath=rel, path=path, source_ext='.log.gz' if name.endswith('.gz') else '.log', folder=folder, ns=ns,
                                      service=service, pod=rules.pod_name(service, base), size_bytes=st.st_size, mtime_ns=st.st_mtime_ns,
                                      pair=path + '.gz' if name.endswith('.log') and name + '.gz' in have else None)
    return files, warnings


def _load_csv(con, table, csv_path, file_id, folder):
    cols = ', '.join(f"string_split({c}, ',')" if c in parse.LIST_COLS else c for c in parse.TABLES[table][1:])
    lit = csv_path.replace("'", "''")
    names = ', '.join(['file_id', 'line_no', 'folder'] + parse.TABLES[table][1:])   # explicit column names: the table may have derived columns (crs_*, Stage 21)
    con.execute(f"""INSERT INTO {table} ({names}) SELECT ?::INTEGER, line_no, ?::DATE, {cols}
                    FROM read_csv('{lit}', header=true, all_varchar=true, allow_quoted_nulls=false, quote='"', escape='"', delim=',')""",
                [file_id, folder])


def _delete_file_rows(con, file_id):
    for table in RAW_TABLES + ['file_counter']: con.execute(f'DELETE FROM {table} WHERE file_id = ?', [file_id])


def derive_folder(con, folder):
    """Derive one folder's aggregates (TRD §3.4); called inside that folder's transaction."""
    derive.run(con, folder, utcnow(), parse.RULES_VERSION)


def derive_all(con, only_folder=None):
    """Re-derive aggregates from the raw tables, without re-parsing. One transaction per folder."""
    done = []
    for fd in [only_folder] if only_folder else derive.folders(con):
        con.execute('BEGIN')
        try: derive_folder(con, fd); con.execute('COMMIT')
        except BaseException: con.execute('ROLLBACK'); raise
        done.append(fd)
    return done


def forget(con, folder):
    """Delete all data of one folder (replaces the old behavior 'folder gone = gone from the dashboard')."""
    con.execute('BEGIN')
    try:
        n = con.execute('SELECT count(*) FROM ingest_file WHERE folder = ?', [folder]).fetchone()[0]
        tables = [r[0] for r in con.execute("SELECT table_name FROM information_schema.columns WHERE column_name = 'folder' AND table_name NOT LIKE 'v\\_%' ESCAPE '\\' AND table_name <> 'ingest_file'").fetchall()]
        con.execute('DELETE FROM file_counter WHERE file_id IN (SELECT file_id FROM ingest_file WHERE folder = ?)', [folder])
        for table in tables + ['ingest_file']: con.execute(f'DELETE FROM {table} WHERE folder = ?', [folder])
        con.execute('COMMIT')
    except BaseException:
        con.execute('ROLLBACK'); raise
    return n


def ignored(con):
    """{'YYYY-MM-DD'} folders ignored by ingest (deleted by an admin from the dashboard, files still on disk)."""
    return {r[0] for r in con.execute('SELECT ignored_folder FROM folder_ignored').fetchall()}


def _next_id(con, seq, table, col):
    """New number from the sequence, but never <= the largest existing number. A DuckDB sequence can lag behind
    after the process is killed (the restored value is smaller than the stored rows) -> "Duplicate key".
    Safe because it is only called under _lock (single writer)."""
    v = con.execute(f"SELECT nextval('{seq}')").fetchone()[0]
    return max(v, con.execute(f'SELECT coalesce(max({col}), 0) + 1 FROM {table}').fetchone()[0])


def run(cfg, con=None, folder=None, force=False, workers=None, progress=None):
    """Run the ingest. Returns a summary; raises Busy when another ingest is running."""
    if not _lock.acquire(blocking=False): raise Busy('an ingest is running')
    detect.use(cfg)
    own = con is None
    try:
        con = con or db.open(cfg.db_path)
        return _run(cfg, con, folder, force, workers, progress or (lambda **k: None))
    finally:
        if own and con is not None: con.close()
        _lock.release()


def _cleanup_killed(cfg, con):
    """A killed process (kill -9, container stopped) never gets to run `finally`: the ingest_run row is left
    'running' and temporary CSVs (holding IPs/emails from logs) are left in data/tmp. Called at the start of an ingest,
    while the ingest lock is held, so no other run is using either."""
    con.execute("UPDATE ingest_run SET finished_at = ?, status = 'failed', message = ? WHERE status = 'running'",
                [utcnow(), json.dumps(['interrupted: the process stopped before the ingest finished; data of unfinished folders is unchanged'])])
    tmp = os.path.join(cfg.data_dir, 'tmp')
    for d in os.listdir(tmp) if os.path.isdir(tmp) else []:
        if d.startswith('run-'): shutil.rmtree(os.path.join(tmp, d), ignore_errors=True)


def _run(cfg, con, only_folder, force, workers, progress):
    t0 = time.time()
    _cleanup_killed(cfg, con)
    run_id = _next_id(con, 'seq_run_id', 'ingest_run', 'run_id')
    con.execute("INSERT INTO ingest_run VALUES (?, ?, NULL, 'running', NULL, NULL, NULL)", [run_id, utcnow()])
    tmp = os.path.join(cfg.data_dir, 'tmp', f'run-{run_id}')
    res = dict(run_id=run_id, status='ok', files_seen=0, files_changed=0, files_parsed=0, files_removed=0, files_failed=0, folders_changed=[], folders_recorrelated=[], refdata=None, warnings=[])
    try:
        files, res['warnings'] = scan([cfg.log_dir, cfg.inbox_dir])
        ign = ignored(con)   # folders an admin deleted from the dashboard: skipped until restored
        files = {k: f for k, f in files.items() if f['folder'] not in ign}
        if only_folder: files = {k: f for k, f in files.items() if f['folder'] == only_folder}
        res['files_seen'] = len(files)
        cols = 'file_id, relpath, source_ext, folder, size_bytes, mtime_ns, sha256, rules_version'
        known = {r[1]: dict(zip(cols.split(', '), r)) for r in con.execute(f'SELECT {cols} FROM ingest_file').fetchall()}
        for k in known.values(): k['folder'] = str(k['folder'])

        # 1. candidates: new files, or a different size/mtime/source file/rules version (without reading content)
        todo = [f for rel, f in sorted(files.items())
                if force or not (k := known.get(rel)) or k['rules_version'] != parse.RULES_VERSION
                or (k['size_bytes'], k['mtime_ns'], k['source_ext']) != (f['size_bytes'], f['mtime_ns'], f['source_ext'])]
        # 2. missing files, only in folders still on disk (a folder gone entirely: data is kept, T2)
        present = {f['folder'] for f in files.values()}
        gone = [k for rel, k in known.items() if rel not in files and k['folder'] in present and (not only_folder or k['folder'] == only_folder)]

        # 3. fingerprint + parse in subprocesses (K2); this process parses nothing
        for i, f in enumerate(todo):
            f['out'] = os.path.join(tmp, str(i)); k = known.get(f['relpath'])
            f['known_sha'] = None if force or not k or k['rules_version'] != parse.RULES_VERSION else k['sha256']
        n = min(4, os.cpu_count() or 1) if workers is None else workers
        args = [(f['path'], f['service'], f['out'], cfg.upstream_prefix, f['known_sha'], f['pair']) for f in todo]
        if n and len(todo) > 2:
            with concurrent.futures.ProcessPoolExecutor(n, mp_context=multiprocessing.get_context('spawn')) as pool:
                futs = [pool.submit(logfiles.work, *a) for a in args]
                for i, (f, fut) in enumerate(zip(todo, futs)):
                    f['res'] = fut.result(); progress(phase='parse', done=i + 1, total=len(todo), file=f['relpath'])
        else:
            for i, (f, a) in enumerate(zip(todo, args)):
                f['res'] = logfiles.work(*a); progress(phase='parse', done=i + 1, total=len(todo), file=f['relpath'])

        # 4. one transaction per folder, in date order (rows loaded in folder order)
        by_folder = {}
        for f in todo: by_folder.setdefault(f['folder'], [[], []])[0].append(f)
        for k in gone: by_folder.setdefault(k['folder'], [[], []])[1].append(k)
        for fd in sorted(by_folder):
            changed, removed = by_folder[fd]
            progress(phase='load', folder=fd)
            con.execute('BEGIN')
            try:
                touched = False
                for k in removed:
                    _delete_file_rows(con, k['file_id']); con.execute('DELETE FROM ingest_file WHERE file_id = ?', [k['file_id']])
                    res['files_removed'] += 1; touched = True
                for f in changed:
                    touched |= _apply_file(con, f, known.get(f['relpath']), res)
                if touched:
                    derive_folder(con, fd); res['folders_changed'].append(fd)
                _hook_before_commit(fd)
                con.execute('COMMIT')
            except BaseException:
                con.execute('ROLLBACK'); raise
        # 5. cross-folder correlation (TRD §3.5): other folders whose simpel-loop events now match newly loaded nginx
        for fd in derive.steps.affected_by(con, res['folders_changed']):
            con.execute('BEGIN')
            try: derive.steps.correlation(con, fd); con.execute('COMMIT')
            except BaseException: con.execute('ROLLBACK'); raise
            res['folders_recorrelated'].append(fd)
        # 5b. CRS detection (Stage 21): folders whose CRS aggregates were built with another rules version/paranoia level are re-derived
        #     from the stored path and User-Agent (no re-parse)
        res['folders_redetected'] = []
        for (fd,) in con.execute('SELECT folder::VARCHAR FROM folder_state WHERE crs_version IS DISTINCT FROM ? ORDER BY 1', [detect.version_key()]).fetchall():
            if fd in res['folders_changed'] or (only_folder and fd != only_folder): continue
            progress(phase='load', folder=fd)
            con.execute('BEGIN')
            try:
                derive.steps.crs(con, fd)
                con.execute('UPDATE folder_state SET crs_version = ? WHERE folder = ?', [detect.version_key(), fd]); con.execute('COMMIT')
            except BaseException: con.execute('ROLLBACK'); raise
            res['folders_redetected'].append(fd)
        res['files_changed'] = res['files_parsed'] + res['files_removed'] + res['files_failed']

        # 6. fill in IP owner & location and the map files (TRD §3.6); a download failure does not fail the ingest
        try:
            r = refdata.run(cfg, con, offline=cfg.offline, log=lambda m: res['warnings'].append(f'refdata: {m}'))
            res['refdata'] = r
            for m in r['ip']['skipped']: res['warnings'].append(f'refdata: {m}')
        except Exception as e:  # noqa: BLE001
            res['warnings'].append(f'refdata failed: {type(e).__name__}: {e}')
    except BaseException as e:
        res['status'] = 'failed'; res['warnings'].append(f'{type(e).__name__}: {e}')
        raise
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        res['seconds'] = round(time.time() - t0, 2)
        con.execute('UPDATE ingest_run SET finished_at = ?, status = ?, files_seen = ?, files_changed = ?, message = ? WHERE run_id = ?',
                    [utcnow(), res['status'], res['files_seen'], res['files_changed'], json.dumps(res['warnings'], ensure_ascii=False), run_id])
    return res


def _hook_before_commit(folder):
    """Hook point for the 'process stopped mid-transaction' test."""


def _apply_file(con, f, k, res):
    """Apply one file's result inside the folder transaction. True when raw table content changed."""
    r, s = f['res'], f['res']['summary']
    if s and not s['known_service']:
        res['warnings'].append(f"{f['relpath']}: unknown service '{f['service']}', treated as Spring Boot")
    if r['pair_sha256'] and r['sha256'] and r['pair_sha256'] != r['sha256']:
        res['warnings'].append(f"{f['relpath']}: .log and .log.gz contents DIFFER; the .log is used")
    if k and k['source_ext'] != f['source_ext'] and r['sha256'] and r['sha256'] != k['sha256']:
        res['warnings'].append(f"{f['relpath']}: {f['source_ext']} differs from the {k['source_ext']} already processed; re-processed")
    file_id = k['file_id'] if k else _next_id(con, 'seq_file_id', 'ingest_file', 'file_id')
    meta = [f['source_ext'], f['size_bytes'], f['mtime_ns']]
    if r['error']:
        res['warnings'].append(f"{f['relpath']}: FAILED to parse: {r['error']}"); res['files_failed'] += 1
        _delete_file_rows(con, file_id); con.execute('DELETE FROM ingest_file WHERE file_id = ?', [file_id])
        # rules_version 0 -> always retried on the next ingest
        con.execute("INSERT INTO ingest_file VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, 0, 0, 'failed', 0, ?)",
                    [file_id, f['relpath'], f['source_ext'], f['folder'], f['ns'], f['service'], f['pod'], f['size_bytes'], f['mtime_ns'], r['sha256'] or '', utcnow()])
        return True
    if s is None:  # content same as already processed: only the source file changed (touched, or .gz <-> .log)
        con.execute('UPDATE ingest_file SET source_ext = ?, size_bytes = ?, mtime_ns = ? WHERE file_id = ?', meta + [file_id])
        return False
    _delete_file_rows(con, file_id); con.execute('DELETE FROM ingest_file WHERE file_id = ?', [file_id])
    status = 'empty' if not s['lines'] else 'corrupt' if s['corrupt_lines'] and not s['rows'] else 'ok'
    if status == 'corrupt' and _export_error(f['path']):   # found in real S3 data 2026-10-07
        res['warnings'].append(f"{f['relpath']}: contains an error message from the log export tool, not logs ('{EXPORT_ERROR}…'); check the log delivery to S3")
    con.execute('INSERT INTO ingest_file VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                [file_id, f['relpath'], f['source_ext'], f['folder'], f['ns'], f['service'], f['pod'], f['size_bytes'], f['mtime_ns'], r['sha256'],
                 s['lines'], s['err'], s['warn'], s['corrupt_lines'], status, parse.RULES_VERSION, utcnow()])
    for table in s['rows']: _load_csv(con, table, os.path.join(f['out'], table + '.csv'), file_id, f['folder'])
    if s['counters']: con.executemany('INSERT INTO file_counter VALUES (?, ?, ?, ?)', [[file_id, *c] for c in s['counters']])
    res['files_parsed'] += 1
    return True


EXPORT_ERROR = 'failed to get parse function'


def _export_error(path):
    """A file whose content is an error message from the log shipping tool (e.g. 'failed to get parse function: unsupported log format'),
    not logs. Only the first 200 bytes are read (.log or .log.gz)."""
    import gzip
    try:
        with (gzip.open if path.endswith('.gz') else open)(path, 'rb') as fh: return fh.read(200).startswith(EXPORT_ERROR.encode())
    except (OSError, EOFError): return False


def checksums(con):
    """{table: (row count, content checksum)} without columns that change every ingest. For the 're-ingest = same' test."""
    skip = {'ingest_file': 'ingested_at, mtime_ns', 'folder_state': 'derived_at'}
    out = {}
    for (t,) in con.execute("SELECT table_name FROM information_schema.tables WHERE table_type = 'BASE TABLE' AND table_name <> 'ingest_run' ORDER BY 1").fetchall():
        ex = f" EXCLUDE ({skip[t]})" if t in skip else ''
        out[t] = con.execute(f'SELECT count(*), coalesce(bit_xor(hash(x)), 0) FROM (SELECT *{ex} FROM {t}) x').fetchone()
    return out
