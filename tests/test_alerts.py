"""Telegram / Discord / email notifications (owner request 2026-10-07). No network: the HTTP and SMTP senders are faked."""
import dataclasses, datetime, http.server, json, os, re, shutil, smtplib, threading, time

import pytest
from fastapi.testclient import TestClient

import logs_mini
from monishield.application import alert_service
from monishield.domain import accounts, alerts
from monishield.infrastructure import config, db, ingest, notify_channels
from monishield.interfaces.api import app as appmod
from conftest import JWT_SECRET

X = {'X-Requested-With': 'uji'}
PW, PW2 = 'sandi-admin-pertama', 'sandi-admin-sesudah-diganti'
TOKEN = '123456789:AAHrahasiaTokenBotTelegramUji0000000'
HOOK = 'https://discord.com/api/webhooks/1234567890/rahasiaWebhookDiscordUji0000'
SMTP_PW = 'sandiSmtpRahasiaUji'
B = '2026-01-02'


@pytest.fixture
def sent(monkeypatch):
    """Capture every HTTP (Telegram/Discord) and SMTP send."""
    box = []
    monkeypatch.setattr(notify_channels, '_post_json', lambda url, payload: box.append(('http', url, payload)) or 200)

    class FakeSMTP:
        def __init__(self, host, port, timeout=None, **kw): box.append(('smtp-open', host, port))
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def starttls(self, context=None): box.append(('smtp-starttls',))
        def login(self, u, p): box.append(('smtp-login', u, p == SMTP_PW))
        def send_message(self, m): box.append(('smtp-send', m['Subject'], m['To'], m.get_body(('plain',)).get_content()))
    monkeypatch.setattr(smtplib, 'SMTP', FakeSMTP)
    return box


@pytest.fixture
def app_env(tmp_path, auth_url, monkeypatch):
    """Folder B + four copies of it (average available) + 2026-01-07 = B with errors multiplied later."""
    monkeypatch.setattr(accounts, 'SCRYPT', (10, 8, 1))
    root = logs_mini.build(tmp_path / 'logs')
    for d in ('2026-01-03', '2026-01-04', '2026-01-05', '2026-01-06'): shutil.copytree(os.path.join(root, B), os.path.join(root, d))
    c = dataclasses.replace(config.Config(), log_dir=root, data_dir=str(tmp_path / 'data'), state_dir=str(tmp_path / 'state'), inbox_dir=str(tmp_path / 'inbox'),
                            cache_dir=str(tmp_path / 'cache'), offline=True, ingest_on_start=False, cookie_secure=False, admin_user='admin', admin_password=PW,
                            jwt_secret=JWT_SECRET, auth_database_url=auth_url)
    con = db.open(c.db_path); ingest.run(c, con, workers=0); con.close()
    with TestClient(appmod.create_app(c)) as tc:
        assert tc.post('/api/auth/login', json=dict(username='admin', password=PW), headers=X).status_code == 200
        assert tc.post('/api/me/password', json=dict(old_password=PW, new_password=PW2), headers=X).status_code == 200
        yield tc, c, root


def configure(tc, **over):
    body = dict(channels=dict(telegram=dict(enabled=True, bot_token=TOKEN, chat_id='-1001234567890'),
                              discord=dict(enabled=True, webhook_url=HOOK),
                              email=dict(enabled=True, host='smtp.example.com', port=587, security='starttls', username='monishield',
                                         password=SMTP_PW, sender='monishield@example.com', to='tim@example.com, ketua@example.com')),
                dashboard_url='https://monishield.example.com', **over)
    r = tc.put('/api/admin/alerts', json=body, headers=X)
    assert r.status_code == 200, r.text
    return r


def test_credentials_are_never_sent_back(app_env):
    tc, c, _ = app_env
    r = configure(tc)
    for s in (TOKEN, HOOK, SMTP_PW): assert s not in r.text and s not in tc.get('/api/admin/alerts').text
    ch = r.json()['channels']
    assert (ch['telegram']['bot_token'], ch['discord']['webhook_url'], ch['email']['password']) == (True, True, True)
    assert ch['telegram']['chat_id'] == '-1001234567890' and ch['email']['to'].startswith('tim@')
    # stored in the .env file (not the database), takes effect immediately in the server config
    env = config.read_dotenv(os.path.join(c.state_dir, '.env'))
    assert (env['TELEGRAM_BOT_TOKEN'], env['S4_ALERT_TELEGRAM'], env['S4_ALERT_TELEGRAM_CHAT_ID'], env['DISCORD_WEBHOOK_URL'], env['SMTP_PASSWORD']) == \
        (TOKEN, 'true', '-1001234567890', HOOK, SMTP_PW)
    assert env['S4_SMTP_TO'] == 'tim@example.com, ketua@example.com' and env['S4_DASHBOARD_URL'] == 'https://monishield.example.com'
    assert tc.app.state.cfg.telegram_bot_token == TOKEN and tc.app.state.auth.setting_get('alerts') is None
    # save again without credentials: they stay stored; `clear` removes them
    r = tc.put('/api/admin/alerts', json=dict(channels=dict(telegram=dict(bot_token='', enabled=True))), headers=X)
    assert r.json()['channels']['telegram']['bot_token'] is True
    r = tc.put('/api/admin/alerts', json=dict(channels=dict(discord=dict(enabled=False)), clear=['discord.webhook_url']), headers=X)
    assert r.json()['channels']['discord']['webhook_url'] is False
    assert config.read_dotenv(os.path.join(c.state_dir, '.env'))['DISCORD_WEBHOOK_URL'] == ''
    audit = tc.get('/api/admin/audit').text
    assert 'alerts.update' in audit and TOKEN not in audit and SMTP_PW not in audit


@pytest.mark.parametrize('ch, msg', [(dict(telegram=dict(bot_token='bukan-token')), 'bot token'), (dict(telegram=dict(chat_id='abc')), 'chat ID'),
                                    (dict(discord=dict(webhook_url='https://evil.example/api/webhooks/1/x')), 'Discord webhook URL'),
                                    (dict(discord=dict(webhook_url='http://discord.com/api/webhooks/1/x')), 'Discord webhook URL'),
                                    (dict(email=dict(to='bukan email')), 'recipients'), (dict(email=dict(enabled=True)), 'incomplete'),
                                    (dict(telegram=dict(enabled=True)), 'not set')])
def test_fields_are_validated(app_env, ch, msg):
    tc, _, _ = app_env
    r = tc.put('/api/admin/alerts', json=dict(channels=ch), headers=X)
    assert r.status_code == 400 and r.json()['error']['code'] == 'invalid_alerts' and msg in r.json()['error']['message']


def test_send_a_test_on_every_channel(app_env, sent):
    tc, _, _ = app_env
    configure(tc)
    for ch in ('telegram', 'discord', 'email'):
        r = tc.post('/api/admin/alerts/test', json=dict(channel=ch), headers=X)
        assert r.status_code == 200, r.text
    http = [x for x in sent if x[0] == 'http']
    assert http[0][1] == f'{alerts.TELEGRAM_API}/bot{TOKEN}/sendMessage' and http[0][2]['chat_id'] == '-1001234567890' and 'MoniShield' in http[0][2]['text']
    assert http[1][1] == HOOK and http[1][2]['allowed_mentions'] == {'parse': []}
    assert ('smtp-open', 'smtp.example.com', 587) in sent and ('smtp-starttls',) in sent and ('smtp-login', 'monishield', True) in sent
    assert [x for x in sent if x[0] == 'smtp-send'][0][2] == 'tim@example.com, ketua@example.com'
    hist = tc.get('/api/admin/alerts').json()['history']
    assert [h['channel'] for h in hist[:3]] == ['email', 'discord', 'telegram'] and all(h['ok'] for h in hist[:3])


def test_send_failure_is_reported_without_credentials(app_env, monkeypatch):
    tc, _, _ = app_env
    configure(tc)
    def refuse(url, payload): raise alerts.AlertFail('ditolak HTTP 401')
    monkeypatch.setattr(notify_channels, '_post_json', refuse)
    r = tc.post('/api/admin/alerts/test', json=dict(channel='telegram'), headers=X)
    assert r.status_code == 424 and 'HTTP 401' in r.json()['error']['message'] and TOKEN not in r.text
    assert tc.get('/api/admin/alerts').json()['history'][0]['ok'] is False


def test_spikes_and_critical_attacks_without_ip_addresses(app_env, sent):
    tc, c, root = app_env
    configure(tc)
    con = tc.app.state.con.cursor()
    try:
        con.execute("UPDATE agg_service SET err = err + 500 WHERE folder = '2026-01-06'")   # error spike vs the 01-02..01-05 average
        cfg = alerts.load(tc.app.state.cfg)
        ev = {e[0]: e for e in alerts.folder_events(cfg, '2026-01-06', tc.app.state.warehouse.folder_facts('2026-01-06', True))}
    finally: con.close()
    assert set(ev) == {'spike', 'critical'}
    _, key, title, text = ev['spike']
    assert key == 'spike:2026-01-06' and 'Error (semua layanan)' in text and 'rata-rata 4 hari' in text and '/command-center?folder=2026-01-06' in text
    _, key, title, text = ev['critical']
    assert 'IP' in text and '33.33.33.199' not in text and '/security?folder=2026-01-06' in text
    # send: all enabled channels, once per key
    cfg = alerts.load(tc.app.state.cfg)
    r = alert_service.deliver(tc.app.state, cfg, ev['spike'][1], 'spike', ev['spike'][2], ev['spike'][3])
    assert r == dict(telegram=None, discord=None, email=None)
    assert alert_service.deliver(tc.app.state, cfg, ev['spike'][1], 'spike', 'x', 'y') == {}
    for x in sent: assert '33.33.33.199' not in json.dumps(x)
    # English
    tc.put('/api/admin/alerts', json=dict(lang='en'), headers=X)
    con = tc.app.state.con.cursor()
    try: ev = {e[0]: e for e in alerts.folder_events(alerts.load(tc.app.state.cfg), '2026-01-06', tc.app.state.warehouse.folder_facts('2026-01-06', True))}
    finally: con.close()
    assert ev['spike'][2] == 'Spike in the logs of 2026-01-05' and 'Errors (all services)' in ev['spike'][3]


def test_sent_after_ingest_and_failed_sync(app_env, sent):
    tc, c, root = app_env
    configure(tc, events=dict(summary=True), summary_hour=0)   # report hour 00:00 WIB: the new folder's report goes out right after ingest
    shutil.copytree(os.path.join(root, B), os.path.join(root, '2026-01-07'))
    assert tc.post('/api/admin/ingest', json={}, headers=X).status_code == 202
    tc.app.state.ingest.wait(60)
    for _ in range(100):
        if any('2026-01-07' in json.dumps(x) for x in sent): break
        time.sleep(0.05)
    time.sleep(0.3)
    titles = [re.sub(r'</?b>', '', x[2]['text'].split('\n')[0]) for x in sent if x[0] == 'http' and 'sendMessage' in x[1]]
    assert 'Serangan kritis di log 2026-01-06 (S3)' in titles and 'Ringkasan log 2026-01-06 (S3)' in titles
    report = next(x[2] for x in sent if x[0] == 'http' and 'sendMessage' in x[1] and 'Ringkasan log 2026-01-06' in x[2]['text'])
    assert report['parse_mode'] == 'HTML' and 'Status: <b>' in report['text'] and '<b>📥 Hasil ingest</b>' in report['text']
    assert '<b>📊 Ringkasan</b>' in report['text'] or 'Status: <b>AMAN' in report['text']
    n = len(sent)
    tc.app.state.alerts._after_sync(dict(at='2026-10-07 01:00:00', errors=[dict(code='s3_denied', where='s3://b/k8s-logs/', message='S3 menolak akses')], failed=['2026-01-08']))
    assert any('Sinkron S3 bermasalah' in json.dumps(x) and 'Log tanggal: 2026-01-07' in json.dumps(x) for x in sent[n:])


def test_todays_folder_has_not_arrived(app_env, sent):
    tc, _, _ = app_env
    configure(tc)
    n = tc.app.state.alerts
    morning = datetime.datetime(2026, 10, 7, 1, 0, tzinfo=datetime.timezone.utc)      # 08:00 WIB: not yet time
    assert n.check_missing(morning) is None
    midday = datetime.datetime(2026, 10, 7, 4, 0, tzinfo=datetime.timezone.utc)     # 11:00 WIB
    assert n.check_missing(midday) == dict(telegram=None, discord=None, email=None)
    assert any('Log tanggal 2026-10-06 belum datang' in json.dumps(x) for x in sent)
    assert n.check_missing(midday) == {}                                            # once per day


def test_no_active_channel_sends_nothing(app_env, sent):
    tc, _, _ = app_env
    assert tc.app.state.alerts.check_missing(datetime.datetime(2026, 10, 7, 4, 0, tzinfo=datetime.timezone.utc)) is None and sent == []


def test_real_json_post_to_a_local_server(monkeypatch):
    got = []

    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a): pass
        def do_POST(self):
            got.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
            self.send_response(401 if 'tolak' in self.path else 200); self.end_headers()
    srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f'http://127.0.0.1:{srv.server_address[1]}'
    try:
        monkeypatch.setenv('NO_PROXY', '127.0.0.1')
        assert notify_channels._post_json(base + '/ok', dict(a=1)) == 200 and got == [dict(a=1)]
        with pytest.raises(alerts.AlertFail, match='HTTP 401'): notify_channels._post_json(base + '/tolak', {})
    finally: srv.shutdown(); srv.server_close()


def test_plain_user_not_allowed(app_env):
    tc, _, _ = app_env
    assert tc.post('/api/admin/users', json=dict(username='rina', display_name='Rina', role='user', password='sandi-awal-rina-123'), headers=X).status_code == 201
    u = TestClient(tc.app)
    u.post('/api/auth/login', json=dict(username='rina', password='sandi-awal-rina-123'), headers=X)
    u.post('/api/me/password', json=dict(old_password='sandi-awal-rina-123', new_password='sandi-baru-rina-123'), headers=X)
    assert u.get('/api/admin/alerts').status_code == 403 and u.post('/api/admin/alerts/test', json=dict(channel='email'), headers=X).status_code == 403


# ------------------------------------------------------------------ thresholds per number and per service (owner request 2026-10-08)
def _facts(svc, svc_avg, errors=100, errors_avg=100):
    kpi = dict(requests=1000, n5xx=0, errors=errors, upstream_errors=0, attack_ips=0, login_fail_ips=0)
    base = dict(requests=1000, n5xx=0, errors=errors_avg, upstream_errors=0, attack_ips=0, login_fail_ips=0)
    return dict(kpi=dict(kpi=kpi, atk_req=0, crit_req=0, svc={s: (e, 1000) for s, e in svc.items()}),
                base=dict(kpi=base, atk_req=0, n_nginx=7, n_all=7, svc=svc_avg), ngx_keys={'requests', 'n5xx'}, crit_cats=[])


def test_threshold_text_round_trip_and_errors():
    assert alerts.parse_spike('') == alerts.SPIKE
    s = alerts.parse_spike('n5xx=3:50, errors=off, attack_ips=1.5:2')
    assert (s['n5xx'], s['errors'], s['attack_ips'], s['upstream_errors']) == ((3, 50), None, (1.5, 2), (2, 20))
    assert alerts.format_spike(s) == 'n5xx=3:50,errors=off,attack_ips=1.5:2'
    d = alerts.parse_service_spike('default=2:50,REPORT-SERVICE=3:200,coredns=off')
    assert d == dict(default=(2, 50), services={'report-service': (3, 200), 'coredns': None})
    assert alerts.format_service_spike(d) == 'default=2:50,coredns=off,report-service=3:200'
    assert alerts.service_threshold(d, 'Report-Service') == (3, 200) and alerts.service_threshold(d, 'lain') == (2, 50)
    for bad in ('n5xx=1:5', 'n5xx=abc', 'tidak_ada=2:5', 'n5xx'):
        with pytest.raises(alerts.AlertFail): alerts.parse_spike(bad)
    with pytest.raises(alerts.AlertFail): alerts.parse_service_spike('../x=2:5')


def test_service_spikes_use_their_own_thresholds():
    cfg = alerts.load(dataclasses.replace(config.Config(), alert_service_spike='default=2:50,report-service=3:200,coredns=off', alert_spike='errors=off'))
    f = _facts(svc=dict(events=120, coredns=900, **{'report-service': 300}), svc_avg=dict(events=50, coredns=10, **{'report-service': 120}), errors=1320, errors_avg=180)
    ev = {e[0]: e for e in alerts.folder_events(cfg, '2026-01-06', f)}
    text = ev['spike'][3]
    assert 'events: 120' in text and 'coredns' not in text and 'report-service' not in text   # muted / below its own threshold
    assert 'Errors (all services)' not in text and 'Error (semua layanan)' not in text      # errors=off
    cfg = alerts.load(dataclasses.replace(config.Config(), alert_service_spike='default=off', alert_spike='errors=off'))
    assert 'spike' not in {e[0] for e in alerts.folder_events(cfg, '2026-01-06', f)}         # every service muted, nothing else rose


def test_thresholds_saved_from_the_page(app_env):
    tc, c, _ = app_env
    configure(tc)
    r = tc.put('/api/admin/alerts', json=dict(spike=dict(n5xx=dict(factor=3, min=50), errors=None),
                                               service_spike=dict(default=dict(factor=2, min=80), services={'coredns': None, 'report-service': dict(factor=4, min=300)})), headers=X)
    assert r.status_code == 200, r.text
    v = r.json()
    assert v['spike']['n5xx'] == dict(factor=3, min=50) and v['spike']['errors'] is None and 'n5xx' in v['spike_all']
    assert v['service_spike'] == dict(default=dict(factor=2, min=80), services={'coredns': None, 'report-service': dict(factor=4, min=300)})
    assert isinstance(v['services'], list)
    env = config.read_dotenv(os.path.join(c.state_dir, '.env'))
    assert env['S4_ALERT_SPIKE'] == 'n5xx=3:50,errors=off' and env['S4_ALERT_SERVICE_SPIKE'] == 'default=2:80,coredns=off,report-service=4:300'
    r = tc.put('/api/admin/alerts', json=dict(service_spike=dict(services={'report-service': dict(factor=1, min=5)})), headers=X)
    assert r.status_code == 400 and 'factor' in r.json()['error']['message']


def test_notifications_name_their_source_and_link_to_it():
    """Owner request 2026-10-23: notifications come from S3 and from Kafka; the title says which, the Kafka key is its own."""
    import types
    from monishield.application import alert_service
    s3, kafka = types.SimpleNamespace(source='s3'), types.SimpleNamespace(source='kafka')
    assert alert_service.Notifier._named(s3, 'spike:2026-01-06', 'Spike') == ('spike:2026-01-06', 'Spike (S3)')       # S3 keys unchanged
    assert alert_service.Notifier._named(kafka, 'spike:2026-01-06', 'Spike') == ('spike:2026-01-06@kafka', 'Spike (Kafka)')
    cfg = dict(lang='en', dashboard_url='https://monishield.example.com')
    assert alerts._link(cfg, '2026-01-06') .endswith('/command-center?folder=2026-01-06')
    assert alerts._link(cfg, '2026-01-06', 'security', 'kafka').endswith('/security?folder=2026-01-06&source=kafka')


# ------------------------------------------------------------------ daily report (owner request 2026-10-28)
def _report_cfg(lang='id'):
    return dict(lang=lang, events=dict(summary=True, spike=True, critical=True), dashboard_url='https://dash.example',
                spike=dict(alerts.SPIKE), service_spike=dict(default=(2, 50), services={}))


def _report_facts(crit=5, corrupt=1, svc_err=1240):
    return dict(kpi=dict(kpi=dict(requests=124822, n5xx=46, errors=2810, upstream_errors=3, attack_ips=14, login_fail_ips=4), atk_req=88,
                         crit_req=crit, lines=191898, corrupt=corrupt, svc={'event-api': (svc_err, 5000)}),
                base=dict(n_all=7, n_nginx=7, kpi=dict(requests=128000, n5xx=40, errors=1990, upstream_errors=2, attack_ips=12, login_fail_ips=4),
                          atk_req=70, svc={'event-api': 540}),
                ngx_keys=set(), crit_cats=['SQL injection'], files=18, warn=856, lines_avg=195000)


EXTRA = dict(seconds=11.6, kafka=dict(files=12, lines=1204331), kafka_state='running', backup=dict(ok=True, day='2026-10-27', bytes=2**20),
             sync=dict(enabled=True, ok=True))


def test_daily_report_content_status_and_language():
    key, title, text = alerts.summary(_report_cfg(), '2026-10-28', _report_facts(), EXTRA)
    assert key == 'summary:2026-10-28' and title == 'Ringkasan log 2026-10-27'
    assert text.startswith('🔴 Status: **KRITIS (3 hal)**')                          # critical attacks -> critical
    for part in ('**📊 Ringkasan** (vs rata-rata 7 hari)', '❌ Error (semua layanan): 2.810 (▲ 41%)', '1️⃣ Error event-api naik: 1.240',
                 '**📥 Hasil ingest**', '🪣 S3 2026-10-27: 18 file · 191.898 baris · 11,6 dtk', '🧩 Kelengkapan 98% dari rata-rata · 1 file rusak',
                 '📨 Kafka 2026-10-27: 12 file · 1.204.331 baris', '💾 Backup 2026-10-27: berhasil ✅ · 1,0 MB', '📡 Kafka: tersambung ✅',
                 '🔗 Buka: https://dash.example/command-center?folder=2026-10-28'):
        assert part in text, part
    en = alerts.summary(_report_cfg('en'), '2026-10-28', _report_facts(), EXTRA)[2]
    assert en.startswith('🔴 Status: **CRITICAL (3 items)**') and '**📥 Ingest result**' in en and 'Errors (all services): 2,810' in en
    quiet = alerts.summary(_report_cfg(), '2026-10-28', _report_facts(crit=0, corrupt=0, svc_err=500), EXTRA)[2]
    assert quiet.startswith('🟢 Status: **AMAN**') and 'Perlu dicek' not in quiet and len(quiet.split('\n')) == 6   # short version
    warn = alerts.summary(_report_cfg(), '2026-10-28', _report_facts(crit=0), dict(EXTRA, backup=dict(ok=False, day='2026-10-27')))[2]
    assert warn.startswith('🟡 Status: **PERLU DICEK (3 hal)**') and 'Backup gagal' in warn and '💾 Backup 2026-10-27: gagal ❌' in warn
    assert alerts.summary(dict(_report_cfg(), events=dict(summary=False)), '2026-10-28', _report_facts(), EXTRA) is None
    assert '33.33.33.199' not in text


def test_daily_report_email_has_sections_and_no_emoji():
    from monishield.domain import letters
    from monishield.infrastructure import letter
    _, title, text = alerts.summary(_report_cfg(), '2026-10-28', _report_facts(), EXTRA)
    lt = letters.notification('id', title, text)
    assert lt['status'] == dict(level='crit', text='Status: KRITIS (3 hal)') and not lt['paragraphs'] and lt['button']['url'].startswith('https://dash.example/')
    assert [s['title'] for s in lt['sections']] == ['Ringkasan (vs rata-rata 7 hari)', 'Perlu dicek', 'Hasil ingest', 'Sistem']
    assert lt['sections'][1]['items'][0].startswith('1. Error event-api') and 'Sinkron S3: OK' in lt['sections'][3]['items']
    html_part, text_part = letter.render_html(lt), letter.render_text(lt)
    assert 'Hasil ingest' in html_part and 'Status: KRITIS (3 hal)' in html_part and '#fef2f2' in html_part   # red status banner
    assert '🔴' not in html_part and '✅' not in text_part and '▲ 41%' in text_part and text_part.count('Status: KRITIS') == 1
    assert '<img' not in html_part   # the brand mark is HTML: no image to break


# ------------------------------------------------------------------ daily report schedule and on request (owner request 2026-10-28)
UTC = datetime.timezone.utc


def test_daily_report_target():
    d = datetime.date(2026, 10, 28)
    assert alerts.report_target('2026-10-28', ['2026-10-29'], d) == ('2026-10-28', 's3')                  # S3 first
    assert alerts.report_target(None, ['2026-10-27', '2026-10-28', '2026-10-29'], d) == ('2026-10-28', 'kafka')   # 29 is filling up
    assert alerts.report_target(None, ['2026-10-29'], d) is None and alerts.report_target(None, [], d) is None


def test_scheduled_daily_report_newest_folder_once(app_env, sent):
    tc, c, _ = app_env
    configure(tc, summary_hour=9)
    assert config.read_dotenv(os.path.join(c.state_dir, '.env'))['S4_ALERT_SUMMARY_HOUR'] == '9'
    n = tc.app.state.alerts
    assert n.daily_report(datetime.datetime(2026, 10, 7, 1, 30, tzinfo=UTC)) is None and sent == []      # 08:30 WIB: not yet
    jam8 = datetime.datetime(2026, 10, 7, 2, 0, tzinfo=UTC)                                             # 09:00 WIB
    assert n.daily_report(jam8) == dict(telegram=None, discord=None, email=None)
    assert any('Ringkasan log 2026-01-05 (S3)' in json.dumps(x) for x in sent)                           # newest folder 2026-01-06
    assert n.daily_report(jam8) == {}                                                                    # once per folder
    v = tc.get('/api/admin/alerts').json()
    assert v['summary_hour'] == 9 and [(x['folder'], x['sent']) for x in v['report_folders'] if x['source'] == 's3'][:3] == \
        [('2026-01-06', True), ('2026-01-05', False), ('2026-01-04', False)]
    tc.put('/api/admin/alerts', json=dict(events=dict(summary=False)), headers=X)
    assert n.daily_report(jam8) is None                                                                  # event off
    r = tc.put('/api/admin/alerts', json=dict(summary_hour=24), headers=X)
    assert r.status_code == 400 and 'Daily report hour' in r.json()['error']['message']


def test_failed_scheduled_report_is_retried_an_hour_later(app_env, sent, monkeypatch):
    tc, _, _ = app_env
    configure(tc, summary_hour=0)
    tc.put('/api/admin/alerts', json=dict(channels=dict(discord=dict(enabled=False), email=dict(enabled=False))), headers=X)
    def down(url, payload): raise alerts.AlertFail('Telegram is down')
    monkeypatch.setattr(notify_channels, '_post_json', down)
    n, now = tc.app.state.alerts, datetime.datetime(2026, 10, 7, 3, 0, tzinfo=UTC)
    assert n.daily_report(now) == dict(telegram='Telegram is down')
    assert n.daily_report(now) is None                                       # not every 10 minutes
    n._tried['summary:2026-01-06'] -= n.RETRY                                # an hour later
    assert n.daily_report(now) == dict(telegram='Telegram is down')


def test_send_the_report_for_old_and_unsent_folders(app_env, sent):
    tc, _, _ = app_env
    r = tc.post('/api/admin/alerts/report', json=dict(folder='2026-01-03'), headers=X)
    assert r.status_code == 400 and r.json()['error']['message'] == 'Turn on and save at least one channel first.'
    configure(tc, events=dict(summary=False))                                   # a report asked for goes out even with the event off
    one = lambda: tc.post('/api/admin/alerts/report', json=dict(folder='2026-01-03'), headers=X)
    r = one()
    assert r.status_code == 200 and r.json() == dict(sent=[dict(folder='2026-01-03', source='s3')], failed=[])
    assert any('Ringkasan log 2026-01-02 (S3)' in json.dumps(x) for x in sent)
    n = len(sent)
    assert one().json()['sent'] and len(sent) > n                           # sent again on request
    r = tc.post('/api/admin/alerts/report', json=dict(pending=True), headers=X).json()
    assert [x['folder'] for x in r['sent']] == ['2026-01-01', '2026-01-02', '2026-01-04', '2026-01-05', '2026-01-06'] and r['failed'] == []   # oldest first
    assert tc.post('/api/admin/alerts/report', json=dict(pending=True), headers=X).json() == dict(sent=[], failed=[])
    r = tc.post('/api/admin/alerts/report', json=dict(folder='2025-12-31'), headers=X)
    assert r.status_code == 404 and r.json()['error']['message'] == 'Log folder not found.'
    assert tc.post('/api/admin/alerts/report', json=dict(folder='2026-01-03', source='x'), headers=X).status_code == 400
    assert 'reports not sent yet: 5 sent, 0 failed' in tc.get('/api/admin/audit').text
