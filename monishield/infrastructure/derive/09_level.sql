-- agg_level (old extra) from per-file counters.
-- TRD §4.4 item 4: simpel-loop uses the EFFECTIVE level: failed 5xx event -> ERROR, other failed events -> WARN
-- (same as the Error/Warning KPI rule); other lines use their original tag.
DELETE FROM agg_level WHERE folder = $f;
INSERT INTO agg_level
SELECT $f, service, level, sum(n)::BIGINT AS n
FROM (
    SELECT f.service, c.key AS level, c.n FROM file_counter c JOIN ingest_file f USING (file_id) WHERE f.folder = $f AND c.kind = 'level'
    UNION ALL SELECT 'om-be-simpel-loop', level, -count(*) FROM sl_event WHERE folder = $f AND failed GROUP BY level
    UNION ALL SELECT 'om-be-simpel-loop', CASE WHEN status BETWEEN 500 AND 599 THEN 'ERROR' ELSE 'WARN' END, count(*) FROM sl_event WHERE folder = $f AND failed GROUP BY ALL)
GROUP BY service, level HAVING sum(n) > 0;
