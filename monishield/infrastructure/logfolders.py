"""Log folders on disk (LogFolders port adapter) of one data source: for S3 the main log folder (S4_LOG_DIR, read-only) and
the inbox (S4_INBOX_DIR: S3 imports, uploads); for Kafka its own inbox (<inbox>/kafka, written by the consumer). Directory
listings only; file contents are read by ingest."""
import os, shutil

from monishield.domain import rules
from monishield.infrastructure.importer import MANIFEST


class LogFolders:
    def __init__(self, cfg, kind='s3'):
        self.cfg, self.kind = cfg, kind

    @staticmethod
    def _dates(root):
        if not root: return set()
        try: return {d for d in os.listdir(root) if rules.DATE_DIR.fullmatch(d)}
        except OSError: return set()

    @staticmethod
    def _has_logs(root, folder):
        if not root: return False   # no main log folder for this source
        p = os.path.join(root, folder)
        return os.path.isdir(p) and any(n.endswith(('.log', '.log.gz')) for _, _, names in os.walk(p) for n in names)

    def dates(self):
        """-> (date folders in the log folder, date folders in the inbox)."""
        return self._dates(self.cfg.log_dir), self._dates(self.cfg.inbox_dir)

    def on_disk(self, folder):
        """-> (has log files in the main log folder, has log files in the inbox)."""
        return self._has_logs(self.cfg.log_dir, folder), self._has_logs(self.cfg.inbox_dir, folder)

    def in_log_dir(self, folder): return bool(self.cfg.log_dir) and os.path.isdir(os.path.join(self.cfg.log_dir, folder))

    def new_folders(self, known):
        """Date folders with log files that are not yet `known`. Cheap: only the top directory listing + candidate folders."""
        unseen = set()
        for root in (self.cfg.log_dir, self.cfg.inbox_dir):
            for d in sorted(self._dates(root) - set(known) - unseen):
                if self._has_logs(root, d): unseen.add(d)
        return sorted(unseen)

    def from_s3(self, folders):
        """Inbox folders holding S3 import results (manifest present)."""
        return {d for d in folders if os.path.exists(os.path.join(self.cfg.inbox_dir, d, MANIFEST))}

    def source(self, folder):
        """Where a folder's logs come from: 'kafka' for the Kafka source; for S3: 'log' (main log folder; it wins when both
        exist), 's3' (S3 import), 'upload' (uploaded from the browser), or None (not on disk)."""
        if self.kind == 'kafka': return 'kafka' if self._has_logs(self.cfg.inbox_dir, folder) else None
        if self._has_logs(self.cfg.log_dir, folder): return 'log'
        if os.path.exists(os.path.join(self.cfg.inbox_dir, folder, MANIFEST)): return 's3'
        return 'upload' if self._has_logs(self.cfg.inbox_dir, folder) else None

    def inbox_ok(self, folder):
        p = os.path.realpath(os.path.join(self.cfg.inbox_dir, folder))
        return os.path.dirname(p) == os.path.realpath(self.cfg.inbox_dir)

    def remove_inbox(self, folder):
        """Delete a folder in the inbox (the main log folder is never deleted). -> True when something was deleted."""
        p = os.path.realpath(os.path.join(self.cfg.inbox_dir, folder))
        if not self.inbox_ok(folder) or not os.path.isdir(p): return False
        shutil.rmtree(p)
        return True
