"""Parser: baris log -> baris tabel mentah (CSV) + penghitung per file (TRD §2.2, §4.2).

Ini parse() sistem lama dengan bentuk keluaran diganti: cabang, urutan pemeriksaan, dan penghitung
lines/err/warn tetap; penjumlahan (Counter) dipindah ke SQL. Catatan `# lama:NN` = baris asal di
build_dashboard.py. Satu-satunya perbedaan perilaku: level error log nginx (TRD §4.4 butir 3).

Parser tidak tahu file_id maupun folder; ingest menambahkannya saat memuat CSV. Murni (tanpa berkas): pembacaan file,
sidik jari, dan penulisan CSV ada di monishield/infrastructure/logfiles.py.
"""
import collections, json

from monishield.domain import rules

# Kolom CSV per tabel, TANPA file_id dan folder. Urutan = urutan kolom di schema.sql setelah keduanya.
TABLES = {
    'nginx_access': ['line_no', 'ts_utc', 'ip', 'method', 'path', 'path_key', 'status', 'bytes', 'ua', 'request_time',
                     'upstream', 'request_id', 'pod_final', 'up_addrs', 'up_statuses', 'attack_cat', 'is_uptime_kuma'],
    'nginx_error': ['line_no', 'service', 'ts_utc', 'level', 'message', 'upstream_host', 'kind', 'request'],
    'fe_access': ['line_no', 'ts_utc', 'ip', 'method', 'path', 'path_key', 'status'],
    'sl_event': ['line_no', 'level', 'request_id', 'event', 'method', 'path', 'path_key', 'status', 'ip', 'duration_ms',
                 'failed', 'err_name', 'err_message'],
    'spring_line': ['line_no', 'service', 'ts_utc', 'level', 'thread', 'logger', 'restart_app', 'restart_seconds',
                    'jwt_expired_ms', 'refresh_expired', 'pdf_template', 'pdf_failed', 'login_kind', 'login_account', 'login_ip'],
    'coredns_error': ['line_no', 'level', 'domain', 'rtype', 'message'],
    'log_message': ['line_no', 'service', 'level', 'msg_key', 'raw'],
}
LIST_COLS = {'up_addrs', 'up_statuses'}  # ditulis 'a,b'; ingest memecahnya menjadi VARCHAR[]

RULES_VERSION = 1  # naikkan bila aturan parse berubah: ingest akan mem-parse ulang semua file (TRD §3.2)

NGINX_SVC, FE_SVC, SL_SVC, DNS_SVC = 'nginx-ingress-controller', 'om-fe-inhouse', 'om-be-simpel-loop', 'coredns'
SPRING_SVCS = ('om-be-appsmanager', 'om-be-referensi', 'om-be-report')
CORRUPT_PREFIX = 'failed to get parse function: unsupported log format'  # baris dari ekspor yang gagal (inv. §3.7)
# TRD §4.4 butir 3: sama di ingress dan frontend. Lama: ingress = error+crit, frontend = error saja.
NGX_ERR_LEVELS = ('error', 'crit', 'alert', 'emerg')


class Out:
    """Keluaran satu file: baris tabel mentah + penghitung. Bawaan menampung baris di memori (`data`); penulis CSV ada di
    monishield/infrastructure/logfiles.py (CsvOut) yang hanya mengganti `_emit`."""

    def __init__(self, service, upstream_prefix='ombudsman-ombudsman-'):
        self.service, self.prefix = service, upstream_prefix
        self.n = 0  # nomor baris yang sedang diproses (mulai 1)
        self.lines = self.err = self.warn = self.corrupt = 0
        self.counter = collections.Counter()  # (kind, key) -> n, menjadi file_counter
        self.rows = collections.Counter()
        self._seen, self.jr, self.data = set(), {}, collections.defaultdict(list)

    def _emit(self, table, values): self.data[table].append(values)

    def row(self, table, *vals):
        assert len(vals) == len(TABLES[table]) - 1, table
        self._emit(table, [self.n, *('true' if v is True else 'false' if v is False else v for v in vals)])
        self.rows[table] += 1

    def msg(self, level, msg, raw):  # lama:107 add_msg
        k = f'{level} | {rules.norm(msg)}'
        first = k not in self._seen
        self._seen.add(k)
        self.row('log_message', self.service, level, k, raw.strip()[:600] if first else None)

    def close(self): pass

    def summary(self):
        return dict(lines=self.lines, err=self.err, warn=self.warn, corrupt_lines=self.corrupt,
                    counters=[[k, key, n] for (k, key), n in sorted(self.counter.items())], rows=dict(self.rows))


def _ngx_error(line, o):  # lama:149-155 (ingress) dan lama:168-169 (frontend)
    m = rules.NGX_ERR.match(line)
    if not m: return
    o.msg(m[1].upper(), m[2], line)
    if m[1] in NGX_ERR_LEVELS: o.err += 1
    else: o.warn += 1
    um = rules.NGX_UPSTREAM.search(line)
    host = kind = req = None
    if um:  # error koneksi ke pod backend (timeout / reset / refused)
        rq = rules.NGX_ERR_REQ.search(line)
        host, kind, req = um[1], rules.NGX_ERRNO.sub('(', m[2])[:100], rq[1][:120] if rq else ''
    o.row('nginx_error', o.service, line[:19].replace('/', '-'), m[1], m[2], host, kind, req)


def parse_nginx(line, o):  # lama:114-156
    m = rules.NGINX.match(line)
    if not m: return _ngx_error(line, o)
    ip, d, mo, y, hm, meth, path, st, size, ua, rt, up = m.groups()
    up = up.replace(o.prefix, '') or '-'
    ts = f'{y}-{rules.MON[mo]:02d}-{int(d):02d} {hm}:{line[m.end(5) + 1:m.end(5) + 3]}'  # detik: lama membuangnya
    tm = rules.NGX_TAIL.search(line.rstrip())
    pod = tm[1].replace(', ', ',').split(' ')[0].split(',')[-1] if tm else '-'  # pod terakhir = yang menjawab
    addrs = sts = None
    if tm:
        fl = tm[1].replace(', ', ',').split(' ')
        if len(fl) == 4: addrs, sts = fl[0], fl[3]
    o.row('nginx_access', ts, ip, meth, path, rules.path_key(path), st, size, ua, rt, up, tm[2] if tm else None,
          pod, addrs, sts, rules.classify(path, ua), 'Uptime-Kuma' in ua)
    if st[0] == '5': o.err += 1


def parse_fe(line, o):  # lama:157-170
    m = rules.FE.match(line)
    if not m: return _ngx_error(line, o)
    d, mo, y, hm, meth, path, st, ip = m.groups()
    ts = f'{y}-{rules.MON[mo]:02d}-{int(d):02d} {hm}:{line[m.end(4) + 1:m.end(4) + 3]}'
    o.row('fe_access', ts, ip.strip(), meth, path, rules.path_key(path), st)
    if st[0] == '5': o.err += 1


def parse_sl(line, o):  # lama:171-207
    m = rules.SL_LINE.match(line)
    if not m: return  # lanjutan multi-line (stack/objek)
    lvl, body = m.groups()
    o.counter['level', lvl] += 1
    if body.startswith('{'):
        try: j = json.loads(body)
        except ValueError: j = None
        if j and 'statusCode' in j:
            path = j.get('path', '')
            st = str(j['statusCode'])
            e = j.get('error') or {}
            failed = j.get('event') == 'http.request.failed'
            o.row('sl_event', lvl, j.get('requestId'), j.get('event'), str(j.get('method')), path, rules.path_key(path), st,
                  j['ipAddress'] if 'ipAddress' in j else None, j.get('durationMs') or 0, failed, e.get('name'), e.get('message'))
            if failed:
                o.msg('ERROR' if st[0] == '5' else 'WARN', f"{st} {e.get('name')}: {e.get('message')}", line)
                if st[0] == '5': o.err += 1
                else: o.warn += 1
            return
    if body.startswith('Email sent successfully'): o.counter['biz', 'Email Terkirim'] += 1
    if mm := rules.SL_NOTIF.match(body): o.counter['mail', mm[1]] += 1
    if lvl == 'ERROR' and rules.SL_MAIL.search(body): o.counter['biz', 'Email Gagal'] += 1
    if lvl == 'ERROR': o.err += 1; o.msg(lvl, body, line)
    elif lvl == 'WARN': o.warn += 1; o.msg(lvl, body, line)


def parse_coredns(line, o):  # lama:208-213
    m = rules.COREDNS.match(line)
    if not m: return
    o.err += 1
    o.row('coredns_error', m[1], m[2], m[3], m[4])
    o.msg('ERROR', f'{m[2]} {m[3]}: ' + rules.COREDNS_ADDR.sub('X', m[4]), line)


def parse_spring(line, o):  # lama:214-239; juga untuk folder layanan tak dikenal (A10)
    m = rules.JAVA.match(line)
    if m:
        ts, lvl, thread, logger, msg = m.groups()
        o.counter['level', lvl] += 1
        if lvl == 'ERROR': o.err += 1
        if lvl == 'WARN': o.warn += 1
        if lvl in ('ERROR', 'WARN'): o.msg(lvl, f'{logger.split(".")[-1]}: {msg}', line)
        rm = rules.SPRING_STARTED.match(msg)
        jm = rules.SPRING_JWT.search(msg)
        if pm := rules.SPRING_PDF.match(msg): o.jr[thread] = pm[1]
        tpl = failed = None
        if msg.startswith('Jasper template path : '):
            tpl, failed = o.jr.pop(thread, '?'), msg.endswith(': null')  # path null = template tidak ada
        login = [(key, lm) for key, rx in (('fail', rules.LOGIN_FAIL), ('lock', rules.LOGIN_LOCK), ('ok', rules.LOGIN_OK)) if (lm := rx.search(msg))]
        # Sistem lama mencatat satu event per pola yang cocok; satu baris hanya punya satu kolom login, jadi
        # baris yang cocok lebih dari satu pola harus menggagalkan file, bukan diam-diam kehilangan event.
        if len(login) > 1: raise ValueError(f'baris {o.n}: lebih dari satu pola login cocok')
        key, lm = login[0] if login else (None, None)
        o.row('spring_line', o.service, f'{ts}:{line[m.end(1) + 1:m.end(1) + 3]}', lvl, thread, logger,
              rm[1] if rm else None, float(rm[2]) if rm else None, int(jm[1]) if jm else None, 'Refresh token expired' in msg,
              tpl, failed, key, lm[1] if lm else None, lm[2] if lm else None)
    elif rules.SPRING_EXC.match(line):
        o.msg('EXC', line.strip(), line)
    elif line.startswith('Hibernate:'):
        o.counter['level', 'Hibernate SQL'] += 1


PARSERS = {NGINX_SVC: parse_nginx, FE_SVC: parse_fe, SL_SVC: parse_sl, DNS_SVC: parse_coredns}


def known_service(service): return service in PARSERS or service in SPRING_SVCS


def parse_lines(lines, out):
    """Baris-baris satu file -> `out` (Out). Murni: pembacaan file ada di monishield/infrastructure/logfiles.py."""
    fn = PARSERS.get(out.service, parse_spring)
    for out.n, line in enumerate(lines, 1):
        if line.startswith(CORRUPT_PREFIX): out.corrupt += 1
        fn(line, out)
    out.lines = out.n
    return dict(out.summary(), service=out.service, known_service=known_service(out.service))
