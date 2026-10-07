"""Ingest dan pengelolaan folder (TRD §3, §5.5). Ingest berjalan DI DALAM proses server (K1), satu pada satu waktu, di
thread latar; derive/hapus folder memegang kunci yang sama sehingga tidak bersamaan dengan ingest."""
import datetime, threading, time

from monishield.domain.errors import Busy, Fail


def now(after_seconds=0):
    """Waktu UTC (tanpa zona, detik bulat) untuk status, seperti kolom waktu lain di API."""
    t = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None, microsecond=0) + datetime.timedelta(seconds=after_seconds)
    return str(t)


class IngestService:
    """Menjalankan ingest (ctx.warehouse) di thread latar; satu pada satu waktu. Sesudahnya: salinan baca + notifikasi."""

    def __init__(self, ctx):
        self.ctx, self._lock, self.thread = ctx, threading.Lock(), None
        self.state = dict(running=False, phase=None, done=0, total=0, folder=None, started_by=None, last=None, error=None)

    def start(self, folder=None, force=False, by=None):
        with self._lock:
            if self.state['running']: raise Busy('Ingest sedang berjalan.')
            self.state.update(running=True, phase='scan', done=0, total=0, folder=folder, started_by=by, error=None)
        self.thread = threading.Thread(target=self._run, args=(folder, force), name='ingest', daemon=True)
        self.thread.start()

    def run_blocking(self, folder, by, wait_seconds=1800):
        """Jalankan ingest satu folder di thread pemanggil (impor S3, unggah), setelah ingest lain selesai. -> ringkasan."""
        t0 = time.time()
        while True:
            with self._lock:
                if not self.state['running']:
                    self.state.update(running=True, phase='scan', done=0, total=0, folder=folder, started_by=by, error=None); break
            if time.time() - t0 > wait_seconds: raise Busy('Ingest lain tidak selesai-selesai.')
            time.sleep(1)
        self._run(folder, False)
        if self.state['error']: raise RuntimeError(self.state['error'])
        return self.state['last']

    def _progress(self, phase, **k): self.state.update(phase=phase, **{x: k[x] for x in ('done', 'total', 'folder') if x in k})

    def _run(self, folder, force):
        try:
            r = self.ctx.warehouse.ingest(folder, force, self._progress)
            self.state['last'] = {k: r[k] for k in ('run_id', 'status', 'files_seen', 'files_changed', 'files_parsed', 'files_removed', 'files_failed',
                                                    'folders_changed', 'folders_recorrelated', 'warnings', 'seconds')}
            self.snapshot()
            self.ctx.alerts.after_ingest(r)   # notifikasi (thread latar; tidak menahan ingest)
        except Busy: self.state['error'] = 'Ingest lain sedang berjalan.'
        except Exception as e:  # noqa: BLE001  galat dilaporkan lewat status, proses server tetap hidup
            self.state['error'] = f'{type(e).__name__}: {e}'
            self.ctx.alerts.after_ingest(None, self.state['error'])
        finally:
            self.state.update(running=False, phase=None)

    def snapshot(self, missing_only=False):
        """Perbarui salinan baca DuckDB untuk DbGate (bila S4_DUCKDB_SNAPSHOT). Gagal -> dicatat di status, ingest tetap sukses."""
        w = self.ctx.warehouse
        if not w.snapshot_wanted(missing_only): return
        try: w.snapshot(); self.ctx.snapshot_error = None
        except Exception as e: self.ctx.snapshot_error = f'{type(e).__name__}: {e}'   # noqa: BLE001

    def wait(self, timeout=None):
        if self.thread: self.thread.join(timeout)

    def status(self):
        """Status di memori + ingest terakhir yang selesai (bertahan setelah server dimulai ulang; waktu UTC) + folder baru +
        ringkasan sinkron S3 (untuk tombol Sinkronkan data di kepala halaman)."""
        m = self.ctx.imports
        last = m.watch.get('last') or {}
        s3 = dict(enabled=bool(m.watch_sources()[0]), running=bool(m.state['running'] and m.state.get('mode') == 'sync'), phase=m.state['phase'],
                  done=m.state['done'], total=m.state['total'], last_at=last.get('at'), last_imported=last.get('imported', []) + last.get('rechecked', []),
                  last_errors=last.get('errors', []))
        return dict(self.state, last_run=self.ctx.warehouse.last_run(), new_folders=new_folders(self.ctx),
                    snapshot_error=getattr(self.ctx, 'snapshot_error', None), s3=s3)


# ------------------------------------------------------------------ folder (permintaan pemilik 2026-10-07: kelola folder)
def new_folders(ctx):
    """Folder tanggal di folder log / kotak masuk yang belum ada di basis data (dan tidak diabaikan)."""
    w = ctx.warehouse
    return ctx.logfolders.new_folders(w.known_folders() | w.ignored())


def _exclusive(ctx):
    if ctx.ingest.state['running']: raise Busy('Ingest sedang berjalan; coba lagi setelah selesai.')
    return ctx.warehouse.exclusive()


def derive(ctx, folder=None):
    with _exclusive(ctx) as w: return w.derive_all(folder)


def forget(ctx, folder):
    with _exclusive(ctx) as w: n = w.forget(folder)
    if not n: raise Fail('not_found', 'Folder tidak ditemukan.', 404)
    return n


def folders(ctx):
    """Semua folder yang dikenal dashboard, ada di disk, atau diabaikan."""
    rows_db, ign = ctx.warehouse.folder_table()
    in_log, in_inbox = ctx.logfolders.dates()
    rows = []
    for f in sorted(set(rows_db) | set(ign) | in_log | in_inbox, reverse=True):
        log, inbox = ctx.logfolders.on_disk(f)
        if f not in rows_db and f not in ign and not (log or inbox): continue   # folder tanggal kosong di disk
        rows.append(dict(folder=f, in_db=f in rows_db, **(rows_db.get(f) or dict(lines=0, files=0, files_corrupt=0)), log=log, inbox=inbox,
                         ignored=f in ign, ignored_by=(ign.get(f) or {}).get('by'), ignored_at=(ign.get(f) or {}).get('at')))
    return dict(rows=rows, log_dir_readonly=True)


def delete_folder(ctx, folder, delete_inbox, by):
    """Hapus data folder dari dashboard. File di kotak masuk ikut dihapus bila diminta; folder log utama hanya dibaca,
    jadi bila filenya masih ada (atau sinkron S3 otomatis aktif) folder itu dicatat "diabaikan" agar ingest/sinkronisasi
    tidak memasukkannya lagi."""
    lf = ctx.logfolders
    if not lf.inbox_ok(folder): raise Fail('invalid_parameter', 'folder tidak sah.', 400)
    with _exclusive(ctx) as w:
        n = w.forget(folder)
        inbox_deleted = bool(delete_inbox) and lf.remove_inbox(folder)
        # masih ada di disk, atau sinkron S3 otomatis aktif (folder akan diunduh lagi dari S3): dicatat "diabaikan"
        ignored = any(lf.on_disk(folder)) or ctx.imports.watch_config()['enabled']
        if ignored: w.ignore(folder, by)
        ctx.ingest.snapshot()
    if not n and not inbox_deleted and not ignored: raise Fail('not_found', 'Folder tidak ditemukan.', 404)
    return dict(folder=folder, files=n, inbox_deleted=inbox_deleted, ignored=ignored)


def restore_folder(ctx, folder):
    """Batalkan "diabaikan": ingest/sinkronisasi berikutnya memasukkan folder itu lagi."""
    if not ctx.warehouse.unignore(folder): raise Fail('not_found', 'Folder tidak sedang diabaikan.', 404)
    return dict(folder=folder, restored=True)
