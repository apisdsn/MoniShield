"""Impor folder log dari awalan S3 (TRD §3.8): tautan -> daftar objek -> pilih -> unduh ke direktori sementara ->
pindah atomik ke kotak masuk -> ingest biasa (oleh pemanggil).

Pembatas satu-satunya antara layar impor dan bucket lain adalah daftar izin `import_buckets` di konfigurasi
server: tautan diperiksa SEBELUM ada koneksi ke AWS. Hanya dua operasi S3 yang dipakai: ListObjectsV2 dan
GetObject. Kredensial: yang ditempel admin (memori proses saja) lalu variabel lingkungan; tidak pernah
dicetak, dicatat, atau dikembalikan.
"""
import datetime, gzip, json, os, re, shutil, threading, time, uuid, zlib

from . import rules

ENDPOINT = None   # hanya uji (S3 tiruan lokal); server selalu memakai titik akhir resmi wilayah `import_region`
MANIFEST = '.s3-import.json'   # di folder kotak masuk: {relpath objek: {key, size, etag[, stored, stored_size]}} unduhan sebelumnya
EXTRACT_RATIO = 20             # hasil ekstrak satu .gz maks. 20× batas ukuran objek (cegah "gzip bomb")
URL = re.compile(r's3://([a-z0-9][a-z0-9.-]{1,61}[a-z0-9])/(.*)')
CONTROL = re.compile(r'[\x00-\x1f\x7f]')


class ImportFail(Exception):
    """Penolakan atau kegagalan impor dengan sebab yang bisa dibaca (kode + pesan; tidak memuat rahasia)."""

    def __init__(self, code, message, status=400):
        super().__init__(message); self.code, self.message, self.status = code, message, status


# ------------------------------------------------------------------ tautan
def parse_url(cfg, url):
    """Periksa tautan terhadap bentuk dan daftar izin. -> (bucket, awalan lengkap berakhiran '/', folder). Tanpa jaringan."""
    if not cfg.import_buckets:
        raise ImportFail('import_disabled', 'Impor tidak diaktifkan di server: isi S4_IMPORT_BUCKETS (mis. {"simpel4-backup": ["k8s-logs/"]}).')
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


# ------------------------------------------------------------------ kredensial
class Credentials:
    """Urutan: yang ditempel admin (memori proses, hilang saat server mulai ulang), lalu variabel lingkungan."""

    def __init__(self, cfg):
        self.cfg, self._mem, self._set_at, self._lock = cfg, None, None, threading.Lock()

    def __repr__(self): return f'<Credentials sumber={self.status()["source"]}>'   # nilai tidak pernah ikut tercetak

    def set(self, access_key_id, secret_access_key, session_token=''):
        ak, sk, st = (str(x or '').strip() for x in (access_key_id, secret_access_key, session_token))
        if not re.fullmatch(r'[A-Z0-9]{16,128}', ak) or not 16 <= len(sk) <= 128 or CONTROL.search(sk) or len(st) > 4096 or CONTROL.search(st):
            raise ImportFail('invalid_credentials', 'Kredensial tidak berbentuk kunci akses AWS (ID kunci huruf besar/angka, kunci rahasia 16–128 karakter).')
        with self._lock:
            self._mem = dict(aws_access_key_id=ak, aws_secret_access_key=sk, **({'aws_session_token': st} if st else {}))
            self._set_at = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None, microsecond=0)

    def clear(self):
        with self._lock: self._mem, self._set_at = None, None

    def get(self):
        """-> (kwargs boto3, sumber) atau (None, None)."""
        with self._lock:
            if self._mem: return dict(self._mem), 'tempel'
        c = self.cfg
        if c.aws_access_key_id and c.aws_secret_access_key:
            return dict(aws_access_key_id=c.aws_access_key_id, aws_secret_access_key=c.aws_secret_access_key,
                        **({'aws_session_token': c.aws_session_token} if c.aws_session_token else {})), 'lingkungan'
        return None, None

    def status(self):
        with self._lock: mem, at = bool(self._mem), self._set_at
        env = bool(self.cfg.aws_access_key_id and self.cfg.aws_secret_access_key)
        return dict(available=mem or env, source='tempel' if mem else 'lingkungan' if env else None,
                    pasted=mem, pasted_at=str(at) if at else None, environment=env)


NO_LIBRARY = ('Impor S3 butuh paket boto3 yang belum terpasang di server. Jalankan: .venv/bin/pip install -e ".[s3]" '
              '(atau ./run.sh, yang kini memasangnya), lalu mulai ulang server.')


def library_ok():
    """boto3 + botocore terpasang? (paket opsional "s3"; diperiksa sebelum job dibuat agar tidak gagal di tengah)"""
    import importlib.util
    return all(importlib.util.find_spec(m) is not None for m in ('boto3', 'botocore'))


NO_CREDENTIALS = ('Tidak ada kredensial AWS. Isi AWS_ACCESS_KEY_ID dan AWS_SECRET_ACCESS_KEY di .env server lalu mulai ulang, '
                  'atau tempel kredensial sementara di layar Ingest & impor.')


# ------------------------------------------------------------------ S3
def _client(cfg, creds):
    import boto3
    from botocore.config import Config
    conf = Config(connect_timeout=10, read_timeout=60, retries=dict(max_attempts=3, mode='standard'), signature_version='s3v4',
                  s3=dict(addressing_style='path') if ENDPOINT else None)
    return boto3.session.Session(region_name=cfg.import_region, **creds).client('s3', endpoint_url=ENDPOINT, config=conf)


def _s3_error(e):
    from botocore.exceptions import BotoCoreError, ClientError, EndpointConnectionError
    if isinstance(e, ClientError):
        code = e.response.get('Error', {}).get('Code', '?')
        if code in ('AccessDenied', 'InvalidAccessKeyId', 'SignatureDoesNotMatch', 'ExpiredToken', 'InvalidToken', '403'):
            return ImportFail('s3_denied', f'S3 menolak akses ({code}): periksa kredensial dan hak baca pada bucket/awalan ini.', 502)
        if code in ('NoSuchBucket', 'NoSuchKey', '404'):
            return ImportFail('s3_not_found', f'S3: {code} (bucket atau objek tidak ada).', 502)
        return ImportFail('s3_error', f'S3 menjawab galat {code}.', 502)
    if isinstance(e, (EndpointConnectionError, BotoCoreError, OSError)):
        return ImportFail('s3_unreachable', f'S3 tidak terjangkau dari server ({type(e).__name__}). Periksa akses keluar server ke titik akhir S3 wilayah impor.', 502)
    return ImportFail('s3_error', f'{type(e).__name__}', 502)


def list_objects(s3, bucket, prefix, cap):
    """[{key, size, etag}] di bawah awalan (ListObjectsV2, berhalaman). Berhenti di `cap` objek."""
    out = []
    for page in s3.get_paginator('list_objects_v2').paginate(Bucket=bucket, Prefix=prefix):
        for o in page.get('Contents', []):
            out.append(dict(key=o['Key'], size=int(o['Size']), etag=str(o.get('ETag', '')).strip('"')))
            if len(out) > cap: return out
    return out


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
            raise ImportFail('import_disabled', 'Impor tidak diaktifkan di server: isi S4_IMPORT_BUCKETS (mis. {"simpel4-backup": ["k8s-logs/"]}).')
        allowed = cfg.import_buckets.get(bucket)
        if allowed is None or not any(base.startswith(p) for p in allowed):
            raise ImportFail('watch_not_allowed', f's3://{bucket}/{base} tidak termasuk daftar izin server (S4_IMPORT_BUCKETS). Yang diizinkan: '
                                                  f'{", ".join(f"s3://{b}/{p}" for b, ps in sorted(cfg.import_buckets.items()) for p in ps)}.')
        if (bucket, base) not in out: out.append((bucket, base))
    return out


def list_folders(s3, bucket, base):
    """Nama folder tanggal (YYYY-MM-DD sah) tepat di bawah awalan: ListObjectsV2 dengan Delimiter '/', jadi isi folder
    tidak ikut didaftar (murah walau riwayat bertahun-tahun)."""
    out = set()
    for page in s3.get_paginator('list_objects_v2').paginate(Bucket=bucket, Prefix=base, Delimiter='/'):
        for cp in page.get('CommonPrefixes', []):
            name = cp['Prefix'][len(base):].rstrip('/')
            if rules.DATE_DIR.fullmatch(name):
                try: datetime.date.fromisoformat(name); out.add(name)
                except ValueError: pass
    return sorted(out)


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
def plan(cfg, objects, prefix, folder):
    """Tentukan objek yang diambil / dilewati. Kunci tidak aman -> seluruh impor ditolak. Melewati batas -> ditolak."""
    inbox = os.path.join(cfg.inbox_dir, folder)
    try:
        with open(os.path.join(inbox, MANIFEST), encoding='utf-8') as fh: before = json.load(fh)
    except (OSError, ValueError): before = {}
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
            kept = os.path.join(inbox, *prev.get('stored', rel).split('/'))
            if os.path.isfile(kept) and os.path.getsize(kept) == prev.get('stored_size', r['size']):
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


# ------------------------------------------------------------------ jalankan
def run(cfg, url, creds_store, dry_run=False, progress=None):
    """Seluruh impor. dry_run = hanya daftar + rencana, tanpa menulis apa pun. Ingest dijalankan PEMANGGIL (punya DuckDB)."""
    progress = progress or (lambda **k: None)
    bucket, prefix, folder = parse_url(cfg, url)
    creds, source = creds_store.get()
    if not creds: raise ImportFail('no_credentials', NO_CREDENTIALS)
    t0 = time.time()
    deadline = t0 + cfg.import_timeout_minutes * 60
    progress(phase='daftar')
    try:
        s3 = _client(cfg, creds)
        objects = list_objects(s3, bucket, prefix, cap=cfg.import_max_objects * 4)
    except ImportFail: raise
    except Exception as e: raise _s3_error(e) from None   # noqa: BLE001  pesan tanpa rahasia
    if len(objects) > cfg.import_max_objects * 4:
        raise ImportFail('too_many_objects', f'Awalan ini berisi lebih dari {cfg.import_max_objects * 4} objek; batas {cfg.import_max_objects} file log.')
    if not objects: raise ImportFail('empty_prefix', f'Tidak ada objek di s3://{bucket}/{prefix}.', 404)
    rows = plan(cfg, objects, prefix, folder)
    take = [r for r in rows if r['action'] == 'ambil']
    res = dict(bucket=bucket, prefix=prefix, folder=folder, dry_run=dry_run, credentials=source, objects=rows,
               take=len(take), skipped=len(rows) - len(take), bytes=sum(r['size'] for r in take), downloaded=0, downloaded_bytes=0, extracted=0, warnings=[])
    local = [r for r in rows if r.get('extract_local')]
    if os.path.isdir(os.path.join(cfg.log_dir, folder)):
        res['warnings'].append(f'folder {folder} juga ada di folder log lokal; saat ingest versi lokal yang dipakai')
    if not dry_run and local: res['extracted'] += _extract_in_inbox(cfg, folder, local)
    if dry_run or not take:
        res['seconds'] = round(time.time() - t0, 2); return res
    tmp = os.path.join(cfg.data_dir, 'tmp', f'import-{uuid.uuid4().hex[:12]}')
    try:
        for i, r in enumerate(take):
            if time.time() > deadline: raise ImportFail('timeout', f'Impor melewati batas waktu {cfg.import_timeout_minutes} menit.', 504)
            dst = os.path.join(tmp, folder, *r['rel'].split('/'))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            n = 0
            try:
                body = s3.get_object(Bucket=bucket, Key=r['key'])['Body']
                with open(dst, 'wb') as fh:
                    for chunk in body.iter_chunks(2**20):
                        n += len(chunk)
                        if n > r['size'] or n > cfg.import_max_object_mb * 2**20:
                            raise ImportFail('size_mismatch', f'Objek {r["rel"]} lebih besar dari yang terdaftar; impor dibatalkan.', 502)
                        fh.write(chunk)
            except ImportFail: raise
            except Exception as e: raise _s3_error(e) from None   # noqa: BLE001
            if n != r['size']: raise ImportFail('size_mismatch', f'Objek {r["rel"]} terunduh {n} byte, terdaftar {r["size"]}; impor dibatalkan.', 502)
            res['downloaded'] += 1; res['downloaded_bytes'] += n
            if cfg.import_extract and r['rel'].endswith('.gz'):   # .log.gz -> .log (di folder sementara; yang dipindah hanya .log)
                r['stored'], r['stored_size'] = r['rel'][:-3], _gunzip(dst, dst[:-3], r['rel'], cfg.import_max_object_mb * 2**20 * EXTRACT_RATIO)
                res['extracted'] += 1
            progress(phase='unduh', done=i + 1, total=len(take))
        _move_into_inbox(cfg, os.path.join(tmp, folder), folder, take)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    res['seconds'] = round(time.time() - t0, 2)
    return res


def _move_into_inbox(cfg, src, folder, take):
    """Folder baru: satu rename (atomik). Folder yang sudah ada: tiap berkas diganti dengan rename (atomik per berkas). Lalu manifest."""
    dst = os.path.join(cfg.inbox_dir, folder)
    os.makedirs(cfg.inbox_dir, exist_ok=True)
    if not os.path.exists(dst):
        try: os.replace(src, dst)
        except OSError: shutil.copytree(src, dst + '.part'); os.replace(dst + '.part', dst)   # beda sistem berkas
    else:
        for r in take:
            kept = r.get('stored', r['rel'])
            s, d = os.path.join(src, *kept.split('/')), os.path.join(dst, *kept.split('/'))
            os.makedirs(os.path.dirname(d), exist_ok=True)
            try: os.replace(s, d)
            except OSError: shutil.copy2(s, d + '.part'); os.replace(d + '.part', d)
            if kept != r['rel']:   # versi .gz lama dari impor sebelumnya tidak dibutuhkan lagi
                try: os.remove(os.path.join(dst, *r['rel'].split('/')))
                except FileNotFoundError: pass
    _manifest_update(dst, take)


def _manifest_update(folder_dir, rows):
    path = os.path.join(folder_dir, MANIFEST)
    try:
        with open(path, encoding='utf-8') as fh: man = json.load(fh)
    except (OSError, ValueError): man = {}
    for r in rows:
        man[r['rel']] = dict(key=r['key'], size=r['size'], etag=r['etag'], **({'stored': r['stored'], 'stored_size': r['stored_size']} if 'stored' in r else {}))
    with open(path + '.tmp', 'w', encoding='utf-8') as fh: json.dump(man, fh, ensure_ascii=False, indent=0, sort_keys=True)
    os.replace(path + '.tmp', path)


def _gunzip(src, dst, rel, limit):
    """Ekstrak src (.gz) ke dst, hapus src. Isi gzip diperiksa utuh; hasil > limit -> impor dibatalkan. -> ukuran hasil."""
    n = 0
    try:
        with gzip.open(src, 'rb') as g, open(dst + '.part', 'wb') as out:
            while chunk := g.read(2**20):
                n += len(chunk)
                if n > limit: break
                out.write(chunk)
    except (OSError, EOFError, zlib.error):
        _rm(dst + '.part')
        raise ImportFail('bad_gzip', f'Objek {rel} bukan gzip yang utuh (rusak atau terpotong); impor dibatalkan.', 502) from None
    if n > limit:
        _rm(dst + '.part')
        raise ImportFail('extract_too_large', f'Hasil ekstrak {rel} melebihi {limit / 2**20:.0f} MB; impor dibatalkan.', 413)
    os.replace(dst + '.part', dst); os.remove(src)
    return n


def _rm(path):
    try: os.remove(path)
    except FileNotFoundError: pass


def _extract_in_inbox(cfg, folder, rows):
    """.gz dari impor sebelumnya (sebelum ekstrak otomatis ada) diekstrak di tempat, tanpa unduh ulang; manifest diperbarui."""
    base = os.path.join(cfg.inbox_dir, folder)
    for r in rows:
        src = os.path.join(base, *r['rel'].split('/'))
        r['stored'], r['stored_size'] = r['rel'][:-3], _gunzip(src, src[:-3], r['rel'], cfg.import_max_object_mb * 2**20 * EXTRACT_RATIO)
    _manifest_update(base, rows)
    return len(rows)
