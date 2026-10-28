"""Status values stored before 2026-10-08 were Indonesian; they are rewritten to English once when the databases open."""
import datetime

from monishield.infrastructure import auth, db


def test_duckdb_status_values_rewritten(tmp_path):
    path = str(tmp_path / 'm.duckdb')
    con = db.open(path)
    con.execute("INSERT INTO ingest_run VALUES (1, now(), now(), 'gagal', 0, 0, NULL), (2, now(), NULL, 'berjalan', NULL, NULL, NULL), (3, now(), now(), 'ok', 1, 1, NULL)")
    for i, st in enumerate(('kosong', 'rusak', 'gagal', 'ok')):
        con.execute("INSERT INTO ingest_file VALUES (?, ?, '.log', ?, 'ns', 'svc', 'pod', 0, 0, '', 0, 0, 0, 0, ?, 1, now())",
                    [i, f'f{i}', datetime.date(2026, 1, 1), st])
    con.close()
    con = db.open(path)
    assert [r[0] for r in con.execute('SELECT status FROM ingest_run ORDER BY run_id').fetchall()] == ['failed', 'running', 'ok']
    assert [r[0] for r in con.execute('SELECT status FROM ingest_file ORDER BY file_id').fetchall()] == ['empty', 'corrupt', 'failed', 'ok']
    con.close()


def test_import_job_status_rewritten(auth_url):
    a = auth.Auth(auth_url, 'x' * 40)
    ids = [a.job_create('admin', 'b', 'p/', '2026-01-01', st) for st in ('berjalan', 'selesai', 'gagal', 'coba')]
    a.close()
    a = auth.Auth(auth_url, 'x' * 40)
    assert [a.job_get(i)['status'] for i in ids] == ['running', 'done', 'failed', 'dry_run']
    a.close()


def test_business_metric_keys_rewritten(tmp_path):
    """Business metric keys stored before 2026-10-28 were Indonesian (agg_biz, file_counter kind 'biz')."""
    path = str(tmp_path / 'm.duckdb')
    con = db.open(path)
    con.execute("INSERT INTO agg_biz VALUES ('2026-01-01', 'Laporan Dibuat', 3), ('2026-01-01', 'OTP Gagal', 1), ('2026-01-02', 'reports_created', 2)")
    con.execute("INSERT INTO file_counter VALUES (1, 'biz', 'Email Terkirim', 4), (1, 'mail', 'Email Terkirim', 1), (1, 'level', 'ERROR', 2)")
    con.close()
    con = db.open(path)
    assert con.execute('SELECT folder::VARCHAR, metric, n FROM agg_biz ORDER BY 1, 2').fetchall() == [
        ('2026-01-01', 'otp_failed', 1), ('2026-01-01', 'reports_created', 3), ('2026-01-02', 'reports_created', 2)]
    assert con.execute('SELECT kind, key, n FROM file_counter ORDER BY 1, 2').fetchall() == [
        ('biz', 'emails_sent', 4), ('level', 'ERROR', 2), ('mail', 'Email Terkirim', 1)]   # only the business counters
    con.close()
