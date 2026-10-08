-- agg_pod: count per ATTEMPT to each pod (including those that failed and were passed on), and attempts with a 5xx status.
DELETE FROM agg_pod WHERE folder = $f;
INSERT INTO agg_pod
SELECT $f, upstream, addr, count(*), count(*) FILTER (WHERE st LIKE '5%')
FROM (SELECT upstream, unnest(up_addrs) AS addr, unnest(up_statuses) AS st FROM nginx_access WHERE folder = $f AND up_addrs IS NOT NULL)
WHERE addr <> '-' GROUP BY upstream, addr;
