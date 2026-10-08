"""Storage for browser log-folder upload sessions: each file to a temp directory, then "finish": extract .gz and
move into the inbox (ingest by the caller). Path rules and limits: monishield/domain/uploads.py."""
import os, shutil, threading, time, uuid

from monishield.domain.s3_import import ImportFail
from monishield.infrastructure import importer

# abandoned upload sessions (tab closed) are cleaned up after cfg.upload_session_hours (S4_UPLOAD_SESSION_HOURS)


class Uploads:
    """Upload sessions in process memory: id -> plan + files received so far. One session = one folder selection."""

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
        if not s or s['by'] != by: raise ImportFail('not_found', 'Upload session not found (expired or owned by another admin).', 404)
        return s

    def target(self, uid, by, i):
        """-> (plan entry, temporary target path) for file i (browser selection index)."""
        s = self.get(uid, by)
        e = next((f for f in s['files'] if f['i'] == i), None)
        if e is None: raise ImportFail('not_found', 'This file is not part of the upload plan.', 404)
        return e, os.path.join(self._dir(uid), *e['rel'].split('/'))

    def received(self, uid, i):
        with self._lock: self.sessions[uid]['got'].add(i)

    def finish(self, uid, by):
        """All files received -> extract .gz (if S4_IMPORT_EXTRACT) -> move into the inbox. -> summary."""
        s = self.get(uid, by)
        missing = [f['rel'] for f in s['files'] if f['i'] not in s['got']]
        if missing: raise ImportFail('incomplete', f'{len(missing)} files not uploaded yet (e.g. {missing[0]}).', 409)
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
                for f in (x for x in s['files'] if x['folder'] == d):   # per file (atomic per file): existing folders get updated too
                    kept = f.get('stored', f['rel'])
                    a, b = os.path.join(base, *kept.split('/')), os.path.join(cfg.inbox_dir, *kept.split('/'))
                    os.makedirs(os.path.dirname(b), exist_ok=True)
                    os.replace(a, b)
                    if kept != f['rel']: importer._rm(os.path.join(cfg.inbox_dir, *f['rel'].split('/')))   # the old .gz is no longer used
                    elif kept.endswith('.gz'): importer._rm(b[:-3])   # an old .log with the same name would win at ingest: remove it
        finally:
            self.drop(uid)
        return dict(folders=folders, files=len(s['files']), bytes=sum(f['size'] for f in s['files']), extracted=extracted)

    def drop(self, uid):
        with self._lock: self.sessions.pop(uid, None)
        shutil.rmtree(self._dir(uid), ignore_errors=True)

    def _expire(self):
        old = [u for u, s in list(self.sessions.items()) if time.time() - s['at'] > self.cfg.upload_session_hours * 3600]
        for u in old: self.drop(u)
        tmp = os.path.join(self.cfg.data_dir, 'tmp')   # leftover sessions from a previous process (server restarted)
        for d in os.listdir(tmp) if os.path.isdir(tmp) else []:
            if d.startswith('upload-') and d[7:] not in self.sessions: shutil.rmtree(os.path.join(tmp, d), ignore_errors=True)
