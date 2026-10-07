"""Unggah folder log dari browser (permintaan pemilik 2026-10-07). Admin memilih folder di komputernya; tampilan mengirim
daftar file dulu (rencana), lalu tiap file satu per satu ke direktori sementara, lalu "selesai": file dipindah ke kotak
masuk dan di-ingest — jalur yang sama dengan impor S3 (TRD §3.8), dengan batas ukuran yang sama (S4_IMPORT_MAX_*).

Bentuk jalur yang diterima (webkitRelativePath dari browser):
  …/<YYYY-MM-DD>/<namespace>/<layanan>/<file>.log[.gz]   folder tanggal (atau induknya, berisi beberapa tanggal)
  <folder apa pun>/<namespace>/<layanan>/<file>           isi SATU tanggal: tanggalnya dipilih di layar (`folder`)
"""
import datetime, os, shutil, threading, time, uuid

from . import importer, rules
from .importer import CONTROL, ImportFail

# sesi unggah yang ditinggalkan (tab ditutup) dibersihkan setelah cfg.upload_session_hours (S4_UPLOAD_SESSION_HOURS)


def _date_ok(s):
    if not rules.DATE_DIR.fullmatch(s or ''): return False
    try: datetime.date.fromisoformat(s); return True
    except ValueError: return False


def plan(cfg, files, folder=''):
    """files: [{path, size}] dari browser -> (diterima [{i, rel, folder, size}], dilewati [{path, reason}]).
    Jalur tidak aman / di luar batas -> ImportFail untuk seluruh unggahan; file yang bukan log hanya dilewati."""
    if folder and not _date_ok(folder): raise ImportFail('invalid_date', 'Tanggal folder harus YYYY-MM-DD yang sah.')
    if not isinstance(files, list) or not files: raise ImportFail('nothing_to_upload', 'Tidak ada file yang dipilih.')
    if len(files) > cfg.import_max_objects * 4:
        raise ImportFail('too_many_objects', f'Lebih dari {cfg.import_max_objects * 4} file dipilih; batas {cfg.import_max_objects} file log per unggahan.')
    ok, skip, seen = [], [], {}
    for i, f in enumerate(files):
        path, size = str((f or {}).get('path') or '')[:1024], (f or {}).get('size')
        parts = path.replace('\\', '/').split('/')
        if CONTROL.search(path) or any(p in ('', '.', '..') for p in parts) or not isinstance(size, int) or size < 0:
            raise ImportFail('unsafe_path', f'Nama file tidak sah, unggahan dibatalkan: {path[:200]!r}.')
        if not parts[-1].endswith(('.log', '.log.gz')): skip.append(dict(path=path, reason='bukan file log')); continue
        k = next((j for j, p in enumerate(parts[:-1]) if _date_ok(p)), None)
        if k is not None: rel = parts[k:]
        elif folder: rel = [folder] + parts[1:]          # folder yang dipilih berisi satu tanggal: namanya diganti tanggal itu
        else: skip.append(dict(path=path, reason='tidak ada folder tanggal (YYYY-MM-DD) di jalurnya; isi tanggal folder')); continue
        if not rules.split_relpath(os.path.join(*rel)):
            skip.append(dict(path=path, reason='bukan <tanggal>/<namespace>/<layanan>/<file>')); continue
        if os.path.isdir(os.path.join(cfg.log_dir, rel[0])):
            skip.append(dict(path=path, reason=f'folder {rel[0]} sudah ada di folder log utama (yang itu yang dipakai)')); continue
        r = '/'.join(rel)
        if r in seen: skip.append(dict(path=path, reason='ganda')); continue
        if size > cfg.import_max_object_mb * 2**20:
            raise ImportFail('object_too_large', f'{path[:200]} {size / 2**20:.0f} MB melebihi batas {cfg.import_max_object_mb} MB per file.')
        seen[r] = len(ok)
        ok.append(dict(i=i, rel=r, folder=rel[0], size=size, path=path))
    keep = []
    for o in ok:   # aturan ingest: .log.gz hanya bila .log pasangannya tidak ada
        if o['rel'].endswith('.gz') and o['rel'][:-3] in seen: skip.append(dict(path=o['path'], reason='.gz berpasangan dengan .log'))
        else: keep.append(o)
    if len(keep) > cfg.import_max_objects:
        raise ImportFail('too_many_objects', f'{len(keep)} file log melebihi batas {cfg.import_max_objects} file per unggahan.')
    total = sum(o['size'] for o in keep)
    if total > cfg.import_max_total_mb * 2**20:
        raise ImportFail('too_large', f'Total {total / 2**20:.0f} MB melebihi batas {cfg.import_max_total_mb} MB per unggahan.')
    return keep, skip


class Uploads:
    """Sesi unggah di memori proses: id -> rencana + file yang sudah diterima. Satu sesi = satu pilihan folder."""

    def __init__(self, cfg):
        self.cfg, self._lock, self.sessions = cfg, threading.Lock(), {}

    def _dir(self, uid): return os.path.join(self.cfg.data_dir, 'tmp', f'upload-{uid}')

    def create(self, by, files):
        self._expire()
        uid = uuid.uuid4().hex
        os.makedirs(self._dir(uid), exist_ok=True)
        with self._lock: self.sessions[uid] = dict(by=by, files=files, got=set(), at=time.time())
        return uid

    def get(self, uid, by):
        s = self.sessions.get(uid) if isinstance(uid, str) else None
        if not s or s['by'] != by: raise ImportFail('not_found', 'Sesi unggah tidak ditemukan (kedaluwarsa atau milik admin lain).', 404)
        return s

    def target(self, uid, by, i):
        """-> (entri rencana, path tujuan sementara) untuk file ke-i (indeks pilihan browser)."""
        s = self.get(uid, by)
        e = next((f for f in s['files'] if f['i'] == i), None)
        if e is None: raise ImportFail('not_found', 'File ini tidak termasuk rencana unggahan.', 404)
        return e, os.path.join(self._dir(uid), *e['rel'].split('/'))

    def received(self, uid, i):
        with self._lock: self.sessions[uid]['got'].add(i)

    def finish(self, uid, by):
        """Semua file sudah diterima -> ekstrak .gz (bila S4_IMPORT_EXTRACT) -> pindah ke kotak masuk. -> ringkasan."""
        s = self.get(uid, by)
        missing = [f['rel'] for f in s['files'] if f['i'] not in s['got']]
        if missing: raise ImportFail('incomplete', f'{len(missing)} file belum terunggah (mis. {missing[0]}).', 409)
        base, cfg, extracted = self._dir(uid), self.cfg, 0
        try:
            for f in s['files']:
                if cfg.import_extract and f['rel'].endswith('.gz'):
                    src = os.path.join(base, *f['rel'].split('/'))
                    importer._gunzip(src, src[:-3], f['rel'], cfg.import_max_object_mb * 2**20 * importer.EXTRACT_RATIO)
                    f['stored'] = f['rel'][:-3]; extracted += 1
            folders = sorted({f['folder'] for f in s['files']})
            os.makedirs(cfg.inbox_dir, exist_ok=True)
            for d in folders:
                for f in (x for x in s['files'] if x['folder'] == d):   # per file (atomik per file): folder yang sudah ada ikut diperbarui
                    kept = f.get('stored', f['rel'])
                    a, b = os.path.join(base, *kept.split('/')), os.path.join(cfg.inbox_dir, *kept.split('/'))
                    os.makedirs(os.path.dirname(b), exist_ok=True)
                    os.replace(a, b)
                    if kept != f['rel']: importer._rm(os.path.join(cfg.inbox_dir, *f['rel'].split('/')))   # .gz lama tidak dipakai lagi
                    elif kept.endswith('.gz'): importer._rm(b[:-3])   # .log lama bernama sama akan menang saat ingest: buang
        finally:
            self.drop(uid)
        return dict(folders=folders, files=len(s['files']), bytes=sum(f['size'] for f in s['files']), extracted=extracted)

    def drop(self, uid):
        with self._lock: self.sessions.pop(uid, None)
        shutil.rmtree(self._dir(uid), ignore_errors=True)

    def _expire(self):
        old = [u for u, s in list(self.sessions.items()) if time.time() - s['at'] > self.cfg.upload_session_hours * 3600]
        for u in old: self.drop(u)
        tmp = os.path.join(self.cfg.data_dir, 'tmp')   # sisa sesi dari proses sebelumnya (server dimulai ulang)
        for d in os.listdir(tmp) if os.path.isdir(tmp) else []:
            if d.startswith('upload-') and d[7:] not in self.sessions: shutil.rmtree(os.path.join(tmp, d), ignore_errors=True)
