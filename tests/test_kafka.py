"""Logs from Kafka (owner request 2026-10-07): Rancher message -> the same folder as the S3 export -> ingest -> the SAME result
as logs from S3. No broker: messages are fed directly to KafkaFeed.handle(); the real broker is tested separately (Docker)."""
import dataclasses, datetime, json, os, threading, time

import httpx, pytest
from fastapi.testclient import TestClient

import logs_mini
from monishield.domain import accounts
from monishield.application import kafka_service
from monishield.infrastructure import config, db, inbox as inboxmod, ingest
from monishield.domain import kafka_message, parse
from monishield.interfaces.api import app as appmod
from conftest import JWT_SECRET

X = {'X-Requested-With': 'uji'}
PW, PW2 = 'sandi-admin-pertama', 'sandi-admin-sesudah-diganti'
B = '2026-01-02'
T = datetime.datetime(2026, 1, 1, 5, 0, tzinfo=datetime.timezone.utc)   # 1 Jan 12:00 WIB -> folder 2 Jan (like the S3 export)
PODS = [('ingress-nginx', 'nginx-ingress-controller', 'pod-n'), ('kube-system', 'coredns', 'pod-d'),
        ('ombudsman', 'om-be-simpel-loop', 'pod-s'), ('ombudsman', 'om-be-report', 'pod-r')]


def rancher(ns, container, pod, line, t=T, **extra):
    """Shape of a Rancher cluster logging (fluentd) -> Kafka message, like the example on the Rancher screen."""
    m = dict(log=line + '\n', stream='stdout', tag=f'kubernetes.var.log.containers.{pod}_{ns}_{container}-5f07a15a2a60ef4aa1b2c3d4e5f6.log',
             docker=dict(container_id='5f07a15a2a60ef4'), kubernetes=dict(container_name=container, namespace_name=ns, pod_name=pod), time=int(t.timestamp()))
    m.update(extra)
    return json.dumps(m).encode()


def messages():
    out, off = [], 0
    for ns, svc, pod in PODS:
        for line in logs_mini.lines(svc).splitlines():
            out.append((rancher(ns, svc, pod, line), None, 0, off)); off += 1
    return out


# ------------------------------------------------------------------ messages
def test_pesan_rancher_dan_variasinya():
    r, why = kafka_message.parse_message(rancher('ombudsman', 'om-be-report', 'om-be-report-7d9f-abcde', 'baris satu'))
    assert why is None and (r['ns'], r['svc'], r['pod'], r['line'], r['t']) == ('ombudsman', 'om-be-report', 'om-be-report-7d9f-abcde', 'baris satu', T)
    # no kubernetes block: from the tag
    m = json.loads(rancher('ombudsman', 'om-be-report', 'om-be-report-7d9f-abcde', 'x')); m.pop('kubernetes')
    assert kafka_message.parse_message(json.dumps(m))[0]['pod'] == 'om-be-report-7d9f-abcde'
    # time: milliseconds, ISO, empty -> Kafka timestamp
    for t in (int(T.timestamp() * 1000), '2026-01-01T05:00:00Z', '2026-01-01T12:00:00+07:00'):
        assert kafka_message.parse_message(rancher('a', 'b', 'c', 'x', time=t))[0]['t'] == T
    assert kafka_message.parse_message(rancher('a', 'b', 'c', 'x', time=None), ts_ms=int(T.timestamp() * 1000))[0]['t'] == T
    # rejected with a reason
    assert kafka_message.parse_message(b'bukan json')[1] == 'not JSON'
    assert kafka_message.parse_message(json.dumps(dict(stream='stdout')))[1] == "no 'log' field"
    assert kafka_message.parse_message(json.dumps(dict(log='x')))[1].startswith('no kubernetes')
    assert kafka_message.parse_message(rancher('..', 'svc', 'pod', 'x'))[1] == 'invalid namespace/container/pod name'   # cannot escape the inbox
    assert kafka_message.parse_message(rancher('ns', 'svc', 'a/../../etc', 'x'))[1] == 'invalid namespace/container/pod name'
    assert kafka_message.parse_message(rancher('ns', 'svc', 'pod', '   '))[1] == 'empty line'


def test_nama_layanan_seperti_folder_s3():
    assert kafka_message.service_of('om-be-appsmanager', 'om-be-appsmanager-bc95dc4fc-sx4f2') == 'om-be-appsmanager'
    assert kafka_message.service_of('app', 'om-be-referensi-5b7c9-xk2pq') == 'om-be-referensi'                  # from the pod prefix
    assert kafka_message.service_of('controller', 'ingress-nginx-controller-7d8f-abcde', 'ingress-nginx') == parse.NGINX_SVC
    assert kafka_message.service_of('layanan-baru', 'layanan-baru-1') == 'layanan-baru'                          # unknown: as is


@pytest.mark.parametrize('wib,folder', [('2026-10-05 00:05:00', '2026-10-06'), ('2026-10-06 00:00:00', '2026-10-06'),
                                        ('2026-10-06 00:00:01', '2026-10-07'), ('2026-10-06 23:59:59', '2026-10-07')])
def test_tanggal_folder_seperti_ekspor_s3(wib, folder):
    """Folder D holds logs (D-1 00:00, D 00:00] WIB — like the S3 folders ('folder 6 Oct holds logs 5 Oct 00:05–6 Oct 00:00 WIB')."""
    t = datetime.datetime.fromisoformat(wib).replace(tzinfo=datetime.timezone(datetime.timedelta(hours=7)))
    assert kafka_message.folder_of(t) == folder


# ------------------------------------------------------------------ equivalent to S3
def test_hasil_ingest_sama_dengan_log_s3(tmp_path):
    """Same lines: via S3 file vs via Kafka message -> identical files and identical database contents."""
    s3 = tmp_path / 's3'
    for ns, svc, pod in PODS: logs_mini.write(logs_mini.log_path(str(s3), B, ns, svc, pod), logs_mini.lines(svc))
    inbox = tmp_path / 'kafka'
    feed = kafka_service.KafkaFeed(type('Ctx', (), {'cfg': config.Config()})())
    sp = inboxmod.Spool(str(inbox))
    feed.handle(messages(), sp)
    assert feed.flush(sp) == {B: sum(len(logs_mini.lines(s).splitlines()) for _, s, _ in PODS)}
    for ns, svc, pod in PODS:
        rel = os.path.relpath(logs_mini.log_path(str(s3), B, ns, svc, pod), str(s3))
        assert (inbox / rel).read_bytes() == (s3 / rel).read_bytes().rstrip(b'\n') + b'\n', rel
    counts = []
    for name, root in (('s3', s3), ('kafka', inbox)):
        c = dataclasses.replace(config.Config(), log_dir=str(tmp_path / f'kosong-{name}'), inbox_dir=str(root), data_dir=str(tmp_path / f'data-{name}'),
                                cache_dir=str(tmp_path / 'cache'), offline=True)
        con = db.open(c.db_path); r = ingest.run(c, con, workers=0)
        assert r['files_failed'] == 0 and r['folders_changed'] == [B]
        counts.append({t: con.execute(f'SELECT count(*) FROM {t}').fetchone()[0] for t in ingest.RAW_TABLES})
        counts[-1]['requests'] = con.execute('SELECT count(*), count(DISTINCT ip) FROM nginx_access').fetchone()
        con.close()
    assert counts[0] == counts[1] and counts[0]['requests'][0] > 0


# ------------------------------------------------------------------ on the server
@pytest.fixture
def client(tmp_path, auth_url, monkeypatch):
    monkeypatch.setattr(accounts, 'SCRYPT', (10, 8, 1))
    c = dataclasses.replace(config.Config(), log_dir=str(tmp_path / 'logs'), data_dir=str(tmp_path / 'data'), state_dir=str(tmp_path / 'state'),
                            inbox_dir=str(tmp_path / 'inbox'), cache_dir=str(tmp_path / 'cache'), offline=True, ingest_on_start=False, cookie_secure=False,
                            admin_user='admin', admin_password=PW, jwt_secret=JWT_SECRET, auth_database_url=auth_url,
                            kafka_brokers='127.0.0.1:9', kafka_topic='k8s-logs', kafka_enabled=False)
    os.makedirs(c.log_dir)
    with TestClient(appmod.create_app(c)) as tc:
        assert tc.post('/api/auth/login', json=dict(username='admin', password=PW), headers=X).status_code == 200
        assert tc.post('/api/me/password', json=dict(old_password=PW, new_password=PW2), headers=X).status_code == 200
        yield tc


def tunggu_ingest(tc):
    for _ in range(600):
        s = tc.get('/api/admin/ingest/status', headers=X).json()
        if not s['running']: return s
        time.sleep(0.05)
    raise AssertionError('ingest tidak selesai')


def test_status_ingest_dan_folder_muncul(client):
    feed = client.app.state.kafka
    s = client.get('/api/admin/kafka', headers=X).json()
    assert (s['configured'], s['enabled'], s['state'], s['topic']) == (True, False, 'off', 'k8s-logs')
    sp = inboxmod.Spool(client.app.state.cfg.inbox_dir)
    feed.handle(messages() + [(b'{"stream":"stdout"}', None, 0, 999)], sp); feed.flush(sp)
    s = client.get('/api/admin/kafka', headers=X).json()
    assert s['received'] == len(messages()) + 1 and s['skipped'] == 1 and s['last_skip']['reason'] == "no 'log' field"
    assert s['per_service']['ingress-nginx/nginx-ingress-controller'] == 11 and s['pending'] == [B] and s['recent'][0]['folder'] == B
    r = client.post('/api/admin/kafka/ingest', headers=X)
    assert r.status_code == 200, r.text
    st = tunggu_ingest(client)
    assert st['last']['folders_changed'] == [B] and st['last']['files_failed'] == 0
    meta = {f['folder']: f for f in client.get('/api/meta', headers=X).json()['folders']}
    assert meta[B]['source'] == 'kafka'   # labelled "(Kafka)" in the UI
    rows = {r['folder']: r for r in client.get('/api/admin/folders', headers=X).json()['rows']}
    assert rows[B]['source'] == 'kafka' and rows[B]['inbox']
    n_ngx = lambda: client.app.state.con.cursor().execute('SELECT count(*) FROM nginx_access').fetchone()[0]
    before, kpi = n_ngx(), client.get(f'/api/folders/{B}/command', headers=X).json()['kpi']['requests']
    assert before > 0 and kpi > 0
    assert client.post('/api/admin/kafka/ingest', headers=X).json()['error']['code'] == 'kafka_nothing'
    # lines arriving later: the file grows, the next ingest reprocesses only that file
    feed.handle([(rancher('ingress-nginx', 'nginx-ingress-controller', 'pod-n', logs_mini.lines('nginx-ingress-controller').splitlines()[0]), None, 0, 2000)], sp)
    feed.flush(sp); client.post('/api/admin/kafka/ingest', headers=X); st = tunggu_ingest(client)
    assert st['last']['files_changed'] == 1 and n_ngx() == before + 1


def test_cek_pesan_tanpa_setelan_dan_tanpa_broker(client):
    client.app.state.cfg.kafka_topic = ''
    r = client.post('/api/admin/kafka/peek', json=dict(n=5), headers=X)
    assert r.status_code == 400 and r.json()['error']['code'] == 'kafka_not_configured'
    client.app.state.cfg.kafka_topic = 'k8s-logs'
    r = client.post('/api/admin/kafka/peek', json=dict(n=5), headers=X)   # 127.0.0.1:9 has no broker
    assert r.status_code == 502 and r.json()['error']['code'] == 'kafka_unreachable'


def serve(app):
    import socket, uvicorn
    s = socket.socket(); s.bind(('127.0.0.1', 0)); port = s.getsockname()[1]; s.close()
    srv = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=port, log_level='warning', lifespan='off'))
    threading.Thread(target=srv.run, daemon=True).start()
    for _ in range(200):
        if srv.started: break
        time.sleep(0.02)
    return srv, port


def test_peta_realtime_tanpa_alamat_ip(client):
    feed = client.app.state.kafka
    assert client.get('/api/live/map', headers=X).status_code == 204          # consumer not running
    sp = inboxmod.Spool(client.app.state.cfg.inbox_dir)
    feed.handle(messages(), sp); feed.flush(sp); client.post('/api/admin/kafka/ingest', headers=X); tunggu_ingest(client)
    con = client.app.state.con.cursor()
    con.execute("UPDATE ip_info SET lat = -6.2, lon = 106.8, is_private = false WHERE ip = '103.176.97.213'")   # offline ingest has no location
    con.close(); feed.live.refresh()
    stop = threading.Event()
    feed.thread = threading.Thread(target=stop.wait, daemon=True); feed.thread.start()   # as if the consumer were running
    line = logs_mini.lines('nginx-ingress-controller').splitlines()[0]
    got = []
    srv, port = serve(client.app)   # the in-process test client waits for the response to finish; the SSE stream needs a real server
    try:
        with httpx.Client(base_url=f'http://127.0.0.1:{port}', cookies={c.name: c.value for c in client.cookies.jar}, trust_env=False, timeout=15) as h, h.stream('GET', '/api/live/map', headers=X) as r:
            assert r.status_code == 200 and r.headers['content-type'].startswith('text/event-stream')
            for raw in r.iter_lines():
                if raw.startswith('data: ') and '"live"' in raw:
                    got.append(json.loads(raw[6:]))
                    feed.handle([(rancher('ingress-nginx', 'nginx-ingress-controller', 'pod-n', line, t=datetime.datetime.now(datetime.timezone.utc)), None, 0, 1)] * 3,
                                inboxmod.Spool(client.app.state.cfg.inbox_dir))
                elif raw.startswith('data: '):
                    got.append(json.loads(raw[6:])); break
    finally: stop.set(); srv.should_exit = True
    assert got[0] == dict(live=True, folder=feed.live_folder())
    assert got[1]['p'] == [[-6.2, 106.8, 3, got[1]['p'][0][3]]] and '103.176.97.213' not in json.dumps(got)
