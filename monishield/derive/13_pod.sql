-- agg_pod: jumlah per PERCOBAAN ke tiap pod (termasuk yang gagal lalu dilempar), dan percobaan berstatus 5xx.
DELETE FROM agg_pod WHERE folder = $f;
INSERT INTO agg_pod
SELECT $f, upstream, addr, count(*), count(*) FILTER (WHERE st LIKE '5%')
FROM (SELECT upstream, unnest(up_addrs) AS addr, unnest(up_statuses) AS st FROM nginx_access WHERE folder = $f AND up_addrs IS NOT NULL)
WHERE addr <> '-' GROUP BY upstream, addr;
