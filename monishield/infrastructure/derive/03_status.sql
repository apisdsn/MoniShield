DELETE FROM agg_status WHERE folder = $f;
INSERT INTO agg_status
SELECT $f, service, status, count(*)
FROM (SELECT 'nginx-ingress-controller' AS service, status FROM nginx_access WHERE folder = $f
      UNION ALL SELECT $fe, status FROM fe_access WHERE folder = $f
      UNION ALL SELECT $sl, status FROM sl_event WHERE folder = $f
      UNION ALL SELECT service, status FROM http_access WHERE folder = $f AND status IS NOT NULL
      UNION ALL SELECT service, status FROM app_line WHERE folder = $f AND status IS NOT NULL)
GROUP BY service, status;
