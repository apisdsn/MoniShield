-- agg_endpoint (paths, pe, dur, ep lama). Durasi dalam detik. nginx: status 101 (websocket) tidak masuk durasi.
-- frontend tidak punya durasi. coredns: key = domain yang gagal resolve.
DELETE FROM agg_endpoint WHERE folder = $f;
INSERT INTO agg_endpoint
WITH e AS (
    SELECT 'nginx-ingress-controller' AS service, method || ' ' || path_key AS key, status,
           CASE WHEN status <> 101 THEN request_time END AS d FROM nginx_access WHERE folder = $f
    UNION ALL SELECT 'om-fe-inhouse', method || ' ' || path_key, status, NULL FROM fe_access WHERE folder = $f
    UNION ALL SELECT 'om-be-simpel-loop', method || ' ' || path_key, status, duration_ms / 1000 FROM sl_event WHERE folder = $f
    UNION ALL SELECT 'coredns', domain, 0, NULL FROM coredns_error WHERE folder = $f),
g AS (
    SELECT service, key, count(*) AS requests,
           count(*) FILTER (WHERE status BETWEEN 400 AND 499) AS n4xx, count(*) FILTER (WHERE status BETWEEN 500 AND 599) AS n5xx,
           count(d) AS dur_n, max(d) AS dur_max, list_sort(list(d) FILTER (WHERE d IS NOT NULL)) AS v
    FROM e GROUP BY service, key)
-- rata-rata dihitung dari daftar TERURUT agar hasilnya sama tiap kali (avg() paralel atas DOUBLE bisa beda di digit terakhir)
SELECT $f, service, key, requests, n4xx, n5xx, dur_n, list_sum(v) / nullif(dur_n, 0), dur_max,
       v[least(dur_n, CAST(floor(0.5::DOUBLE * dur_n) AS BIGINT) + 1)],
       v[least(dur_n, CAST(floor(0.95::DOUBLE * dur_n) AS BIGINT) + 1)],
       v[least(dur_n, CAST(floor(0.99::DOUBLE * dur_n) AS BIGINT) + 1)]
FROM g;
