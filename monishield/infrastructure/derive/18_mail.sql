-- agg_mail: email notifikasi simpel-loop per jenis (dari penghitung per file).
DELETE FROM agg_mail WHERE folder = $f;
INSERT INTO agg_mail
SELECT $f, c.key, sum(c.n)::BIGINT FROM file_counter c JOIN ingest_file f USING (file_id)
WHERE f.folder = $f AND c.kind = 'mail' GROUP BY c.key;
