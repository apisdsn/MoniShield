"""Aturan unggah folder log dari browser (permintaan pemilik 2026-10-07): jalur yang diterima, folder tanggal, batas
ukuran yang sama dengan impor S3. Murni; berkas sementara dan pemindahan ke kotak masuk di
monishield/infrastructure/uploads.py.

Bentuk jalur yang diterima (webkitRelativePath dari browser):
  …/<YYYY-MM-DD>/<namespace>/<layanan>/<file>.log[.gz]   folder tanggal (atau induknya, berisi beberapa tanggal)
  <folder apa pun>/<namespace>/<layanan>/<file>           isi SATU tanggal: tanggalnya dipilih di layar (`folder`)
"""
import datetime, os

from monishield.domain import rules
from monishield.domain.s3_import import CONTROL, ImportFail

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
