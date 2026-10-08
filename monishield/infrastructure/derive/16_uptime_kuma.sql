-- Uptime-Kuma: checks per hour (failed = status not 2xx/3xx) and target 'METHOD path → upstream' (raw path).
DELETE FROM agg_uk_hour WHERE folder = $f;
INSERT INTO agg_uk_hour
SELECT $f, date_trunc('hour', ts_utc + INTERVAL 7 HOUR), count(*), count(*) FILTER (WHERE status NOT BETWEEN 200 AND 399)
FROM nginx_access WHERE folder = $f AND is_uptime_kuma GROUP BY ALL;
DELETE FROM agg_uk_target WHERE folder = $f;
INSERT INTO agg_uk_target
SELECT $f, method || ' ' || path || ' → ' || upstream, count(*)
FROM nginx_access WHERE folder = $f AND is_uptime_kuma GROUP BY ALL;
