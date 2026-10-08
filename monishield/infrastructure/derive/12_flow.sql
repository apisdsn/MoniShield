-- agg_flow: (source IP, upstream) -> pod that answered. Not truncated; "top 3 pods" is applied at query time.
DELETE FROM agg_flow WHERE folder = $f;
INSERT INTO agg_flow
SELECT $f, ip, upstream, pod_final, count(*) FROM nginx_access WHERE folder = $f GROUP BY ALL;
