-- agg_service: satu baris per layanan yang punya file di folder ini (termasuk yang 0 baris), seperti D.days lama.
-- err/warn = penghitung parser per file (definisi lama + TRD §4.4 butir 3). err_http = respons/event 5xx; err_log = sisanya.
DELETE FROM agg_service WHERE folder = $f;
INSERT INTO agg_service
WITH f AS (
    SELECT service, sum(lines) AS lines, sum(err) AS err, sum(warn) AS warn, count(*) AS files,
           count(*) FILTER (WHERE lines = 0) AS files_empty, count(*) FILTER (WHERE status = 'corrupt') AS files_corrupt
    FROM ingest_file WHERE folder = $f GROUP BY service),
req AS (
    SELECT 'nginx-ingress-controller' AS service, status, ip, false AS failed FROM nginx_access WHERE folder = $f
    UNION ALL SELECT 'om-fe-inhouse', status, ip, false FROM fe_access WHERE folder = $f
    UNION ALL SELECT 'om-be-simpel-loop', status, ip, failed FROM sl_event WHERE folder = $f),
r AS (
    SELECT service, count(*) AS requests, count(*) FILTER (WHERE status BETWEEN 400 AND 499) AS n4xx,
           count(*) FILTER (WHERE status BETWEEN 500 AND 599) AS n5xx, count(DISTINCT ip) AS ip_unique,
           count(*) FILTER (WHERE status BETWEEN 500 AND 599 AND (failed OR service <> 'om-be-simpel-loop')) AS err_http
    FROM req GROUP BY service),
u AS (
    SELECT service, count(DISTINCT lower(split_part(login_account, '@', 1))) AS users_ok
    FROM spring_line WHERE folder = $f AND login_kind = 'ok' GROUP BY service)
SELECT $f, f.service, f.lines, f.err, f.warn, coalesce(r.err_http, 0), f.err - coalesce(r.err_http, 0),
       f.files, f.files_empty, f.files_corrupt,
       coalesce(r.requests, 0), coalesce(r.n4xx, 0), coalesce(r.n5xx, 0), coalesce(r.ip_unique, 0), coalesce(u.users_ok, 0)
FROM f LEFT JOIN r USING (service) LEFT JOIN u USING (service);
