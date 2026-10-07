-- agg_flow: (IP asal, upstream) -> pod yang menjawab. Tidak dipotong; "3 pod teratas" diterapkan saat query.
DELETE FROM agg_flow WHERE folder = $f;
INSERT INTO agg_flow
SELECT $f, ip, upstream, pod_final, count(*) FROM nginx_access WHERE folder = $f GROUP BY ALL;
