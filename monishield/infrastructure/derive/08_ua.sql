-- agg_ua: key = first 90 characters of the User-Agent (the old truncation, before grouping).
DELETE FROM agg_ua WHERE folder = $f;
INSERT INTO agg_ua
SELECT $f, left(ua, 90), count(*) FROM nginx_access WHERE folder = $f GROUP BY ALL;
