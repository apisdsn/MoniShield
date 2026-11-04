-- agg_flow: (source IP, upstream) -> pod that answered. Not truncated; "top 3 pods" is applied at query time.
DELETE FROM agg_flow WHERE folder = $f;
INSERT INTO agg_flow
SELECT $f, ip, upstream, pod_final, count(*)
FROM (SELECT ip, upstream, pod_final FROM nginx_access WHERE folder = $f
      -- common formats: the module is the upstream, or the service itself; no pod is known
      UNION ALL SELECT ip, coalesce(upstream, service), '-' FROM http_access WHERE folder = $f)
GROUP BY ALL;
