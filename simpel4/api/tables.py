"""Endpoint tabel (TRD §5.4): satu kontrak untuk 25 tabel yang bisa dilanjutkan, difilter, dan diurut.

Tiap tabel = satu SELECT atas tabel agregat (parameter $f folder, $s layanan, $m modul) + daftar kolom teks
untuk `q` + daftar kolom yang boleh diurut. Nama tabel, kolom urut, dan arah TIDAK pernah disisipkan dari
masukan: semuanya dicocokkan dengan daftar di bawah, sisanya lewat parameter terikat (TRD §8.1).
"""
import dataclasses, re

from fastapi import APIRouter, Depends, Request

from .common import ApiError, cursor, folder_param, ip_cell, require_user_ready

NG = 'nginx-ingress-controller'
MAX_LIMIT, MAX_Q = 500, 200
T = "strftime({}, '%Y-%m-%d %H:%M')"   # TIMESTAMP WIB -> teks format lama
UTC = "strftime({} + INTERVAL 7 HOUR, '%Y-%m-%d %H:%M')"

# Keparahan kategori serangan aturan LAMA (konstanta SEV di template); aturan CRS membawa keparahannya sendiri (Tahap 21).
SEV = {'Log4Shell / RCE': 3, 'SQL Injection': 3, 'Path Traversal / LFI': 3, 'XSS': 3,
       'Probe file sensitif': 2, 'Scan CMS / WordPress': 2, 'Probe PHP / CGI': 2, 'UA tool/scanner otomatis': 1}
_in = lambda n: ', '.join("'" + c.replace("'", "''") + "'" for c, s in SEV.items() if s == n)
SEV_SQL = f'CASE WHEN category IN ({_in(3)}) THEN 3 WHEN category IN ({_in(2)}) THEN 2 ELSE 1 END'


@dataclasses.dataclass(frozen=True)
class Table:
    sql: str
    limit: int                 # batas bawaan = batas tabel itu di sistem lama
    order: str                 # urutan bawaan (urutan lama), selalu berakhir pada kunci unik agar halaman stabil
    text: tuple                # kolom yang dicari `q`
    sort: tuple                # kolom yang boleh diurut
    ip: str = None             # kolom IP utama: pemiliknya ikut dicari `q`, lokasinya tersedia untuk baris
    ip_lists: tuple = ()       # kolom berisi daftar IP
    per_service: bool = False  # wajib parameter `service`
    fix: object = None         # penyesuaian bentuk baris


def _flow(r):
    r['pods'] = [[p['pod'], p['n']] for p in r['pods']]
    lokasi = dict(city=r['_city'], region=r['_region'], cc=r['_country']) if r['_lat'] is not None else None
    r['location'] = lokasi or ('internal' if r['_cc'] == '-' else None)   # None = tidak diketahui


EP = """SELECT key, requests, n4xx, n5xx, p50, p95, p99, dur_max AS max, (n4xx + n5xx) / requests AS error_rate
        FROM agg_endpoint WHERE folder = $f AND service = $s AND dur_n >= 5"""
TABLES = {
    'endpoints': Table('SELECT key, requests AS n FROM agg_endpoint WHERE folder = $f AND service = $s', 20, 'n DESC, key', ('key',), ('key', 'n'), per_service=True),
    'endpoint-errors': Table('SELECT status, key, n FROM agg_endpoint_error WHERE folder = $f AND service = $s', 20, 'n DESC, status, key',
                             ('status', 'key'), ('status', 'key', 'n'), per_service=True),
    'endpoint-perf': Table(EP, 25, 'p95 DESC, key', ('key',), ('key', 'requests', 'p50', 'p95', 'p99', 'max', 'error_rate'), per_service=True),
    'endpoint-error-rate': Table(EP + ' AND requests >= 20 AND n4xx + n5xx > 0', 20, 'error_rate DESC, key', ('key',),
                                 ('key', 'requests', 'n4xx', 'n5xx', 'error_rate'), per_service=True),
    'slow': Table("SELECT seq, duration_ms, key, status FROM agg_slow WHERE folder = $f AND $s = 'om-be-simpel-loop'", 15, 'duration_ms DESC, seq',
                  ('key', 'status'), ('duration_ms', 'key', 'status'), per_service=True),
    'ips': Table('SELECT ip, requests AS n FROM agg_ip WHERE folder = $f AND service = $s', 15, 'n DESC, ip', ('ip',), ('ip', 'n'), ip='ip', per_service=True),
    'user-agents': Table(f"SELECT ua90 AS ua, n FROM agg_ua WHERE folder = $f AND $s = '{NG}'", 12, 'n DESC, ua', ('ua',), ('ua', 'n'), per_service=True),
    # `service` opsional: tanpa layanan = pesan lintas layanan (Overview)
    'messages': Table("""SELECT service, level, msg_key, n, sample_raw AS sample FROM agg_message
                         WHERE folder = $f AND (CAST($s AS VARCHAR) IS NULL OR service = $s)""", 40, 'n DESC, service, msg_key',
                      ('service', 'msg_key'), ('service', 'level', 'msg_key', 'n')),
    'flows': Table("""SELECT ip AS src, upstream, regexp_replace(upstream, '-\\d+$', '') AS module, sum(n) AS requests,
                             list(struct_pack(pod := pod, n := n) ORDER BY n DESC, pod)[:3] AS pods
                      FROM agg_flow WHERE folder = $f AND (CAST($m AS VARCHAR) IS NULL OR regexp_replace(upstream, '-\\d+$', '') = $m)
                      GROUP BY ip, upstream""", 100, 'requests DESC, src, upstream', ('src', 'module', '_city', '_region', '_country'),
                   ('src', 'module', 'requests'), ip='src', fix=_flow),
    'attack-urls': Table(f"""SELECT category, {SEV_SQL} AS severity, method_path, hits, ip_count, top_ip, status_counts, sizes, upstreams, ua_first AS ua,
                                    {T.format('first_wib')} AS first, {T.format('last_wib')} AS last
                             FROM agg_attack_url WHERE folder = $f""", 300, 'severity DESC, hits DESC, category, method_path',
                         ('category', 'method_path', 'top_ip', 'status_counts', 'upstreams', 'ua'), ('category', 'severity', 'method_path', 'hits', 'ip_count', 'first', 'last'),
                         ip='top_ip'),
    'attack-ips': Table(f"""SELECT ip, hits, cats, list_max(list_transform(map_keys(cats), category -> {SEV_SQL})) AS max_severity, status_counts,
                                   ua_top AS ua, {T.format('first_wib')} AS first, {T.format('last_wib')} AS last
                            FROM agg_attack_ip WHERE folder = $f""", 100, 'hits DESC, ip', ('ip', 'cats', 'status_counts', 'ua'),
                        ('ip', 'hits', 'max_severity', 'first', 'last'), ip='ip'),
    'accounts': Table(f"""SELECT account, fail, lock, ok, fail_ips, ok_ips, flags, {T.format('first_wib')} AS first, {T.format('last_wib')} AS last, notes
                          FROM agg_account WHERE folder = $f""", 150,
                      "list_contains(flags, 'Sukses Dari IP Berbeda') DESC, len(flags) DESC, fail DESC, account",   # urutan lama:268
                      ('account', 'fail_ips', 'ok_ips', 'flags', 'notes'), ('account', 'fail', 'lock', 'ok', 'first', 'last'), ip_lists=('fail_ips', 'ok_ips')),
    'login-ips': Table(f"""SELECT ip, fail, lock, ok, list_sort(accounts) AS accounts, {T.format('first_wib')} AS first, {T.format('last_wib')} AS last
                           FROM agg_login_ip WHERE folder = $f AND (fail > 0 OR lock > 0)""", 100, 'lock DESC, fail DESC, ip',
                       ('ip', 'accounts'), ('ip', 'fail', 'lock', 'ok', 'first', 'last'), ip='ip'),
    'ip-4xx': Table(f"SELECT ip, n4xx AS n, ua_first_4xx AS ua FROM agg_ip WHERE folder = $f AND service = '{NG}' AND n4xx > 0", 20, 'n DESC, ip',
                    ('ip', 'ua'), ('ip', 'n'), ip='ip'),
    'c401': Table(f"""SELECT ip AS client, key AS endpoint, n, peak_per_min, {T.format('first_wib')} AS first, {T.format('last_wib')} AS last
                      FROM agg_c401 WHERE folder = $f""", 30, 'n DESC, client, endpoint', ('client', 'endpoint'),
                  ('client', 'endpoint', 'n', 'peak_per_min', 'first', 'last'), ip='client'),
    'pdf-templates': Table('SELECT template, ok, fail FROM agg_report WHERE folder = $f', MAX_LIMIT, 'fail DESC, ok DESC, template', ('template',), ('template', 'ok', 'fail')),
    'dns': Table('SELECT domain, n FROM v_dns WHERE folder = $f', 20, 'n DESC, domain', ('domain',), ('domain', 'n')),
    'upstreams': Table('SELECT upstream, requests, n5xx FROM agg_upstream WHERE folder = $f', 12, 'requests DESC, upstream', ('upstream',), ('upstream', 'requests', 'n5xx')),
    'incidents': Table(f"""SELECT seq, {T.format('start_wib')} AS start, {T.format('end_wib')} AS "end", n, upstreams, statuses
                           FROM agg_incident WHERE folder = $f""", MAX_LIMIT, 'seq', ('upstreams', 'statuses'), ('seq', 'start', 'n')),
    'upstream-errors': Table(f"""SELECT {UTC.format('ts_utc')} AS time, kind, upstream_host AS pod, request, ts_utc AS _ts, file_id AS _file, line_no AS _line
                                 FROM v_upstream_error WHERE folder = $f""", 200, '_ts DESC, _file DESC, _line DESC', ('kind', 'pod', 'request'), ('time', 'kind', 'pod')),
    'uptime-targets': Table('SELECT target, n FROM agg_uk_target WHERE folder = $f', 5, 'n DESC, target', ('target',), ('target', 'n')),
    'backend-pods': Table("""SELECT p.upstream, p.addr AS pod, p.attempts AS requests, p.attempts / sum(p.attempts) OVER (PARTITION BY p.upstream) AS share,
                                    p.n5xx, coalesce(r.n, 0) AS retries
                             FROM agg_pod p LEFT JOIN (SELECT upstream, addr_first, sum(n) AS n FROM agg_retry WHERE folder = $f GROUP BY ALL) r
                                  ON r.upstream = p.upstream AND r.addr_first = p.addr
                             WHERE p.folder = $f""", MAX_LIMIT, 'upstream, pod', ('upstream', 'pod'), ('upstream', 'pod', 'requests', 'share', 'n5xx', 'retries')),
    'restarts': Table(f"""SELECT {UTC.format('ts_utc')} AS time, service, pod, restart_app AS app, restart_seconds AS seconds, ts_utc AS _ts
                          FROM v_restart WHERE folder = $f""", MAX_LIMIT, 'service, time, pod, app, seconds', ('service', 'pod', 'app'), ('time', 'service', 'pod', 'seconds')),
    'activity': Table('SELECT key, n FROM agg_activity WHERE folder = $f', 20, 'n DESC, key', ('key',), ('key', 'n')),
    'trace': Table(f"""SELECT ip AS client, status, error, key, n, url, upstream, ua, {T.format('first_wib')} AS first, {T.format('last_wib')} AS last, max_ms
                       FROM agg_trace WHERE folder = $f""", 300, 'n DESC, client, status, error, key', ('client', 'status', 'error', 'url', 'ua'),
                   ('client', 'status', 'error', 'n', 'max_ms', 'first', 'last'), ip='client'),
}

# Tahap 21 (TRD §4.6): bila cfg.attack_rules = 'crs', dua tabel serangan dibaca dari agregat OWASP CRS (kategori = CAPEC/keluarga,
# keparahan dari aturan CRS, kolom `rules` = ID aturan). Agregat lama tetap ada untuk uji kesetaraan (attack_rules = 'lama').
CRS_TABLES = {
    'attack-urls': Table(f"""SELECT category, severity, method_path, hits, ip_count, top_ip, status_counts, sizes, upstreams, ua_first AS ua, rules,
                                    {T.format('first_wib')} AS first, {T.format('last_wib')} AS last
                             FROM agg_crs_url WHERE folder = $f""", 300, 'severity DESC, hits DESC, category, method_path',
                         ('category', 'method_path', 'top_ip', 'status_counts', 'upstreams', 'ua', 'rules'), ('category', 'severity', 'method_path', 'hits', 'ip_count', 'first', 'last'),
                         ip='top_ip'),
    'attack-ips': Table(f"""SELECT ip, hits, cats, max_severity, status_counts, ua_top AS ua, {T.format('first_wib')} AS first, {T.format('last_wib')} AS last
                            FROM agg_crs_ip WHERE folder = $f""", 100, 'hits DESC, ip', ('ip', 'cats', 'status_counts', 'ua'),
                        ('ip', 'hits', 'max_severity', 'first', 'last'), ip='ip'),
}


def owners(cur, ips):
    """{ip: sel IP + pemilik} untuk sekumpulan IP (TRD §5.1), satu query."""
    ips = list({i for i in ips if i})
    if not ips: return {}
    got = {r[0]: r for r in cur.execute(f"SELECT ip, asn, cc, org FROM ip_info WHERE ip IN ({', '.join('?' * len(ips))})", ips).fetchall()}
    return {ip: ip_cell(*got[ip]) if ip in got else ip_cell(ip) for ip in ips}


def cells(cur, rows, cols=(), lists=()):
    """Ganti kolom IP di `rows` (daftar dict) dengan sel IP + pemilik."""
    own = owners(cur, [r[c] for r in rows for c in cols] + [ip for r in rows for c in lists for ip in r[c]])
    for r in rows:
        for c in cols: r[c] = own[r[c]] if r[c] else None
        for c in lists: r[c] = [own[ip] for ip in r[c]]
    return rows


def table_of(name, scheme='crs'):
    """Definisi tabel; tabel serangan mengikuti aturan deteksi yang dipakai (cfg.attack_rules)."""
    return CRS_TABLES[name] if scheme == 'crs' and name in CRS_TABLES else TABLES.get(name)


def page(cur, name, folder, service=None, module=None, q='', sort=None, dir='desc', limit=None, offset=0, scheme='crs'):
    """Satu halaman tabel. Pemanggil sudah memvalidasi `name`, `sort`, `dir`; di sini hanya nilai terikat."""
    t = table_of(name, scheme)
    limit = t.limit if limit is None else limit
    join = f""", i.org AS _org, i.cc AS _cc, i.city AS _city, i.region AS _region, i.country AS _country, i.lat AS _lat
               FROM t LEFT JOIN ip_info i ON i.ip = t."{t.ip}\"""" if t.ip else ' FROM t'
    head = f'WITH t AS ({t.sql}), u AS (SELECT t.*{join}) '
    text = [f'CAST("{c}" AS VARCHAR)' for c in t.text] + (['_org'] if t.ip else [])
    cond = f"contains(lower(concat_ws(' ', {', '.join(text)})), $q)" if q else 'TRUE'
    order = (f'"{sort}" {"ASC" if dir == "asc" else "DESC"} NULLS LAST, ' if sort else '') + t.order
    run = lambda sql: cur.execute(sql, {k: v for k, v in dict(f=folder, s=service, m=module, q=q.lower()).items() if re.search(rf'\${k}\b', sql)})
    total, matched = run(f'{head}SELECT count(*), count(*) FILTER (WHERE {cond}) FROM u').fetchone()
    res = run(f'{head}SELECT * FROM u WHERE {cond} ORDER BY {order} LIMIT {int(limit)} OFFSET {int(offset)}')
    names = [d[0] for d in res.description]
    rows = [dict(zip(names, r)) for r in res.fetchall()]
    for r in rows:
        if t.fix: t.fix(r)
        for k in [k for k in r if k.startswith('_')]: del r[k]
    cells(cur, rows, (t.ip,) if t.ip else (), t.ip_lists)
    return dict(table=name, total=total, matched=matched, limit=limit, offset=offset, rows=rows)


def first(cur, name, folder, service=None, module=None, limit=None, scheme='crs'):
    """Halaman pertama untuk respons halaman: {total, rows} (TRD §5.1)."""
    p = page(cur, name, folder, service=service, module=module, limit=limit, scheme=scheme)
    return dict(total=p['total'], rows=p['rows'])


def services(cur, folder): return {r[0]: r[1] for r in cur.execute('SELECT service, lines FROM agg_service WHERE folder = ?', [folder]).fetchall()}


def _int(v, nama, lo, hi):
    if not re.fullmatch(r'\d{1,6}', v) or not lo <= int(v) <= hi: raise ApiError(400, 'invalid_parameter', f'Parameter tidak sah: {nama}.')
    return int(v)


router = APIRouter(prefix='/api')


@router.get('/folders/{folder}/tables/{table}')
def table_page(table: str, request: Request, folder: str = Depends(folder_param), user=Depends(require_user_ready), cur=Depends(cursor)):
    p = request.query_params
    asing = set(p) - {'service', 'module', 'q', 'sort', 'dir', 'limit', 'offset'}
    if asing: raise ApiError(400, 'invalid_parameter', 'Parameter tidak dikenal.')
    scheme = request.app.state.cfg.attack_rules
    t = table_of(table, scheme)
    if not t: raise ApiError(404, 'not_found', 'Tabel tidak ditemukan.')
    service, module, q, sort, dir = p.get('service'), p.get('module'), p.get('q', ''), p.get('sort'), p.get('dir', 'desc')
    if t.per_service and not service: raise ApiError(400, 'invalid_parameter', 'Parameter wajib: service.')
    if service is not None and service not in services(cur, folder): raise ApiError(404, 'not_found', 'Layanan tidak ditemukan.')
    if module is not None and (table != 'flows' or len(module) > 100): raise ApiError(400, 'invalid_parameter', 'Parameter tidak sah: module.')
    if len(q) > MAX_Q: raise ApiError(400, 'invalid_parameter', 'Parameter tidak sah: q.')
    if sort is not None and sort not in t.sort: raise ApiError(400, 'invalid_parameter', 'Parameter tidak sah: sort.')
    if dir not in ('asc', 'desc'): raise ApiError(400, 'invalid_parameter', 'Parameter tidak sah: dir.')
    limit = _int(p['limit'], 'limit', 1, MAX_LIMIT) if 'limit' in p else None
    offset = _int(p['offset'], 'offset', 0, 999999) if 'offset' in p else 0
    return page(cur, table, folder, service=service, module=module or None, q=q, sort=sort, dir=dir, limit=limit, offset=offset, scheme=scheme)
