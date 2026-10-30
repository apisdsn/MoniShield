"""Raw Logs page (owner request 2026-10-30): search the original log files of one date folder, every service at once.

The files are read where ingest found them (the source's log folder, then its inbox); the database only lends times to
JSON event lines that have none (their request ID is in the ingress log). Matching, entries and levels are in
monishield/domain/rawlog.py. Searches are bounded: a time budget per search and a cap on the entries kept.
"""
import datetime, gzip, heapq, os, re, time

from monishield.domain import log_formats, parse, rawlog, rules, services as profile, timezone
from .sql import reject

BUDGET_SECONDS = 20        # one search stops reading files after this; the answer says it is partial
KEEP = 20_000              # matching entries kept per search (newest/oldest by time after sorting); more = partial
DOWNLOAD_MAX = 100_000


def folder_files(roots, folder):
    """Log files of one date folder -> [dict(relpath, path, ns, service, pod, size)]. Like ingest: the first root that has
    the folder wins, and a .log.gz is read only when its .log is absent."""
    for root in roots:
        base = os.path.join(root, folder) if root else None
        if not base or not os.path.isdir(base): continue
        out = []
        for d, _, names in os.walk(base):
            have = set(names)
            for name in sorted(names):
                if not (name.endswith('.log') or (name.endswith('.log.gz') and name[:-3] not in have)): continue
                path = os.path.join(d, name)
                rel = os.path.relpath(path, root)
                parts = rules.split_relpath(rel)
                if not parts: continue
                _, ns, service, base_name = parts
                out.append(dict(relpath=rel.replace(os.sep, '/'), path=path, ns=ns, service=service, pod=rules.pod_name(service, base_name),
                                size=os.path.getsize(path)))
        return sorted(out, key=lambda f: f['relpath'])
    return []


def _rule(ns, service):
    """How the service's files are read: (multiline start regex or None, times without a zone are UTC)."""
    rs = log_formats.current() or log_formats.default_rules(profile.current())
    r = log_formats.match(rs, ns, service)
    return (re.compile(r.multiline) if r and r.multiline else None), (r is None or r.format in parse.LEGACY or r.format == 'spring-boot')


def _open(path):
    return gzip.open(path, 'rt', encoding='utf-8', errors='replace') if path.endswith('.gz') else open(path, encoding='utf-8', errors='replace')


def _local(t):
    """UTC 'YYYY-MM-DD HH:MM:SS[.mmm]' -> local text with the same precision."""
    if not t: return None
    dt = datetime.datetime.fromisoformat(t) + timezone.current().delta
    return dt.strftime('%Y-%m-%d %H:%M:%S') + (t[19:] if len(t) > 19 else '')


def _ingress_times(cur, folder, ids):
    """request ID -> UTC time of its ingress access line (the events log has no time of its own)."""
    if not ids or cur is None: return {}
    ids = sorted(ids)[:5000]
    rows = cur.execute(f"SELECT request_id, strftime(min(ts_utc), '%Y-%m-%d %H:%M:%S') FROM nginx_access WHERE folder = ? AND request_id IN ({', '.join('?' * len(ids))}) GROUP BY 1",
                       [folder, *ids]).fetchall()
    return dict(rows)


def run(cur, roots, folder, q, keep=KEEP, budget=BUDGET_SECONDS, newest_first=True):
    """Search every file of the folder -> dict(hits sorted by time, total, partial, files, services, seconds)."""
    t0 = time.monotonic()
    stop = lambda: time.monotonic() - t0 > budget
    files = folder_files(roots, folder)
    svc = {}
    for f in files:
        s = svc.setdefault(f['service'], dict(service=f['service'], files=0, matches=0, pods=set()))
        s['files'] += 1; s['pods'].add(f['pod'])
    heap, searched, partial, counted = [], 0, None, {'n': 0}
    sign = 1 if newest_first else -1
    pending = []   # matches without a time: placed once the ingress times are known

    def accept(h):
        counted['n'] += 1
        svc[h['service']]['matches'] += 1
        _push(heap, h, keep, sign)

    for f in files:
        if q.services and f['service'] not in q.services: continue
        if q.pods and f['pod'] not in q.pods: continue
        if stop(): partial = 'time'; break
        start, naive_utc = _rule(f['ns'], f['service'])
        with _open(f['path']) as fh:
            for h in rawlog.search(fh, q, start, naive_utc, stop):
                h.update(file=f['relpath'], service=f['service'], pod=f['pod'], ns=f['ns'])
                if h['time'] is not None: accept(h)
                elif len(pending) < keep: pending.append(h)
                else: partial = partial or 'many'
        searched += 1
        if stop() and searched < len(files): partial = 'time'
    # entries without a time (JSON events): the time of the ingress line with the same request ID, else the line above
    for h in pending: h['fields'] = rawlog.fields(h['text'])
    times = _ingress_times(cur, folder, {h['fields']['request_id'] for h in pending if h['fields']['request_id']})
    last = {}   # file -> time of its previous entry placed so far (lines in a row without a time take it over)
    for h in pending:
        rid = h['fields']['request_id']
        if rid and rid in times: h['time'], h['time_from'] = times[rid], 'request'
        elif h['near'] or last.get(h['file']): h['time'], h['time_from'] = h['near'] or last[h['file']], 'near'
        if h['time']: last[h['file']] = h['time']
        if h['time'] and not q.in_time(h['time'][:19]): continue
        if h['time'] is None and (q.start or q.end): continue
        accept(h)
    hits = [x[-1] for x in sorted(heap, key=lambda x: x[:-1], reverse=True)]
    if counted['n'] > keep: partial = partial or 'many'
    return dict(hits=hits, total=counted['n'], partial=partial, files_total=len(files), files_searched=searched,
                seconds=round(time.monotonic() - t0, 2), services=svc)


_seq = iter(range(1 << 62))


def _push(heap, h, keep, sign):
    """Keep the `keep` best entries by time (newest when sign=1). Untimed entries sort last either way."""
    t = h['time'] or ''
    key = (1 if t else 0, t if sign > 0 else _neg(t), h['file'] if sign > 0 else _neg(h['file']), h['line'] * sign, next(_seq))
    item = (*key, h)
    if len(heap) < keep: heapq.heappush(heap, item)
    elif item[:-1] > heap[0][:-1]: heapq.heapreplace(heap, item)


def _neg(s):
    """Reverse the order of strings (oldest first): invert each character."""
    return ''.join(chr(0x10FFFF - ord(c)) for c in s)


def _hit_view(h):
    f = h.get('fields') or rawlog.fields(h['text'])
    return dict(file=h['file'], line=h['line'], lines=h['lines'], service=h['service'], pod=h['pod'], ns=h['ns'], time=_local(h['time']),
                time_from=h.get('time_from', 'line' if h['time'] else None), kind=h['kind'], text=h['text'], spans=h['spans'], **f)


def _roots(cfg): return [cfg.log_dir, cfg.inbox_dir]


def search(cur, cfg, folder, params):
    """GET /api/folders/{folder}/raw: one page of matching entries + per-service counts."""
    q = rawlog.query_from(params, folder, timezone.current())
    try: limit = max(1, min(int(params.get('limit') or 200), rawlog.MAX_LIMIT)); offset = max(0, int(params.get('offset') or 0))
    except ValueError: raise reject(400, 'invalid_parameter', 'limit and offset are numbers.') from None
    order = params.get('order') or 'desc'
    if order not in ('asc', 'desc'): raise reject(400, 'invalid_parameter', 'order must be asc or desc.')
    r = run(cur, _roots(cfg), folder, q, newest_first=order == 'desc')
    hits = r['hits'] if order == 'desc' else _oldest_first(r['hits'])
    services = sorted(({**s, 'pods': sorted(s['pods'])} for s in r['services'].values()), key=lambda s: (-s['matches'], s['service']))
    return dict(query=dict(mode=q.mode, q=q.text), total=r['total'], offset=offset, limit=limit, partial=r['partial'],
                files_total=r['files_total'], files_searched=r['files_searched'], seconds=r['seconds'], services=services,
                rows=[_hit_view(h) for h in hits[offset:offset + limit]]), q


def _oldest_first(hits):
    """asc: timed entries oldest first, untimed ones last (run() already kept the oldest ones)."""
    timed = [h for h in hits if h['time']]
    return sorted(timed, key=lambda h: (h['time'], h['file'], h['line'])) + [h for h in hits if not h['time']]


def download(cur, cfg, folder, params):
    """GET /api/folders/{folder}/raw/download: every matching entry (up to 100,000), oldest first, as grep -n prints them:
    `<file>:<line>: <text>`."""
    q = rawlog.query_from(params, folder, timezone.current())
    r = run(cur, _roots(cfg), folder, q, keep=DOWNLOAD_MAX, budget=BUDGET_SECONDS * 3, newest_first=False)
    out = [f'{h["file"]}:{h["line"]}: {h["text"]}' for h in _oldest_first(r['hits'])]
    if r['partial']: out.append(f'# partial: {"time budget reached" if r["partial"] == "time" else "more than " + str(DOWNLOAD_MAX) + " entries"}')
    return dict(file=('\n'.join(out) + '\n').encode('utf-8'), media_type='text/plain; charset=utf-8',
                filename=f'monishield-raw-{folder}.log'), q, r['total']


def context(cur, cfg, folder, params):
    """GET /api/folders/{folder}/raw/context?file=&line=&n=: the entries around one line of one file of the folder."""
    rel = params.get('file') or ''
    f = next((x for x in folder_files(_roots(cfg), folder) if x['relpath'] == rel), None)   # only a file of this folder
    if f is None: raise reject(404, 'not_found', 'File not found.')
    try: line, n = int(params.get('line') or 0), int(params.get('n') or 3)
    except ValueError: raise reject(400, 'invalid_parameter', 'line and n are numbers.') from None
    start, naive_utc = _rule(f['ns'], f['service'])
    with _open(f['path']) as fh: c = rawlog.context(fh, line, n, start, naive_utc)
    if c['entry'] is None: raise reject(404, 'not_found', 'No log entry starts at that line.')
    view = lambda i: dict(i, time=_local(i['time']))
    return dict(file=rel, service=f['service'], pod=f['pod'], before=[view(i) for i in c['before']], entry=view(c['entry']),
                after=[view(i) for i in c['after']])
