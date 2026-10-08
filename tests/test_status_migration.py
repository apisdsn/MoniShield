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
