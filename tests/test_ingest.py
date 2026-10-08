"""Incremental, safely repeatable ingest (TRD §9.4), over a small synthetic log folder (logs_mini)."""
import dataclasses, os, shutil, threading

import duckdb, pytest

import logs_mini
from monishield.infrastructure import config, db, ingest, logfiles
from monishield.domain import parse

A, B = '2026-01-01', '2026-01-02'
SL = ('ombudsman', 'om-be-simpel-loop', 'pod-s')


@pytest.fixture
def env(tmp_path):
    root = logs_mini.build(tmp_path / 'logs')
    cfg = dataclasses.replace(config.Config(), log_dir=root, data_dir=str(tmp_path / 'data'), inbox_dir=str(tmp_path / 'inbox'),
                              state_dir=str(tmp_path / 'data'), cache_dir=str(tmp_path / 'cache'), offline=True)
    con = db.open(cfg.db_path)
    yield cfg, con, root
    con.close()


def go(cfg, con, **kw): return ingest.run(cfg, con, workers=0, **kw)  # offline cfg: refdata only records that the reference files have not been downloaded
def q(con, sql, *p): return con.execute(sql, list(p)).fetchall()
def files(con): return {r[0].split(os.sep)[-2]: r[1:] for r in q(con, 'SELECT relpath, source_ext, lines, err, warn, corrupt_lines, status, ns, pod, folder::VARCHAR FROM ingest_file')}
def raw_sums(con): return {t: v for t, v in ingest.checksums(con).items() if t in ingest.RAW_TABLES + ['file_counter', 'ingest_file', 'folder_state']}
def touch(path, ns=5_000_000_000): st = os.stat(path); os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + ns))


def test_ingest_pertama(env):
    cfg, con, root = env
    r = go(cfg, con)
    assert (r['status'], r['files_seen'], r['files_parsed'], r['files_failed'], r['folders_changed']) == ('ok', 9, 9, 0, [A, B])
    f = files(con)
    assert f['nginx-ingress-controller'] == ('.log', 11, 2, 1, 0, 'ok', 'ingress-nginx', 'pod-n', B)
    assert f['om-fe-inhouse'] == ('.log', 5, 1, 0, 0, 'ok', '-', 'pod-f', A)                    # folder without namespace (A9)
    assert f['om-be-simpel-loop'][:2] == ('.log', 9) and f['om-be-report'][:2] == ('.log.gz', 4)  # .log wins; .gz is read when alone
    assert f['om-be-referensi'] == ('.log', 1, 0, 0, 1, 'corrupt', 'ombudsman', 'pod-x', B)        # counted as a line, marked corrupt
    assert sorted(r_[0] for r_ in q(con, "SELECT status FROM ingest_file WHERE service = 'om-be-appsmanager'")) == ['empty', 'ok']
    assert f['layanan-baru'][5] == 'ok' and any("unknown service 'layanan-baru'" in w for w in r['warnings'])  # A10
    n = {t: q(con, f'SELECT count(*) FROM {t}')[0][0] for t in ingest.RAW_TABLES}
    assert n == dict(nginx_access=7, nginx_error=4, fe_access=2, sl_event=4, spring_line=18, coredns_error=1, log_message=19)
    assert q(con, "SELECT len(up_addrs), len(up_statuses), pod_final = up_addrs[2] FROM nginx_access WHERE len(up_addrs) > 1") == [(2, 2, True)]  # retry line
    assert q(con, "SELECT folder::VARCHAR, status, is_uptime_kuma, ts_utc::VARCHAR FROM nginx_access WHERE line_no = 2") == [(B, 200, True, '2026-09-27 17:02:58')]
    assert q(con, "SELECT kind, key, n FROM file_counter c JOIN ingest_file f USING (file_id) WHERE service = 'om-be-simpel-loop' AND kind <> 'level' ORDER BY 1") == \
        [('biz', 'Email Terkirim', 1), ('mail', 'sendNotificationMailToKepalaKeasistenanRiksa', 1)]
    assert q(con, 'SELECT folder::VARCHAR, lines, files, files_empty, files_corrupt FROM folder_state ORDER BY 1') == [(A, 15, 2, 0, 0), (B, 38, 7, 1, 1)]  # B: 11 + 3 + 9 + 4 + 1 + 0 + 10
    assert q(con, "SELECT range_start_utc::VARCHAR, range_end_utc::VARCHAR FROM folder_state WHERE folder = ?", A) == [('2026-09-25 16:04:19', '2026-09-27 23:44:36')]  # password reset line = last timestamp
    assert not os.path.exists(os.path.join(cfg.data_dir, 'tmp', f"run-{r['run_id']}"))  # temporary CSV cleaned up
    assert q(con, 'SELECT status, files_seen, files_changed FROM ingest_run') == [('ok', 9, 9)]


def test_kunci_file_id_line_no_unik(env):
    cfg, con, _ = env
    go(cfg, con); go(cfg, con, force=True)
    for t in ingest.RAW_TABLES:
        assert q(con, f'SELECT count(*) FROM (SELECT file_id, line_no FROM {t} GROUP BY ALL HAVING count(*) > 1)')[0][0] == 0, t


def test_ingest_dua_kali_sama(env, monkeypatch):
    cfg, con, _ = env
    go(cfg, con); before = ingest.checksums(con)
    monkeypatch.setattr(logfiles, 'work', lambda *a: pytest.fail('file yang tidak berubah tidak boleh dibaca'))
    r = go(cfg, con)
    assert (r['files_seen'], r['files_changed'], r['folders_changed']) == (9, 0, []) and ingest.checksums(con) == before


def test_force_dan_rules_version_parse_ulang_dengan_hasil_sama(env, monkeypatch):
    cfg, con, _ = env
    go(cfg, con); before = raw_sums(con)
    assert go(cfg, con, force=True)['files_parsed'] == 9 and raw_sums(con) == before
    monkeypatch.setattr(parse, 'RULES_VERSION', parse.RULES_VERSION + 1)
    r = go(cfg, con)
    assert r['files_parsed'] == 9 and q(con, 'SELECT DISTINCT rules_version FROM ingest_file') == [(parse.RULES_VERSION,)]


def test_file_bertambah_hanya_folder_itu_dan_sama_dengan_ingest_bersih(env, tmp_path):
    cfg, con, root = env
    go(cfg, con); a_before = q(con, 'SELECT * FROM ingest_file WHERE folder = ? ORDER BY 1', A)
    p = logs_mini.log_path(root, B, *SL)
    with open(p, 'a') as fh: fh.write('[OM-ERROR] {"event":"http.request.failed","requestId":"z","method":"GET","path":"/x","statusCode":500,"durationMs":3}\n')
    os.remove(p + '.gz')
    r = go(cfg, con)
    assert (r['files_parsed'], r['folders_changed']) == (1, [B]) and q(con, 'SELECT * FROM ingest_file WHERE folder = ? ORDER BY 1', A) == a_before
    assert q(con, "SELECT lines, err, warn FROM ingest_file WHERE service = 'om-be-simpel-loop'") == [(10, 1, 2)] and q(con, 'SELECT count(*) FROM sl_event')[0][0] == 5
    cfg2 = dataclasses.replace(cfg, data_dir=str(tmp_path / 'bersih')); con2 = db.open(cfg2.db_path)
    go(cfg2, con2)
    assert raw_sums(con2) == raw_sums(con)  # incremental ingest = clean ingest
    con2.close()


def test_disentuh_tetapi_isi_sama_tidak_parse_ulang(env):
    cfg, con, root = env
    go(cfg, con); before = {k: v for k, v in raw_sums(con).items() if k != 'ingest_file'}
    p = logs_mini.log_path(root, B, 'ingress-nginx', 'nginx-ingress-controller', 'pod-n'); touch(p)
    r = go(cfg, con)
    assert (r['files_parsed'], r['files_changed'], r['folders_changed']) == (0, 0, [])
    assert q(con, "SELECT mtime_ns FROM ingest_file WHERE service = 'nginx-ingress-controller'") == [(os.stat(p).st_mtime_ns,)]
    assert {k: v for k, v in raw_sums(con).items() if k != 'ingest_file'} == before


def test_gz_lalu_log_identik_tanpa_parse_ulang(env):
    cfg, con, root = env
    go(cfg, con); before = {k: v for k, v in raw_sums(con).items() if k != 'ingest_file'}
    gz = logs_mini.log_path(root, B, 'ombudsman', 'om-be-report', 'pod-r', '.log.gz')
    logs_mini.write(gz[:-3], logs_mini.lines('om-be-report'))  # identical .log appears
    r = go(cfg, con)
    assert (r['files_parsed'], [w for w in r['warnings'] if not w.startswith('refdata:')]) == (0, [])
    assert q(con, "SELECT source_ext, size_bytes FROM ingest_file WHERE service = 'om-be-report'") == [('.log', os.path.getsize(gz[:-3]))]
    assert {k: v for k, v in raw_sums(con).items() if k != 'ingest_file'} == before and q(con, "SELECT count(*) FROM ingest_file WHERE service = 'om-be-report'") == [(1,)]
    os.remove(gz[:-3])  # .log gone, .gz remains: back to .gz, still no re-parse
    r = go(cfg, con)
    assert r['files_parsed'] == 0 and q(con, "SELECT source_ext FROM ingest_file WHERE service = 'om-be-report'") == [('.log.gz',)]


def test_pasangan_berbeda_dicatat_dan_log_yang_dipakai(env):
    cfg, con, root = env
    go(cfg, con)
    gz = logs_mini.log_path(root, B, 'ombudsman', 'om-be-report', 'pod-r', '.log.gz')
    logs_mini.write(gz[:-3], logs_mini.lines('om-be-report').splitlines(True)[0])  # .log has only 1 line, .gz 4 lines
    r = go(cfg, con)
    assert r['files_parsed'] == 1 and q(con, "SELECT source_ext, lines FROM ingest_file WHERE service = 'om-be-report'") == [('.log', 1)]
    assert any('DIFFER' in w for w in r['warnings']) and any('differs from the .log.gz already processed' in w for w in r['warnings'])
    assert 'DIFFER' in q(con, 'SELECT message FROM ingest_run ORDER BY run_id DESC LIMIT 1')[0][0]


def test_pasangan_identik_tanpa_peringatan(env):
    cfg, con, _ = env
    assert not [w for w in go(cfg, con)['warnings'] if 'BERBEDA' in w]  # simpel-loop has .log + identical .log.gz


def test_file_dihapus_barisnya_hilang(env):
    cfg, con, root = env
    go(cfg, con)
    os.remove(logs_mini.log_path(root, B, 'kube-system', 'coredns', 'pod-d'))
    r = go(cfg, con)
    assert (r['files_removed'], r['folders_changed']) == (1, [B])
    assert q(con, 'SELECT count(*) FROM coredns_error')[0][0] == 0 and q(con, "SELECT count(*) FROM log_message WHERE service = 'coredns'")[0][0] == 0
    assert q(con, "SELECT count(*) FROM ingest_file WHERE service = 'coredns'")[0][0] == 0 and q(con, 'SELECT files, lines FROM folder_state WHERE folder = ?', B) == [(6, 35)]


def test_folder_hilang_seluruhnya_data_dipertahankan_dan_forget(env):
    cfg, con, root = env
    go(cfg, con); before = ingest.checksums(con)
    shutil.rmtree(os.path.join(root, A))
    r = go(cfg, con)
    assert (r['files_removed'], r['files_seen']) == (0, 7) and ingest.checksums(con) == before  # T2
    assert ingest.forget(con, A) == 2
    assert q(con, 'SELECT count(*) FROM ingest_file WHERE folder = ?', A)[0][0] == 0 and q(con, 'SELECT count(*) FROM fe_access')[0][0] == 0
    assert q(con, 'SELECT count(*) FROM folder_state')[0][0] == 1 and q(con, 'SELECT count(*) FROM ingest_file WHERE folder = ?', B)[0][0] == 7
    assert q(con, 'SELECT count(*) FROM file_counter c LEFT JOIN ingest_file f USING (file_id) WHERE f.file_id IS NULL')[0][0] == 0


def test_file_gagal_parse_file_lain_tetap_masuk_dan_dicoba_lagi(env):
    cfg, con, root = env
    dua_pola = ("2026-09-27 23:39:32.545  WARN 1 --- [x] c.U : Invalid password for user/email: 'a@b' from IP: 1.2.3.4 "
                "due to 3 failed login attempts for user/email: 'a@b' from IP: 1.2.3.4\n")
    p = logs_mini.write(logs_mini.log_path(root, B, 'ombudsman', 'om-be-report', 'pod-bad'), dua_pola)
    r = go(cfg, con)
    assert (r['files_failed'], r['files_parsed'], r['status']) == (1, 9, 'ok') and any('FAILED to parse' in w and 'login pattern' in w for w in r['warnings'])
    assert q(con, "SELECT status, lines FROM ingest_file WHERE pod = 'pod-bad'") == [('failed', 0)] and q(con, 'SELECT count(*) FROM nginx_access')[0][0] == 7
    assert go(cfg, con)['files_failed'] == 1  # retried on every ingest
    logs_mini.write(p, logs_mini.lines('om-be-report'))
    r = go(cfg, con)
    assert (r['files_failed'], r['files_parsed']) == (0, 1) and q(con, "SELECT status, lines FROM ingest_file WHERE pod = 'pod-bad'") == [('ok', 4)]


def test_terhenti_di_tengah_transaksi_lalu_bersih(env, monkeypatch):
    cfg, con, _ = env
    def mati(folder):
        if folder == B: raise KeyboardInterrupt('proses dihentikan')
    monkeypatch.setattr(ingest, '_hook_before_commit', mati)
    with pytest.raises(KeyboardInterrupt): go(cfg, con)
    assert q(con, 'SELECT DISTINCT folder::VARCHAR FROM ingest_file') == [(A,)]          # folder A already committed
    assert q(con, 'SELECT count(*) FROM nginx_access')[0][0] == 0 and q(con, 'SELECT count(*) FROM file_counter c JOIN ingest_file f USING (file_id) WHERE folder = ?', B)[0][0] == 0
    assert q(con, 'SELECT status FROM ingest_run')[0][0] == 'failed' and not os.listdir(os.path.join(cfg.data_dir, 'tmp'))
    monkeypatch.undo()
    r = go(cfg, con)
    assert (r['files_parsed'], r['folders_changed']) == (7, [B])
    cfg2 = dataclasses.replace(cfg, data_dir=cfg.data_dir + '2'); con2 = db.open(cfg2.db_path); go(cfg2, con2)
    assert {k: v[0] for k, v in raw_sums(con).items()} == {k: v[0] for k, v in raw_sums(con2).items()}  # line count = clean ingest
    con2.close()


def test_dimatikan_paksa_dibersihkan_pada_ingest_berikutnya(env):
    """kill -9 / container killed mid-ingest (tested in docker, Step 7): `finally` does not run, so the ingest_run
    row is left 'berjalan' and the temporary CSV is left behind. The next ingest marks that run failed and removes the leftovers."""
    cfg, con, _ = env
    go(cfg, con)
    con.execute("INSERT INTO ingest_run VALUES (90, now(), NULL, 'running', NULL, NULL, NULL)")
    sisa = os.path.join(cfg.data_dir, 'tmp', 'run-90'); os.makedirs(sisa); open(os.path.join(sisa, '0'), 'w').write('203.0.113.9,budi@contoh.go.id')
    r = go(cfg, con)
    assert r['status'] == 'ok' and not os.path.exists(sisa)
    st, msg, selesai = q(con, 'SELECT status, message, finished_at FROM ingest_run WHERE run_id = 90')[0]
    assert st == 'failed' and 'interrupted' in msg and selesai is not None


def test_sequence_tertinggal_tidak_membuat_duplicate_key(env):
    """Owner report 2026-10-07: 'Duplicate key "run_id: 28"'. The DuckDB sequence can lag behind the stored rows
    (e.g. after the process was killed). Ingest must still run with a new, unused number."""
    cfg, con, root = env
    go(cfg, con)
    runs, fids = q(con, 'SELECT max(run_id) FROM ingest_run')[0][0], q(con, 'SELECT max(file_id) FROM ingest_file')[0][0]
    for sq in ('seq_run_id', 'seq_file_id'): con.execute(f'DROP SEQUENCE {sq}'); con.execute(f'CREATE SEQUENCE {sq}')   # start again from 1
    shutil.copytree(os.path.join(root, B), os.path.join(root, '2026-01-09'))                                        # new file -> new file_id
    r = go(cfg, con)
    assert r['status'] == 'ok' and r['run_id'] == runs + 1 and '2026-01-09' in r['folders_changed']
    assert q(con, 'SELECT min(file_id) FROM ingest_file WHERE folder = ?', '2026-01-09')[0][0] > fids
    assert q(con, 'SELECT count(*), count(DISTINCT file_id) FROM ingest_file')[0] == q(con, 'SELECT count(*), count(*) FROM ingest_file')[0]
    assert go(cfg, con)['run_id'] == runs + 2


def test_salinan_baca_untuk_dbgate(env):
    """Step 7: DbGate (docker compose) opens a COPY of DuckDB, not the server's file (K1). The copy holds the same data,
    is open read-only while the server keeps holding the original file, and is replaced whole on the next refresh."""
    cfg, con, root = env
    go(cfg, con)
    path = db.snapshot(con, cfg)
    assert path == db.snapshot_path(cfg) and not os.path.exists(path + '.tmp')
    ro = duckdb.connect(path, read_only=True)
    try: assert ingest.checksums(ro) == ingest.checksums(con)
    finally: ro.close()
    open(path + '.tmp', 'wb').write(b'sisa salinan yang terputus')   # a previously interrupted copy does not interfere
    open(path + '.wal', 'wb').write(b'wal penampil atas salinan lama')  # must not be rotated into the new copy
    shutil.copytree(os.path.join(root, B), os.path.join(root, '2026-01-09'))
    go(cfg, con); db.snapshot(con, cfg)
    ro = duckdb.connect(path, read_only=True)
    try: assert ro.execute("SELECT count(*) FROM folder_state WHERE folder = '2026-01-09'").fetchone() == (1,) and ingest.checksums(ro) == ingest.checksums(con)
    finally: ro.close()
    assert not os.path.exists(path + '.wal')
    assert con.execute('SELECT count(*) FROM duckdb_databases() WHERE NOT internal').fetchone() == (1,)   # copy already released


def test_berkas_nama_lama_dipindah(tmp_path):
    """data/simpel4.duckdb (old app name) is used as monishield.duckdb without re-ingesting."""
    old = tmp_path / 'simpel4.duckdb'
    con = duckdb.connect(str(old)); con.execute('CREATE TABLE penanda AS SELECT 42 AS x'); con.close()
    cfg = dataclasses.replace(config.Config(), data_dir=str(tmp_path))
    assert cfg.db_path.endswith('monishield.duckdb')
    con = db.open(cfg.db_path)
    try: assert con.execute('SELECT x FROM penanda').fetchone() == (42,) and not old.exists()
    finally: con.close()


def test_berkas_berisi_galat_ekspor_diberi_peringatan(env):
    """Real S3 data 2026-10-07: a log file containing one export-tool error line ('failed to get parse function…'). Marked
    corrupt as usual, plus a warning explaining the cause."""
    cfg, con, root = env
    d = os.path.join(root, '2026-01-09', 'ingress-nginx', 'nginx-ingress-controller'); os.makedirs(d)
    with open(os.path.join(d, 'log_nginx-ingress-controller_pod-n_2026-01-09-00-00.log'), 'w') as fh:
        fh.write('failed to get parse function: unsupported log format: "' + '\\x00' * 50 + '"')
    r = go(cfg, con)
    assert any("contains an error message from the log export tool" in w and 'nginx-ingress-controller' in w for w in r['warnings'])
    assert q(con, "SELECT status FROM ingest_file WHERE folder = '2026-01-09'") == [('corrupt',)]


def test_hanya_satu_ingest_pada_satu_waktu(env):
    cfg, con, _ = env
    assert ingest._lock.acquire(blocking=False)
    try:
        with pytest.raises(ingest.Busy): go(cfg, con)
    finally: ingest._lock.release()
    assert go(cfg, con)['status'] == 'ok'


def test_opsi_folder(env):
    cfg, con, _ = env
    r = go(cfg, con, folder=A)
    assert (r['files_seen'], r['folders_changed']) == (2, [A]) and q(con, 'SELECT DISTINCT folder::VARCHAR FROM ingest_file') == [(A,)]
    assert go(cfg, con)['folders_changed'] == [B]


def test_kotak_masuk_dan_folder_ganda(env):
    cfg, con, root = env
    C_ = '2026-01-03'
    logs_mini.write(logs_mini.log_path(cfg.inbox_dir, C_, 'kube-system', 'coredns', 'pod-i'), logs_mini.lines('coredns'))
    logs_mini.write(logs_mini.log_path(cfg.inbox_dir, A, None, 'om-fe-inhouse', 'pod-ganda'), logs_mini.lines('om-fe-inhouse'))
    r = go(cfg, con)
    assert r['files_seen'] == 10 and r['folders_changed'] == [A, B, C_] and any(f'folder {A} is in' in w for w in r['warnings'])
    assert q(con, "SELECT count(*) FROM ingest_file WHERE pod = 'pod-ganda'")[0][0] == 0 and q(con, "SELECT folder::VARCHAR FROM ingest_file WHERE pod = 'pod-i'") == [(C_,)]


def test_subproses_sama_dengan_dalam_proses(env, tmp_path):
    cfg, con, _ = env
    r = ingest.run(cfg, con, workers=2)  # ProcessPoolExecutor (spawn)
    cfg2 = dataclasses.replace(cfg, data_dir=str(tmp_path / 'inline')); con2 = db.open(cfg2.db_path); go(cfg2, con2)
    assert r['files_parsed'] == 9 and raw_sums(con) == raw_sums(con2)
    con2.close()
