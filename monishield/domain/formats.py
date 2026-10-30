"""Readers for the common log formats of docs/11-log-formats.md (stage 52, step 1b).

Each reader turns one log entry (a line, or several when a rule has `multiline`) into the NORMAL FORM: a dict with any of
time (UTC, 'YYYY-MM-DD HH:MM:SS'), level (ERROR / WARN / INFO / DEBUG), ip, method, path, status, bytes, duration_ms,
request_id, user, message, logger, upstream, ua, referer. None = the entry does not fit the format (an unread line).
The five legacy presets (ingress-nginx, nginx-frontend, coredns, events-json, spring-boot) stay in domain/parse.py.
Pure: standard library only.
"""
import datetime, json, re

from monishield.domain import timezone

UTC = datetime.timezone.utc

# ------------------------------------------------------------------ time
ISO = re.compile(r'(\d{4}-\d\d-\d\d)[T ](\d\d:\d\d:\d\d)(?:[.,](\d+))?\s*(Z|[+-]\d\d:?\d\d)?', re.I)
CLF = '%d/%b/%Y:%H:%M:%S %z'   # 10/Oct/2026:13:55:36 +0000
MONTHS = {m: i for i, m in enumerate('jan feb mar apr may jun jul aug sep oct nov dec'.split(), 1)}


def _utc(dt):
    """aware -> UTC naive; naive = the site's local time (S4_TIMEZONE_OFFSET) -> UTC naive."""
    if dt.tzinfo: return dt.astimezone(UTC).replace(tzinfo=None)
    return dt - timezone.current().delta


def parse_time(value, fmt='iso', now=None):
    """A time value in the rule's `time_format` -> 'YYYY-MM-DD HH:MM:SS' UTC, or None."""
    if value is None or value == '': return None
    try:
        if fmt in ('epoch', 'epoch_ms') or (fmt == 'iso' and isinstance(value, (int, float))):
            v = float(value)
            if fmt == 'epoch_ms' or (fmt == 'iso' and v > 1e11): v /= 1000   # a number in an iso field: guess seconds / ms
            dt = datetime.datetime.fromtimestamp(v, UTC).replace(tzinfo=None)
        elif fmt == 'iso':
            m = ISO.search(str(value))
            if not m: return None
            dt = datetime.datetime.fromisoformat(f'{m[1]}T{m[2]}')
            if m[4]: dt = dt.replace(tzinfo=UTC if m[4].upper() == 'Z' else datetime.datetime.strptime(m[4].replace(':', ''), '%z').tzinfo)
            dt = _utc(dt)
        elif fmt == 'clf': dt = _utc(datetime.datetime.strptime(str(value), CLF))
        elif fmt == 'syslog':   # 'Oct  9 13:55:36': no year -> the latest one that is not in the future
            mon, day, hms = str(value).split()
            now = now or datetime.datetime.now(UTC)
            local_now = timezone.current().local(now)
            dt = datetime.datetime(local_now.year, MONTHS[mon.lower()], int(day), *map(int, hms.split(':')))
            if dt > local_now + datetime.timedelta(days=1): dt = dt.replace(year=dt.year - 1)
            dt = _utc(dt)
        else: dt = _utc(datetime.datetime.strptime(str(value), fmt))
    except (ValueError, KeyError, OverflowError, OSError):
        return None
    return dt.strftime('%Y-%m-%d %H:%M:%S')


# ------------------------------------------------------------------ level
WORDS = {'error': 'ERROR', 'err': 'ERROR', 'fatal': 'ERROR', 'crit': 'ERROR', 'critical': 'ERROR', 'emerg': 'ERROR',
         'emergency': 'ERROR', 'alert': 'ERROR', 'severe': 'ERROR', 'panic': 'ERROR', 'warn': 'WARN', 'warning': 'WARN',
         'info': 'INFO', 'information': 'INFO', 'notice': 'INFO', 'debug': 'DEBUG', 'trace': 'DEBUG', 'verbose': 'DEBUG', 'fine': 'DEBUG'}
GUESS = ((re.compile(r'\b(ERROR|ERR|FATAL|CRITICAL|CRIT|SEVERE|PANIC|EXCEPTION)\b', re.I), 'ERROR'),
         (re.compile(r'\b(WARN|WARNING)\b', re.I), 'WARN'), (re.compile(r'\b(DEBUG|TRACE)\b', re.I), 'DEBUG'))


def level_of(value, site_levels=None):
    """'warning', 'E', 50 (pino/bunyan), 'SEVERE' (with the rule's `levels`) -> ERROR / WARN / INFO / DEBUG, or None."""
    if value is None or value == '': return None
    if site_levels and str(value) in site_levels: return site_levels[str(value)]
    if isinstance(value, (int, float)) or str(value).isdigit():   # pino / bunyan numbers
        n = int(value)
        return 'ERROR' if n >= 50 else 'WARN' if n >= 40 else 'INFO' if n >= 30 else 'DEBUG'
    w = str(value).strip().lower()
    return WORDS.get(w) or {'e': 'ERROR', 'w': 'WARN', 'i': 'INFO', 'd': 'DEBUG'}.get(w)


def guess_level(text):
    for rx, lvl in GUESS:
        if rx.search(text): return lvl
    return 'INFO'


# ------------------------------------------------------------------ shared cleanup
def _int(v):
    try: return int(float(v)) if v not in (None, '', '-') else None
    except (TypeError, ValueError): return None


def _num(v):
    try: return float(v) if v not in (None, '', '-') else None
    except (TypeError, ValueError): return None


def finish(d, rule):
    """Normalise the values of one entry: level, numbers, path without query for path_key (done by the caller)."""
    out = {k: v for k, v in d.items() if v not in (None, '', '-')}
    if 'level' in out: out['level'] = level_of(out['level'], dict(rule.levels)) or guess_level(str(out['level']))
    for k in ('status', 'bytes'):
        if k in out: out[k] = _int(out[k])
    if 'duration_ms' in out: out['duration_ms'] = _num(out['duration_ms'])
    if 'method' in out: out['method'] = str(out['method']).upper()[:12]
    for k in ('ip', 'path', 'request_id', 'user', 'logger', 'upstream', 'ua', 'referer'):
        if k in out: out[k] = str(out[k])
    if 'message' in out: out['message'] = str(out['message'])
    return {k: v for k, v in out.items() if v is not None}


# ------------------------------------------------------------------ access logs (nginx / apache combined)
COMBINED = re.compile(r'(?P<ip>\S+) \S+ (?P<user>\S+) \[(?P<time>[^\]]+)\] "(?P<method>[A-Z]+) (?P<path>\S+)(?: [^"]*)?" '
                      r'(?P<status>\d{3}) (?P<bytes>\d+|-)(?: "(?P<referer>[^"]*)" "(?P<ua>[^"]*)")?(?P<rest>.*)$')
TAIL_SECONDS = re.compile(r'^\s+(\d+\.\d+)(?:\s|$)')   # nginx $request_time right after the user agent


def read_combined(text, rule):
    m = COMBINED.match(text)
    if not m: return None
    d = m.groupdict()
    d['time'] = parse_time(d['time'], 'clf' if rule.time_format == 'iso' else rule.time_format)
    if not d['time']: return None
    if t := TAIL_SECONDS.match(d.pop('rest') or ''): d['duration_ms'] = float(t[1]) * 1000
    d['message'] = f'{d["method"]} {d["path"]} {d["status"]}'
    return finish(d, rule)


# ------------------------------------------------------------------ json lines
def dig(obj, path):
    """'req.url' -> obj['req']['url']; a key that itself has a dot ('http.status') wins over nesting."""
    if path in obj: return obj[path]
    cur = obj
    for part in path.split('.'):
        if not isinstance(cur, dict) or part not in cur: return None
        cur = cur[part]
    return cur


JSON_DEFAULTS = {  # tried in order when the rule does not map a column
    'time': ('time', 'timestamp', '@timestamp', 'ts', 'date', 'datetime', 'Timestamp', 't'),
    'level': ('level', 'severity', 'lvl', 'loglevel', 'log.level', 'Level', '@l', 'levelname'),
    'message': ('message', 'msg', 'Message', '@m', '@mt', 'event', 'log'),
    'request_id': ('request_id', 'requestId', 'trace_id', 'traceId', 'reqId', 'correlation_id', 'x_request_id'),
    'method': ('method', 'http.method', 'req.method', 'request.method'),
    'path': ('path', 'url', 'http.path', 'req.url', 'request.path', 'uri', 'request_uri'),
    'status': ('status', 'statusCode', 'status_code', 'http.status_code', 'res.statusCode', 'response.status'),
    'duration_ms': ('duration_ms', 'durationMs', 'latency_ms', 'responseTime', 'response_time_ms', 'elapsed_ms'),
    'ip': ('ip', 'client_ip', 'remote_addr', 'remoteAddress', 'clientIp', 'req.remoteAddress', 'ipAddress'),
    'user': ('user', 'user_id', 'userId', 'username'),
    'logger': ('logger', 'logger_name', 'name', 'module', 'caller'),
    'ua': ('user_agent', 'userAgent', 'ua', 'http.user_agent'),
}


def _pick(obj, rule, col):
    mapped = dict(rule.fields).get(col)
    if mapped: return dig(obj, mapped)
    for k in JSON_DEFAULTS.get(col, ()):
        v = dig(obj, k)
        if v is not None: return v
    return None


def from_mapping(obj, rule):
    d = {c: _pick(obj, rule, c) for c in JSON_DEFAULTS}
    for c in ('bytes', 'upstream', 'referer'):
        if (mapped := dict(rule.fields).get(c)): d[c] = dig(obj, mapped)
    d['time'] = parse_time(d['time'], rule.time_format) if d['time'] is not None else None
    if d['message'] is not None and not isinstance(d['message'], str): d['message'] = json.dumps(d['message'], ensure_ascii=False)
    if d['message'] is None and d.get('method') and d.get('path'): d['message'] = f'{d["method"]} {d["path"]} {d.get("status") or ""}'.strip()
    if d['time'] is None and d['message'] is None: return None
    return finish(d, rule)


def read_json(text, rule):
    s = text.strip()
    i = s.find('{')
    if i < 0: return None
    try: obj = json.loads(s[i:])
    except ValueError: return None
    return from_mapping(obj, rule) if isinstance(obj, dict) else None


# ------------------------------------------------------------------ logfmt
LOGFMT = re.compile(r'([\w.@/-]+)=("(?:[^"\\]|\\.)*"|\S*)')


def read_logfmt(text, rule):
    pairs = LOGFMT.findall(text)
    if len(pairs) < 2: return None
    obj = {k: (json.loads(v) if v.startswith('"') else v) for k, v in pairs}
    return from_mapping(obj, rule)


# ------------------------------------------------------------------ syslog
RFC5424 = re.compile(r'<(?P<pri>\d{1,3})>1 (?P<time>\S+) (?P<host>\S+) (?P<app>\S+) (?P<proc>\S+) (?P<msgid>\S+) (?:-|\[.*?\])\s?(?P<message>.*)$')
RFC3164 = re.compile(r'(?:<(?P<pri>\d{1,3})>)?(?P<time>[A-Z][a-z]{2} [ \d]\d \d\d:\d\d:\d\d) (?P<host>\S+) (?P<app>[^:\[\s]+)(?:\[\d+\])?: (?P<message>.*)$')
SEVERITY = ('ERROR', 'ERROR', 'ERROR', 'ERROR', 'WARN', 'INFO', 'INFO', 'DEBUG')   # syslog severity 0..7


def read_syslog(text, rule, now=None):
    m = RFC5424.match(text)
    t = parse_time(m['time'], 'iso') if m else None
    if not m:
        m = RFC3164.match(text)
        if not m: return None
        t = parse_time(m['time'], 'syslog', now)
    d = dict(time=t, message=m['message'], logger=m['app'])
    d['level'] = SEVERITY[int(m['pri']) % 8] if m['pri'] else guess_level(m['message'])
    return finish(d, rule) if t else None


# ------------------------------------------------------------------ regex / plain
def read_regex(text, rule, compiled):
    head, _, rest = text.partition('\n')          # the pattern describes the first line; the rest is a stack trace
    m = compiled.search(head)
    if not m: return None
    d = {k: v for k, v in m.groupdict().items() if v is not None}
    if rest: d['message'] = (d.get('message', '') + '\n' + rest).strip()
    d['time'] = parse_time(d.get('time'), rule.time_format)
    if not d['time']: return None
    if 'level' not in d: d['level'] = guess_level(d.get('message', ''))
    return finish(d, rule)


def read_plain(text, rule):
    m = ISO.search(text[:64])
    return finish(dict(time=parse_time(m[0]) if m else None, level=guess_level(text), message=text.strip()), rule)


# ------------------------------------------------------------------ entries (multiline)
def entries(lines, start=None):
    """Lines -> (line number of the entry's first line, text). With `start` (compiled regex), a line that does not match
    is appended to the previous entry (stack traces); a file that does not start with a match starts with an entry anyway."""
    cur, first = None, 0
    for n, line in enumerate(lines, 1):
        line = line.rstrip('\n')
        if start is None:
            yield n, line
            continue
        if start.search(line) or cur is None:
            if cur is not None: yield first, cur
            cur, first = line, n
        else:
            cur += '\n' + line
    if cur is not None: yield first, cur


def reader(rule):
    """Rule -> function(text) -> normal form or None. Compiles the rule's pattern once."""
    f = rule.format
    if f in ('nginx-combined', 'apache-combined'): return lambda t: read_combined(t, rule)
    if f == 'json': return lambda t: read_json(t, rule)
    if f == 'logfmt': return lambda t: read_logfmt(t, rule)
    if f == 'syslog': return lambda t: read_syslog(t, rule)
    if f == 'regex':
        rx = re.compile(rule.pattern)
        return lambda t: read_regex(t, rule, rx)
    if f == 'plain': return lambda t: read_plain(t, rule)
    raise ValueError(f'no common reader for format {f!r}')   # legacy presets and `auto` are handled by domain/parse.py
