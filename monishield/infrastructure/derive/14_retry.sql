-- agg_retry: pod pertama gagal lalu request dilempar ke pod lain.
DELETE FROM agg_retry WHERE folder = $f;
INSERT INTO agg_retry
SELECT $f, upstream, up_addrs[1], up_statuses[1], count(*)
FROM nginx_access WHERE folder = $f AND len(up_addrs) > 1 GROUP BY ALL;
