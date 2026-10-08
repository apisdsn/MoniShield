-- agg_ip (old ips, ip4, ip4ua). ua_first_4xx = UA (100 chars) of that IP's FIRST 4xx response, ingress only.
-- simpel-loop: only events that have an ipAddress.
DELETE FROM agg_ip WHERE folder = $f;
INSERT INTO agg_ip
SELECT $f, service, ip, count(*), count(*) FILTER (WHERE status BETWEEN 400 AND 499),
       arg_min(left(ua, 100), ord) FILTER (WHERE ua IS NOT NULL AND status BETWEEN 400 AND 499)
FROM (SELECT 'nginx-ingress-controller' AS service, a.ip, a.status, a.ua, (f.relpath, a.line_no) AS ord
      FROM nginx_access a JOIN ingest_file f USING (file_id) WHERE a.folder = $f
      UNION ALL SELECT 'om-fe-inhouse', ip, status, NULL, NULL FROM fe_access WHERE folder = $f
      UNION ALL SELECT 'om-be-simpel-loop', ip, status, NULL, NULL FROM sl_event WHERE folder = $f AND ip IS NOT NULL)
GROUP BY service, ip;
