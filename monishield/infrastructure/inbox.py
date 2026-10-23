"""Inbox for logs from Kafka (Inbox port adapter): log lines are appended to files laid out the SAME as the
S3 export, <inbox>/<date>/<namespace>/<service>/log_<service>_<pod>_<date>-00-00.log (monishield/domain/kafka_message.py)."""
import collections, datetime, json, os

from monishield.domain.kafka_message import folder_of, relpath

MARK = '.kafka-feed.json'          # marks an inbox folder filled by Kafka
S3_MANIFEST = '.s3-import.json'    # = importer.MANIFEST (not imported: importer imports this module)
SUPERSEDED = '.kafka-superseded'   # <inbox>/.kafka-superseded/<date>/...: Kafka files an S3 copy replaced (kept, out of the dashboard)


def s3_files(folder_dir):
    """Logical file names of the S3 copy in an inbox folder: the manifest keys and the names they were stored under."""
    try:
        with open(os.path.join(folder_dir, S3_MANIFEST), encoding='utf-8') as fh: man = json.load(fh)
    except (OSError, ValueError): return set()
    return set(man) | {m.get('stored', k) for k, m in man.items()}


def supersede(inbox, folder, s3=(), duplicate_services=()):
    """A folder holds ONE source. The S3 copy of the date is complete, so every file of the folder that is not part of it is
    Kafka's and leaves the folder (owner request 2026-10-23: no mixing S3 and Kafka in a folder). Files of the services
    the S3 copy brings (`duplicate_services`, "namespace/service") are the same lines again: deleted. Files of services
    only Kafka sends are MOVED to <inbox>/.kafka-superseded/<folder>/ (nothing is lost, nothing is counted). The Kafka mark
    goes. Ingest then drops the rows of the files that left. `s3` = files being added by the import that is running.
    -> number of files removed or moved."""
    dst = os.path.join(inbox, folder)
    keep = set(s3) | s3_files(dst) | {MARK, S3_MANIFEST}
    out = []
    for root, _, files in os.walk(dst):
        for name in files:
            rel = os.path.relpath(os.path.join(root, name), dst).replace(os.sep, '/')
            if rel not in keep: out.append(rel)
    for rel in out:
        src = os.path.join(dst, *rel.split('/'))
        if '/'.join(rel.split('/')[:2]) in duplicate_services: os.remove(src); continue
        to = os.path.join(inbox, SUPERSEDED, folder, *rel.split('/'))
        os.makedirs(os.path.dirname(to), exist_ok=True)
        os.replace(src, to)
    for root, dirs, files in os.walk(dst, topdown=False):   # empty service folders left behind
        if root != dst and not os.listdir(root): os.rmdir(root)
    try: os.remove(os.path.join(dst, MARK))
    except FileNotFoundError: pass
    return len(out)


def reconcile(inbox):
    """Folders that already have both an S3 copy and the Kafka mark (made before this rule existed): supersede them.
    Cheap when there is nothing to do (a directory listing). -> the folders that were changed."""
    try: names = sorted(os.listdir(inbox))
    except OSError: return []
    done = []
    for d in names:
        p = os.path.join(inbox, d)
        if d.startswith('.') or not os.path.exists(os.path.join(p, MARK)) or not os.path.exists(os.path.join(p, S3_MANIFEST)): continue
        if supersede(inbox, d): done.append(d)
    return done


class Spool:
    """Line buffer per file; flush() appends them to the files in the inbox."""

    def __init__(self, inbox):
        self.inbox, self.buf, self.n = inbox, collections.defaultdict(list), 0

    def add(self, rec):
        f = folder_of(rec['t'])
        self.buf[relpath(rec, f)].append(rec['line']); self.n += 1
        return f

    def flush(self):
        """-> {folder: lines written}. Lines for a date whose complete S3 copy is already in the inbox (S3 manifest
        present, see importer.py) are dropped: they are in the S3 files already and would be counted twice."""
        out = collections.Counter()
        for rel, lines in self.buf.items():
            if os.path.exists(os.path.join(self.inbox, rel.split(os.sep, 1)[0], S3_MANIFEST)): continue
            path = os.path.join(self.inbox, rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'a', encoding='utf-8', newline='\n') as fh: fh.write('\n'.join(lines) + '\n')
            out[rel.split(os.sep, 1)[0]] += len(lines)
        for f, n in out.items():
            mp = os.path.join(self.inbox, f, MARK)
            try: m = json.load(open(mp, encoding='utf-8'))
            except (OSError, ValueError): m = dict(lines=0)
            m.update(lines=m.get('lines', 0) + n, updated=datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds'))
            with open(mp, 'w', encoding='utf-8') as fh: json.dump(m, fh)
        self.buf.clear(); self.n = 0
        return dict(out)
