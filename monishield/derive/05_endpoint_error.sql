-- agg_endpoint_error (perr lama). nginx: semua 4xx/5xx, kunci 'METODE path_key'. frontend: semua 4xx/5xx, kunci
-- path_key TANPA metode (begitu di sistem lama). simpel-loop: hanya event gagal, status apa pun.
DELETE FROM agg_endpoint_error WHERE folder = $f;
INSERT INTO agg_endpoint_error
SELECT $f, service, status, key, count(*)
FROM (SELECT 'nginx-ingress-controller' AS service, status, method || ' ' || path_key AS key FROM nginx_access WHERE folder = $f AND status BETWEEN 400 AND 599
      UNION ALL SELECT 'om-fe-inhouse', status, path_key FROM fe_access WHERE folder = $f AND status BETWEEN 400 AND 599
      UNION ALL SELECT 'om-be-simpel-loop', status, method || ' ' || path_key FROM sl_event WHERE folder = $f AND failed)
GROUP BY service, status, key;
