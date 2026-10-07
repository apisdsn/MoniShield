-- agg_c401: klien dengan 401 berulang per (IP, endpoint); puncak = jumlah terbanyak dalam satu menit WIB.
DELETE FROM agg_c401 WHERE folder = $f;
INSERT INTO agg_c401
SELECT $f, ip, key, sum(n)::BIGINT, max(n), min(minute_wib), max(minute_wib)
FROM (SELECT ip, method || ' ' || path_key AS key, date_trunc('minute', ts_utc + INTERVAL 7 HOUR) AS minute_wib, count(*) AS n
      FROM nginx_access WHERE folder = $f AND status = 401 GROUP BY ALL)
GROUP BY ip, key;
