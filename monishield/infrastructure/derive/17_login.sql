-- Login (inv. §4.2). Only the auth service: in the old system login stats were per service and the view read
-- auth service's only. accounts = accounts attempted, only from wrong password / reset (not from successful logins).
DELETE FROM agg_login_ip WHERE folder = $f;
INSERT INTO agg_login_ip
SELECT $f, login_ip, count(*) FILTER (WHERE login_kind = 'fail'), count(*) FILTER (WHERE login_kind = 'lock'), count(*) FILTER (WHERE login_kind = 'ok'),
       coalesce(list_sort(list(DISTINCT login_account) FILTER (WHERE login_kind IN ('fail', 'lock'))), []),
       min(date_trunc('minute', ts_utc + to_minutes($tz))), max(date_trunc('minute', ts_utc + to_minutes($tz)))
FROM spring_line WHERE folder = $f AND service = $am AND login_kind IS NOT NULL GROUP BY login_ip;
DELETE FROM agg_login_hour WHERE folder = $f;
INSERT INTO agg_login_hour
SELECT $f, date_trunc('hour', ts_utc + to_minutes($tz)), count(*) FILTER (WHERE login_kind = 'fail'), count(*) FILTER (WHERE login_kind = 'ok')
FROM spring_line WHERE folder = $f AND service = $am AND login_kind IN ('fail', 'ok') GROUP BY ALL;
