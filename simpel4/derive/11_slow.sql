-- agg_slow: event simpel-loop >= 1.000 ms, urut seperti sorted(..., reverse=True) lama: durasi, kunci, status menurun.
DELETE FROM agg_slow WHERE folder = $f;
INSERT INTO agg_slow
SELECT $f, row_number() OVER (ORDER BY duration_ms DESC, key DESC, status::VARCHAR DESC), duration_ms, key, status
FROM (SELECT duration_ms, method || ' ' || path_key AS key, status FROM sl_event WHERE folder = $f AND duration_ms >= 1000);
