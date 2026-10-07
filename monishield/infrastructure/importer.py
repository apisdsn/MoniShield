"""Impor folder log dari awalan S3 (TRD §3.8): tautan -> daftar objek -> pilih -> unduh ke direktori sementara ->
pindah atomik ke kotak masuk -> ingest biasa (oleh pemanggil).

Pembatas satu-satunya antara layar impor dan bucket lain adalah daftar izin `import_buckets` di konfigurasi
server: tautan diperiksa SEBELUM ada koneksi ke AWS. Hanya dua operasi S3 yang dipakai: ListObjectsV2 dan
GetObject. Kredensial: yang ditempel admin (memori proses saja) lalu variabel lingkungan; tidak pernah
dicetak, dicatat, atau dikembalikan.
"""
import datetime, gzip, json, os, re, shutil, threading, time, uuid, zlib

from monishield.domain import rules, s3_import
from monishield.domain.s3_import import CONTROL, NO_CREDENTIALS, ImportFail, allowed_examples, parse_url, parse_watch, pick   # noqa: F401

ENDPOINT = None   # hanya uji (S3 tiruan lokal); server selalu memakai titik akhir resmi wilayah `import_region`
MANIFEST = '.s3-import.json'   # di folder kotak masuk: {relpath objek: {key, size, etag[, stored, stored_size]}} unduhan sebelumnya
EXTRACT_RATIO = 20             # hasil ekstrak satu .gz maks. 20× batas ukuran objek (cegah "gzip bomb")


# ------------------------------------------------------------------ kredensial
class Credentials:
    """Urutan: yang ditempel admin (memori proses, hilang saat server mulai ulang), lalu konfigurasi server (.env, yang
    juga diisi layar Konfigurasi; atau variabel lingkungan)."""

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
            if self._mem: return dict(self._mem), 'pasted'
        c = self.cfg
        if c.aws_access_key_id and c.aws_secret_access_key:
            return dict(aws_access_key_id=c.aws_access_key_id, aws_secret_access_key=c.aws_secret_access_key,
                        **({'aws_session_token': c.aws_session_token} if c.aws_session_token else {})), 'environment'
        return None, None

    def status(self):
        with self._lock: mem, at = bool(self._mem), self._set_at
        env = bool(self.cfg.aws_access_key_id and self.cfg.aws_secret_access_key)
        return dict(available=mem or env, source='pasted' if mem else 'environment' if env else None,
                    pasted=mem, pasted_at=str(at) if at else None, environment=env)


NO_LIBRARY = ('Impor S3 butuh paket boto3 yang belum terpasang di server. Jalankan: .venv/bin/pip install -e ".[s3]" '
              '(atau ./run.sh, yang kini memasangnya), lalu mulai ulang server.')


def library_ok():
    """boto3 + botocore terpasang? (paket opsional "s3"; diperiksa sebelum job dibuat agar tidak gagal di tengah)"""
    import importlib.util
    return all(importlib.util.find_spec(m) is not None for m in ('boto3', 'botocore'))


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


def plan(cfg, objects, prefix, folder):
    """Rencana objek (aturan di domain.s3_import.plan) dengan manifest unduhan sebelumnya dari kotak masuk."""
    inbox = os.path.join(cfg.inbox_dir, folder)
    try:
        with open(os.path.join(inbox, MANIFEST), encoding='utf-8') as fh: before = json.load(fh)
    except (OSError, ValueError): before = {}

    def have(stored, size):
        kept = os.path.join(inbox, *stored.split('/'))
        return os.path.isfile(kept) and os.path.getsize(kept) == size
    return s3_import.plan(cfg, objects, prefix, folder, before, have)


# ------------------------------------------------------------------ jalankan
def run(cfg, url, creds_store, dry_run=False, progress=None):
    """Seluruh impor. dry_run = hanya daftar + rencana, tanpa menulis apa pun. Ingest dijalankan PEMANGGIL (punya DuckDB)."""
    progress = progress or (lambda **k: None)
    bucket, prefix, folder = parse_url(cfg, url)
    creds, source = creds_store.get()
    if not creds: raise ImportFail('no_credentials', NO_CREDENTIALS)
    t0 = time.time()
    deadline = t0 + cfg.import_timeout_minutes * 60
    progress(phase='list')
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
            progress(phase='download', done=i + 1, total=len(take))
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


# ------------------------------------------------------------------ port S3Gateway (dipakai monishield/application/import_service.py)
class S3Gateway:
    """Akses S3 untuk lapisan application: kredensial (memori proses + .env), unduh awalan, daftar folder tanggal, uji
    koneksi. Fungsi modul dicari saat dipanggil (uji bisa mengganti `library_ok`, `ENDPOINT`)."""

    def __init__(self, cfg):
        self.cfg, self.creds = cfg, Credentials(cfg)

    def library_ok(self): return library_ok()

    def ready(self):
        """Pustaka + kredensial ada; bila tidak -> ImportFail (400) dengan petunjuknya."""
        if not library_ok(): raise ImportFail('no_s3_library', NO_LIBRARY, 400)
        if not self.creds.get()[0]: raise ImportFail('no_credentials', NO_CREDENTIALS, 400)

    def run(self, url, dry_run=False, progress=None): return run(self.cfg, url, self.creds, dry_run=dry_run, progress=progress)

    def list_folders(self, bucket, base): return list_folders(_client(self.cfg, self.creds.get()[0]), bucket, base)

    def probe(self, bucket, prefix):
        """Daftar satu objek (uji koneksi). Galat -> ImportFail."""
        try: _client(self.cfg, self.creds.get()[0]).list_objects_v2(Bucket=bucket, Prefix=prefix, MaxKeys=1)
        except Exception as e: raise _s3_error(e) from None   # noqa: BLE001

    def error(self, e): return e if isinstance(e, ImportFail) else _s3_error(e)
