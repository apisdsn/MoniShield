"""Backups (owner request 2026-10-27): a daily copy of what cannot be rebuilt from the logs alone, in one folder per day:

    <backup dir>/<YYYY-MM-DD>/s3.duckdb.gz       the S3 database (raw rows + aggregates of every folder)
                             kafka.duckdb.gz    the Kafka database
                             accounts.json.gz   every table of the account database (users, password hashes, audit log, ...)
                             manifest.json      sizes + sha256 of the files, time, MoniShield version

The raw log files are not copied: their rows are in the databases, and the S3 ones can be fetched again. Files and folders
are private (0600/0700): they hold password hashes and IP addresses. Optionally the folder is also copied to object storage
(S4_BACKUP_S3=s3://bucket/prefix/, with the keys of the object storage settings; they need write access there).

Restore (server stopped): `monishield restore <backup folder>` puts the databases back (the current ones are kept beside them
as *.before-restore) and refills an EMPTY account database.
"""
import base64, datetime, gzip, hashlib, json, os, shutil, stat, tempfile, threading

from monishield import __version__
from monishield.domain import s3_import, storage
from monishield.domain.errors import Fail
from monishield.infrastructure import ingest

FILES = ('s3.duckdb.gz', 'kafka.duckdb.gz', 'accounts.json.gz')
_lock = threading.Lock()


def _sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(2**20), b''): h.update(chunk)
    return h.hexdigest()


def _gzip(src, dst):
    with open(src, 'rb') as a, gzip.open(dst, 'wb', compresslevel=6) as b: shutil.copyfileobj(a, b, 2**20)


def copy_duckdb(con, dst_gz):
    """Consistent copy of the database behind `con` (COPY FROM DATABASE), gzipped to dst_gz. Holds the ingest lock (waits for a
    running ingest) so the copy never sees half a folder."""
    if not ingest._lock.acquire(timeout=1800): raise Fail('backup_busy', 'An ingest has been running for 30 minutes; the backup was not made.', 409)
    try:
        # next to the backup, on the data volume: /tmp is in memory (tmpfs) in the Docker container
        tmp = tempfile.mkdtemp(prefix='.copy-', dir=os.path.dirname(dst_gz))
        try:
            path = os.path.join(tmp, 'copy.duckdb')
            cur = con.cursor()
            try:
                main = cur.execute('SELECT current_database()').fetchone()[0]
                cur.execute(f"ATTACH '{path}' AS backup_copy")
                try: cur.execute(f'COPY FROM DATABASE "{main}" TO backup_copy')
                finally: cur.execute('DETACH backup_copy')
            finally: cur.close()
            _gzip(path, dst_gz)
        finally: shutil.rmtree(tmp, ignore_errors=True)
    finally: ingest._lock.release()


def _json_value(v):
    if isinstance(v, (bytes, bytearray, memoryview)): return {'$b64': base64.b64encode(bytes(v)).decode()}
    if isinstance(v, (datetime.datetime, datetime.date)): return {'$dt': v.isoformat()}
    return v


def export_accounts(engine, metadata, dst_gz):
    """Every table of the account database, as {table: [row dicts]} (bytes as base64, times as ISO text)."""
    from sqlalchemy import select
    out = {}
    with engine.connect() as c:
        for t in metadata.sorted_tables:
            out[t.name] = [{k: _json_value(v) for k, v in r._mapping.items()} for r in c.execute(select(t))]
    with gzip.open(dst_gz, 'wt', encoding='utf-8') as fh: json.dump(dict(version=__version__, tables=out), fh, ensure_ascii=False)


def _from_json(v, col_type):
    if isinstance(v, dict) and '$b64' in v: return base64.b64decode(v['$b64'])
    if isinstance(v, dict) and '$dt' in v:
        d = datetime.datetime.fromisoformat(v['$dt'])
        return d.date() if col_type.python_type is datetime.date else d
    return v


def restore_accounts(engine, metadata, src_gz):
    """Refill an EMPTY account database from accounts.json.gz. -> {table: rows}. Refuses when any table already has rows."""
    from sqlalchemy import func, insert, select, text
    with gzip.open(src_gz, 'rt', encoding='utf-8') as fh: data = json.load(fh)['tables']
    done = {}
    with engine.begin() as c:
        busy = [t.name for t in metadata.sorted_tables if c.execute(select(func.count()).select_from(t)).scalar()]
        if busy: raise Fail('restore_not_empty', f'The account database is not empty ({", ".join(busy)}); restore needs an empty one.', 409)
        for t in metadata.sorted_tables:
            rows = [{k: _from_json(v, t.c[k].type) for k, v in r.items() if k in t.c} for r in data.get(t.name, [])]
            if rows: c.execute(insert(t), rows)
            done[t.name] = len(rows)
        if engine.dialect.name == 'postgresql':   # serial ids continue after the restored rows
            for t in metadata.sorted_tables:
                pk = list(t.primary_key.columns)
                if len(pk) == 1 and pk[0].autoincrement in (True, 'auto') and pk[0].type.python_type is int and done[t.name]:
                    c.execute(text(f"SELECT setval(pg_get_serial_sequence('{t.name}', '{pk[0].name}'), (SELECT max({pk[0].name}) FROM {t.name}))"))
    return done


class Backups:
    """Backups port adapter (monishield/application/backup_service.py)."""

    def __init__(self, cfg): self.cfg = cfg

    def root(self): return self.cfg.backup_path

    def make(self, cons, auth, day):
        """Write today's backup folder (replaced when it exists). -> manifest dict. cons = {'s3': con, 'kafka': con}."""
        if not _lock.acquire(blocking=False): raise Fail('backup_busy', 'A backup is already running.', 409)
        try:
            os.makedirs(self.root(), mode=0o700, exist_ok=True)
            final = os.path.join(self.root(), day)
            work = final + '.part'
            shutil.rmtree(work, ignore_errors=True)
            os.makedirs(work, mode=0o700)
            started = datetime.datetime.now(datetime.timezone.utc)
            try:
                for name, con in cons.items(): copy_duckdb(con, os.path.join(work, f'{name}.duckdb.gz'))
                from monishield.infrastructure.auth import Base
                export_accounts(auth.engine, Base.metadata, os.path.join(work, 'accounts.json.gz'))
                files = {}
                for f in sorted(os.listdir(work)):
                    p = os.path.join(work, f); os.chmod(p, stat.S_IRUSR | stat.S_IWUSR)
                    files[f] = dict(bytes=os.path.getsize(p), sha256=_sha256(p))
                man = dict(day=day, version=__version__, started=started.isoformat(timespec='seconds'),
                           finished=datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds'), files=files)
                with open(os.path.join(work, 'manifest.json'), 'w', encoding='utf-8') as fh: json.dump(man, fh, indent=1)
                os.chmod(os.path.join(work, 'manifest.json'), stat.S_IRUSR | stat.S_IWUSR)
                shutil.rmtree(final, ignore_errors=True)
                os.replace(work, final)
                return man
            except BaseException:
                shutil.rmtree(work, ignore_errors=True); raise
        finally: _lock.release()

    def list(self):
        """Backups on disk, newest first: [dict(day, bytes, files, version, finished)]; folders without a manifest are skipped."""
        out = []
        try: names = sorted(os.listdir(self.root()), reverse=True)
        except OSError: return out
        for d in names:
            p = os.path.join(self.root(), d, 'manifest.json')
            try:
                with open(p, encoding='utf-8') as fh: m = json.load(fh)
            except (OSError, ValueError): continue
            out.append(dict(day=m.get('day', d), bytes=sum(f['bytes'] for f in m['files'].values()), files=sorted(m['files']), version=m.get('version'),
                            finished=m.get('finished')))
        return out

    def prune(self, keep):
        """Keep the newest `keep` backups. -> days deleted."""
        gone = [b['day'] for b in self.list()[keep:]]
        for d in gone: shutil.rmtree(os.path.join(self.root(), d), ignore_errors=True)
        return gone

    def upload(self, day, client=None):
        """Copy one backup folder to S4_BACKUP_S3. -> the s3:// address. client = an S3 client (tests); default: the object
        storage settings' client."""
        target = self.cfg.backup_s3.strip()
        if not target: return None
        if storage.is_azure(self.cfg.storage_provider): raise Fail('backup_upload', 'Copying backups to Azure Blob Storage is not supported; use an S3-compatible provider.', 400)
        bucket, _, prefix = target[5:].partition('/')
        if not bucket: raise Fail('backup_upload', 'S4_BACKUP_S3 must look like s3://bucket/prefix/.', 400)
        prefix = (prefix.rstrip('/') + '/') if prefix else ''
        if client is None:
            from monishield.infrastructure import importer
            creds, _ = importer.Credentials(self.cfg).get()
            if not creds: raise Fail('backup_upload', s3_import.NO_CREDENTIALS, 400)
            client = importer._client(self.cfg, creds)
        folder = os.path.join(self.root(), day)
        try:
            for f in sorted(os.listdir(folder)): client.upload_file(os.path.join(folder, f), bucket, f'{prefix}{day}/{f}')
        except Fail: raise
        except Exception as e:   # noqa: BLE001  access denied, wrong bucket, network: one readable message, no keys
            raise Fail('backup_upload', f'Copying the backup to {target} failed ({type(e).__name__}: {str(e)[:200]}).', 502) from None
        return f's3://{bucket}/{prefix}{day}/'


def restore(cfg, folder, auth_engine, metadata, accounts=True, databases=True):
    """Put a backup back (server STOPPED: DuckDB has one owner). The current database files are kept as *.before-restore.
    -> dict of what was restored."""
    from monishield.domain import config_model
    with open(os.path.join(folder, 'manifest.json'), encoding='utf-8') as fh: man = json.load(fh)
    for f, info in man['files'].items():
        if _sha256(os.path.join(folder, f)) != info['sha256']: raise Fail('restore_corrupt', f'{f} does not match its checksum; the backup is damaged.', 400)
    done = {}
    if databases:
        for name, path in (('s3', cfg.db_path), ('kafka', config_model.kafka_config(cfg).db_path)):
            src = os.path.join(folder, f'{name}.duckdb.gz')
            if not os.path.exists(src): continue
            os.makedirs(os.path.dirname(path), exist_ok=True)
            for p in (path, path + '.wal'):
                if os.path.exists(p): os.replace(p, p + '.before-restore')
            with gzip.open(src, 'rb') as a, open(path, 'wb') as b: shutil.copyfileobj(a, b, 2**20)
            done[name] = path
    if accounts and os.path.exists(os.path.join(folder, 'accounts.json.gz')):
        done['accounts'] = restore_accounts(auth_engine, metadata, os.path.join(folder, 'accounts.json.gz'))
    return done
