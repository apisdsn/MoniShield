"""Inbox for logs from Kafka (Inbox port adapter): log lines are appended to files laid out the SAME as the
S3 export, <kafka inbox>/<date>/<namespace>/<service>/log_<service>_<pod>_<date>-00-00.log (monishield/domain/kafka_message.py).
The Kafka inbox is its own folder (<inbox>/kafka): Kafka and S3 never share a folder (owner request 2026-10-23)."""
import collections, os, shutil

from monishield.domain.kafka_message import folder_of, relpath

MARK = '.kafka-feed.json'          # old layout only: marked an inbox folder filled by Kafka (see migrate)
S3_MANIFEST = '.s3-import.json'    # = importer.MANIFEST (not imported: importer imports this module)
SUPERSEDED = '.kafka-superseded'   # old layout only: Kafka files an S3 copy had replaced (see migrate)


class Spool:
    """Line buffer per file; flush() appends them to the files in the inbox."""

    def __init__(self, inbox):
        self.inbox, self.buf, self.n = inbox, collections.defaultdict(list), 0

    def add(self, rec):
        f = folder_of(rec['t'])
        self.buf[relpath(rec, f)].append(rec['line']); self.n += 1
        return f

    def flush(self):
        """Append the buffered lines to their files. -> {folder: lines written}."""
        out = collections.Counter()
        for rel, lines in self.buf.items():
            path = os.path.join(self.inbox, rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'a', encoding='utf-8', newline='\n') as fh: fh.write('\n'.join(lines) + '\n')
            out[rel.split(os.sep, 1)[0]] += len(lines)
        self.buf.clear(); self.n = 0
        return dict(out)


def _merge(src, dst):
    """Move the files of the folder `src` into `dst` (created when missing). A file that already exists there keeps the
    name `<name>.moved` beside it: nothing is overwritten or lost."""
    for root, _, files in os.walk(src):
        for name in files:
            rel = os.path.relpath(os.path.join(root, name), src)
            to = os.path.join(dst, rel)
            os.makedirs(os.path.dirname(to), exist_ok=True)
            if os.path.exists(to): to += '.moved'
            shutil.move(os.path.join(root, name), to)
    shutil.rmtree(src, ignore_errors=True)


def migrate(inbox, kafka_inbox):
    """Move Kafka's files out of the old shared layout into the Kafka inbox (once, safe to repeat):
      * a folder with the Kafka mark and no S3 manifest is Kafka's: moved as a whole;
      * a folder with the mark AND an S3 manifest holds an S3 copy plus Kafka files: everything that is not in the manifest
        is Kafka's and moves;
      * <inbox>/.kafka-superseded/<date>/ (Kafka files an S3 copy had replaced) joins the Kafka folder of that date.
    -> (folders that were Kafka's alone, folders whose Kafka files moved): the first list must be forgotten by the S3 database."""
    kafka_only, split = [], []
    try: names = sorted(os.listdir(inbox))
    except OSError: return kafka_only, split
    for d in names:
        p = os.path.join(inbox, d)
        if d.startswith('.') or not os.path.isdir(p) or not os.path.exists(os.path.join(p, MARK)): continue
        if not os.path.exists(os.path.join(p, S3_MANIFEST)):
            _merge(p, os.path.join(kafka_inbox, d)); kafka_only.append(d); continue
        keep = _s3_files(p) | {MARK, S3_MANIFEST}
        for root, _, files in os.walk(p):
            for name in files:
                rel = os.path.relpath(os.path.join(root, name), p).replace(os.sep, '/')
                if rel in keep: continue
                to = os.path.join(kafka_inbox, d, *rel.split('/'))
                os.makedirs(os.path.dirname(to), exist_ok=True)
                shutil.move(os.path.join(root, name), to if not os.path.exists(to) else to + '.moved')
        try: os.remove(os.path.join(p, MARK))
        except FileNotFoundError: pass
        for root, _, _ in os.walk(p, topdown=False):   # empty service folders left behind
            if root != p and not os.listdir(root): os.rmdir(root)
        split.append(d)
    old = os.path.join(inbox, SUPERSEDED)
    if os.path.isdir(old):
        for d in sorted(os.listdir(old)):
            _merge(os.path.join(old, d), os.path.join(kafka_inbox, d))
        shutil.rmtree(old, ignore_errors=True)
    return kafka_only, split


def _s3_files(folder_dir):
    """Logical file names of the S3 copy in an inbox folder: the manifest keys and the names they were stored under."""
    import json
    try:
        with open(os.path.join(folder_dir, S3_MANIFEST), encoding='utf-8') as fh: man = json.load(fh)
    except (OSError, ValueError): return set()
    return set(man) | {m.get('stored', k) for k, m in man.items()}
