-- agg_ua: kunci = 90 karakter pertama User-Agent (pemotongan lama, sebelum mengelompokkan).
DELETE FROM agg_ua WHERE folder = $f;
INSERT INTO agg_ua
SELECT $f, left(ua, 90), count(*) FROM nginx_access WHERE folder = $f GROUP BY ALL;
