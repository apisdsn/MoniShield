"""The newest lines of one service, read from its log files (LogLines port adapter of the Log Formats page).

Files are found the way Raw Logs finds them (queries/rawlogs.folder_files): the first root that has the date folder wins.
A plain .log file is read from its end, a .log.gz is read through. Nothing is cached or stored; the lines can hold personal
data, so they only go to the caller."""
import collections, gzip, os

from monishield.infrastructure.queries import rawlogs

BLOCK = 64 * 1024
MAX_LINE = 20_000   # characters kept of one line


def _tail_plain(path, n):
    with open(path, 'rb') as fh:
        end = fh.seek(0, os.SEEK_END)
        data, pos = b'', end
        while pos > 0 and data.count(b'\n') <= n:
            step = min(BLOCK, pos)
            pos -= step
            fh.seek(pos)
            data = fh.read(step) + data
    lines = data.decode('utf-8', errors='replace').splitlines()
    return lines[-n:] if pos == 0 else lines[1:][-n:]   # the first line of a block read from the middle may be cut


def _tail_gz(path, n):
    with gzip.open(path, 'rt', encoding='utf-8', errors='replace') as fh: return list(collections.deque((x.rstrip('\n') for x in fh), maxlen=n))


class LogLines:
    def tail(self, cfg, folders, ns, service, n):
        """-> (folder, last n lines of the service in the newest of `folders` that has it, oldest first), or (None, [])."""
        for folder in folders:
            files = [f for f in rawlogs.folder_files([cfg.log_dir, cfg.inbox_dir], folder) if f['service'] == service and (ns is None or f['ns'] == ns)]
            if not files: continue
            lines = []
            for f in sorted(files, key=lambda f: os.path.getmtime(f['path']), reverse=True):   # newest file first, then older ones fill up
                try: got = (_tail_gz if f['path'].endswith('.gz') else _tail_plain)(f['path'], n - len(lines))
                except OSError: continue
                lines = got + lines
                if len(lines) >= n: break
            if lines: return folder, [x[:MAX_LINE] for x in lines]
        return None, []
