"""Pemicu ingest, penurunan ulang, dan penghapusan folder (TRD §5.5). Ingest berjalan DI DALAM proses API (K1)."""
import datetime, json, os, shutil
import threading
import time
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel

from monishield.infrastructure import db, importer, ingest
from monishield.domain import rules
from monishield.application import settings
from .common import DATE, ApiError, client_ip, require_admin, require_admin_or_job

router = APIRouter(prefix='/api/admin')


def _now(after_seconds=0):
    """Waktu UTC (tanpa zona, detik bulat) untuk status, seperti kolom waktu lain di API."""
    t = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None, microsecond=0) + datetime.timedelta(seconds=after_seconds)
    return str(t)


class IngestManager:
    """Menjalankan ingest di thread latar atas kursor DuckDB milik proses ini; satu pada satu waktu."""

    def __init__(self, app):
        self.app, self._lock, self.thread = app, threading.Lock(), None
        self.state = dict(running=False, phase=None, done=0, total=0, folder=None, started_by=None, last=None, error=None)

    def start(self, folder=None, force=False, by=None):
        with self._lock:
            if self.state['running']: raise ApiError(409, 'ingest_running', 'Ingest sedang berjalan.')
            self.state.update(running=True, phase='pindai', done=0, total=0, folder=folder, started_by=by, error=None)
        self.thread = threading.Thread(target=self._run, args=(folder, force), name='ingest', daemon=True)
        self.thread.start()

    def run_blocking(self, folder, by, wait_seconds=1800):
        """Jalankan ingest satu folder di thread pemanggil (impor S3), setelah ingest lain selesai. -> ringkasan."""
        t0 = time.time()
        while True:
            with self._lock:
                if not self.state['running']:
                    self.state.update(running=True, phase='pindai', done=0, total=0, folder=folder, started_by=by, error=None); break
            if time.time() - t0 > wait_seconds: raise ApiError(409, 'ingest_running', 'Ingest lain tidak selesai-selesai.')
            time.sleep(1)
        self._run(folder, False)
        if self.state['error']: raise RuntimeError(self.state['error'])
        return self.state['last']

    def _progress(self, phase, **k): self.state.update(phase=phase, **{x: k[x] for x in ('done', 'total', 'folder') if x in k})

    def _run(self, folder, force):
        cur = self.app.state.con.cursor()
        try:
            r = ingest.run(self.app.state.cfg, cur, folder=folder, force=force, progress=self._progress)
            self.state['last'] = {k: r[k] for k in ('run_id', 'status', 'files_seen', 'files_changed', 'files_parsed', 'files_removed', 'files_failed',
                                                    'folders_changed', 'folders_recorrelated', 'warnings', 'seconds')}
            _snapshot(self.app, cur)
            self.app.state.alerts.after_ingest(r)   # notifikasi (thread latar; tidak menahan ingest)
        except ingest.Busy: self.state['error'] = 'Ingest lain sedang berjalan.'
        except Exception as e:  # noqa: BLE001  galat dilaporkan lewat status, proses API tetap hidup
            self.state['error'] = f'{type(e).__name__}: {e}'
            self.app.state.alerts.after_ingest(None, self.state['error'])
        finally:
            cur.close(); self.state.update(running=False, phase=None)

    def wait(self, timeout=None):
        if self.thread: self.thread.join(timeout)


class IngestBody(BaseModel):
    folder: Optional[str] = None
    force: bool = False


class FolderBody(BaseModel):
    folder: Optional[str] = None


def _folder(value, required=False):
    if value is None and not required: return None
    if not isinstance(value, str) or not DATE.fullmatch(value): raise ApiError(400, 'invalid_parameter', 'folder harus berbentuk YYYY-MM-DD.')
    return value


def _audit(request, who, action, detail):
    request.app.state.auth.audit(action, getattr(request.state, 'user', None), f"{detail or ''} oleh {who['username']}".strip(), client_ip(request))


@router.post('/ingest', status_code=202)
def start_ingest(request: Request, body: IngestBody = IngestBody(), who=Depends(require_admin_or_job)):
    folder = _folder(body.folder)
    request.app.state.ingest.start(folder, body.force, who['username'])
    _audit(request, who, 'ingest.start', f"folder={folder or 'semua'} force={body.force}")
    return dict(started=True)


@router.get('/ingest/status')
def ingest_status(request: Request, who=Depends(require_admin_or_job)):
    """Status di memori + ingest terakhir yang selesai dari database (bertahan setelah server dimulai ulang; waktu UTC)."""
    cur = request.app.state.con.cursor()
    try:
        r = cur.execute("""SELECT started_at, finished_at, status, files_seen, files_changed, message FROM ingest_run
                          WHERE finished_at IS NOT NULL ORDER BY run_id DESC LIMIT 1""").fetchone()
    finally: cur.close()
    last_run = r and dict(started_at=str(r[0].replace(microsecond=0)), finished_at=str(r[1].replace(microsecond=0)), status=r[2], files_seen=r[3], files_changed=r[4],
                          warnings=json.loads(r[5]) if r[5] else [])
    m = request.app.state.imports
    last = m.watch.get('last') or {}
    s3 = dict(enabled=bool(m.watch_sources()[0]), running=bool(m.state['running'] and m.state.get('mode') == 'sync'), phase=m.state['phase'],
              done=m.state['done'], total=m.state['total'], last_at=last.get('at'), last_imported=last.get('imported', []) + last.get('rechecked', []),
              last_errors=last.get('errors', []))   # untuk tombol Sinkronkan data di kepala halaman
    return dict(request.app.state.ingest.state, last_run=last_run, new_folders=_new_folders(request),
                snapshot_error=getattr(request.app.state, 'snapshot_error', None), s3=s3)


def _snapshot(app, cur):
    """Perbarui salinan baca DuckDB untuk DbGate (bila S4_DUCKDB_SNAPSHOT). Gagal -> dicatat di status, ingest tetap sukses."""
    if not app.state.cfg.duckdb_snapshot: return
    try: db.snapshot(cur, app.state.cfg); app.state.snapshot_error = None
    except Exception as e: app.state.snapshot_error = f'{type(e).__name__}: {e}'   # noqa: BLE001


def _new_folders(request):
    """Folder tanggal (YYYY-MM-DD) di folder log / kotak masuk yang belum ada di basis data. Hanya daftar isi direktori
    teratas (murah, dipanggil tombol Sinkronkan tiap menit); file baru di folder lama baru terlihat saat ingest berjalan."""
    cfg = request.app.state.cfg
    cur = request.app.state.con.cursor()
    try: dikenal = {str(r[0]) for r in cur.execute('SELECT folder FROM folder_state').fetchall()} | ingest.ignored(cur)
    finally: cur.close()
    baru = set()
    for root in (cfg.log_dir, cfg.inbox_dir):
        try: calon = [d for d in os.listdir(root) if rules.DATE_DIR.fullmatch(d) and d not in dikenal and d not in baru]
        except OSError: continue
        for d in calon:   # hanya folder yang berisi file log (folder kosong tidak akan pernah masuk basis data)
            if any(n.endswith(('.log', '.log.gz')) for _, _, names in os.walk(os.path.join(root, d)) for n in names): baru.add(d)
    return sorted(baru)


def _exclusive(request, fn):
    """derive/forget tidak boleh berjalan bersamaan dengan ingest."""
    if request.app.state.ingest.state['running'] or not ingest._lock.acquire(blocking=False):
        raise ApiError(409, 'ingest_running', 'Ingest sedang berjalan; coba lagi setelah selesai.')
    cur = request.app.state.con.cursor()
    try: return fn(cur)
    finally: cur.close(); ingest._lock.release()


@router.post('/derive')
def derive(request: Request, body: FolderBody = FolderBody(), admin=Depends(require_admin)):
    folder = _folder(body.folder)
    done = _exclusive(request, lambda cur: ingest.derive_all(cur, folder))
    _audit(request, admin, 'derive', f"folder={folder or 'semua'}")
    return dict(folders=done)


class DeleteBody(BaseModel):
    delete_inbox: bool = True   # hapus juga file log di kotak masuk (hasil impor S3); folder log utama tidak pernah dihapus


def _on_disk(cfg, root, folder):
    p = os.path.join(root, folder)
    return os.path.isdir(p) and any(n.endswith(('.log', '.log.gz')) for _, _, names in os.walk(p) for n in names)


@router.get('/folders')
def folders_list(request: Request, admin=Depends(require_admin)):
    """Kelola folder (permintaan pemilik 2026-10-07): semua folder yang dikenal dashboard, di disk, atau diabaikan."""
    cfg, cur = request.app.state.cfg, request.app.state.con.cursor()
    try:
        db = {str(f): dict(lines=l, files=n, files_corrupt=c) for f, l, n, c in cur.execute('SELECT folder, lines, files, files_corrupt FROM folder_state').fetchall()}
        ign = {f: dict(by=b, at=str(a.replace(microsecond=0)) if a else None) for f, b, a in cur.execute('SELECT ignored_folder, by_user, at_utc FROM folder_ignored').fetchall()}
    finally: cur.close()
    disk = set()
    for root in (cfg.log_dir, cfg.inbox_dir):
        try: disk |= {d for d in os.listdir(root) if rules.DATE_DIR.fullmatch(d)}
        except OSError: pass
    rows = []
    for f in sorted(set(db) | set(ign) | disk, reverse=True):
        log, inbox = _on_disk(cfg, cfg.log_dir, f), _on_disk(cfg, cfg.inbox_dir, f)
        if f not in db and f not in ign and not (log or inbox): continue   # folder tanggal kosong di disk
        rows.append(dict(folder=f, in_db=f in db, **(db.get(f) or dict(lines=0, files=0, files_corrupt=0)), log=log, inbox=inbox,
                         ignored=f in ign, ignored_by=(ign.get(f) or {}).get('by'), ignored_at=(ign.get(f) or {}).get('at')))
    return dict(rows=rows, log_dir_readonly=True)


@router.post('/folders/{folder}/delete')
def folder_delete(folder: str, request: Request, body: DeleteBody = DeleteBody(), admin=Depends(require_admin)):
    """Hapus data folder dari dashboard. File di kotak masuk ikut dihapus bila diminta; folder log utama hanya dibaca,
    jadi bila filenya masih ada (atau sinkron S3 otomatis aktif) folder itu dicatat "diabaikan" agar ingest/sinkronisasi
    tidak memasukkannya lagi."""
    folder, cfg = _folder(folder, required=True), request.app.state.cfg
    inbox = os.path.realpath(os.path.join(cfg.inbox_dir, folder))
    if os.path.dirname(inbox) != os.path.realpath(cfg.inbox_dir): raise ApiError(400, 'invalid_parameter', 'folder tidak sah.')

    def kerja(cur):
        n = ingest.forget(cur, folder)
        hapus_inbox = body.delete_inbox and os.path.isdir(inbox)
        if hapus_inbox: shutil.rmtree(inbox)
        # masih ada di disk, atau sinkron S3 otomatis aktif (folder akan diunduh lagi dari S3): dicatat "diabaikan"
        sisa = _on_disk(cfg, cfg.log_dir, folder) or _on_disk(cfg, cfg.inbox_dir, folder) or request.app.state.imports.watch_config()['enabled']
        if sisa:
            cur.execute('INSERT OR REPLACE INTO folder_ignored VALUES (?, ?, ?)', [folder, admin['username'], datetime.datetime.now(datetime.UTC).replace(tzinfo=None)])
        return n, hapus_inbox, sisa
    n, hapus_inbox, sisa = _exclusive(request, lambda cur: (kerja(cur), _snapshot(request.app, cur))[0])
    if not n and not hapus_inbox and not sisa: raise ApiError(404, 'not_found', 'Folder tidak ditemukan.')
    _audit(request, admin, 'folder.delete', f"folder={folder} ({n} file data{'; kotak masuk dihapus' if hapus_inbox else ''}{'; diabaikan' if sisa else ''})")
    return dict(folder=folder, files=n, inbox_deleted=hapus_inbox, ignored=sisa)


@router.post('/folders/{folder}/restore')
def folder_restore(folder: str, request: Request, admin=Depends(require_admin)):
    """Batalkan "diabaikan": ingest/sinkronisasi berikutnya memasukkan folder itu lagi."""
    folder = _folder(folder, required=True)
    cur = request.app.state.con.cursor()
    try:
        if not cur.execute('SELECT 1 FROM folder_ignored WHERE ignored_folder = ?', [folder]).fetchone(): raise ApiError(404, 'not_found', 'Folder tidak sedang diabaikan.')
        cur.execute('DELETE FROM folder_ignored WHERE ignored_folder = ?', [folder])
    finally: cur.close()
    _audit(request, admin, 'folder.restore', f'folder={folder}')
    return dict(folder=folder, restored=True)


@router.post('/forget')
def forget(body: FolderBody, request: Request, admin=Depends(require_admin)):
    folder = _folder(body.folder, required=True)
    n = _exclusive(request, lambda cur: ingest.forget(cur, folder))
    if not n: raise ApiError(404, 'not_found', 'Folder tidak ditemukan.')
    _audit(request, admin, 'forget', f'folder={folder} ({n} file)')
    return dict(folder=folder, files=n)


# ------------------------------------------------------------------ impor S3 (TRD §3.8, Tahap 19)
class ImportManager:
    """Satu impor pada satu waktu, di thread latar: unduh (importer) lalu ingest folder itu. Rencana objek per job disimpan di memori."""

    def __init__(self, app):
        self.app, self._lock = app, threading.Lock()
        self.creds = importer.Credentials(app.state.cfg)
        self.state = dict(running=False, job_id=None, phase=None, done=0, total=0, mode=None)   # mode: 'manual' (tautan) / 'sync' (otomatis)
        self.plans, self.thread = {}, None   # job_id -> hasil importer.run (dibatasi 20 terakhir)
        self.watch = dict(last=None, next_check=None)   # sinkron otomatis: hasil putaran terakhir, jadwal berikutnya (UTC)

    def start(self, url, dry_run, by):
        cfg = self.app.state.cfg
        try: bucket, prefix, folder = importer.parse_url(cfg, url)          # tautan diperiksa sebelum ada koneksi ke AWS
        except importer.ImportFail as e: raise ApiError(e.status, e.code, e.message) from None
        if not importer.library_ok(): raise ApiError(400, 'no_s3_library', importer.NO_LIBRARY)
        if not self.creds.get()[0]: raise ApiError(400, 'no_credentials', importer.NO_CREDENTIALS)
        with self._lock:
            if self.state['running']: raise ApiError(409, 'import_running', 'Impor lain sedang berjalan; tunggu sampai selesai.')
            self.state.update(running=True, job_id=None, phase='daftar', done=0, total=0, mode='manual')
        try: job = self.app.state.auth.job_create(by, bucket, prefix, folder, 'coba' if dry_run else 'berjalan')
        except BaseException: self.state.update(running=False, phase=None); raise
        self.state['job_id'] = job
        self.thread = threading.Thread(target=self._run, args=(job, url, dry_run, by), name='import', daemon=True)
        self.thread.start()
        return job

    def _progress(self, phase, **k): self.state.update(phase=phase, **{x: k[x] for x in ('done', 'total') if x in k})

    def _run(self, job, url, dry_run, by):
        try: self._job(job, url, dry_run)
        finally: self.state.update(running=False, phase=None)

    def _job(self, job, url, dry_run):
        """Satu job impor (unduh lalu ingest folder itu). -> True bila selesai tanpa galat; galat dicatat di job."""
        auth, cfg = self.app.state.auth, self.app.state.cfg
        try:
            r = importer.run(cfg, url, self.creds, dry_run=dry_run, progress=self._progress)
            msg = f"{r['take']} objek {'akan diambil' if dry_run else 'diambil'}, {r['skipped']} dilewati"
            if r.get('extracted'): msg += f", {r['extracted']} .gz diekstrak menjadi .log"
            if not dry_run:
                self.state['phase'] = 'ingest'
                ing = self.app.state.ingest.run_blocking(r['folder'], f'impor #{job}')
                r['ingest'] = {k: ing[k] for k in ('run_id', 'status', 'files_changed', 'files_failed')}
                msg += f"; ingest #{ing['run_id']}: {ing['files_changed']} file berubah"
            msg += ''.join(f'; {w}' for w in r['warnings'])
            self._keep(job, r)
            auth.job_finish(job, 'coba' if dry_run else 'selesai', r['bytes'] if dry_run else r['downloaded_bytes'],
                            r['take'] if dry_run else r['downloaded'], r['skipped'], msg)
            return True
        except importer.ImportFail as e:
            self._keep(job, dict(error=dict(code=e.code, message=e.message)))
            auth.job_finish(job, 'gagal', message=f'[{e.code}] {e.message}')   # kode di depan: tampilan menerjemahkannya (EN)
        except Exception as e:  # noqa: BLE001  galat dilaporkan lewat status job; tanpa rahasia (pesan boto tidak memuat kunci)
            self._keep(job, dict(error=dict(code='import_failed', message=f'{type(e).__name__}: {e}'[:500])))
            auth.job_finish(job, 'gagal', message=f'[import_failed] {type(e).__name__}: {e}'[:500])
        return False

    # -------------------------------------------------------------- sinkron otomatis dari awalan induk S3 (S4_S3_WATCH)
    def watch_config(self):
        """Setelan sinkron yang berlaku (.env: S4_S3_WATCH, S4_S3_WATCH_MINUTES, S4_S3_WATCH_ENABLED; layar menulis ke sana).
        -> dict(url, minutes, enabled, source='file'|'environment'|None)"""
        cfg = self.app.state.cfg
        return dict(url=cfg.s3_watch, minutes=cfg.s3_watch_minutes, enabled=cfg.s3_watch_enabled and bool(cfg.s3_watch),
                    source=settings.source('s3_watch', settings.file_values(self.app)))

    def watch_sources(self):
        """-> (daftar s3://… yang dipantau, pesan galat konfigurasi atau None). Kosong bila sinkron dimatikan."""
        w = self.watch_config()
        if not w['enabled']: return [], None
        try: return [f's3://{b}/{p}' for b, p in importer.parse_watch(self.app.state.cfg, w['url'])], None
        except importer.ImportFail as e: return [], e.message

    def set_watch(self, url, minutes, enabled, by):
        """Simpan setelan dari layar (diperiksa dulu terhadap daftar izin, tanpa jaringan) lalu bangunkan penjadwal:
        bila aktif, pemeriksaan pertama berjalan beberapa detik kemudian."""
        url = (url or '').strip()
        if enabled:
            if not url: raise ApiError(400, 'invalid_watch', 'Isi alamat folder induk S3, mis. s3://nama-bucket/k8s-logs/.')
            try: importer.parse_watch(self.app.state.cfg, url)
            except importer.ImportFail as e: raise ApiError(400, e.code, e.message) from None
        if minutes not in WATCH_MINUTES: raise ApiError(400, 'invalid_parameter', f'Jeda harus salah satu dari {", ".join(map(str, WATCH_MINUTES))} menit.')
        try: settings.write_watch(self.app, url, minutes, enabled)
        except settings.SettingsFail as e: raise ApiError(400, e.code, str(e)) from None
        self._kick_loop()
        return self.watch_config()

    def sync(self, by):
        """Periksa folder induk S3 sekarang, di thread latar: folder tanggal yang belum dikenal diimpor + di-ingest."""
        cfg, w = self.app.state.cfg, self.watch_config()
        try: sources = importer.parse_watch(cfg, w['url']) if w['enabled'] else []
        except importer.ImportFail as e: raise ApiError(400, e.code, e.message) from None
        if not sources: raise ApiError(400, 'watch_disabled', 'Sinkron S3 otomatis belum aktif: isi alamat folder induk S3 di kartu Impor dari S3 (mis. s3://nama-bucket/k8s-logs/).')
        if not importer.library_ok(): raise ApiError(400, 'no_s3_library', importer.NO_LIBRARY)
        if not self.creds.get()[0]: raise ApiError(400, 'no_credentials', importer.NO_CREDENTIALS)
        with self._lock:
            if self.state['running']: raise ApiError(409, 'import_running', 'Impor lain sedang berjalan; tunggu sampai selesai.')
            self.state.update(running=True, job_id=None, phase='periksa', done=0, total=0, mode='sync')
        self.thread = threading.Thread(target=self._sync, args=(sources, by), name='s3-sync', daemon=True)
        self.thread.start()

    def _known(self):
        """Folder yang sudah dikenal (basis data, diabaikan, folder log, kotak masuk) dan folder kotak masuk hasil S3."""
        cfg, cur = self.app.state.cfg, self.app.state.con.cursor()
        try:
            known = {str(r[0]) for r in cur.execute('SELECT folder FROM folder_state').fetchall()}
            ign = ingest.ignored(cur)
        finally: cur.close()
        dirs = {}
        for root in (cfg.log_dir, cfg.inbox_dir):
            try: dirs[root] = {d for d in os.listdir(root) if rules.DATE_DIR.fullmatch(d)}
            except OSError: dirs[root] = set()
        from_s3 = {d for d in dirs[cfg.inbox_dir] if os.path.exists(os.path.join(cfg.inbox_dir, d, importer.MANIFEST))} - ign - dirs[cfg.log_dir]
        return known | ign | dirs[cfg.log_dir] | dirs[cfg.inbox_dir], from_s3

    def _sync(self, sources, by):
        cfg, auth = self.app.state.cfg, self.app.state.auth
        res = dict(at=_now(), by=by, sources=[], imported=[], rechecked=[], failed=[], waiting=0, errors=[])
        try:
            s3 = importer._client(cfg, self.creds.get()[0])
            known, from_s3 = self._known()
            today = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=7)).date()   # tanggal folder = WIB
            seen, todo = set(), []
            for bucket, base in sources:
                try: folders = [f for f in importer.list_folders(s3, bucket, base) if f not in seen]
                except Exception as e:  # noqa: BLE001
                    x = importer._s3_error(e); res['errors'].append(dict(code=x.code, where=f's3://{bucket}/{base}', message=x.message)); continue
                seen.update(folders)
                take, again, waiting = importer.pick(folders, known, from_s3, today, cfg.s3_watch_days, cfg.s3_watch_recheck_days, cfg.s3_watch_max_folders)
                res['sources'].append(dict(source=f's3://{bucket}/{base}', folders=len(folders), new=len(take) + waiting))
                res['waiting'] += waiting
                todo += [(bucket, base, f, False) for f in take]
                for f in again:   # hasil sinkron yang masih baru: diunduh lagi hanya bila ada objek baru/berubah
                    try: p = importer.run(cfg, f's3://{bucket}/{base}{f}/', self.creds, dry_run=True)
                    except importer.ImportFail as e: res['errors'].append(dict(code=e.code, where=f, message=e.message)); continue
                    if p['take'] or any(o.get('extract_local') for o in p['objects']): todo.append((bucket, base, f, True))
            for i, (bucket, base, f, again) in enumerate(todo):
                self.state.update(phase='unduh', done=i, total=len(todo))
                job = auth.job_create(by, bucket, f'{base}{f}/', f, 'berjalan')
                self.state['job_id'] = job
                ok = self._job(job, f's3://{bucket}/{base}{f}/', False)
                (res['failed'] if not ok else res['rechecked'] if again else res['imported']).append(f)
        except Exception as e:  # noqa: BLE001
            x = e if isinstance(e, importer.ImportFail) else importer._s3_error(e)
            res['errors'].append(dict(code=x.code, where=None, message=x.message))
        finally:
            self.watch['last'] = res
            self.state.update(running=False, phase=None, job_id=None)
            self.app.state.alerts.after_sync(res)

    def start_watch(self, first=60):
        """Penjadwal (selalu hidup; membaca setelan tiap putaran): pemeriksaan pertama `first` detik setelah server mulai,
        lalu tiap `minutes`. Setelan diubah dari layar -> dibangunkan, pemeriksaan berikutnya ±5 detik lagi."""
        self._kick, self._stopped = threading.Event(), False
        threading.Thread(target=self._watch_loop, args=(first,), name='s3-watch', daemon=True).start()

    def _kick_loop(self):
        if getattr(self, '_kick', None): self._kick.set()

    def _watch_loop(self, delay):
        by = '(sinkron S3 otomatis)'
        while not self._stopped:
            w = self.watch_config()
            if not w['enabled'] or w['minutes'] <= 0:
                self.watch['next_check'] = None
                self._kick.wait(300); self._kick.clear(); delay = 5
                continue
            self.watch['next_check'] = _now(delay)
            if self._kick.wait(delay):   # setelan berubah / server berhenti
                self._kick.clear(); delay = 5
                continue
            delay = w['minutes'] * 60
            try: self.sync(by)
            except ApiError as e:
                if e.status_code == 409: delay = 300   # impor manual sedang berjalan: coba lagi 5 menit lagi
                else: self.watch['last'] = dict(at=_now(), by=by, sources=[], imported=[], rechecked=[], failed=[], waiting=0, errors=[dict(code=e.detail['code'], where=None, message=e.detail['message'])])

    def stop_watch(self):
        self._stopped = True
        self._kick_loop()

    def _keep(self, job, r):
        self.plans[job] = r
        for old in sorted(self.plans)[:-20]: self.plans.pop(old, None)

    def wait(self, timeout=None):
        if self.thread: self.thread.join(timeout)


WATCH_MINUTES = (5, 15, 30, 60, 180, 360, 720, 1440)


class WatchBody(BaseModel):
    url: str = ''
    minutes: int = 60
    enabled: bool = True


class ImportBody(BaseModel):
    url: str = ''
    dry_run: bool = False


class CredBody(BaseModel):
    access_key_id: str = ''
    secret_access_key: str = ''
    session_token: str = ''


def _import_view(request):
    m, cfg = request.app.state.imports, request.app.state.cfg
    sources, problem = m.watch_sources()
    w = m.watch_config()
    watch = dict(enabled=bool(sources), sources=sources, problem=problem, url=w['url'], minutes=w['minutes'], source=w['source'],
                 minute_options=WATCH_MINUTES, days=cfg.s3_watch_days,
                 max_folders=cfg.s3_watch_max_folders, **m.watch)
    return dict(enabled=bool(cfg.import_buckets), library=importer.library_ok(), allowed=importer.allowed_examples(cfg), region=cfg.import_region,
                credentials=m.creds.status(), running=m.state['running'], state=m.state, watch=watch)


@router.post('/import', status_code=202)
def start_import(request: Request, body: ImportBody = ImportBody(), who=Depends(require_admin_or_job)):
    job = request.app.state.imports.start(body.url, body.dry_run, who['username'])
    _audit(request, who, 'import.start', f"#{job} {body.url[:300]}{' (coba)' if body.dry_run else ''}")
    return dict(job_id=job)


@router.put('/import/watch')
def set_watch(body: WatchBody, request: Request, admin=Depends(require_admin)):
    """Atur sinkron S3 otomatis dari layar: alamat folder induk (s3://bucket/awalan/), jeda, aktif/mati. Admin saja."""
    w = request.app.state.imports.set_watch(body.url, body.minutes, body.enabled, admin['username'])
    _audit(request, admin, 'import.watch', f"{'aktif' if w['enabled'] else 'mati'}: {w['url'][:300]} tiap {w['minutes']} menit")
    return _import_view(request)['watch']


@router.post('/import/sync', status_code=202)
def sync_s3(request: Request, who=Depends(require_admin_or_job)):
    """Periksa awalan S4_S3_WATCH sekarang (tombol "Periksa S3 sekarang", atau cron dengan token mesin)."""
    request.app.state.imports.sync(who['username'])
    _audit(request, who, 'import.sync', 'periksa folder baru di S3')
    return dict(started=True)


@router.get('/import')
def import_overview(request: Request, limit: int = Query(20, ge=1, le=100), admin=Depends(require_admin)):
    return dict(_import_view(request), jobs=request.app.state.auth.job_list(limit))


@router.get('/import/{job_id}')
def import_job(job_id: int, request: Request, who=Depends(require_admin_or_job)):
    m = request.app.state.imports
    j = request.app.state.auth.job_get(job_id)
    if not j: raise ApiError(404, 'not_found', 'Job impor tidak ditemukan.')
    live = m.state if m.state['job_id'] == job_id and m.state['running'] else None
    return dict(j, running=bool(live), progress=live, result=m.plans.get(job_id))


@router.post('/import/credentials')
def set_credentials(body: CredBody, request: Request, admin=Depends(require_admin)):
    """Hanya admin bersesi (bukan token mesin). Nilai disimpan di memori proses saja dan tidak pernah dikembalikan."""
    try: request.app.state.imports.creds.set(body.access_key_id, body.secret_access_key, body.session_token)
    except importer.ImportFail as e: raise ApiError(e.status, e.code, e.message) from None
    _audit(request, admin, 'import.credentials.set', 'kredensial sementara ditempel (memori)')
    return dict(credentials=request.app.state.imports.creds.status())


@router.delete('/import/credentials')
def clear_credentials(request: Request, admin=Depends(require_admin)):
    request.app.state.imports.creds.clear()
    _audit(request, admin, 'import.credentials.clear', 'kredensial sementara dihapus')
    return dict(credentials=request.app.state.imports.creds.status())
