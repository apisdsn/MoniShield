DELETE FROM agg_status WHERE folder = $f;
INSERT INTO agg_status
SELECT $f, service, status, count(*)
FROM (SELECT 'nginx-ingress-controller' AS service, status FROM nginx_access WHERE folder = $f
      UNION ALL SELECT 'om-fe-inhouse', status FROM fe_access WHERE folder = $f
      UNION ALL SELECT 'om-be-simpel-loop', status FROM sl_event WHERE folder = $f)
GROUP BY service, status;
