"""IP profile and attacker IP list (Stage 24 item 4).

GET /api/folders/{folder}/ips/{ip}          one IP: owner & location (offline database), numbers in this folder, its trail in
                                            all folders, and its requests in this folder (nginx ingress, at most 1,000).
GET /api/folders/{folder}/security/attack-ips.csv   this folder's attack source IPs as CSV (for a WAF block list).
GET /api/folders/{folder}/security/blocklist        ready-to-use block list: nginx / ingress-nginx / text / json (2026-10-07).
Nothing is sent to third-party services: location and owner come from the ip_info table.
"""
import csv, io, ipaddress, re
from urllib.parse import unquote_plus


from monishield.domain import detect
from monishield.infrastructure.queries.sql import _all, reject
from .tables import NG, SEV_SQL, T, UTC

MAX_REQ = 1000


def _ip(ip):
    if not re.fullmatch(r'[0-9A-Fa-f.:]{2,45}', ip or ''): raise reject(400, 'invalid_parameter', 'Invalid parameter: ip.')
    return ip


def _schema(cfg):
    return cfg.attack_rules == 'crs'


def ip_profile(cur, folder, cfg, ip):
    ip, crs = _ip(ip), _schema(cfg)
    I = 'agg_crs_ip' if crs else 'agg_attack_ip'
    info = cur.execute('SELECT asn, cc, org, is_private, city, region, country FROM ip_info WHERE ip = ?', [ip]).fetchone()
    # trail in all folders: ingress requests, attack requests, failed/successful logins
    days = {}
    for f, n in _all(cur, 'SELECT folder::VARCHAR, requests FROM agg_ip WHERE ip = ? AND service = ?', ip, NG): days.setdefault(f, {})['requests'] = n
    for f, n in _all(cur, f'SELECT folder::VARCHAR, hits FROM {I} WHERE ip = ?', ip): days.setdefault(f, {})['attacks'] = n
    for f, a, b in _all(cur, 'SELECT folder::VARCHAR, fail, ok FROM agg_login_ip WHERE ip = ?', ip): days.setdefault(f, {}).update(login_fail=a, login_ok=b)
    for f, n in _all(cur, 'SELECT folder::VARCHAR, sum(n) FROM agg_trace WHERE ip = ? GROUP BY 1', ip): days.setdefault(f, {})['traced'] = int(n)
    if not days and not info: raise reject(404, 'not_found', 'IP not found in any data.')
    folders = [dict(folder=f, requests=d.get('requests', 0), attacks=d.get('attacks', 0), login_fail=d.get('login_fail', 0),
                    login_ok=d.get('login_ok', 0), traced=d.get('traced', 0)) for f, d in sorted(days.items(), reverse=True)]

    cat = "CASE WHEN capec IS NULL THEN NULL ELSE capec || '/' || crs_attack END" if crs else 'attack_cat'
    sev = 'crs_severity' if crs else SEV_SQL.replace('category', 'attack_cat')
    k = cur.execute(f"""SELECT count(*), count(*) FILTER (WHERE status BETWEEN 400 AND 499), count(*) FILTER (WHERE status >= 500),
                               count(*) FILTER (WHERE {cat} IS NOT NULL), count(DISTINCT path_key), count(DISTINCT ua),
                               {UTC.format('min(ts_utc)')}, {UTC.format('max(ts_utc)')}
                        FROM nginx_access WHERE folder = ? AND ip = ?""", [folder, ip]).fetchone()
    rows = [dict(time=t, method=m, path=unquote_plus(p)[:300], status=s, bytes=b, ua=u[:160], upstream=up, request_id=rid,
                 category=c, severity=sv if c else None, rules=list(r or []))
            for t, m, p, s, b, u, up, rid, c, sv, r in cur.execute(f"""
                SELECT {UTC.format('ts_utc')}, method, path, status, bytes, ua, upstream, request_id, {cat}, {sev},
                       {'crs_rules' if crs else '[]::INTEGER[]'}
                FROM nginx_access WHERE folder = ? AND ip = ? ORDER BY ts_utc, file_id, line_no LIMIT {MAX_REQ}""", [folder, ip]).fetchall()]
    login = cur.execute(f"""SELECT fail, lock, ok, list_sort(accounts), {T.format('first_wib')}, {T.format('last_wib')}
                            FROM agg_login_ip WHERE folder = ? AND ip = ?""", [folder, ip]).fetchone()
    return dict(
        ip=ip, scheme='crs' if crs else 'lama',
        info=dict(asn=info[0], cc=info[1], org=info[2], private=bool(info[3]), city=info[4], region=info[5], country=info[6]) if info else None,
        kpi=dict(requests=k[0], n4xx=k[1], n5xx=k[2], attacks=k[3], endpoints=k[4], user_agents=k[5], first=k[6], last=k[7],
                 login_fail=login[0] if login else 0, resets=login[1] if login else 0, login_ok=login[2] if login else 0),
        accounts=login[3] if login else [], folders=folders, requests=rows, truncated=k[0] > MAX_REQ,
        rule_msgs=detect.rule_msgs(i for r in rows for i in r['rules']) if crs else {})


def _safe(v):
    """CSV cell safe to open in a spreadsheet: text starting with = + - @ gets a quote prefix (prevents formula injection)."""
    s = '' if v is None else str(v)
    return "'" + s if s[:1] in ('=', '+', '-', '@', '\t', '\r') else s


BLOCK_FORMATS = ('nginx', 'ingress', 'txt', 'json')


def _excluded(cfg, ip, private, org):
    """Reason this IP must not go into the block list, or None. Prevents blocking our own network."""
    try: a = ipaddress.ip_address(ip)
    except ValueError: return 'invalid'
    if private or a.is_private or a.is_loopback or a.is_link_local or a.is_reserved or a.is_multicast: return 'private'
    if cfg.blocklist_exclude_org and org and re.search(cfg.blocklist_exclude_org, org, re.I): return 'org'
    for net in (x.strip() for x in cfg.blocklist_exclude.split(',') if x.strip()):
        try:
            if a in ipaddress.ip_network(net, strict=False): return 'list'
        except ValueError: continue
    return None


def blocklist(cur, folder, cfg, format='nginx', days=1, min_severity=1, min_hits=1, lang='id'):
    """Ready-to-use block list (owner request 2026-10-07, suggestion 6) from the attack source IPs of `days` folders up to
    this folder: nginx (`deny`), ingress-nginx annotation (`denylist-source-range`), text with one IP per line, or JSON
    (preview). Private IPs, network owners matching S4_BLOCKLIST_EXCLUDE_ORG, and S4_BLOCKLIST_EXCLUDE are excluded."""
    if format not in BLOCK_FORMATS: raise reject(400, 'invalid_parameter', f'format must be one of {", ".join(BLOCK_FORMATS)}.')
    crs = _schema(cfg)
    I = 'agg_crs_ip' if crs else 'agg_attack_ip'
    msev = 'a.max_severity' if crs else f"list_max(list_transform(map_keys(a.cats), category -> {SEV_SQL}))"
    rows = _all(cur, f"""SELECT a.ip, sum(a.hits) AS hits, max({msev}) AS sev, count(DISTINCT a.folder) AS days, any_value(i.is_private), any_value(i.org),
                                any_value(i.country), max(a.last_wib)
                         FROM {I} a LEFT JOIN ip_info i USING (ip)
                         WHERE a.folder BETWEEN ?::DATE - (? - 1) * INTERVAL 1 DAY AND ?::DATE GROUP BY a.ip
                         HAVING max({msev}) >= ? AND sum(a.hits) >= ? ORDER BY hits DESC, a.ip""", folder, days, folder, min_severity, min_hits)
    take, skipped = [], {'private': 0, 'org': 0, 'list': 0, 'invalid': 0}
    for ip, hits, sev, nd, private, org, cc, last in rows:
        why = _excluded(cfg, ip, private, org)
        if why: skipped[why] += 1
        else: take.append(dict(ip=ip, hits=hits, severity=sev, days=nd, org=org, country=cc, last=str(last) if last else None))
    first = cur.execute('SELECT (?::DATE - (? - 1) * INTERVAL 1 DAY)::DATE', [folder, days]).fetchone()[0]
    crit = dict(folder_from=str(first), folder_to=folder, days=days, min_severity=min_severity, min_hits=min_hits, scheme='crs' if crs else 'lama')
    if format == 'json':
        return dict(criteria=crit, count=len(take), excluded=skipped, ips=take[:500])
    en = lang == 'en'
    head = [f"MoniShield — {'block list' if en else 'daftar blokir'} {crit['folder_from']}..{folder} ({len(take)} IP)",
            (f"criteria: severity >= {min_severity}, requests >= {min_hits}; excluded: {sum(skipped.values())} (private/own network/exclude list)" if en else
             f"kriteria: keparahan >= {min_severity}, request >= {min_hits}; dikecualikan: {sum(skipped.values())} (privat/jaringan sendiri/daftar kecuali)"),
            ('review before applying' if en else 'periksa dulu sebelum dipasang')]
    ips = sorted((x['ip'] for x in take), key=lambda v: ipaddress.ip_address(v))
    if format == 'nginx':
        body = '\n'.join([f'# {h}' for h in head] + [f'deny {ip};' for ip in ips]) + '\n'
    elif format == 'ingress':
        cidrs = ','.join(f'{ip}/32' if ':' not in ip else f'{ip}/128' for ip in ips)
        body = '\n'.join([f'# {h}' for h in head] + ['metadata:', '  annotations:', f'    nginx.ingress.kubernetes.io/denylist-source-range: "{cidrs}"']) + '\n'
    else:
        body = '\n'.join(ips) + '\n'
    ext = {'nginx': 'conf', 'ingress': 'yaml', 'txt': 'txt'}[format]
    return dict(file=body, media_type='text/plain; charset=utf-8', filename=f'blokir-{folder}-{days}h.{ext}')


def attack_ips_csv(cur, folder, cfg):
    crs = _schema(cfg)
    I = 'agg_crs_ip' if crs else 'agg_attack_ip'
    msev = 'a.max_severity' if crs else f"list_max(list_transform(map_keys(a.cats), category -> {SEV_SQL}))"
    rows = _all(cur, f"""SELECT a.ip, a.hits, array_to_string(list_sort(map_keys(a.cats)), ' | '), {msev}, i.country, i.asn, i.org,
                                {T.format('a.first_wib')}, {T.format('a.last_wib')}
                         FROM {I} a LEFT JOIN ip_info i USING (ip) WHERE a.folder = ? ORDER BY a.hits DESC, a.ip""", folder)
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator='\n')
    w.writerow(['ip', 'request_serangan', 'kategori', 'keparahan_maks', 'negara', 'asn', 'pemilik_jaringan', 'pertama_wib', 'terakhir_wib'])
    for r in rows: w.writerow([_safe(v) for v in r])
    return dict(file=buf.getvalue(), media_type='text/csv; charset=utf-8', filename=f'ip-serangan-{folder}.csv')
