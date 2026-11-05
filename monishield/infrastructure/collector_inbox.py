"""Inbox for logs from collectors (CollectorInbox port adapter): lines are appended to files laid out the SAME as the S3
export, <collector inbox>/<date>/<namespace>/<service>/log_<service>_<pod>_<date>-HH-00.log (monishield/domain/otlp_logs.py).
The collector inbox is its own folder (<inbox>/collector): collectors never share a folder with S3 or Kafka."""
import collections, os, shutil, threading


class UnsafePath(ValueError):
    """A relative path that would leave the inbox."""


class CollectorInbox:
    def __init__(self, root):
        self.root = os.path.abspath(root)
        self._guard, self._locks = threading.Lock(), {}

    def _lock(self, path):
        """One lock per file, so requests for different files do not wait for each other."""
        with self._guard: return self._locks.setdefault(path, threading.Lock())

    def _path(self, rel):
        """Defence in depth on top of the domain's name checks: the file must stay inside the inbox, symlinks resolved."""
        path = os.path.join(self.root, rel)
        real, base = os.path.realpath(path), os.path.realpath(self.root)
        if os.path.isabs(rel) or os.path.commonpath([real, base]) != base or real == base:
            raise UnsafePath('path leaves the inbox')
        return path

    def append(self, records):
        """Append the lines of the records to their files and make them durable. -> {folder: lines written}.
        Lines of one file go out in ONE write under that file's lock, so two requests never interleave their lines."""
        by_file = collections.defaultdict(list)
        for rec in records: by_file[rec['relpath']].append(rec['line'])
        paths = {rel: self._path(rel) for rel in by_file}   # all checked before the first byte is written
        out = collections.Counter()
        for rel, lines in by_file.items():
            self._write(paths[rel], '\n'.join(lines) + '\n')
            out[rel.split(os.sep, 1)[0]] += len(lines)
        return dict(out)

    def _write(self, path, text):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with self._lock(path), open(path, 'a', encoding='utf-8', newline='\n') as fh:
            fh.write(text); fh.flush(); os.fsync(fh.fileno())

    def free_bytes(self):
        """Free space of the disk the inbox is on (its nearest existing parent while the inbox itself is not created yet)."""
        p = self.root
        while not os.path.exists(p) and os.path.dirname(p) != p: p = os.path.dirname(p)
        return shutil.disk_usage(p).free
