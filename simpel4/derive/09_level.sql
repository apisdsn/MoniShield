-- agg_level (extra lama) dari penghitung per file.
-- TRD §4.4 butir 4: simpel-loop memakai tingkat EFEKTIF: event gagal 5xx -> ERROR, event gagal lainnya -> WARN
-- (sama dengan aturan KPI Error/Warning); baris lain memakai tag aslinya.
DELETE FROM agg_level WHERE folder = $f;
INSERT INTO agg_level
SELECT $f, service, level, sum(n)::BIGINT AS n
FROM (
    SELECT f.service, c.key AS level, c.n FROM file_counter c JOIN ingest_file f USING (file_id) WHERE f.folder = $f AND c.kind = 'level'
    UNION ALL SELECT 'om-be-simpel-loop', level, -count(*) FROM sl_event WHERE folder = $f AND failed GROUP BY level
    UNION ALL SELECT 'om-be-simpel-loop', CASE WHEN status BETWEEN 500 AND 599 THEN 'ERROR' ELSE 'WARN' END, count(*) FROM sl_event WHERE folder = $f AND failed GROUP BY ALL)
GROUP BY service, level HAVING sum(n) > 0;
