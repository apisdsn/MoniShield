"""Raw log search (owner request 2026-10-30): the original lines of every service, read from the log files on disk.

Pure rules, no I/O: what one log entry is (a line plus its stack trace), its time and level, and whether it matches the
search. The files are opened by monishield/infrastructure/queries/rawlogs.py. Nothing is masked (owner decision): a search
shows the text exactly as the service wrote it; every search and download is recorded in the audit log by the API.
"""
import dataclasses, datetime, ipaddress, itertools, re

from . import formats, log_formats, rules
from .errors import Fail

MODES = ('text', 'regex', 'request', 'ip')
KINDS = ('ERROR', 'WARN', 'INFO', 'DEBUG', '5xx', '4xx', '3xx', '2xx', 'other')
MAX_QUERY = 500          # characters of the search text
MAX_ENTRY = 20_000       # characters kept of one entry (a very long stack trace is cut)
MAX_SPANS = 20           # highlighted matches per entry
MAX_CONTEXT = 20         # entries before / after a line
MAX_LIMIT = 1000         # entries per page

# a line that continues the previous entry: indented, a Java/Node stack frame, "Caused by:", or an exception name line
CONT = re.compile(r'(?:[ \t]|Caused by:|\.\.\. \d+ (?:more|common frames omitted)|[\w.$]+(?:Exception|Error|Throwable)(?::|$))')

# ------------------------------------------------------------------ time
CLF_TIME = re.compile(r'\[(\d\d/\w{3}/\d{4}:\d\d:\d\d:\d\d [+-]\d{4})\]')               # nginx / apache access
SLASH_TIME = re.compile(r'(\d{4})/(\d\d)/(\d\d) (\d\d:\d\d:\d\d)')                      # nginx error log
JSON_TIME = re.compile(r'"(?:@timestamp|timestamp|time|ts|datetime)"\s*:\s*(?:"([^"]{8,40})"|(\d{10,13}(?:\.\d+)?))')
LOGFMT_TIME = re.compile(r'\b(?:time|ts|timestamp)=("?)(\S+?)\1(?:\s|$)')


def _iso(m, naive_utc):
    """formats.ISO match -> 'YYYY-MM-DD HH:MM:SS[.mmm]' UTC. A time without a zone is UTC for today's parsers (Kubernetes
    pods log in UTC) and the site's zone for formats of log-formats.toml, as their readers do."""
    if m[4] or not naive_utc:
        t = formats.parse_time(m[0])
        if t is None: return None
    else:
        t = f'{m[1]} {m[2]}'
    return t + (f'.{m[3][:3].ljust(3, "0")}' if m[3] else '')


def line_time(text, naive_utc=True):
    """Time written in a log entry -> 'YYYY-MM-DD HH:MM:SS[.mmm]' UTC, or None (e.g. JSON event lines without a time)."""
    head = text[:400]
    if m := CLF_TIME.search(head): return formats.parse_time(m[1], 'clf')
    if (m := formats.ISO.match(head)) or (m := formats.ISO.search(head[:48])): return _iso(m, naive_utc)
    if m := SLASH_TIME.match(head):
        return f'{m[1]}-{m[2]}-{m[3]} {m[4]}' if naive_utc else formats.parse_time(f'{m[1]}-{m[2]}-{m[3]} {m[4]}')
    if m := JSON_TIME.search(head):
        if m[2]: return formats.parse_time(float(m[2]), 'iso')
        if mm := formats.ISO.search(m[1]): return _iso(mm, naive_utc)
    if (m := LOGFMT_TIME.search(head)) and (mm := formats.ISO.search(m[2])): return _iso(mm, naive_utc)
    return None


# ------------------------------------------------------------------ level / status
ACCESS_STATUS = re.compile(r'HTTP/[\d.]+" (\d{3}) ')
TAG_LEVEL = re.compile(r'\[[A-Za-z0-9_]+-(\w+)\]')                 # events: [TAG-LEVEL] {...}
BRACKET_LEVEL = re.compile(r'\[(\w+)\] ')                           # coredns [ERROR] …, nginx error … [error] …
JAVA_LEVEL = re.compile(r'\d{4}-\d\d-\d\d[T ][\d:.,]+\S*\s+([A-Za-z]+)\s')
JSON_LEVEL = re.compile(r'"(?:level|severity|lvl|log\.level|levelname)"\s*:\s*"?(\w+)')
LOGFMT_LEVEL = re.compile(r'\b(?:level|lvl|severity)=(\w+)')


def kind_of(text):
    """ERROR / WARN / INFO / DEBUG for application lines, 5xx / 4xx / 3xx / 2xx for access lines, else 'other'."""
    head = text[:600]
    if (m := ACCESS_STATUS.search(head)) and not TAG_LEVEL.match(head):
        return f'{m[1][0]}xx' if m[1][0] in '2345' else 'other'
    for rx in (TAG_LEVEL, JAVA_LEVEL, JSON_LEVEL, LOGFMT_LEVEL):
        if (m := (rx.match(head) if rx in (TAG_LEVEL, JAVA_LEVEL) else rx.search(head))) and (lvl := formats.level_of(m[1])): return lvl
    if (m := SLASH_TIME.match(head)) and (b := BRACKET_LEVEL.search(head, m.end())) and (lvl := formats.level_of(b[1])): return lvl
    if (m := BRACKET_LEVEL.match(head)) and (lvl := formats.level_of(m[1])): return lvl
    for rx, lvl in formats.GUESS:
        if rx.search(head): return lvl
    return 'other'


# ------------------------------------------------------------------ fields shown next to a line
REQUEST_ID = re.compile(r'"?\b(?:requestId|request_id|reqId|req_id|traceId|trace_id|x-request-id)"?\s*[:=]\s*"?([\w.:-]{4,100})', re.I)
TAIL_ID = re.compile(r'\b([0-9a-f]{32})\s*$')
JSON_IP = re.compile(r'"(?:ipAddress|ip|clientIp|client_ip|remoteAddress|remote_addr)"\s*:\s*"([0-9a-fA-F.:]{3,45})"')
IPV4 = re.compile(r'(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])')
REQUEST_LINE = re.compile(r'"?\b(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)"?[ ,:"]+(?:"?path"?\s*:\s*")?(/[^\s"]*)')
JSON_STATUS = re.compile(r'"(?:status|statusCode|status_code)"\s*:\s*"?(\d{3})\b')


def fields(text):
    """Request ID, client IP, HTTP status, method and path of an entry when the line carries them (first line only)."""
    head = text.split('\n', 1)[0][:4000]
    rid = (m[1] if (m := REQUEST_ID.search(head)) else None) or (m[1] if (m := TAIL_ID.search(head)) else None)
    ip = None
    if m := JSON_IP.search(head): ip = m[1]
    elif m := rules.FE.match(head): ip = m[8].strip()           # web frontend: first X-Forwarded-For entry
    elif m := IPV4.search(head): ip = m[0]
    status = (m[1] if (m := ACCESS_STATUS.search(head)) else None) or (m[1] if (m := JSON_STATUS.search(head)) else None)
    rq = REQUEST_LINE.search(head)
    return dict(request_id=rid, ip=ip, status=int(status) if status else None, method=rq[1] if rq else None, path=rq[2][:300] if rq else None)


# ------------------------------------------------------------------ the search
@dataclasses.dataclass(frozen=True)
class Query:
    mode: str
    text: str
    rx: re.Pattern
    services: frozenset = frozenset()   # empty = every service
    pods: frozenset = frozenset()
    kinds: frozenset = frozenset()      # empty = every kind
    start: str | None = None            # UTC 'YYYY-MM-DD HH:MM:SS', inclusive
    end: str | None = None              # UTC, exclusive

    def in_time(self, t):
        return (self.start is None or t >= self.start) and (self.end is None or t < self.end)

    def describe(self):
        """For the audit log: what was searched (no result data)."""
        parts = [f'mode={self.mode}', f'q={self.text[:120]}']
        if self.services: parts.append('services=' + ','.join(sorted(self.services))[:200])
        if self.kinds: parts.append('kinds=' + ','.join(k for k in KINDS if k in self.kinds))
        if self.start or self.end: parts.append(f'utc={self.start or ""}..{self.end or ""}')
        return ' '.join(parts)


def bad(message): return Fail('invalid_parameter', message, 400)


def pattern(mode, text):
    """The search as a compiled pattern. Text: case-insensitive words; regex: as written (checked like log-formats.toml
    patterns: length and nested repeats); request: a request ID; ip: one IPv4/IPv6 address, not part of a longer one."""
    text = (text or '').strip()
    if mode not in MODES: raise bad('mode must be text, regex, request or ip.')
    if not text: raise bad('Enter something to search for.')
    if len(text) > MAX_QUERY: raise bad(f'The search text is longer than {MAX_QUERY} characters.')
    if mode == 'text': return re.compile(re.escape(text), re.I)
    if mode == 'regex':
        try: return log_formats.check_regex(text, 'search', 'the pattern')
        except log_formats.FormatError as e: raise bad(str(e).removeprefix('search: ').capitalize() + '.') from None
    if mode == 'request':
        if not re.fullmatch(r'[\w.:-]{4,100}', text): raise bad('A request ID is 4-100 letters, digits, ".", ":", "_" or "-".')
        return re.compile(r'(?<![\w-])' + re.escape(text) + r'(?![\w-])', re.I)
    try: ip = ipaddress.ip_address(text)
    except ValueError: raise bad('Enter one IP address, e.g. 203.0.113.5.') from None
    return re.compile(r'(?<![\w.:])' + re.escape(str(ip)) + (r'(?![\w.])' if ip.version == 4 else r'(?![\w:])'), re.I)


def local_window(folder, start, end, zone):
    """'HH:MM' local times on the folder's day -> UTC bounds; `end` includes its whole minute. Empty -> None."""
    def at(hm, extra):
        if not hm: return None
        if not re.fullmatch(r'([01]\d|2[0-3]):[0-5]\d', hm): raise bad('Times are HH:MM, e.g. 16:00.')
        t = datetime.datetime.fromisoformat(f'{folder}T{hm}:00') + extra - zone.delta
        return t.strftime('%Y-%m-%d %H:%M:%S')
    a, b = at(start, datetime.timedelta()), at(end, datetime.timedelta(minutes=1))
    if a and b and b <= a: raise bad('The end time must be after the start time.')
    return a, b


def query_from(params, folder, zone):
    """API parameters -> Query. Lists are comma-separated; unknown kinds are refused."""
    split = lambda k: frozenset(x.strip() for x in (params.get(k) or '').split(',') if x.strip())
    kinds = split('kinds')
    if unknown := sorted(kinds - set(KINDS)): raise bad(f'Unknown level or status: {", ".join(unknown)[:80]}.')
    mode = params.get('mode') or 'text'
    start, end = local_window(folder, params.get('from'), params.get('to'), zone)
    return Query(mode=mode, text=(params.get('q') or '').strip(), rx=pattern(mode, params.get('q')), services=split('services'),
                 pods=split('pods'), kinds=frozenset() if kinds == set(KINDS) else kinds, start=start, end=end)


def entries(lines, start=None):
    """Lines -> (line number of the entry's first line, number of lines, text). A stack trace stays with the line above it:
    with `start` (a rule's `multiline` regex) a line that does not match it continues the entry; otherwise lines that look
    like a continuation (CONT) do."""
    cur, first, count = None, 0, 0
    for n, line in enumerate(lines, 1):
        line = line.rstrip('\r\n')
        cont = (not start.search(line)) if start is not None else bool(CONT.match(line))
        if cur is not None and cont:
            count += 1
            if len(cur) < MAX_ENTRY: cur += '\n' + line
            continue
        if cur is not None: yield first, count, cur
        cur, first, count = line, n, 1
    if cur is not None: yield first, count, cur


def search(lines, q, start=None, naive_utc=True, stop=None):
    """Entries of one file that match `q` -> dicts (line, lines, text, time, near, kind, spans). `time` is the entry's own
    time (UTC) or None; `near` is the time of the entry above it when the entry has none (JSON events). `stop()` is
    checked every 2,000 entries: True ends the file early (time budget)."""
    prev = None
    for i, (n, count, text) in enumerate(entries(lines, start)):
        if stop is not None and i % 2000 == 0 and stop(): return
        spans = [m.span() for m in itertools.islice((m for m in q.rx.finditer(text) if m.end() > m.start()), MAX_SPANS)]
        if not spans:
            prev = text
            continue
        kind = kind_of(text)
        if q.kinds and kind not in q.kinds:
            prev = text
            continue
        t = line_time(text, naive_utc)
        if t is not None and not q.in_time(t[:19]):
            prev = text
            continue
        near = None if t is not None or prev is None else line_time(prev, naive_utc)
        yield dict(line=n, lines=count, text=text if len(text) <= MAX_ENTRY else text[:MAX_ENTRY] + ' …', time=t, near=near, kind=kind, spans=spans)
        prev = text


def context(lines, line_no, n, start=None, naive_utc=True):
    """The entry that starts at `line_no` with `n` entries before and after it -> dict(before, entry, after), each item
    dict(line, text, time, kind); entry None when no entry starts there."""
    n = max(0, min(int(n), MAX_CONTEXT))
    before, entry, after = [], None, []
    for first, _count, text in entries(lines, start):
        item = dict(line=first, text=text if len(text) <= MAX_ENTRY else text[:MAX_ENTRY] + ' …', time=line_time(text, naive_utc), kind=kind_of(text))
        if entry is None:
            if first == line_no: entry = item
            elif first > line_no: break
            else:
                before.append(item)
                if len(before) > n: before.pop(0)
        else:
            if len(after) >= n: break
            after.append(item)
    return dict(before=before if entry else [], entry=entry, after=after)
