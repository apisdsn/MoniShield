"""Inbox for logs from Kafka (Inbox port adapter): log lines are appended to files laid out the SAME as the
S3 export, <inbox>/<date>/<namespace>/<service>/log_<service>_<pod>_<date>-00-00.log (monishield/domain/kafka_message.py)."""
import collections, datetime, json, os

from monishield.domain.kafka_message import folder_of, relpath

MARK = '.kafka-feed.json'          # marks an inbox folder filled by Kafka


class Spool:
    """Line buffer per file; flush() appends them to the files in the inbox."""

    def __init__(self, inbox):
        self.inbox, self.buf, self.n = inbox, collections.defaultdict(list), 0

    def add(self, rec):
        f = folder_of(rec['t'])
        self.buf[relpath(rec, f)].append(rec['line']); self.n += 1
        return f

    def flush(self):
        """-> {folder: lines written}."""
        out = collections.Counter()
        for rel, lines in self.buf.items():
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
