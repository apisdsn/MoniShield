"""Kotak masuk untuk log dari Kafka (adapter port Inbox): baris log ditambahkan ke file dengan susunan yang SAMA dengan
ekspor S3, <kotak masuk>/<tanggal>/<namespace>/<layanan>/log_<layanan>_<pod>_<tanggal>-00-00.log (monishield/domain/kafka_message.py)."""
import collections, datetime, json, os

from monishield.domain.kafka_message import folder_of, relpath

MARK = '.kafka-feed.json'          # penanda folder kotak masuk yang diisi Kafka


class Spool:
    """Penampung baris per file; flush() menambahkannya ke file di kotak masuk."""

    def __init__(self, inbox):
        self.inbox, self.buf, self.n = inbox, collections.defaultdict(list), 0

    def add(self, rec):
        f = folder_of(rec['t'])
        self.buf[relpath(rec, f)].append(rec['line']); self.n += 1
        return f

    def flush(self):
        """-> {folder: baris ditulis}."""
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
