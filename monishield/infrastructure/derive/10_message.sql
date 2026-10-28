-- agg_message (old msgs + samples). Sample = first original line in read order (relpath, line_no).
DELETE FROM agg_message WHERE folder = $f;
INSERT INTO agg_message
SELECT $f, m.service, m.msg_key, any_value(m.level), count(*),
       arg_min(m.raw, (f.relpath, m.line_no)) FILTER (WHERE m.raw IS NOT NULL)
FROM log_message m JOIN ingest_file f USING (file_id) WHERE m.folder = $f
GROUP BY m.service, m.msg_key;
