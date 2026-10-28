-- agg_retry: first pod failed and the request was passed on to another pod.
DELETE FROM agg_retry WHERE folder = $f;
INSERT INTO agg_retry
SELECT $f, upstream, up_addrs[1], up_statuses[1], count(*)
FROM nginx_access WHERE folder = $f AND len(up_addrs) > 1 GROUP BY ALL;
