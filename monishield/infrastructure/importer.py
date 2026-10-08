"""Import a log folder from an S3 prefix (TRD §3.8): link -> list objects -> pick -> download to a temp directory ->
atomic move into the inbox -> regular ingest (by the caller).

The only barrier between the import page and other buckets is the `import_buckets` allow list in the server
configuration: the link is checked BEFORE any connection to AWS. Only two S3 operations are used: ListObjectsV2 and
GetObject. Credentials: those pasted by an admin (process memory only), then environment variables; never
printed, logged, or returned.
"""
import datetime, gzip, json, os, re, shutil, threading, time, uuid, zlib

from monishield.domain import rules, s3_import
from monishield.domain.s3_import import CONTROL, NO_CREDENTIALS, ImportFail, allowed_examples, parse_url, parse_watch, pick   # noqa: F401

ENDPOINT = None   # tests only (local fake S3); the server always uses the official endpoint of region `import_region`
MANIFEST = '.s3-import.json'   # in the inbox folder: {object relpath: {key, size, etag[, stored, stored_size]}} of previous downloads
EXTRACT_RATIO = 20             # extracted size of one .gz max. 20× the object size limit (prevents a "gzip bomb")


# ------------------------------------------------------------------ credentials
class Credentials:
    """Order: pasted by an admin (process memory, lost on server restart), then the server configuration (.env, which
    the Configuration page also fills; or environment variables)."""

    def __init__(self, cfg):
        self.cfg, self._mem, self._set_at, self._lock = cfg, None, None, threading.Lock()

    def __repr__(self): return f'<Credentials source={self.status()["source"]}>'   # values are never printed

    def set(self, access_key_id, secret_access_key, session_token=''):
        ak, sk, st = (str(x or '').strip() for x in (access_key_id, secret_access_key, session_token))
        if not re.fullmatch(r'[A-Z0-9]{16,128}', ak) or not 16 <= len(sk) <= 128 or CONTROL.search(sk) or len(st) > 4096 or CONTROL.search(st):
            raise ImportFail('invalid_credentials', 'The credentials do not look like an AWS access key (key ID upper-case letters/digits, secret key 16–128 characters).')
        with self._lock:
            self._mem = dict(aws_access_key_id=ak, aws_secret_access_key=sk, **({'aws_session_token': st} if st else {}))
            self._set_at = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None, microsecond=0)

    def clear(self):
        with self._lock: self._mem, self._set_at = None, None

    def get(self):
        """-> (boto3 kwargs, source) or (None, None)."""
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


NO_LIBRARY = ('S3 import needs the boto3 package, which is not installed on the server. Run: .venv/bin/pip install -e ".[s3]" '
              '(or ./run.sh, which now installs it), then restart the server.')


def library_ok():
    """boto3 + botocore installed? (optional "s3" package; checked before a job is created so it does not fail midway)"""
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
            return ImportFail('s3_denied', f'S3 denied access ({code}): check the credentials and read permission on this bucket/prefix.', 502)
        if code in ('NoSuchBucket', 'NoSuchKey', '404'):
            return ImportFail('s3_not_found', f'S3: {code} (bucket or object does not exist).', 502)
        return ImportFail('s3_error', f'S3 answered with error {code}.', 502)
    if isinstance(e, (EndpointConnectionError, BotoCoreError, OSError)):
        return ImportFail('s3_unreachable', f'S3 is unreachable from the server ({type(e).__name__}). Check the server\'s outbound access to the S3 endpoint of the import region.', 502)
    return ImportFail('s3_error', f'{type(e).__name__}', 502)


def list_objects(s3, bucket, prefix, cap):
    """[{key, size, etag}] under the prefix (ListObjectsV2, paginated). Stops at `cap` objects."""
    out = []
    for page in s3.get_paginator('list_objects_v2').paginate(Bucket=bucket, Prefix=prefix):
        for o in page.get('Contents', []):
            out.append(dict(key=o['Key'], size=int(o['Size']), etag=str(o.get('ETag', '')).strip('"')))
            if len(out) > cap: return out
    return out


def list_folders(s3, bucket, base):
    """Names of date folders (valid YYYY-MM-DD) directly under the prefix: ListObjectsV2 with Delimiter '/', so folder
    contents are not listed (cheap even with years of history)."""
    out = set()
    for page in s3.get_paginator('list_objects_v2').paginate(Bucket=bucket, Prefix=base, Delimiter='/'):
        for cp in page.get('CommonPrefixes', []):
            name = cp['Prefix'][len(base):].rstrip('/')
            if rules.DATE_DIR.fullmatch(name):
                try: datetime.date.fromisoformat(name); out.add(name)
                except ValueError: pass
    return sorted(out)


def plan(cfg, objects, prefix, folder):
    """Object plan (rules in domain.s3_import.plan) with the previous-download manifest from the inbox."""
    inbox = os.path.join(cfg.inbox_dir, folder)
    try:
        with open(os.path.join(inbox, MANIFEST), encoding='utf-8') as fh: before = json.load(fh)
    except (OSError, ValueError): before = {}

    def have(stored, size):
        kept = os.path.join(inbox, *stored.split('/'))
        return os.path.isfile(kept) and os.path.getsize(kept) == size
    return s3_import.plan(cfg, objects, prefix, folder, before, have)


# ------------------------------------------------------------------ run
def run(cfg, url, creds_store, dry_run=False, progress=None):
    """The whole import. dry_run = list + plan only, writes nothing. Ingest is run by the CALLER (owns DuckDB)."""
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
    except Exception as e: raise _s3_error(e) from None   # noqa: BLE001  message without secrets
    if len(objects) > cfg.import_max_objects * 4:
        raise ImportFail('too_many_objects', f'This prefix contains more than {cfg.import_max_objects * 4} objects; the limit is {cfg.import_max_objects} log files.')
    if not objects: raise ImportFail('empty_prefix', f'No objects in s3://{bucket}/{prefix}.', 404)
    rows = plan(cfg, objects, prefix, folder)
    take = [r for r in rows if r['action'] == 'fetch']
    res = dict(bucket=bucket, prefix=prefix, folder=folder, dry_run=dry_run, credentials=source, objects=rows,
               take=len(take), skipped=len(rows) - len(take), bytes=sum(r['size'] for r in take), downloaded=0, downloaded_bytes=0, extracted=0, warnings=[])
    local = [r for r in rows if r.get('extract_local')]
    if os.path.isdir(os.path.join(cfg.log_dir, folder)):
        res['warnings'].append(f'folder {folder} also exists in the local log folder; the local version is used when ingesting')
    if not dry_run and local: res['extracted'] += _extract_in_inbox(cfg, folder, local)
    if dry_run or not take:
        res['seconds'] = round(time.time() - t0, 2); return res
    tmp = os.path.join(cfg.data_dir, 'tmp', f'import-{uuid.uuid4().hex[:12]}')
    try:
        for i, r in enumerate(take):
            if time.time() > deadline: raise ImportFail('timeout', f'The import exceeded the time limit of {cfg.import_timeout_minutes} minutes.', 504)
            dst = os.path.join(tmp, folder, *r['rel'].split('/'))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            n = 0
            try:
                body = s3.get_object(Bucket=bucket, Key=r['key'])['Body']
                with open(dst, 'wb') as fh:
                    for chunk in body.iter_chunks(2**20):
                        n += len(chunk)
                        if n > r['size'] or n > cfg.import_max_object_mb * 2**20:
                            raise ImportFail('size_mismatch', f'Object {r["rel"]} is larger than listed; import cancelled.', 502)
                        fh.write(chunk)
            except ImportFail: raise
            except Exception as e: raise _s3_error(e) from None   # noqa: BLE001
            if n != r['size']: raise ImportFail('size_mismatch', f'Object {r["rel"]} downloaded {n} bytes, listed {r["size"]}; import cancelled.', 502)
            res['downloaded'] += 1; res['downloaded_bytes'] += n
            if cfg.import_extract and r['rel'].endswith('.gz'):   # .log.gz -> .log (in the temp folder; only the .log is moved)
                r['stored'], r['stored_size'] = r['rel'][:-3], _gunzip(dst, dst[:-3], r['rel'], cfg.import_max_object_mb * 2**20 * EXTRACT_RATIO)
                res['extracted'] += 1
            progress(phase='download', done=i + 1, total=len(take))
        _move_into_inbox(cfg, os.path.join(tmp, folder), folder, take)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    res['seconds'] = round(time.time() - t0, 2)
    return res


def _move_into_inbox(cfg, src, folder, take):
    """New folder: one rename (atomic). Existing folder: each file is replaced by a rename (atomic per file). Then the manifest."""
    dst = os.path.join(cfg.inbox_dir, folder)
    os.makedirs(cfg.inbox_dir, exist_ok=True)
    if not os.path.exists(dst):
        try: os.replace(src, dst)
        except OSError: shutil.copytree(src, dst + '.part'); os.replace(dst + '.part', dst)   # different file system
    else:
        for r in take:
            kept = r.get('stored', r['rel'])
            s, d = os.path.join(src, *kept.split('/')), os.path.join(dst, *kept.split('/'))
            os.makedirs(os.path.dirname(d), exist_ok=True)
            try: os.replace(s, d)
            except OSError: shutil.copy2(s, d + '.part'); os.replace(d + '.part', d)
            if kept != r['rel']:   # the old .gz version from a previous import is no longer needed
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
    """Extract src (.gz) to dst, delete src. The gzip content is checked in full; result > limit -> import cancelled. -> result size."""
    n = 0
    try:
        with gzip.open(src, 'rb') as g, open(dst + '.part', 'wb') as out:
            while chunk := g.read(2**20):
                n += len(chunk)
                if n > limit: break
                out.write(chunk)
    except (OSError, EOFError, zlib.error):
        _rm(dst + '.part')
        raise ImportFail('bad_gzip', f'Object {rel} is not a complete gzip (corrupt or truncated); import cancelled.', 502) from None
    if n > limit:
        _rm(dst + '.part')
        raise ImportFail('extract_too_large', f'Extracted {rel} exceeds {limit / 2**20:.0f} MB; import cancelled.', 413)
    os.replace(dst + '.part', dst); os.remove(src)
    return n


def _rm(path):
    try: os.remove(path)
    except FileNotFoundError: pass


def _extract_in_inbox(cfg, folder, rows):
    """.gz files from earlier imports (before automatic extraction existed) are extracted in place, without re-download; manifest updated."""
    base = os.path.join(cfg.inbox_dir, folder)
    for r in rows:
        src = os.path.join(base, *r['rel'].split('/'))
        r['stored'], r['stored_size'] = r['rel'][:-3], _gunzip(src, src[:-3], r['rel'], cfg.import_max_object_mb * 2**20 * EXTRACT_RATIO)
    _manifest_update(base, rows)
    return len(rows)


# ------------------------------------------------------------------ S3Gateway port (used by monishield/application/import_service.py)
class S3Gateway:
    """S3 access for the application layer: credentials (process memory + .env), prefix download, date folder list, connection
    test. Module functions are looked up at call time (tests can replace `library_ok`, `ENDPOINT`)."""

    def __init__(self, cfg):
        self.cfg, self.creds = cfg, Credentials(cfg)

    def library_ok(self): return library_ok()

    def ready(self):
        """Library + credentials present; otherwise -> ImportFail (400) with the hint."""
        if not library_ok(): raise ImportFail('no_s3_library', NO_LIBRARY, 400)
        if not self.creds.get()[0]: raise ImportFail('no_credentials', NO_CREDENTIALS, 400)

    def run(self, url, dry_run=False, progress=None): return run(self.cfg, url, self.creds, dry_run=dry_run, progress=progress)

    def list_folders(self, bucket, base): return list_folders(_client(self.cfg, self.creds.get()[0]), bucket, base)

    def probe(self, bucket, prefix):
        """List one object (connection test). Error -> ImportFail."""
        try: _client(self.cfg, self.creds.get()[0]).list_objects_v2(Bucket=bucket, Prefix=prefix, MaxKeys=1)
        except Exception as e: raise _s3_error(e) from None   # noqa: BLE001

    def error(self, e): return e if isinstance(e, ImportFail) else _s3_error(e)
