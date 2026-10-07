"""Layanan log dari Kafka: konsumen di thread latar (KafkaFeed) + kejadian peta realtime (LiveHub). Adapter: klien Kafka
monishield/infrastructure/kafka_client.py, kotak masuk monishield/infrastructure/inbox.py; aturan pesan
monishield/domain/kafka_message.py.

Log dari Kafka (permintaan pemilik 2026-10-07: "apakah bisa dibuat seperti logging existing?").

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
import collections, datetime, re, threading, time

from monishield.domain import parse
from monishield.domain.errors import Busy, Fail
from monishield.domain.kafka_message import configured, folder_of, parse_message

FLUSH_SECONDS, FLUSH_LINES = 5, 20000
RECENT = 50


# ------------------------------------------------------------------ realtime: lokasi IP -> browser (tanpa IP)
class LiveHub:
    """Kumpulan kejadian per detik: {(lat, lon, modul): n}. Pembaca (SSE) mengambil yang lebih baru dari nomor terakhirnya."""

    def __init__(self, ctx):
        self.ctx, self._lock, self.seq, self.ring = ctx, threading.Lock(), 0, collections.deque(maxlen=120)
        self.geo, self.geo_at, self.cur, self.cur_sec = {}, 0, collections.Counter(), None

    def _geo(self):
        if time.time() - self.geo_at > 300:
            self.geo_at = time.time()
            try: self.geo = self.ctx.warehouse.ip_locations()
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
class KafkaFeed:
    """Konsumen di thread latar milik proses server (ingest tetap satu pemilik DuckDB, TRD K1)."""

    def __init__(self, ctx):
        self.ctx, self.thread, self._stop = ctx, None, threading.Event()
        self.live = LiveHub(ctx)
        self.recent = collections.deque(maxlen=RECENT)
        self._reset_stats()

    def _reset_stats(self):
        self.stats = dict(state='mati', since=None, received=0, written=0, skipped=0, last_message_at=None, last_ingest_at=None,
                          error=None, last_skip=None, per_service={}, folders={})
        self.pending = set()   # folder yang bertambah sejak ingest terakhir

    # -------------------------------------------------------------- kendali
    def start(self):
        cfg = self.ctx.cfg
        if not (cfg.kafka_enabled and configured(cfg)): self.stats['state'] = 'mati'; return
        kc = self.ctx.kafka_client
        if not kc.library_ok(): self.stats.update(state='galat', error=kc.no_library); return
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

    def running(self): return bool(self.thread and self.thread.is_alive())

    def peek(self, n=10):
        """"Cek pesan": n pesan TERAKHIR dari topic (tanpa grup konsumen; tidak menggeser posisi baca)."""
        return self.ctx.kafka_client.peek(self.ctx.cfg, n)

    def ingest_now(self):
        if not self.pending: raise Fail('kafka_nothing', 'Belum ada baris baru dari Kafka sejak ingest terakhir.', 400)
        if not self.maybe_ingest(force=True): raise Busy('Ingest lain sedang berjalan; coba lagi sebentar.')

    def live_folder(self): return folder_of(datetime.datetime.now(datetime.timezone.utc))

    def status(self):
        cfg = self.ctx.cfg
        return dict(configured=configured(cfg), enabled=cfg.kafka_enabled, library=self.ctx.kafka_client.library_ok(), brokers=cfg.kafka_brokers, topic=cfg.kafka_topic,
                    group=cfg.kafka_group, security=cfg.kafka_security, ingest_minutes=cfg.kafka_ingest_minutes, live_folder=self.live_folder(),
                    pending=sorted(self.pending), recent=list(self.recent)[::-1], **self.stats)

    # -------------------------------------------------------------- inti (dapat diuji tanpa broker)
    def handle(self, records, spool):
        """records: [(value, timestamp_ms, partition, offset)]."""
        prefix = self.ctx.cfg.upstream_prefix
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
        if not self.pending or (not force and now - last < self.ctx.cfg.kafka_ingest_minutes * 60): return False
        ing = self.ctx.ingest
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
        cfg, kc, wait = self.ctx.cfg, self.ctx.kafka_client, 5
        spool = self.ctx.inbox(cfg.inbox_dir)
        while not self._stop.is_set():
            c = None
            try:
                self.stats.update(state='menyambung', error=None)
                c = kc.consumer(cfg)
                self.stats.update(state='berjalan', since=datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None).isoformat(timespec='seconds'))
                wait, last_flush = 5, time.time()
                while not self._stop.is_set():
                    for recs in c.poll(timeout_ms=1000): self.handle(recs, spool)
                    if spool.n and (spool.n >= FLUSH_LINES or time.time() - last_flush >= FLUSH_SECONDS):
                        self.flush(spool); c.commit(); last_flush = time.time()
                    elif not spool.n: last_flush = time.time()
                    self.maybe_ingest()
                if spool.n: self.flush(spool); c.commit()
            except Exception as e:   # noqa: BLE001  broker mati / sandi salah: status + coba lagi berkala
                f = kc.error(e)
                self.stats.update(state='galat', error=f'[{f.code}] {f.message}')
                self._stop.wait(wait); wait = min(wait * 2, 120)
            finally:
                if c is not None:
                    try: c.close()
                    except Exception: pass   # noqa: BLE001
        self.stats['state'] = 'mati'
