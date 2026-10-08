-- agg_endpoint_error (old perr). nginx: all 4xx/5xx, key 'METHOD path_key'. frontend: all 4xx/5xx, key
-- path_key WITHOUT method (as in the old system). simpel-loop: only failed events, any status.
DELETE FROM agg_endpoint_error WHERE folder = $f;
INSERT INTO agg_endpoint_error
SELECT $f, service, status, key, count(*)
FROM (SELECT 'nginx-ingress-controller' AS service, status, method || ' ' || path_key AS key FROM nginx_access WHERE folder = $f AND status BETWEEN 400 AND 599
      UNION ALL SELECT 'om-fe-inhouse', status, path_key FROM fe_access WHERE folder = $f AND status BETWEEN 400 AND 599
      UNION ALL SELECT 'om-be-simpel-loop', status, method || ' ' || path_key FROM sl_event WHERE folder = $f AND failed)
GROUP BY service, status, key;
