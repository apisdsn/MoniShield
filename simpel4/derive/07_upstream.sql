DELETE FROM agg_upstream WHERE folder = $f;
INSERT INTO agg_upstream
SELECT $f, upstream, count(*), count(*) FILTER (WHERE status BETWEEN 500 AND 599)
FROM nginx_access WHERE folder = $f GROUP BY upstream;
