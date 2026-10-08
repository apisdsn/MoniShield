-- agg_slow: simpel-loop events >= 1,000 ms, ordered like the old sorted(..., reverse=True): duration, key, status descending.
DELETE FROM agg_slow WHERE folder = $f;
INSERT INTO agg_slow
SELECT $f, row_number() OVER (ORDER BY duration_ms DESC, key DESC, status::VARCHAR DESC), duration_ms, key, status
FROM (SELECT duration_ms, method || ' ' || path_key AS key, status FROM sl_event WHERE folder = $f AND duration_ms >= 1000);
