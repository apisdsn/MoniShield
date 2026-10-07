"""Log dari Kafka (permintaan pemilik 2026-10-07: "apakah bisa dibuat seperti logging existing?").

Rancher (cluster logging -> Kafka, fluentd) mengirim satu pesan JSON per baris log container:
    {"log": "<baris asli>", "stream": "stdout", "tag": "kubernetes.var.log.containers.<pod>_<ns>_<container>-<id>.log",
     "docker": {"container_id": …}, "kubernetes": {"container_name": …, "namespace_name": …, "pod_name": …}, "time": 1515680329}
Isinya sama dengan log di S3: `log` = satu baris file, sedangkan namespace/layanan/pod yang di S3 ada di nama folder/file
diambil dari `kubernetes.*`. Konsumen ini menulis ulang pesan menjadi susunan folder yang SAMA dengan ekspor S3:
    <kotak masuk>/<tanggal>/<namespace>/<layanan>/log_<layanan>_<pod>_<tanggal>-00-00.log
lalu ingest berkala (S4_KAFKA_INGEST_MINUTES) memproses file yang bertambah — semua halaman dashboard langsung jalan.

Tanggal folder mengikuti ekspor S3 yang ada: folder D berisi log (D-1 00:00, D 00:00] WIB, jadi kejadian hari ini masuk
folder bertanggal BESOK (folder itu "sedang terisi" sampai tengah malam). Folder yang sudah diisi Kafka tidak diambil lagi
oleh sinkron S3 (folder sudah dikenal), jadi tidak ganda; jangan mengimpor S3 manual untuk tanggal yang sama.

Pengiriman: offset di-commit SESUDAH baris ditulis ke disk (at-least-once). Bila server mati di antara keduanya, beberapa
baris bisa tertulis dua kali; jarang dan kecil.

Realtime (animasi peta): baris nginx-ingress diteruskan ke `LiveHub` -> SSE /api/live/map. Yang dikirim ke browser hanya
koordinat lokasi (dari basis data IP lokal/offline, tabel ip_info) + modul, BUKAN alamat IP. IP yang belum dikenal
(belum pernah di-ingest) tidak digambar sampai ingest berikutnya mengisi lokasinya.
"""
import collections, datetime, json, os, re, threading, time

from . import parse

WIB = datetime.timedelta(hours=7)
NAME = re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]{0,252}')
TAG = re.compile(r'containers\.([^_]+)_([^_]+)_(.+?)-[0-9a-f]{12,64}\.log$')
MARK = '.kafka-feed.json'          # penanda folder kotak masuk yang diisi Kafka
FLUSH_SECONDS, FLUSH_LINES = 5, 20000
RECENT = 50


class KafkaFail(Exception):
    def __init__(self, code, message, status=400):
        super().__init__(message); self.code, self.message, self.status = code, message, status


def library_ok():
    import importlib.util
    return importlib.util.find_spec('kafka') is not None


NO_LIBRARY = ('Konsumen Kafka butuh paket kafka-python yang belum terpasang di server. Jalankan: .venv/bin/pip install -e ".[kafka]" '
              '(image Docker sudah memuatnya), lalu mulai ulang server.')


# ------------------------------------------------------------------ pesan -> baris log
def service_of(container, pod, ns=''):
    """Nama layanan seperti folder S3. Nama container biasanya sudah sama; bila tidak (mis. ingress-nginx Helm memakai
    container 'controller'), dicocokkan dari awalan nama pod."""
    if parse.known_service(container): return container
    for s in list(parse.PARSERS) + list(parse.SPRING_SVCS):
        if pod.startswith(s + '-'): return s
    if container == 'controller' and 'ingress' in ns: return parse.NGINX_SVC
    return container


def _time(obj, ts_ms):
    t = obj.get('time', obj.get('@timestamp'))
    try:
        if isinstance(t, (int, float)) or (isinstance(t, str) and re.fullmatch(r'\d+(\.\d+)?', t)):
            t = float(t)
            if t > 1e14: t /= 1e6        # mikrodetik
            elif t > 1e11: t /= 1e3      # milidetik
            return datetime.datetime.fromtimestamp(t, datetime.timezone.utc)
        if isinstance(t, str) and t:
            d = datetime.datetime.fromisoformat(t.replace('Z', '+00:00'))
            return d if d.tzinfo else d.replace(tzinfo=datetime.timezone.utc)
    except (ValueError, OverflowError, OSError): pass
    if ts_ms: return datetime.datetime.fromtimestamp(ts_ms / 1000, datetime.timezone.utc)
    return datetime.datetime.now(datetime.timezone.utc)


def parse_message(value, ts_ms=None):
    """bytes/str pesan Kafka -> (dict(ns, svc, pod, line, t), None) atau (None, alasan)."""
    try: obj = json.loads(value)
    except (ValueError, UnicodeDecodeError): return None, 'bukan JSON'
    if not isinstance(obj, dict): return None, 'bukan objek JSON'
    line = obj.get('log', obj.get('message'))
    if not isinstance(line, str): return None, "tanpa kolom 'log'"
    line = line.rstrip('\r\n')
    if not line.strip(): return None, 'baris kosong'
    k = obj.get('kubernetes') if isinstance(obj.get('kubernetes'), dict) else {}
    ns, container, pod = k.get('namespace_name'), k.get('container_name'), k.get('pod_name')
    if not (ns and container and pod) and isinstance(obj.get('tag'), str):
        m = TAG.search(obj['tag'])
        if m: pod, ns, container = pod or m[1], ns or m[2], container or m[3]
    if not (ns and container and pod): return None, 'tanpa kubernetes.namespace_name/container_name/pod_name'
    if not all(isinstance(x, str) and NAME.fullmatch(x) for x in (ns, container, pod)): return None, 'nama namespace/container/pod tidak sah'
    return dict(ns=ns, svc=service_of(container, pod, ns), pod=pod, line=line, t=_time(obj, ts_ms)), None


def folder_of(t):
    """Folder tanggal seperti ekspor S3: (D-1 00:00, D 00:00] WIB -> D."""
    w = t.astimezone(datetime.timezone.utc).replace(tzinfo=None) + WIB
    return ((w - datetime.timedelta(microseconds=1)).date() + datetime.timedelta(days=1)).isoformat()


def relpath(rec, folder):
    return os.path.join(folder, rec['ns'], rec['svc'], f"log_{rec['svc']}_{rec['pod']}_{folder}-00-00.log")


class Spool:
    """Penampung baris per file; flush() menambahkannya ke file di kotak masuk."""

    def __init__(self, inbox):
        self.inbox, self.buf, self.n = inbox, collections.defaultdict(list), 0

    def add(self, rec):
        f = folder_of(rec['t'])
        self.buf[relpath(rec, f)].append(rec['line']); self.n += 1
        return f

    def flush(self):
        """-> {folder: baris ditulis}."""
        out = collections.Counter()
        for rel, lines in self.buf.items():
            path = os.path.join(self.inbox, rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'a', encoding='utf-8', newline='\n') as fh: fh.write('\n'.join(lines) + '\n')
            out[rel.split(os.sep, 1)[0]] += len(lines)
        for f, n in out.items():
            mp = os.path.join(self.inbox, f, MARK)
            try: m = json.load(open(mp, encoding='utf-8'))
            except (OSError, ValueError): m = dict(lines=0)
            m.update(lines=m.get('lines', 0) + n, updated=datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds'))
            with open(mp, 'w', encoding='utf-8') as fh: json.dump(m, fh)
        self.buf.clear(); self.n = 0
        return dict(out)


# ------------------------------------------------------------------ realtime: lokasi IP -> browser (tanpa IP)
class LiveHub:
    """Kumpulan kejadian per detik: {(lat, lon, modul): n}. Pembaca (SSE) mengambil yang lebih baru dari nomor terakhirnya."""

    def __init__(self, app):
        self.app, self._lock, self.seq, self.ring = app, threading.Lock(), 0, collections.deque(maxlen=120)
        self.geo, self.geo_at, self.cur, self.cur_sec = {}, 0, collections.Counter(), None

    def _geo(self):
        if time.time() - self.geo_at > 300:
            self.geo_at = time.time()
            try:
                c = self.app.state.con.cursor()
                try: self.geo = {ip: (round(la, 3), round(lo, 3)) for ip, la, lo in c.execute('SELECT ip, lat, lon FROM ip_info WHERE lat IS NOT NULL AND NOT coalesce(is_private, false)').fetchall()}
                finally: c.close()
            except Exception: pass   # noqa: BLE001  basis data sedang dipakai ingest: coba lagi nanti
        return self.geo

    def refresh(self): self.geo_at = 0

    def nginx_line(self, line, prefix):
        ip = line.split(' ', 1)[0]
        g = self._geo().get(ip)
        if not g: return
        up = (re.search(r'\[([^\]]*)\] \[', line) or [None, ''])[1].replace(prefix, '') or '-'
        sec = int(time.time())
        with self._lock:
            if self.cur_sec is not None and sec != self.cur_sec: self._close()
            self.cur_sec = sec
            self.cur[(g[0], g[1], up)] += 1

    def _close(self):
        if self.cur:
            self.seq += 1
            self.ring.append((self.seq, [[la, lo, n, mod] for (la, lo, mod), n in self.cur.items()]))
        self.cur = collections.Counter()

    def since(self, seq):
        """-> (nomor terbaru, [[lat, lon, n, modul], …]) untuk kejadian setelah `seq`."""
        with self._lock:
            if self.cur_sec is not None and int(time.time()) != self.cur_sec: self._close(); self.cur_sec = None
            pts = [p for s, ps in self.ring if s > seq for p in ps]
            return self.seq, pts


# ------------------------------------------------------------------ konsumen
def _client_kwargs(cfg):
    kw = dict(bootstrap_servers=[x.strip() for x in cfg.kafka_brokers.split(',') if x.strip()], security_protocol=cfg.kafka_security.upper(),
              client_id='monishield', request_timeout_ms=30000, bootstrap_timeout_ms=10000)
    if cfg.kafka_security.upper().startswith('SASL'):
        kw.update(sasl_mechanism=cfg.kafka_sasl_mechanism.upper(), sasl_plain_username=cfg.kafka_username, sasl_plain_password=cfg.kafka_password)
    if cfg.kafka_ca_file: kw['ssl_cafile'] = cfg.kafka_ca_file
    return kw


def configured(cfg): return bool(cfg.kafka_brokers and cfg.kafka_topic)


def _err(e):
    """Galat pustaka -> pesan yang bisa dibaca (tanpa sandi)."""
    n = type(e).__name__
    if n in ('NoBrokersAvailable', 'KafkaConnectionError') or (n == 'KafkaTimeoutError' and 'bootstrap' in str(e)): return KafkaFail('kafka_unreachable', f'Broker Kafka tidak terjangkau dari server ({n}). Periksa alamat broker dan firewall.', 502)
    if 'Authentication' in n or 'SaslAuthentication' in n: return KafkaFail('kafka_auth', 'Kafka menolak nama pengguna/sandi SASL.', 502)
    if n in ('TopicAuthorizationFailedError', 'GroupAuthorizationFailedError'): return KafkaFail('kafka_denied', f'Kafka menolak akses ({n}).', 502)
    return KafkaFail('kafka_error', f'Kafka: {n}: {str(e)[:200]}', 502)


def peek(cfg, n=10):
    """Ambil n pesan TERAKHIR topic (tanpa grup konsumen, tanpa commit) untuk "Cek pesan" di layar."""
    if not configured(cfg): raise KafkaFail('kafka_not_configured', 'Isi alamat broker dan topic Kafka dulu.')
    if not library_ok(): raise KafkaFail('no_kafka_library', NO_LIBRARY)
    from kafka import KafkaConsumer, TopicPartition
    try:
        c = KafkaConsumer(enable_auto_commit=False, group_id=None, consumer_timeout_ms=4000, **_client_kwargs(cfg))
    except Exception as e: raise _err(e) from None   # noqa: BLE001
    try:
        parts = c.partitions_for_topic(cfg.kafka_topic)
        if not parts: raise KafkaFail('kafka_no_topic', f'Topic "{cfg.kafka_topic}" tidak ada (atau belum pernah menerima pesan).', 404)
        tps = [TopicPartition(cfg.kafka_topic, p) for p in sorted(parts)]
        c.assign(tps)
        end, beg = c.end_offsets(tps), c.beginning_offsets(tps)
        for tp in tps: c.seek(tp, max(beg[tp], end[tp] - n))
        got, t0 = [], time.time()
        while time.time() - t0 < 6 and sum(1 for _ in got) < n * len(tps):
            batch = c.poll(timeout_ms=800)
            if not batch and all(c.position(tp) >= end[tp] for tp in tps): break
            for recs in batch.values(): got.extend(recs)
        got.sort(key=lambda r: r.timestamp or 0)
        out = []
        for r in got[-n:]:
            rec, why = parse_message(r.value, r.timestamp)
            out.append(dict(partition=r.partition, offset=r.offset, at=datetime.datetime.fromtimestamp((r.timestamp or 0) / 1000, datetime.timezone.utc).isoformat(timespec='seconds'),
                            raw=(r.value or b'')[:2000].decode('utf-8', 'replace'), ok=rec is not None, reason=why,
                            target=relpath(rec, folder_of(rec['t'])) if rec else None))
        total = sum(end[tp] - beg[tp] for tp in tps)
        return dict(topic=cfg.kafka_topic, partitions=len(tps), messages_retained=total, messages=out)
    except KafkaFail: raise
    except Exception as e: raise _err(e) from None   # noqa: BLE001
    finally: c.close()


class KafkaFeed:
    """Konsumen di thread latar milik proses server (ingest tetap satu pemilik DuckDB, TRD K1)."""

    def __init__(self, app):
        self.app, self.thread, self._stop = app, None, threading.Event()
        self.live = LiveHub(app)
        self.recent = collections.deque(maxlen=RECENT)
        self._reset_stats()

    def _reset_stats(self):
        self.stats = dict(state='mati', since=None, received=0, written=0, skipped=0, last_message_at=None, last_ingest_at=None,
                          error=None, last_skip=None, per_service={}, folders={})
        self.pending = set()   # folder yang bertambah sejak ingest terakhir

    # -------------------------------------------------------------- kendali
    def start(self):
        cfg = self.app.state.cfg
        if not (cfg.kafka_enabled and configured(cfg)): self.stats['state'] = 'mati'; return
        if not library_ok(): self.stats.update(state='galat', error=NO_LIBRARY); return
        if self.thread and self.thread.is_alive(): return
        self._stop = threading.Event()
        self.thread = threading.Thread(target=self._loop, name='kafka', daemon=True)
        self.thread.start()

    def stop(self, timeout=15):
        self._stop.set()
        if self.thread: self.thread.join(timeout)
        self.thread = None

    def restart(self):
        self.stop(); self._reset_stats(); self.start()

    def live_folder(self): return folder_of(datetime.datetime.now(datetime.timezone.utc))

    def status(self):
        cfg = self.app.state.cfg
        return dict(configured=configured(cfg), enabled=cfg.kafka_enabled, library=library_ok(), brokers=cfg.kafka_brokers, topic=cfg.kafka_topic,
                    group=cfg.kafka_group, security=cfg.kafka_security, ingest_minutes=cfg.kafka_ingest_minutes, live_folder=self.live_folder(),
                    pending=sorted(self.pending), recent=list(self.recent)[::-1], **self.stats)

    # -------------------------------------------------------------- inti (dapat diuji tanpa broker)
    def handle(self, records, spool):
        """records: [(value, timestamp_ms, partition, offset)]."""
        prefix = self.app.state.cfg.upstream_prefix
        for value, ts, part, off in records:
            self.stats['received'] += 1
            rec, why = parse_message(value, ts)
            if not rec:
                self.stats['skipped'] += 1
                self.stats['last_skip'] = dict(reason=why, sample=(value or b'')[:300].decode('utf-8', 'replace') if isinstance(value, bytes) else str(value)[:300])
                continue
            f = spool.add(rec)
            key = f"{rec['ns']}/{rec['svc']}"
            self.stats['per_service'][key] = self.stats['per_service'].get(key, 0) + 1
            self.stats['last_message_at'] = rec['t'].astimezone(datetime.timezone.utc).replace(tzinfo=None).isoformat(timespec='seconds')
            self.recent.append(dict(at=self.stats['last_message_at'], folder=f, ns=rec['ns'], svc=rec['svc'], pod=rec['pod'], line=rec['line'][:400],
                                    partition=part, offset=off))
            if rec['svc'] == parse.NGINX_SVC: self.live.nginx_line(rec['line'], prefix)

    def flush(self, spool):
        wrote = spool.flush()
        for f, n in wrote.items():
            self.stats['written'] += n
            self.stats['folders'][f] = self.stats['folders'].get(f, 0) + n
            self.pending.add(f)
        return wrote

    def maybe_ingest(self, now=None, force=False):
        """Ingest berkala folder yang bertambah (lewat IngestManager: satu pemilik DuckDB). -> True bila dimulai."""
        now = now or time.time()
        last = getattr(self, '_last_ingest', 0)
        if not self.pending or (not force and now - last < self.app.state.cfg.kafka_ingest_minutes * 60): return False
        ing = self.app.state.ingest
        if ing.state['running']: return False
        folders = sorted(self.pending)
        try: ing.start(folders[0] if len(folders) == 1 else None, False, '(kafka)')
        except Exception: return False   # noqa: BLE001  ingest lain baru saja mulai: coba putaran berikutnya
        self._last_ingest = now
        self.pending.clear()
        self.stats['last_ingest_at'] = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None).isoformat(timespec='seconds')
        self.live.refresh()
        return True

    # -------------------------------------------------------------- thread
    def _loop(self):
        from kafka import KafkaConsumer
        cfg, wait = self.app.state.cfg, 5
        spool = Spool(cfg.inbox_dir)
        while not self._stop.is_set():
            c = None
            try:
                self.stats.update(state='menyambung', error=None)
                c = KafkaConsumer(cfg.kafka_topic, group_id=cfg.kafka_group, enable_auto_commit=False, auto_offset_reset=cfg.kafka_offset_reset,
                                  max_poll_records=2000, **_client_kwargs(cfg))
                self.stats.update(state='berjalan', since=datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None).isoformat(timespec='seconds'))
                wait, last_flush = 5, time.time()
                while not self._stop.is_set():
                    batch = c.poll(timeout_ms=1000)
                    for recs in batch.values(): self.handle([(r.value, r.timestamp, r.partition, r.offset) for r in recs], spool)
                    if spool.n and (spool.n >= FLUSH_LINES or time.time() - last_flush >= FLUSH_SECONDS):
                        self.flush(spool); c.commit(); last_flush = time.time()
                    elif not spool.n: last_flush = time.time()
                    self.maybe_ingest()
                if spool.n: self.flush(spool); c.commit()
            except Exception as e:   # noqa: BLE001  broker mati / sandi salah: status + coba lagi berkala
                f = _err(e)
                self.stats.update(state='galat', error=f'[{f.code}] {f.message}')
                self._stop.wait(wait); wait = min(wait * 2, 120)
            finally:
                if c is not None:
                    try: c.close()
                    except Exception: pass   # noqa: BLE001
        self.stats['state'] = 'mati'
