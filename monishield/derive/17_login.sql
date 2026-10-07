-- Login (inv. §4.2). Hanya om-be-appsmanager: di sistem lama statistik login per layanan dan tampilan membaca
-- milik appsmanager saja. accounts = akun yang dicoba, hanya dari password salah / reset (bukan dari login sukses).
DELETE FROM agg_login_ip WHERE folder = $f;
INSERT INTO agg_login_ip
SELECT $f, login_ip, count(*) FILTER (WHERE login_kind = 'fail'), count(*) FILTER (WHERE login_kind = 'lock'), count(*) FILTER (WHERE login_kind = 'ok'),
       coalesce(list_sort(list(DISTINCT login_account) FILTER (WHERE login_kind IN ('fail', 'lock'))), []),
       min(date_trunc('minute', ts_utc + INTERVAL 7 HOUR)), max(date_trunc('minute', ts_utc + INTERVAL 7 HOUR))
FROM spring_line WHERE folder = $f AND service = 'om-be-appsmanager' AND login_kind IS NOT NULL GROUP BY login_ip;
DELETE FROM agg_login_hour WHERE folder = $f;
INSERT INTO agg_login_hour
SELECT $f, date_trunc('hour', ts_utc + INTERVAL 7 HOUR), count(*) FILTER (WHERE login_kind = 'fail'), count(*) FILTER (WHERE login_kind = 'ok')
FROM spring_line WHERE folder = $f AND service = 'om-be-appsmanager' AND login_kind IN ('fail', 'ok') GROUP BY ALL;
