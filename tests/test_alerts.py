"""Telegram / Discord / email notifications (owner request 2026-10-07). No network: the HTTP and SMTP senders are faked."""
import dataclasses, datetime, http.server, json, os, shutil, threading, time

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
        def send_message(self, m): box.append(('smtp-send', m['Subject'], m['To'], m.get_content()))
    monkeypatch.setattr(notify_channels.smtplib, 'SMTP', FakeSMTP)
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


def setel(tc, **over):
    body = dict(channels=dict(telegram=dict(enabled=True, bot_token=TOKEN, chat_id='-1001234567890'),
                              discord=dict(enabled=True, webhook_url=HOOK),
                              email=dict(enabled=True, host='smtp.contoh.go.id', port=587, security='starttls', username='monishield',
                                         password=SMTP_PW, sender='monishield@contoh.go.id', to='tim@contoh.go.id, ketua@contoh.go.id')),
                dashboard_url='https://monishield.contoh.go.id', **over)
    r = tc.put('/api/admin/alerts', json=body, headers=X)
    assert r.status_code == 200, r.text
    return r


def test_kredensial_tidak_pernah_dikirim_balik(app_env):
    tc, c, _ = app_env
    r = setel(tc)
    for s in (TOKEN, HOOK, SMTP_PW): assert s not in r.text and s not in tc.get('/api/admin/alerts').text
    ch = r.json()['channels']
    assert (ch['telegram']['bot_token'], ch['discord']['webhook_url'], ch['email']['password']) == (True, True, True)
    assert ch['telegram']['chat_id'] == '-1001234567890' and ch['email']['to'].startswith('tim@')
    # stored in the .env file (not the database), takes effect immediately in the server config
    env = config.read_dotenv(os.path.join(c.state_dir, '.env'))
    assert (env['TELEGRAM_BOT_TOKEN'], env['S4_ALERT_TELEGRAM'], env['S4_ALERT_TELEGRAM_CHAT_ID'], env['DISCORD_WEBHOOK_URL'], env['SMTP_PASSWORD']) == \
        (TOKEN, 'true', '-1001234567890', HOOK, SMTP_PW)
    assert env['S4_SMTP_TO'] == 'tim@contoh.go.id, ketua@contoh.go.id' and env['S4_DASHBOARD_URL'] == 'https://monishield.contoh.go.id'
    assert tc.app.state.cfg.telegram_bot_token == TOKEN and tc.app.state.auth.setting_get('alerts') is None
    # save again without credentials: they stay stored; `clear` removes them
    r = tc.put('/api/admin/alerts', json=dict(channels=dict(telegram=dict(bot_token='', enabled=True))), headers=X)
    assert r.json()['channels']['telegram']['bot_token'] is True
    r = tc.put('/api/admin/alerts', json=dict(channels=dict(discord=dict(enabled=False)), clear=['discord.webhook_url']), headers=X)
    assert r.json()['channels']['discord']['webhook_url'] is False
    assert config.read_dotenv(os.path.join(c.state_dir, '.env'))['DISCORD_WEBHOOK_URL'] == ''
    audit = tc.get('/api/admin/audit').text
    assert 'alerts.update' in audit and TOKEN not in audit and SMTP_PW not in audit


@pytest.mark.parametrize('ch,msg', [(dict(telegram=dict(bot_token='bukan-token')), 'bot token'), (dict(telegram=dict(chat_id='abc')), 'chat ID'),
                                    (dict(discord=dict(webhook_url='https://evil.example/api/webhooks/1/x')), 'Discord webhook URL'),
                                    (dict(discord=dict(webhook_url='http://discord.com/api/webhooks/1/x')), 'Discord webhook URL'),
                                    (dict(email=dict(to='bukan email')), 'recipients'), (dict(email=dict(enabled=True)), 'incomplete'),
                                    (dict(telegram=dict(enabled=True)), 'not set')])
def test_isian_diperiksa(app_env, ch, msg):
    tc, _, _ = app_env
    r = tc.put('/api/admin/alerts', json=dict(channels=ch), headers=X)
    assert r.status_code == 400 and r.json()['error']['code'] == 'invalid_alerts' and msg in r.json()['error']['message']


def test_kirim_uji_tiap_saluran(app_env, sent):
    tc, _, _ = app_env
    setel(tc)
    for ch in ('telegram', 'discord', 'email'):
        r = tc.post('/api/admin/alerts/test', json=dict(channel=ch), headers=X)
        assert r.status_code == 200, r.text
    http = [x for x in sent if x[0] == 'http']
    assert http[0][1] == f'{alerts.TELEGRAM_API}/bot{TOKEN}/sendMessage' and http[0][2]['chat_id'] == '-1001234567890' and 'MoniShield' in http[0][2]['text']
    assert http[1][1] == HOOK and http[1][2]['allowed_mentions'] == {'parse': []}
    assert ('smtp-open', 'smtp.contoh.go.id', 587) in sent and ('smtp-starttls',) in sent and ('smtp-login', 'monishield', True) in sent
    assert [x for x in sent if x[0] == 'smtp-send'][0][2] == 'tim@contoh.go.id, ketua@contoh.go.id'
    hist = tc.get('/api/admin/alerts').json()['history']
    assert [h['channel'] for h in hist[:3]] == ['email', 'discord', 'telegram'] and all(h['ok'] for h in hist[:3])


def test_gagal_kirim_dilaporkan_tanpa_kredensial(app_env, monkeypatch):
    tc, _, _ = app_env
    setel(tc)
    def tolak(url, payload): raise alerts.AlertFail('ditolak HTTP 401')
    monkeypatch.setattr(notify_channels, '_post_json', tolak)
    r = tc.post('/api/admin/alerts/test', json=dict(channel='telegram'), headers=X)
    assert r.status_code == 502 and 'HTTP 401' in r.json()['error']['message'] and TOKEN not in r.text
    assert tc.get('/api/admin/alerts').json()['history'][0]['ok'] is False


def test_lonjakan_dan_serangan_kritis_tanpa_alamat_ip(app_env, sent):
    tc, c, root = app_env
    setel(tc)
    con = tc.app.state.con.cursor()
    try:
        con.execute("UPDATE agg_service SET err = err + 500 WHERE folder = '2026-01-06'")   # error spike vs the 01-02..01-05 average
        cfg = alerts.load(tc.app.state.cfg)
        ev = {e[0]: e for e in alerts.folder_events(cfg, '2026-01-06', tc.app.state.warehouse.folder_facts('2026-01-06', True))}
    finally: con.close()
    assert set(ev) == {'spike', 'critical'}
    _, key, title, text = ev['spike']
    assert key == 'spike:2026-01-06' and 'Error (semua layanan)' in text and 'rata-rata 4 folder' in text and '#/peta?folder=2026-01-06' in text
    _, key, title, text = ev['critical']
    assert 'IP' in text and '34.19.127.199' not in text and '#/keamanan?folder=2026-01-06' in text
    # send: all enabled channels, once per key
    cfg = alerts.load(tc.app.state.cfg)
    r = alert_service.deliver(tc.app.state, cfg, ev['spike'][1], 'spike', ev['spike'][2], ev['spike'][3])
    assert r == dict(telegram=None, discord=None, email=None)
    assert alert_service.deliver(tc.app.state, cfg, ev['spike'][1], 'spike', 'x', 'y') == {}
    for x in sent: assert '34.19.127.199' not in json.dumps(x)
    # English
    tc.put('/api/admin/alerts', json=dict(lang='en'), headers=X)
    con = tc.app.state.con.cursor()
    try: ev = {e[0]: e for e in alerts.folder_events(alerts.load(tc.app.state.cfg), '2026-01-06', tc.app.state.warehouse.folder_facts('2026-01-06', True))}
    finally: con.close()
    assert ev['spike'][2] == 'Spike in folder 2026-01-06' and 'Errors (all services)' in ev['spike'][3]


def test_sesudah_ingest_dan_sinkron_gagal_terkirim(app_env, sent):
    tc, c, root = app_env
    setel(tc, events=dict(summary=True))
    shutil.copytree(os.path.join(root, B), os.path.join(root, '2026-01-07'))
    assert tc.post('/api/admin/ingest', json={}, headers=X).status_code == 202
    tc.app.state.ingest.wait(60)
    for _ in range(100):
        if any('2026-01-07' in json.dumps(x) for x in sent): break
        time.sleep(0.05)
    time.sleep(0.3)
    titles = [x[2]['text'].split('\n')[0] for x in sent if x[0] == 'http' and 'sendMessage' in x[1]]
    assert 'Serangan kritis di folder 2026-01-07' in titles and 'Ringkasan folder 2026-01-07' in titles
    n = len(sent)
    tc.app.state.alerts._after_sync(dict(at='2026-10-07 01:00:00', errors=[dict(code='s3_denied', where='s3://b/k8s-logs/', message='S3 menolak akses')], failed=['2026-01-08']))
    assert any('Sinkron S3 bermasalah' in json.dumps(x) and '2026-01-08' in json.dumps(x) for x in sent[n:])


def test_folder_hari_ini_belum_datang(app_env, sent):
    tc, _, _ = app_env
    setel(tc)
    n = tc.app.state.alerts
    pagi = datetime.datetime(2026, 10, 7, 1, 0, tzinfo=datetime.timezone.utc)      # 08:00 WIB: not yet time
    assert n.check_missing(pagi) is None
    siang = datetime.datetime(2026, 10, 7, 4, 0, tzinfo=datetime.timezone.utc)     # 11:00 WIB
    assert n.check_missing(siang) == dict(telegram=None, discord=None, email=None)
    assert any('Folder log 2026-10-07 belum datang' in json.dumps(x) for x in sent)
    assert n.check_missing(siang) == {}                                            # once per day


def test_tanpa_saluran_aktif_tidak_ada_kiriman(app_env, sent):
    tc, _, _ = app_env
    assert tc.app.state.alerts.check_missing(datetime.datetime(2026, 10, 7, 4, 0, tzinfo=datetime.timezone.utc)) is None and sent == []


def test_post_json_sungguhan_ke_server_lokal(monkeypatch):
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


def test_user_biasa_tidak_boleh(app_env):
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
    d = alerts.parse_service_spike('default=2:50,OM-BE-REPORT=3:200,coredns=off')
    assert d == dict(default=(2, 50), services={'om-be-report': (3, 200), 'coredns': None})
    assert alerts.format_service_spike(d) == 'default=2:50,coredns=off,om-be-report=3:200'
    assert alerts.service_threshold(d, 'Om-Be-Report') == (3, 200) and alerts.service_threshold(d, 'lain') == (2, 50)
    for bad in ('n5xx=1:5', 'n5xx=abc', 'tidak_ada=2:5', 'n5xx'):
        with pytest.raises(alerts.AlertFail): alerts.parse_spike(bad)
    with pytest.raises(alerts.AlertFail): alerts.parse_service_spike('../x=2:5')


def test_service_spikes_use_their_own_thresholds():
    cfg = alerts.load(dataclasses.replace(config.Config(), alert_service_spike='default=2:50,om-be-report=3:200,coredns=off', alert_spike='errors=off'))
    f = _facts(svc=dict(simpel=120, coredns=900, **{'om-be-report': 300}), svc_avg=dict(simpel=50, coredns=10, **{'om-be-report': 120}), errors=1320, errors_avg=180)
    ev = {e[0]: e for e in alerts.folder_events(cfg, '2026-01-06', f)}
    text = ev['spike'][3]
    assert 'simpel: 120' in text and 'coredns' not in text and 'om-be-report' not in text   # muted / below its own threshold
    assert 'Errors (all services)' not in text and 'Error (semua layanan)' not in text      # errors=off
    cfg = alerts.load(dataclasses.replace(config.Config(), alert_service_spike='default=off', alert_spike='errors=off'))
    assert 'spike' not in {e[0] for e in alerts.folder_events(cfg, '2026-01-06', f)}         # every service muted, nothing else rose


def test_thresholds_saved_from_the_page(app_env):
    tc, c, _ = app_env
    setel(tc)
    r = tc.put('/api/admin/alerts', json=dict(spike=dict(n5xx=dict(factor=3, min=50), errors=None),
                                               service_spike=dict(default=dict(factor=2, min=80), services={'coredns': None, 'om-be-report': dict(factor=4, min=300)})), headers=X)
    assert r.status_code == 200, r.text
    v = r.json()
    assert v['spike']['n5xx'] == dict(factor=3, min=50) and v['spike']['errors'] is None and 'n5xx' in v['spike_all']
    assert v['service_spike'] == dict(default=dict(factor=2, min=80), services={'coredns': None, 'om-be-report': dict(factor=4, min=300)})
    assert isinstance(v['services'], list)
    env = config.read_dotenv(os.path.join(c.state_dir, '.env'))
    assert env['S4_ALERT_SPIKE'] == 'n5xx=3:50,errors=off' and env['S4_ALERT_SERVICE_SPIKE'] == 'default=2:80,coredns=off,om-be-report=4:300'
    r = tc.put('/api/admin/alerts', json=dict(service_spike=dict(services={'om-be-report': dict(factor=1, min=5)})), headers=X)
    assert r.status_code == 400 and 'factor' in r.json()['error']['message']
