"""Ingest bertahap dan aman diulang (TRD §3.1–§3.3): pindai -> sidik jari -> parse (subproses) -> muat CSV.

Satu transaksi per folder (K7). Hanya proses pemilik DuckDB yang memanggil run(); subproses hanya mem-parse.
Agregat diturunkan lewat derive_folder(), yang diisi tahap berikutnya.
"""
import concurrent.futures, datetime, json, multiprocessing, os, shutil, threading, time

from . import db, derive, detect, parse, refdata, rules

RAW_TABLES = list(parse.TABLES)
_lock = threading.Lock()  # satu ingest pada satu waktu (TRD §3.1)


def utcnow(): return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)  # semua waktu di database UTC


class Busy(RuntimeError):
    """Ingest lain sedang berjalan."""


def scan(roots):
    """{relpath logis (tanpa .gz): info file}. roots berurutan menurut prioritas: folder yang sama di dua akar -> akar pertama."""
    files, warnings, owner = {}, [], {}
    for root in roots:
        if not os.path.isdir(root): continue
        for top in sorted(os.listdir(root)):
            if not rules.DATE_DIR.fullmatch(top) or not os.path.isdir(os.path.join(root, top)): continue
            if owner.setdefault(top, root) != root:
                warnings.append(f'folder {top} ada di {owner[top]} dan {root}; yang kedua diabaikan'); continue
            for d, _, names in os.walk(os.path.join(root, top)):
                have = set(names)
                for name in sorted(names):
                    # aturan lama: semua *.log; *.log.gz hanya bila .log pasangannya tidak ada
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
    names = ', '.join(['file_id', 'line_no', 'folder'] + parse.TABLES[table][1:])   # nama kolom eksplisit: tabel bisa punya kolom turunan (crs_*, Tahap 21)
    con.execute(f"""INSERT INTO {table} ({names}) SELECT ?::INTEGER, line_no, ?::DATE, {cols}
                    FROM read_csv('{lit}', header=true, all_varchar=true, allow_quoted_nulls=false, quote='"', escape='"', delim=',')""",
                [file_id, folder])


def _delete_file_rows(con, file_id):
    for table in RAW_TABLES + ['file_counter']: con.execute(f'DELETE FROM {table} WHERE file_id = ?', [file_id])


def derive_folder(con, folder):
    """Turunkan agregat satu folder (TRD §3.4); dipanggil di dalam transaksi folder itu."""
    derive.run(con, folder, utcnow(), parse.RULES_VERSION)


def derive_all(con, only_folder=None):
    """Turunkan ulang agregat dari tabel mentah, tanpa parse ulang. Satu transaksi per folder."""
    done = []
    for fd in [only_folder] if only_folder else derive.folders(con):
        con.execute('BEGIN')
        try: derive_folder(con, fd); con.execute('COMMIT')
        except BaseException: con.execute('ROLLBACK'); raise
        done.append(fd)
    return done


def forget(con, folder):
    """Hapus semua data satu folder (pengganti perilaku lama 'folder hilang = hilang dari dashboard')."""
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


def run(cfg, con=None, folder=None, force=False, workers=None, progress=None):
    """Jalankan ingest. Mengembalikan ringkasan; melempar Busy bila ingest lain berjalan."""
    if not _lock.acquire(blocking=False): raise Busy('ingest sedang berjalan')
    detect.use(cfg)
    own = con is None
    try:
        con = con or db.open(cfg.db_path)
        return _run(cfg, con, folder, force, workers, progress or (lambda **k: None))
    finally:
        if own and con is not None: con.close()
        _lock.release()


def _run(cfg, con, only_folder, force, workers, progress):
    t0 = time.time()
    run_id = con.execute("SELECT nextval('seq_run_id')").fetchone()[0]
    con.execute("INSERT INTO ingest_run VALUES (?, ?, NULL, 'berjalan', NULL, NULL, NULL)", [run_id, utcnow()])
    tmp = os.path.join(cfg.data_dir, 'tmp', f'run-{run_id}')
    res = dict(run_id=run_id, status='ok', files_seen=0, files_changed=0, files_parsed=0, files_removed=0, files_failed=0, folders_changed=[], folders_recorrelated=[], refdata=None, warnings=[])
    try:
        files, res['warnings'] = scan([cfg.log_dir, cfg.inbox_dir])
        if only_folder: files = {k: f for k, f in files.items() if f['folder'] == only_folder}
        res['files_seen'] = len(files)
        cols = 'file_id, relpath, source_ext, folder, size_bytes, mtime_ns, sha256, rules_version'
        known = {r[1]: dict(zip(cols.split(', '), r)) for r in con.execute(f'SELECT {cols} FROM ingest_file').fetchall()}
        for k in known.values(): k['folder'] = str(k['folder'])

        # 1. calon: file baru, atau ukuran/mtime/berkas sumber/versi aturan berbeda (tanpa membaca isi)
        todo = [f for rel, f in sorted(files.items())
                if force or not (k := known.get(rel)) or k['rules_version'] != parse.RULES_VERSION
                or (k['size_bytes'], k['mtime_ns'], k['source_ext']) != (f['size_bytes'], f['mtime_ns'], f['source_ext'])]
        # 2. file yang hilang, hanya di folder yang masih ada di disk (folder hilang seluruhnya: data dipertahankan, T2)
        present = {f['folder'] for f in files.values()}
        gone = [k for rel, k in known.items() if rel not in files and k['folder'] in present and (not only_folder or k['folder'] == only_folder)]

        # 3. sidik jari + parse di subproses (K2); proses ini tidak mem-parse apa pun
        for i, f in enumerate(todo):
            f['out'] = os.path.join(tmp, str(i)); k = known.get(f['relpath'])
            f['known_sha'] = None if force or not k or k['rules_version'] != parse.RULES_VERSION else k['sha256']
        n = min(4, os.cpu_count() or 1) if workers is None else workers
        args = [(f['path'], f['service'], f['out'], cfg.upstream_prefix, f['known_sha'], f['pair']) for f in todo]
        if n and len(todo) > 2:
            with concurrent.futures.ProcessPoolExecutor(n, mp_context=multiprocessing.get_context('spawn')) as pool:
                futs = [pool.submit(parse.work, *a) for a in args]
                for i, (f, fut) in enumerate(zip(todo, futs)):
                    f['res'] = fut.result(); progress(phase='parse', done=i + 1, total=len(todo), file=f['relpath'])
        else:
            for i, (f, a) in enumerate(zip(todo, args)):
                f['res'] = parse.work(*a); progress(phase='parse', done=i + 1, total=len(todo), file=f['relpath'])

        # 4. satu transaksi per folder, urut tanggal (baris termuat urut folder)
        by_folder = {}
        for f in todo: by_folder.setdefault(f['folder'], [[], []])[0].append(f)
        for k in gone: by_folder.setdefault(k['folder'], [[], []])[1].append(k)
        for fd in sorted(by_folder):
            changed, removed = by_folder[fd]
            progress(phase='muat', folder=fd)
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
        # 5. korelasi lintas folder (TRD §3.5): folder lain yang event simpel-loop-nya kini cocok dengan nginx yang baru masuk
        for fd in derive.steps.affected_by(con, res['folders_changed']):
            con.execute('BEGIN')
            try: derive.steps.correlation(con, fd); con.execute('COMMIT')
            except BaseException: con.execute('ROLLBACK'); raise
            res['folders_recorrelated'].append(fd)
        # 5b. deteksi CRS (Tahap 21): folder yang agregat CRS-nya dibuat dengan versi aturan/tingkat paranoia lain diturunkan ulang
        #     dari path dan User-Agent yang tersimpan (tanpa parse ulang)
        res['folders_redetected'] = []
        for (fd,) in con.execute('SELECT folder::VARCHAR FROM folder_state WHERE crs_version IS DISTINCT FROM ? ORDER BY 1', [detect.version_key()]).fetchall():
            if fd in res['folders_changed'] or (only_folder and fd != only_folder): continue
            progress(phase='muat', folder=fd)
            con.execute('BEGIN')
            try:
                derive.steps.crs(con, fd)
                con.execute('UPDATE folder_state SET crs_version = ? WHERE folder = ?', [detect.version_key(), fd]); con.execute('COMMIT')
            except BaseException: con.execute('ROLLBACK'); raise
            res['folders_redetected'].append(fd)
        res['files_changed'] = res['files_parsed'] + res['files_removed'] + res['files_failed']

        # 6. lengkapi pemilik & lokasi IP dan berkas peta (TRD §3.6); kegagalan unduh tidak menggagalkan ingest
        try:
            r = refdata.run(cfg, con, offline=cfg.offline, log=lambda m: res['warnings'].append(f'refdata: {m}'))
            res['refdata'] = r
            for m in r['ip']['lewat']: res['warnings'].append(f'refdata: {m}')
        except Exception as e:  # noqa: BLE001
            res['warnings'].append(f'refdata gagal: {type(e).__name__}: {e}')
    except BaseException as e:
        res['status'] = 'gagal'; res['warnings'].append(f'{type(e).__name__}: {e}')
        raise
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        res['seconds'] = round(time.time() - t0, 2)
        con.execute('UPDATE ingest_run SET finished_at = ?, status = ?, files_seen = ?, files_changed = ?, message = ? WHERE run_id = ?',
                    [utcnow(), res['status'], res['files_seen'], res['files_changed'], json.dumps(res['warnings'], ensure_ascii=False), run_id])
    return res


def _hook_before_commit(folder):
    """Titik sisip untuk uji 'proses terhenti di tengah transaksi'."""


def _apply_file(con, f, k, res):
    """Terapkan hasil satu file di dalam transaksi folder. True bila isi tabel mentah berubah."""
    r, s = f['res'], f['res']['summary']
    if s and not s['known_service']:
        res['warnings'].append(f"{f['relpath']}: layanan tak dikenal '{f['service']}', diperlakukan sebagai Spring Boot")
    if r['pair_sha256'] and r['sha256'] and r['pair_sha256'] != r['sha256']:
        res['warnings'].append(f"{f['relpath']}: isi .log dan .log.gz BERBEDA; .log yang dipakai")
    if k and k['source_ext'] != f['source_ext'] and r['sha256'] and r['sha256'] != k['sha256']:
        res['warnings'].append(f"{f['relpath']}: {f['source_ext']} berbeda dari {k['source_ext']} yang sudah diproses; diproses ulang")
    file_id = k['file_id'] if k else con.execute("SELECT nextval('seq_file_id')").fetchone()[0]
    meta = [f['source_ext'], f['size_bytes'], f['mtime_ns']]
    if r['error']:
        res['warnings'].append(f"{f['relpath']}: GAGAL di-parse: {r['error']}"); res['files_failed'] += 1
        _delete_file_rows(con, file_id); con.execute('DELETE FROM ingest_file WHERE file_id = ?', [file_id])
        # rules_version 0 -> selalu dicoba lagi pada ingest berikutnya
        con.execute("INSERT INTO ingest_file VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, 0, 0, 'gagal', 0, ?)",
                    [file_id, f['relpath'], f['source_ext'], f['folder'], f['ns'], f['service'], f['pod'], f['size_bytes'], f['mtime_ns'], r['sha256'] or '', utcnow()])
        return True
    if s is None:  # isi sama dengan yang sudah diproses: hanya berkas sumbernya yang berubah (disentuh, atau .gz <-> .log)
        con.execute('UPDATE ingest_file SET source_ext = ?, size_bytes = ?, mtime_ns = ? WHERE file_id = ?', meta + [file_id])
        return False
    _delete_file_rows(con, file_id); con.execute('DELETE FROM ingest_file WHERE file_id = ?', [file_id])
    status = 'kosong' if not s['lines'] else 'rusak' if s['corrupt_lines'] and not s['rows'] else 'ok'
    con.execute('INSERT INTO ingest_file VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                [file_id, f['relpath'], f['source_ext'], f['folder'], f['ns'], f['service'], f['pod'], f['size_bytes'], f['mtime_ns'], r['sha256'],
                 s['lines'], s['err'], s['warn'], s['corrupt_lines'], status, parse.RULES_VERSION, utcnow()])
    for table in s['rows']: _load_csv(con, table, os.path.join(f['out'], table + '.csv'), file_id, f['folder'])
    if s['counters']: con.executemany('INSERT INTO file_counter VALUES (?, ?, ?, ?)', [[file_id, *c] for c in s['counters']])
    res['files_parsed'] += 1
    return True


def checksums(con):
    """{tabel: (jumlah baris, checksum isi)} tanpa kolom yang berubah tiap ingest. Untuk uji 'ingest ulang = sama'."""
    skip = {'ingest_file': 'ingested_at, mtime_ns', 'folder_state': 'derived_at'}
    out = {}
    for (t,) in con.execute("SELECT table_name FROM information_schema.tables WHERE table_type = 'BASE TABLE' AND table_name <> 'ingest_run' ORDER BY 1").fetchall():
        ex = f" EXCLUDE ({skip[t]})" if t in skip else ''
        out[t] = con.execute(f'SELECT count(*), coalesce(bit_xor(hash(x)), 0) FROM (SELECT *{ex} FROM {t}) x').fetchone()
    return out
