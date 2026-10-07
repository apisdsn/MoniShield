"""Folder log di disk (adapter port LogFolders): folder log utama (S4_LOG_DIR, hanya dibaca) dan kotak masuk
(S4_INBOX_DIR: hasil impor S3, unggahan, Kafka). Hanya daftar isi direktori; isi file dibaca ingest."""
import os, shutil

from monishield.domain import rules
from monishield.infrastructure.importer import MANIFEST


class LogFolders:
    def __init__(self, cfg): self.cfg = cfg

    def _roots(self): return (self.cfg.log_dir, self.cfg.inbox_dir)

    @staticmethod
    def _dates(root):
        try: return {d for d in os.listdir(root) if rules.DATE_DIR.fullmatch(d)}
        except OSError: return set()

    @staticmethod
    def _has_logs(root, folder):
        p = os.path.join(root, folder)
        return os.path.isdir(p) and any(n.endswith(('.log', '.log.gz')) for _, _, names in os.walk(p) for n in names)

    def dates(self):
        """-> (folder tanggal di folder log, folder tanggal di kotak masuk)."""
        return self._dates(self.cfg.log_dir), self._dates(self.cfg.inbox_dir)

    def on_disk(self, folder):
        """-> (ada file log di folder log utama, ada file log di kotak masuk)."""
        return self._has_logs(self.cfg.log_dir, folder), self._has_logs(self.cfg.inbox_dir, folder)

    def in_log_dir(self, folder): return os.path.isdir(os.path.join(self.cfg.log_dir, folder))

    def new_folders(self, known):
        """Folder tanggal berisi file log yang belum `known`. Murah: hanya daftar isi direktori teratas + folder calon."""
        baru = set()
        for root in self._roots():
            for d in sorted(self._dates(root) - set(known) - baru):
                if self._has_logs(root, d): baru.add(d)
        return sorted(baru)

    def from_s3(self, folders):
        """Folder kotak masuk yang berisi hasil impor S3 (ada manifest)."""
        return {d for d in folders if os.path.exists(os.path.join(self.cfg.inbox_dir, d, MANIFEST))}

    def inbox_ok(self, folder):
        p = os.path.realpath(os.path.join(self.cfg.inbox_dir, folder))
        return os.path.dirname(p) == os.path.realpath(self.cfg.inbox_dir)

    def remove_inbox(self, folder):
        """Hapus folder di kotak masuk (folder log utama tidak pernah dihapus). -> True bila ada yang dihapus."""
        p = os.path.realpath(os.path.join(self.cfg.inbox_dir, folder))
        if not self.inbox_ok(folder) or not os.path.isdir(p): return False
        shutil.rmtree(p)
        return True
