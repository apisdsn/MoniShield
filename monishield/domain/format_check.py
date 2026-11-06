"""Try a log format on sample lines: the suggestion and the test of the Log Formats page (docs/11-log-formats.md, step 1e).

Pure (standard library only): the lines are read from the files by monishield/infrastructure/log_lines.py. A line is "read"
when the format gives it the columns the ingest needs: an access log line needs a time, a client address and a path (like
`_common` in domain/parse.py); any other line needs one of the readers to accept it.
"""
import json

from . import formats, log_formats, rules, services
from .log_formats import PRESETS, Rule

# Formats that need no settings, most specific first: on a tie the first one wins; `plain` reads everything, so it is last
SUGGEST_ORDER = ('caddy-json', 'ingress-nginx', 'nginx-combined', 'apache-combined', 'json', 'logfmt', 'syslog', 'spring-boot', 'coredns', 'plain')
HTTP_SHARE = 0.6     # an access log format wins over an application format that reads more, when it reads this share of that
PLAIN_MIN = 0.5      # `plain` is suggested only when no other format reads at least this share of the lines
SAMPLE = 200         # lines of a service used for a suggestion
TEST_ROWS = 5        # entries shown by a test
TEXT_MAX = 300       # characters of an unread line sent to the page


# Readers of today's parsers (domain/parse.py), as normal-form columns without the counters
def _read_ingress(rule):
    def read(line):
        if m := rules.NGINX.match(line):
            ip, d, mo, y, hm, meth, path, st = m[1], m[2], m[3], m[4], m[5], m[6], m[7], m[8]
            return dict(time=f'{y}-{rules.MON[mo]:02d}-{int(d):02d} {hm}:{line[m.end(5) + 1:m.end(5) + 3]}', ip=ip, method=meth, path=path, status=int(st))
        if m := rules.NGX_ERR.match(line): return dict(time=line[:19].replace('/', '-'), level=formats.level_of(m[1]) or 'ERROR', message=m[2])
        return None
    return read


def _read_frontend(rule):
    def read(line):
        if m := rules.FE.match(line):
            return dict(time=f'{m[3]}-{rules.MON[m[2]]:02d}-{int(m[1]):02d} {m[4]}:{line[m.end(4) + 1:m.end(4) + 3]}', ip=m[8].strip(), method=m[5], path=m[6], status=int(m[7]))
        if m := rules.NGX_ERR.match(line): return dict(time=line[:19].replace('/', '-'), level=formats.level_of(m[1]) or 'ERROR', message=m[2])
        return None
    return read


def _read_coredns(rule):
    def read(line):
        m = rules.COREDNS.match(line)
        return dict(level='ERROR', message=f'{m[2]} {m[3]}: {m[4]}') if m else None
    return read


def _read_spring(rule):
    def read(line):
        m = rules.JAVA.match(line)
        if not m: return None
        return dict(time=f'{m[1]}:{line[m.end(1) + 1:m.end(1) + 3]}', level=formats.level_of(m[2]) or m[2], message=f'{m[4].split(".")[-1]}: {m[5]}')
    return read


def _read_events(rule):
    sl = rules.sl_line(rule.tag or services.current().event_tag)

    def read(line):
        m = sl.match(line)
        if not m: return None
        d = dict(level=formats.level_of(m[1]) or m[1], message=m[2][:200])
        if m[2].startswith('{'):
            try: j = json.loads(m[2])
            except ValueError: j = None
            if isinstance(j, dict) and 'statusCode' in j:
                d.update(method=str(j.get('method') or ''), path=str(j.get('path') or ''), status=formats._int(j['statusCode']), ip=str(j.get('ipAddress') or ''))
        return d
    return read


LEGACY_READERS = {'ingress-nginx': _read_ingress, 'nginx-frontend': _read_frontend, 'coredns': _read_coredns, 'spring-boot': _read_spring, 'events-json': _read_events}


def reader(rule):
    """Rule -> function(text) -> columns or None. `auto` reads as `plain`, as the ingest does until detection exists."""
    if rule.format == 'auto': rule = Rule(rule.match, 'plain', 'app')
    if rule.format in LEGACY_READERS: return LEGACY_READERS[rule.format](rule)
    return formats.reader(rule)


def is_read(rule, d):
    """Does the ingest keep this entry? An access log entry needs a time, a client address and a path."""
    if d is None: return False
    if (rule.kind or PRESETS.get(rule.format)) == 'http' and rule.format not in ('ingress-nginx', 'nginx-frontend'):
        return bool(d.get('time') and d.get('ip') and d.get('path'))
    return True


def entries(rule, lines):
    """Lines -> entries (a multiline rule joins a stack trace to its first line). Blank lines are left out."""
    lines = [x for x in lines if x.strip()]
    if rule.multiline: return [text for _, text in formats.entries(lines, formats.re.compile(rule.multiline))]
    return lines


def _level(d):
    if d.get('level'): return d['level']
    st = d.get('status')
    return 'ERROR' if st and st >= 500 else 'WARN' if st and st >= 400 else 'INFO'


def view(d):
    """Columns of the test table. The time is UTC text 'YYYY-MM-DD HH:MM:SS[.mmm]' (the API turns it into the site's time)."""
    return dict(time=d.get('time'), level=_level(d) if d.get('time') or d.get('level') or d.get('status') else d.get('level'), ip=d.get('ip'), method=d.get('method'),
                path=d.get('path'), message=None if d.get('path') else (d.get('message') or '')[:300], status=d.get('status'))


def count(rule, lines):
    """-> (entries read, entries). Entries are the unit the ingest counts unread lines in."""
    read, texts = reader(rule), entries(rule, lines)
    n = 0
    for t in texts:
        try: n += is_read(rule, read(t))
        except Exception: pass   # noqa: BLE001  a line a reader chokes on is an unread line
    return n, len(texts)


def pct(read, total): return round(100 * read / total, 1) if total else None


def suggest(lines, current):
    """The format that reads the most of `lines`. Ties go to the more specific format (SUGGEST_ORDER); `plain` only when nothing
    else reads PLAIN_MIN of them. `current` = the rule that reads the service today.
    -> dict(lines, current=dict(format, read_pct), suggested=dict(format, kind, read_pct), better=bool, candidates=[…]) or None without lines."""
    texts = [x for x in lines if x.strip()]
    if not texts: return None
    found = []
    for i, fmt in enumerate(SUGGEST_ORDER):
        rule = Rule('*', fmt, PRESETS[fmt])
        n, total = count(rule, texts)
        found.append(dict(format=fmt, kind=PRESETS[fmt], read=n, total=total, read_pct=pct(n, total), order=i))
    specific = [c for c in found if c['format'] != 'plain']
    best = max(specific, key=lambda c: (c['read'], -c['order']))
    # a real access log holds other entries too (Caddy's certificate messages), which a generic format reads as well: the access
    # log format still wins when it reads most of the lines and HTTP_SHARE of what the generic one reads
    if best['kind'] != 'http' and (web := [c for c in specific if c['kind'] == 'http' and c['read'] >= HTTP_SHARE * best['read'] and c['read'] >= PLAIN_MIN * c['total']]):
        best = web[0]
    pick = best if best['read'] >= PLAIN_MIN * best['total'] else found[-1]
    n, total = count(current, texts)
    cur = dict(format=current.format, read=n, read_pct=pct(n, total))
    better = pick['format'] != current.format and (pick['read'] > n or (current.format in ('plain', 'auto') and pick['format'] != 'plain'))
    return dict(lines=len(texts), current=cur, suggested=dict(format=pick['format'], kind=pick['kind'], read_pct=pick['read_pct']), better=better,
                candidates=[dict(format=c['format'], read_pct=c['read_pct']) for c in found])


def test(rule, lines, rows=TEST_ROWS):
    """The last `rows` entries of `lines` read with `rule` -> dict(read, total, rows=[dict(read, text, + view columns)]). Nothing is stored."""
    read, texts = reader(rule), entries(rule, lines)
    out, n = [], 0
    for t in texts:
        try: d = read(t)
        except Exception: d = None   # noqa: BLE001
        ok = is_read(rule, d)
        n += ok
        out.append(dict(read=ok, text=t[:TEXT_MAX], **(view(d) if ok else {})))
    return dict(read=n, total=len(texts), rows=out[-rows:])
