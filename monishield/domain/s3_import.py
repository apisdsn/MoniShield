"""Aturan impor dari S3 (TRD §3.8): bentuk tautan, daftar izin bucket/awalan (S4_IMPORT_BUCKETS), folder induk untuk
sinkron otomatis, pemilihan folder baru, dan rencana objek yang diambil. Murni (tanpa jaringan/berkas); unduhan ada di
monishield/infrastructure/importer.py."""
import datetime, os, re

from monishield.domain import rules
from monishield.domain.errors import Fail

URL = re.compile(r's3://([a-z0-9][a-z0-9.-]{1,61}[a-z0-9])/(.*)')


CONTROL = re.compile(r'[\x00-\x1f\x7f]')


class ImportFail(Fail):
    """Penolakan atau kegagalan impor dengan sebab yang bisa dibaca (kode + pesan; tidak memuat rahasia)."""


# ------------------------------------------------------------------ tautan
def parse_url(cfg, url):
    """Periksa tautan terhadap bentuk dan daftar izin. -> (bucket, awalan lengkap berakhiran '/', folder). Tanpa jaringan."""
    if not cfg.import_buckets:
        raise ImportFail('import_disabled', 'Impor tidak diaktifkan di server: isi S4_IMPORT_BUCKETS (mis. {"nama-bucket": ["k8s-logs/"]}).')
    if not isinstance(url, str) or len(url) > 1024 or CONTROL.search(url):
        raise ImportFail('invalid_url', 'Tautan harus berbentuk s3://<bucket>/<awalan>/<YYYY-MM-DD>/.')
    m = URL.fullmatch(url.strip())
    if not m: raise ImportFail('invalid_url', 'Tautan harus berbentuk s3://<bucket>/<awalan>/<YYYY-MM-DD>/.')
    bucket, path = m.group(1), m.group(2).rstrip('/')
    parts = path.split('/')
    if not path or '' in parts or '..' in parts or '.' in parts:
        raise ImportFail('invalid_url', 'Tautan harus berbentuk s3://<bucket>/<awalan>/<YYYY-MM-DD>/ tanpa "..", "." atau garis miring ganda.')
    folder = parts[-1]
    try:
        if not rules.DATE_DIR.fullmatch(folder): raise ValueError
        datetime.date.fromisoformat(folder)
    except ValueError:
        raise ImportFail('invalid_date', f'Komponen terakhir tautan harus tanggal YYYY-MM-DD yang sah (nama folder), bukan "{folder[:40]}".') from None
    base = '/'.join(parts[:-1]) + '/' if len(parts) > 1 else ''
    allowed = cfg.import_buckets.get(bucket)
    if allowed is None:
        raise ImportFail('bucket_not_allowed', f'Bucket ini tidak diizinkan. Yang diizinkan: {", ".join(sorted(cfg.import_buckets))}.')
    if not any(base.startswith(p) for p in allowed):
        raise ImportFail('prefix_not_allowed', f'Awalan ini tidak diizinkan untuk bucket {bucket}. Yang diizinkan: '
                                               f'{", ".join(f"s3://{bucket}/{p}<tanggal>/" for p in allowed)}.')
    return bucket, base + folder + '/', folder


def allowed_examples(cfg):
    """Contoh bentuk tautan yang diterima (untuk layar impor)."""
    return [f's3://{b}/{p}<YYYY-MM-DD>/' for b, ps in sorted(cfg.import_buckets.items()) for p in ps]


NO_CREDENTIALS = ('Tidak ada kredensial AWS. Isi di layar Konfigurasi (menu akun; ditulis ke .env) atau langsung '
                  'AWS_ACCESS_KEY_ID dan AWS_SECRET_ACCESS_KEY di .env server, atau tempel kredensial sementara di layar Ingest & impor.')


# ------------------------------------------------------------------ pantau awalan induk (sinkron otomatis, permintaan pemilik 2026-10-07)
def parse_watch(cfg, text=None):
    """Folder induk yang dipantau (dari layar, atau S4_S3_WATCH; satu atau beberapa s3://<bucket>/<awalan>/, dipisah
    koma; garis miring di akhir boleh tidak ada) -> [(bucket, awalan)]. Diperiksa terhadap daftar izin
    S4_IMPORT_BUCKETS yang sama dengan impor manual; tanpa jaringan."""
    out = []
    text = cfg.s3_watch if text is None else text
    for u in (x for x in re.split(r'[,\s]+', (text or '').strip()) if x):
        m = URL.fullmatch(u) if len(u) <= 1024 and not CONTROL.search(u) else None
        path = m.group(2).strip('/') if m else ''
        parts = path.split('/') if path else []
        if not m or '' in parts or '..' in parts or '.' in parts:
            raise ImportFail('invalid_watch', f'"{u[:100]}" harus berbentuk s3://<bucket>/<awalan>/ (folder induk berisi folder YYYY-MM-DD).')
        bucket, base = m.group(1), path + '/' if path else ''
        if parts and rules.DATE_DIR.fullmatch(parts[-1]):
            raise ImportFail('watch_is_date', f'Masukkan folder INDUK tanpa tanggal, mis. s3://{bucket}/{"/".join(parts[:-1])}/ (bukan folder {parts[-1]}).')
        if not cfg.import_buckets:
            raise ImportFail('import_disabled', 'Impor tidak diaktifkan di server: isi S4_IMPORT_BUCKETS (mis. {"nama-bucket": ["k8s-logs/"]}).')
        allowed = cfg.import_buckets.get(bucket)
        if allowed is None or not any(base.startswith(p) for p in allowed):
            raise ImportFail('watch_not_allowed', f's3://{bucket}/{base} tidak termasuk daftar izin server (S4_IMPORT_BUCKETS). Yang diizinkan: '
                                                  f'{", ".join(f"s3://{b}/{p}" for b, ps in sorted(cfg.import_buckets.items()) for p in ps)}.')
        if (bucket, base) not in out: out.append((bucket, base))
    return out


def pick(folders, known, from_s3, today, days, recheck_days, max_new):
    """Dari folder di S3: yang BARU (belum dikenal sama sekali) dan yang DIPERIKSA ULANG (hasil impor S3 yang masih baru,
    mungkin bertambah file). Hanya folder dalam `days` hari terakhir (0 = semua). Folder baru diambil maksimal `max_new`
    per putaran, terbaru dulu; sisanya menyusul di putaran berikutnya. -> (baru, ulang, tertunda)"""
    floor = (today - datetime.timedelta(days=days)).isoformat() if days else ''
    fresh = (today - datetime.timedelta(days=recheck_days)).isoformat()
    new = [f for f in folders if f >= floor and f not in known]
    take = sorted(new[-max_new:]) if max_new > 0 else []
    again = [f for f in folders if f >= fresh and f in from_s3 and f not in take]
    return take, again, len(new) - len(take)


# ------------------------------------------------------------------ pilih
def plan(cfg, objects, prefix, folder, before=None, have_stored=lambda stored, size: False):
    """Tentukan objek yang diambil / dilewati. Kunci tidak aman -> seluruh impor ditolak. Melewati batas -> ditolak.
    before = manifest unduhan sebelumnya {rel: {key, size, etag[, stored, stored_size]}}; have_stored(rel_simpan, ukuran)
    = berkas hasil unduhan lama masih utuh di kotak masuk (diperiksa adapter, bukan di sini)."""
    before = before or {}
    rows, keys = [], set()
    for o in objects:
        rel = o['key'][len(prefix):] if o['key'].startswith(prefix) else None
        if rel is None or rel.startswith('/') or '//' in rel or CONTROL.search(rel) or any(p in ('..', '.') for p in rel.split('/')):
            raise ImportFail('unsafe_key', f'Kunci objek tidak aman, impor dibatalkan: {o["key"][:200]!r}.')
        keys.add(rel)
        rows.append(dict(rel=rel, **o))
    n_log = 0
    for r in rows:
        rel, name = r['rel'], r['rel'].rsplit('/', 1)[-1]
        ok_name = name.endswith('.log') or name.endswith('.log.gz')
        if not ok_name or rel.endswith('/') or not rules.split_relpath(os.path.join(folder, *rel.split('/'))):
            r.update(action='lewati', reason='bukan file log'); continue
        n_log += 1
        if name.endswith('.gz') and rel[:-3] in keys:
            r.update(action='lewati', reason='.gz berpasangan dengan .log'); continue
        prev = before.get(rel)
        if prev and prev.get('etag') == r['etag'] and prev.get('size') == r['size']:
            if have_stored(prev.get('stored', rel), prev.get('stored_size', r['size'])):
                # unduhan lama berupa .gz yang belum diekstrak: diekstrak di tempat saat impor dijalankan (tanpa unduh ulang)
                r.update(action='lewati', reason='sama dengan unduhan sebelumnya',
                         extract_local=bool(cfg.import_extract and rel.endswith('.gz') and 'stored' not in prev))
                continue
        if r['size'] > cfg.import_max_object_mb * 2**20:
            raise ImportFail('object_too_large', f'Objek {rel} {r["size"] / 2**20:.0f} MB melebihi batas {cfg.import_max_object_mb} MB per objek.')
        r.update(action='ambil', reason='')
    if n_log > cfg.import_max_objects:
        raise ImportFail('too_many_objects', f'{n_log} file log di awalan ini melebihi batas {cfg.import_max_objects} objek.')
    total = sum(r['size'] for r in rows if r['action'] == 'ambil')
    if total > cfg.import_max_total_mb * 2**20:
        raise ImportFail('too_large', f'Total unduhan {total / 2**20:.0f} MB melebihi batas {cfg.import_max_total_mb} MB.')
    return rows
