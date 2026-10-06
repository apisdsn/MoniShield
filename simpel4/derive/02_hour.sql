-- agg_hour (hour/herr lama). simpel-loop diisi dari korelasi (Tahap 6): lognya tidak bercap waktu.
-- TRD §4.4 butir 2: err nginx/frontend = 5xx + baris error log ber-level error, sehingga jumlah per jam = KPI Error.
DELETE FROM agg_hour WHERE folder = $f AND service <> 'om-be-simpel-loop';
INSERT INTO agg_hour
SELECT $f, service, date_trunc('hour', ts_utc + INTERVAL 7 HOUR) AS hour_wib, sum(total), sum(err)
FROM (
    SELECT 'nginx-ingress-controller' AS service, ts_utc, 1 AS total, (status BETWEEN 500 AND 599)::INT AS err FROM nginx_access WHERE folder = $f
    UNION ALL SELECT 'om-fe-inhouse', ts_utc, 1, (status BETWEEN 500 AND 599)::INT FROM fe_access WHERE folder = $f
    UNION ALL SELECT service, ts_utc, 0, 1 FROM nginx_error WHERE folder = $f AND level IN ('error', 'crit', 'alert', 'emerg')
    UNION ALL SELECT service, ts_utc, 1, (level = 'ERROR')::INT FROM spring_line WHERE folder = $f)
GROUP BY service, hour_wib;
