"""Impor folder log dari S3 (TRD §3.8, Tahap 19) dan sinkron otomatis dari folder induk S3 (permintaan pemilik
2026-10-07). Satu impor pada satu waktu, di thread latar: unduh (ctx.s3) lalu ingest folder itu (ctx.ingest)."""
import datetime, threading

from monishield.application import settings_service
from monishield.application.ingest_service import now
from monishield.domain import s3_import
from monishield.domain.errors import Busy, Fail
from monishield.domain.s3_import import ImportFail

WATCH_MINUTES = (5, 15, 30, 60, 180, 360, 720, 1440)
SYNC_BY = '(sinkron S3 otomatis)'


class ImportService:
    """Rencana objek per job disimpan di memori (20 terakhir); riwayat job di basis data akun (ctx.auth)."""

    def __init__(self, ctx):
        self.ctx, self._lock = ctx, threading.Lock()
        self.state = dict(running=False, job_id=None, phase=None, done=0, total=0, mode=None)   # mode: 'manual' (tautan) / 'sync' (otomatis)
        self.plans, self.thread = {}, None   # job_id -> hasil unduhan
        self.watch = dict(last=None, next_check=None)   # sinkron otomatis: hasil putaran terakhir, jadwal berikutnya (UTC)

    @property
    def creds(self): return self.ctx.s3.creds   # kredensial yang ditempel admin (memori proses) + .env

    def _claim(self, phase, mode):
        with self._lock:
            if self.state['running']: raise Busy('Impor lain sedang berjalan; tunggu sampai selesai.', 'import_running')
            self.state.update(running=True, job_id=None, phase=phase, done=0, total=0, mode=mode)

    # -------------------------------------------------------------- impor satu tautan
    def start(self, url, dry_run, by):
        bucket, prefix, folder = s3_import.parse_url(self.ctx.cfg, url)   # tautan diperiksa sebelum ada koneksi ke AWS
        self.ctx.s3.ready()
        self._claim('list', 'manual')
        try: job = self.ctx.auth.job_create(by, bucket, prefix, folder, 'dry_run' if dry_run else 'running')
        except BaseException: self.state.update(running=False, phase=None); raise
        self.state['job_id'] = job
        self.thread = threading.Thread(target=self._run, args=(job, url, dry_run), name='import', daemon=True)
        self.thread.start()
        return job

    def _progress(self, phase, **k): self.state.update(phase=phase, **{x: k[x] for x in ('done', 'total') if x in k})

    def _run(self, job, url, dry_run):
        try: self._job(job, url, dry_run)
        finally: self.state.update(running=False, phase=None)

    def _job(self, job, url, dry_run):
        """Satu job impor (unduh lalu ingest folder itu). -> True bila selesai tanpa galat; galat dicatat di job."""
        auth = self.ctx.auth
        try:
            r = self.ctx.s3.run(url, dry_run=dry_run, progress=self._progress)
            msg = f"{r['take']} objek {'akan diambil' if dry_run else 'diambil'}, {r['skipped']} dilewati"
            if r.get('extracted'): msg += f", {r['extracted']} .gz diekstrak menjadi .log"
            if not dry_run:
                self.state['phase'] = 'ingest'
                ing = self.ctx.ingest.run_blocking(r['folder'], f'impor #{job}')
                r['ingest'] = {k: ing[k] for k in ('run_id', 'status', 'files_changed', 'files_failed')}
                msg += f"; ingest #{ing['run_id']}: {ing['files_changed']} file berubah"
            msg += ''.join(f'; {w}' for w in r['warnings'])
            self._keep(job, r)
            auth.job_finish(job, 'dry_run' if dry_run else 'done', r['bytes'] if dry_run else r['downloaded_bytes'],
                            r['take'] if dry_run else r['downloaded'], r['skipped'], msg)
            return True
        except ImportFail as e:
            self._keep(job, dict(error=dict(code=e.code, message=e.message)))
            auth.job_finish(job, 'failed', message=f'[{e.code}] {e.message}')   # kode di depan: tampilan menerjemahkannya (EN)
        except Exception as e:  # noqa: BLE001  galat dilaporkan lewat status job; tanpa rahasia (pesan boto tidak memuat kunci)
            self._keep(job, dict(error=dict(code='import_failed', message=f'{type(e).__name__}: {e}'[:500])))
            auth.job_finish(job, 'failed', message=f'[import_failed] {type(e).__name__}: {e}'[:500])
        return False

    def _keep(self, job, r):
        self.plans[job] = r
        for old in sorted(self.plans)[:-20]: self.plans.pop(old, None)

    def job(self, job_id):
        j = self.ctx.auth.job_get(job_id)
        if not j: raise Fail('not_found', 'Job impor tidak ditemukan.', 404)
        live = self.state if self.state['job_id'] == job_id and self.state['running'] else None
        return dict(j, running=bool(live), progress=live, result=self.plans.get(job_id))

    # -------------------------------------------------------------- sinkron otomatis dari awalan induk S3 (S4_S3_WATCH)
    def watch_config(self):
        """Setelan sinkron yang berlaku (.env: S4_S3_WATCH, S4_S3_WATCH_MINUTES, S4_S3_WATCH_ENABLED; layar menulis ke sana).
        -> dict(url, minutes, enabled, source='file'|'environment'|None)"""
        cfg = self.ctx.cfg
        return dict(url=cfg.s3_watch, minutes=cfg.s3_watch_minutes, enabled=cfg.s3_watch_enabled and bool(cfg.s3_watch),
                    source=settings_service.source(self.ctx, 's3_watch'))

    def watch_sources(self):
        """-> (daftar s3://… yang dipantau, pesan galat konfigurasi atau None). Kosong bila sinkron dimatikan."""
        w = self.watch_config()
        if not w['enabled']: return [], None
        try: return [f's3://{b}/{p}' for b, p in s3_import.parse_watch(self.ctx.cfg, w['url'])], None
        except ImportFail as e: return [], e.message

    def set_watch(self, url, minutes, enabled):
        """Simpan setelan dari layar (diperiksa dulu terhadap daftar izin, tanpa jaringan) lalu bangunkan penjadwal:
        bila aktif, pemeriksaan pertama berjalan beberapa detik kemudian."""
        url = (url or '').strip()
        if enabled:
            if not url: raise Fail('invalid_watch', 'Isi alamat folder induk S3, mis. s3://nama-bucket/k8s-logs/.', 400)
            try: s3_import.parse_watch(self.ctx.cfg, url)
            except ImportFail as e: raise Fail(e.code, e.message, 400) from None
        if minutes not in WATCH_MINUTES: raise Fail('invalid_parameter', f'Jeda harus salah satu dari {", ".join(map(str, WATCH_MINUTES))} menit.', 400)
        settings_service.write_watch(self.ctx, url, minutes, enabled)
        self._kick_loop()
        return self.watch_config()

    def sync(self, by):
        """Periksa folder induk S3 sekarang, di thread latar: folder tanggal yang belum dikenal diimpor + di-ingest."""
        w = self.watch_config()
        try: sources = s3_import.parse_watch(self.ctx.cfg, w['url']) if w['enabled'] else []
        except ImportFail as e: raise Fail(e.code, e.message, 400) from None
        if not sources: raise Fail('watch_disabled', 'Sinkron S3 otomatis belum aktif: isi alamat folder induk S3 di kartu Impor dari S3 (mis. s3://nama-bucket/k8s-logs/).', 400)
        self.ctx.s3.ready()
        self._claim('check', 'sync')
        self.thread = threading.Thread(target=self._sync, args=(sources, by), name='s3-sync', daemon=True)
        self.thread.start()

    def _known(self):
        """Folder yang sudah dikenal (basis data, diabaikan, folder log, kotak masuk) dan folder kotak masuk hasil S3."""
        w, lf = self.ctx.warehouse, self.ctx.logfolders
        known, ign = w.known_folders(), w.ignored()
        in_log, in_inbox = lf.dates()
        from_s3 = lf.from_s3(in_inbox) - ign - in_log
        return known | ign | in_log | in_inbox, from_s3

    def _sync(self, sources, by):
        cfg, auth, s3 = self.ctx.cfg, self.ctx.auth, self.ctx.s3
        res = dict(at=now(), by=by, sources=[], imported=[], rechecked=[], failed=[], waiting=0, errors=[])
        try:
            known, from_s3 = self._known()
            today = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=7)).date()   # tanggal folder = WIB
            seen, todo = set(), []
            for bucket, base in sources:
                try: folders = [f for f in s3.list_folders(bucket, base) if f not in seen]
                except Exception as e:  # noqa: BLE001
                    x = s3.error(e); res['errors'].append(dict(code=x.code, where=f's3://{bucket}/{base}', message=x.message)); continue
                seen.update(folders)
                take, again, waiting = s3_import.pick(folders, known, from_s3, today, cfg.s3_watch_days, cfg.s3_watch_recheck_days, cfg.s3_watch_max_folders)
                res['sources'].append(dict(source=f's3://{bucket}/{base}', folders=len(folders), new=len(take) + waiting))
                res['waiting'] += waiting
                todo += [(bucket, base, f, False) for f in take]
                for f in again:   # hasil sinkron yang masih baru: diunduh lagi hanya bila ada objek baru/berubah
                    try: p = s3.run(f's3://{bucket}/{base}{f}/', dry_run=True)
                    except ImportFail as e: res['errors'].append(dict(code=e.code, where=f, message=e.message)); continue
                    if p['take'] or any(o.get('extract_local') for o in p['objects']): todo.append((bucket, base, f, True))
            for i, (bucket, base, f, again) in enumerate(todo):
                self.state.update(phase='download', done=i, total=len(todo))
                job = auth.job_create(by, bucket, f'{base}{f}/', f, 'running')
                self.state['job_id'] = job
                ok = self._job(job, f's3://{bucket}/{base}{f}/', False)
                (res['failed'] if not ok else res['rechecked'] if again else res['imported']).append(f)
        except Exception as e:  # noqa: BLE001
            x = s3.error(e)
            res['errors'].append(dict(code=x.code, where=None, message=x.message))
        finally:
            self.watch['last'] = res
            self.state.update(running=False, phase=None, job_id=None)
            self.ctx.alerts.after_sync(res)

    def start_watch(self, first=60):
        """Penjadwal (selalu hidup; membaca setelan tiap putaran): pemeriksaan pertama `first` detik setelah server mulai,
        lalu tiap `minutes`. Setelan diubah dari layar -> dibangunkan, pemeriksaan berikutnya ±5 detik lagi."""
        self._kick, self._stopped = threading.Event(), False
        threading.Thread(target=self._watch_loop, args=(first,), name='s3-watch', daemon=True).start()

    def _kick_loop(self):
        if getattr(self, '_kick', None): self._kick.set()

    def _watch_loop(self, delay):
        while not self._stopped:
            w = self.watch_config()
            if not w['enabled'] or w['minutes'] <= 0:
                self.watch['next_check'] = None
                self._kick.wait(300); self._kick.clear(); delay = 5
                continue
            self.watch['next_check'] = now(delay)
            if self._kick.wait(delay):   # setelan berubah / server berhenti
                self._kick.clear(); delay = 5
                continue
            delay = w['minutes'] * 60
            try: self.sync(SYNC_BY)
            except Fail as e:
                if e.status == 409: delay = 300   # impor manual sedang berjalan: coba lagi 5 menit lagi
                else: self.watch['last'] = dict(at=now(), by=SYNC_BY, sources=[], imported=[], rechecked=[], failed=[], waiting=0,
                                                errors=[dict(code=e.code, where=None, message=e.message)])

    def stop_watch(self):
        self._stopped = True
        self._kick_loop()

    def wait(self, timeout=None):
        if self.thread: self.thread.join(timeout)

    # -------------------------------------------------------------- tampilan kartu impor
    def view(self):
        cfg = self.ctx.cfg
        sources, problem = self.watch_sources()
        w = self.watch_config()
        watch = dict(enabled=bool(sources), sources=sources, problem=problem, url=w['url'], minutes=w['minutes'], source=w['source'],
                     minute_options=WATCH_MINUTES, days=cfg.s3_watch_days, max_folders=cfg.s3_watch_max_folders, **self.watch)
        return dict(enabled=bool(cfg.import_buckets), library=self.ctx.s3.library_ok(), allowed=s3_import.allowed_examples(cfg), region=cfg.import_region,
                    credentials=self.creds.status(), running=self.state['running'], state=self.state, watch=watch)
