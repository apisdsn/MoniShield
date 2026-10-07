"""Notifikasi Telegram / Discord / email (permintaan pemilik 2026-10-07). Tanpa jaringan: pengirim HTTP dan SMTP ditiru."""
import dataclasses, datetime, http.server, json, os, shutil, threading, time

import pytest
from fastapi.testclient import TestClient

import logs_mini
from monishield import alerts, auth, config, db, ingest
from monishield.api import app as appmod
from conftest import JWT_SECRET

X = {'X-Requested-With': 'uji'}
PW, PW2 = 'sandi-admin-pertama', 'sandi-admin-sesudah-diganti'
TOKEN = '123456789:AAHrahasiaTokenBotTelegramUji0000000'
HOOK = 'https://discord.com/api/webhooks/1234567890/rahasiaWebhookDiscordUji0000'
SMTP_PW = 'sandiSmtpRahasiaUji'
B = '2026-01-02'


@pytest.fixture
def sent(monkeypatch):
    """Tangkap semua kiriman HTTP (Telegram/Discord) dan SMTP."""
    box = []
    monkeypatch.setattr(alerts, '_post_json', lambda url, payload: box.append(('http', url, payload)) or 200)

    class FakeSMTP:
        def __init__(self, host, port, timeout=None, **kw): box.append(('smtp-open', host, port))
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def starttls(self, context=None): box.append(('smtp-starttls',))
        def login(self, u, p): box.append(('smtp-login', u, p == SMTP_PW))
        def send_message(self, m): box.append(('smtp-send', m['Subject'], m['To'], m.get_content()))
    monkeypatch.setattr(alerts.smtplib, 'SMTP', FakeSMTP)
    return box


@pytest.fixture
def app_env(tmp_path, auth_url, monkeypatch):
    """Folder B + empat salinannya (rata-rata tersedia) + 2026-01-07 = B dengan error dilipatgandakan nanti."""
    monkeypatch.setattr(auth, 'SCRYPT', (10, 8, 1))
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
    # simpan lagi tanpa kredensial: tetap tersimpan; `clear` menghapus
    r = tc.put('/api/admin/alerts', json=dict(channels=dict(telegram=dict(bot_token='', enabled=True))), headers=X)
    assert r.json()['channels']['telegram']['bot_token'] is True
    r = tc.put('/api/admin/alerts', json=dict(channels=dict(discord=dict(enabled=False)), clear=['discord.webhook_url']), headers=X)
    assert r.json()['channels']['discord']['webhook_url'] is False
    audit = tc.get('/api/admin/audit').text
    assert 'alerts.update' in audit and TOKEN not in audit and SMTP_PW not in audit


@pytest.mark.parametrize('ch,msg', [(dict(telegram=dict(bot_token='bukan-token')), 'Token bot'), (dict(telegram=dict(chat_id='abc')), 'Chat ID'),
                                    (dict(discord=dict(webhook_url='https://evil.example/api/webhooks/1/x')), 'webhook Discord'),
                                    (dict(discord=dict(webhook_url='http://discord.com/api/webhooks/1/x')), 'webhook Discord'),
                                    (dict(email=dict(to='bukan email')), 'Penerima'), (dict(email=dict(enabled=True)), 'belum lengkap'),
                                    (dict(telegram=dict(enabled=True)), 'belum diisi')])
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
    monkeypatch.setattr(alerts, '_post_json', tolak)
    r = tc.post('/api/admin/alerts/test', json=dict(channel='telegram'), headers=X)
    assert r.status_code == 502 and 'HTTP 401' in r.json()['error']['message'] and TOKEN not in r.text
    assert tc.get('/api/admin/alerts').json()['history'][0]['ok'] is False


def test_lonjakan_dan_serangan_kritis_tanpa_alamat_ip(app_env, sent):
    tc, c, root = app_env
    setel(tc)
    con = tc.app.state.con.cursor()
    try:
        con.execute("UPDATE agg_service SET err = err + 500 WHERE folder = '2026-01-06'")   # lonjakan error vs rata-rata 01-02..01-05
        cfg = alerts.load(tc.app.state.auth)
        ev = {e[0]: e for e in alerts.folder_events(con, cfg, '2026-01-06', True)}
    finally: con.close()
    assert set(ev) == {'spike', 'critical'}
    _, key, title, text = ev['spike']
    assert key == 'spike:2026-01-06' and 'Error (semua layanan)' in text and 'rata-rata 4 folder' in text and '#/peta?folder=2026-01-06' in text
    _, key, title, text = ev['critical']
    assert 'IP' in text and '34.19.127.199' not in text and '#/keamanan?folder=2026-01-06' in text
    # kirim: semua saluran aktif, sekali per kunci
    cfg = alerts.load(tc.app.state.auth)
    r = alerts.deliver(tc.app.state.auth, cfg, ev['spike'][1], 'spike', ev['spike'][2], ev['spike'][3])
    assert r == dict(telegram=None, discord=None, email=None)
    assert alerts.deliver(tc.app.state.auth, cfg, ev['spike'][1], 'spike', 'x', 'y') == {}
    for x in sent: assert '34.19.127.199' not in json.dumps(x)
    # bahasa Inggris
    tc.put('/api/admin/alerts', json=dict(lang='en'), headers=X)
    con = tc.app.state.con.cursor()
    try: ev = {e[0]: e for e in alerts.folder_events(con, alerts.load(tc.app.state.auth), '2026-01-06', True)}
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
    pagi = datetime.datetime(2026, 10, 7, 1, 0, tzinfo=datetime.timezone.utc)      # 08.00 WIB: belum waktunya
    assert n.check_missing(pagi) is None
    siang = datetime.datetime(2026, 10, 7, 4, 0, tzinfo=datetime.timezone.utc)     # 11.00 WIB
    assert n.check_missing(siang) == dict(telegram=None, discord=None, email=None)
    assert any('Folder log 2026-10-07 belum datang' in json.dumps(x) for x in sent)
    assert n.check_missing(siang) == {}                                            # sekali per hari


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
        assert alerts._post_json(base + '/ok', dict(a=1)) == 200 and got == [dict(a=1)]
        with pytest.raises(alerts.AlertFail, match='HTTP 401'): alerts._post_json(base + '/tolak', {})
    finally: srv.shutdown(); srv.server_close()


def test_user_biasa_tidak_boleh(app_env):
    tc, _, _ = app_env
    assert tc.post('/api/admin/users', json=dict(username='rina', display_name='Rina', role='user', password='sandi-awal-rina-123'), headers=X).status_code == 201
    u = TestClient(tc.app)
    u.post('/api/auth/login', json=dict(username='rina', password='sandi-awal-rina-123'), headers=X)
    u.post('/api/me/password', json=dict(old_password='sandi-awal-rina-123', new_password='sandi-baru-rina-123'), headers=X)
    assert u.get('/api/admin/alerts').status_code == 403 and u.post('/api/admin/alerts/test', json=dict(channel='email'), headers=X).status_code == 403
