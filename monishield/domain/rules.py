"""Old system rules, COPIED AS IS from build_dashboard.py (TRD §4.1).

Do not "tidy up": numeric parity with the old system depends on these regexes and functions being exactly the same.
tests/test_rules.py compares this module with build_dashboard.py as long as the old file still exists.
Note `# old:NN` = source line number in build_dashboard.py.

The only intentional differences from the original:
- fetch(), load_ip2asn(), and map_labels() (download + file reading) moved to monishield/infrastructure/refdata.py
  and take file paths (the original used the ROOT/.cache constant); this module is pure;
- patterns that the old system wrote inline in parse() are given names here (same pattern contents);
- pod_name() and split_relpath() are pieces of build() turned into functions.
"""
import bisect, collections, datetime, functools, ipaddress, os, re, socket
from urllib.parse import unquote_plus

C = collections.Counter  # old:11

# ---------------------------------------------------------------- log line patterns  (old:13-24)
NGINX = re.compile(r'(\S+) - \S+ \[(\d+)/(\w+)/(\d+):(\d+:\d+):\d+ [^\]]+\] "(\S+) (\S+)[^"]*" (\d{3}) (\d+) "[^"]*" "([^"]*)" \d+ ([\d.]+) \[([^\]]*)\]')
FE = re.compile(r'\S+ - \S+ \[(\d+)/(\w+)/(\d+):(\d+:\d+):\d+ [^\]]+\] "(\S+) (\S+)[^"]*" (\d{3}) \d+ "[^"]*" "[^"]*" "([^",]*)')
JAVA = re.compile(r'(\d{4}-\d\d-\d\d \d\d:\d\d):\d\d\.\d+ +(\w+) \d+ --- \[([^\]]+)\] (\S+) *: (.*)')
NGX_TAIL = re.compile(r'\] \[[^\]]*\] (.+) ([0-9a-f]{32})$')  # upstream_addr len time status req_id (may contain retries 'a, b')
BIZ_EP = {  # simpel-loop endpoint -> business metric (2xx responses only)
    'POST /tx-laporan': 'Laporan Dibuat', 'POST /tx-laporan/registrasi': 'Registrasi Laporan',
    'POST /tx-laporan/request-otp': 'OTP Diminta', 'POST /tx-laporan/verify-otp': 'OTP Terverifikasi',
    'POST /tx-file-upload': 'File Diunggah', 'POST /files': 'File Diunggah', 'POST /tx-lampiran': 'Lampiran Ditambahkan',
}
NGX_ERR = re.compile(r'\d{4}/\d\d/\d\d \d\d:\d\d:\d\d \[(\w+)\] \d+#\d+: \*\d+ (.*?)(?:, client:|$)')
MON = {m: i for i, m in enumerate('Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec'.split(), 1)}

# Patterns the old system wrote inline in parse(); same contents, just named.
SL_LINE = re.compile(r'\[OM-(\w+)\] (.*)')                                  # old:172
SL_NOTIF = re.compile(r'Notification email sent successfully (\w+)')         # old:203
SL_MAIL = re.compile(r'mail', re.I)                                         # old:204
COREDNS = re.compile(r'\[(\w+)\] plugin/errors: \d+ (\S+) (\w+): (.*)')      # old:209
COREDNS_ADDR = re.compile(r'[\d.]+:\d+')                                    # old:212
NGX_UPSTREAM = re.compile(r'upstream: "https?://([^/"]+)')                   # old:152
NGX_ERR_TS = re.compile(r'(\d{4})/(\d\d)/(\d\d) (\d\d:\d\d)')                # old:154
NGX_ERR_REQ = re.compile(r'request: "(\S+ \S+)')                             # old:154
NGX_ERRNO = re.compile(r'\(\d+: ')                                          # old:155
SPRING_STARTED = re.compile(r'Started (\w+) in ([\d.]+) seconds')           # old:222
SPRING_JWT = re.compile(r'JWT token is expired: .* a difference of (\d+) milliseconds')  # old:223
SPRING_PDF = re.compile(r'(\S+) pdf path')                                  # old:225
SPRING_EXC = re.compile(r'[\w.$]+(Exception|Error)\b')                      # old:236

# ---------------------------------------------------------------- attack classification  (old:32-43)
# Attack indicators in the URL (after URL-decode). Order = priority, the first match is used.
# ponytail: simple regex signatures, may give false positives/negatives; use a WAF (ModSecurity/CRS) for serious detection.
ATTACKS = [(n, re.compile(p, re.I)) for n, p in [
    ('SQL Injection', r"union\s+(all\s+)?select|select\s.{1,60}\sfrom|information_schema|sleep\(\d|benchmark\(|waitfor\s+delay|'\s*or\s*'?\d|\bor\s+1=1|;\s*drop\s"),
    ('XSS', r"<script|javascript:|on(error|load)\s*=|alert\(|<svg|<iframe"),
    ('Path Traversal / LFI', r"\.\./|\.\.\\|/etc/(passwd|shadow|hosts)|win\.ini|/proc/self"),
    ('Log4Shell / RCE', r"\$\{jndi:|\$\{.*\}|;\s*(cat|wget|curl|id|uname|sh)\b|\|\s*(cat|id|sh)\b|/bin/(ba)?sh|cmd\.exe|base64_decode|eval\(|system\("),
    ('Probe file sensitif', r"/\.(env|git|svn|aws|ssh|htaccess|htpasswd|ds_store|npmrc|docker)|/config\.(json|php|ya?ml)|\.(sql|bak|old|swp)$|/id_rsa|/actuator|/server-status|/_profiler|/debug/"),
    ('Scan CMS / WordPress', r"wp-(admin|content|includes|login|json)|wordpress|xmlrpc|joomla|drupal|phpmyadmin|/pma/"),
    ('Probe PHP / CGI', r"\.(php\d?|asp|aspx|jsp|cgi)\b|cgi-bin"),
]]
SCANNER_UA = re.compile(r'sqlmap|nikto|nmap|masscan|zgrab|nuclei|gobuster|dirbuster|dirb|wpscan|acunetix|nessus|openvas|-scanner|python-requests|go-http-client|curl/|wget|libwww|httpx|fuzz', re.I)

# Production base URL per upstream (old:46-53). In v2 these are configuration DEFAULT VALUES (config.py), not constants.
HOSTS = {
    'om-be-simpel-loop-3000': 'https://api-simpel4.ombudsman.go.id',
    'om-be-appsmanager-3000': 'https://appsmanager-simpel4.ombudsman.go.id',
    'om-be-referensi-3000': 'https://reference-simpel4.ombudsman.go.id',
    'om-be-report-3000': 'https://report-simpel4.ombudsman.go.id',
    'om-fe-inhouse-3000': 'https://simpel4.ombudsman.go.id',            # from same-origin asset referers
    'cattle-system-rancher-80': 'https://rancher-prd.ombudsman.go.id',  # from Rancher UI referers
}
LOGIN_FAIL = re.compile(r"Invalid password for user/email: '([^']*)' from IP: ([\d.]+)")  # old:54
LOGIN_LOCK = re.compile(r"due to 3 failed login attempts for user/email: '([^']*)' from IP: ([\d.]+)")
LOGIN_OK = re.compile(r"User '([^']*)' successfully logged in from IP: ([\d.]+)")


@functools.lru_cache(maxsize=200_000)  # URLs repeat a lot (assets, polling endpoints)
def path_attack(path):  # old:59
    p = unquote_plus(unquote_plus(path))  # handle double encoding
    return next((name for name, rx in ATTACKS if rx.search(p)), None)


def classify(path, ua):  # old:65
    if cat := path_attack(path): return cat
    if '${' in unquote_plus(ua): return 'Log4Shell / RCE'  # lookup payload ${...} in the User-Agent; patterns like ';id' are not used (Instagram UA contains '; id;')
    if SCANNER_UA.search(ua): return 'UA tool/scanner otomatis'


# ---------------------------------------------------------------- normalization  (old:82-94)
def norm(msg):
    """Unify messages that differ only in numbers/ids/times so they can be counted as one kind."""
    msg = re.sub(r"'[^']*@[^']*'", "'<email>'", msg)
    msg = re.sub(r'\d{4}-\d\d-\d\dT[\d:]+Z', '<ts>', msg)
    msg = re.sub(r'\b[0-9a-f]{16,}\b', '<id>', msg)
    msg = re.sub(r'\b\d+(\.\d+)?\b', '#', msg)
    return msg[:220]


def path_key(p):
    p = p.split('?')[0]
    p = re.sub(r'/[0-9a-f-]{16,}', '/:id', p)
    return re.sub(r'/\d+', '/:n', p)[:120]


# ---------------------------------------------------------------- JWT, accounts, incidents  (old:242-281)
def jwt_bucket(ms):
    for lim, name in ((5 * 60e3, '< 5 Menit'), (3600e3, '5–60 Menit'), (86400e3, '1–24 Jam'), (7 * 86400e3, '1–7 Hari')):
        if ms < lim: return name
    return '> 7 Hari'


def dt(ts): return datetime.datetime.strptime(ts, '%Y-%m-%d %H:%M')


def accounts(lev, window_min=60):
    """Per account: failures/successes, IPs, and the red flag 'success after several failures' (sign of a compromised account)."""
    per = collections.defaultdict(list)
    for e in sorted(lev): per[e[1]].append(e)
    rows = []
    for user, ev in per.items():
        fails = [e for e in ev if e[3] == 'fail']; oks = [e for e in ev if e[3] == 'ok']
        if not fails: continue
        flags, hits = set(), []
        for ok in oks:
            recent = [f for f in fails if 0 <= (dt(ok[0]) - dt(f[0])).total_seconds() <= window_min * 60]
            if len(recent) >= 3:
                flags.add('Sukses Setelah ≥3 Gagal')
                if ok[2] not in {f[2] for f in recent}: flags.add('Sukses Dari IP Berbeda'); hits.append(f'{ok[0]} sukses dari {ok[2]}')
        if len({f[2] for f in fails}) >= 2: flags.add('Dicoba Dari ≥2 IP')
        rows.append([user, len(fails), sum(e[3] == 'lock' for e in ev), len(oks), sorted({f[2] for f in fails}), sorted({o[2] for o in oks}),
                     sorted(flags), ev[0][0], ev[-1][0], hits[:3]])
    return sorted(rows, key=lambda r: (-('Sukses Dari IP Berbeda' in r[6]), -len(r[6]), -r[1]))[:150]


def incidents(inc, gap_min=5):
    """Group adjacent minutes with 5xx (gap <= gap_min) into one incident."""
    per_min = collections.defaultdict(lambda: [0, C(), C()])
    for (ts, up, st), n in inc.items(): p = per_min[ts]; p[0] += n; p[1][up] += n; p[2][st] += n
    out = []
    for ts in sorted(per_min):
        n, ups, sts = per_min[ts]
        if out and (dt(ts) - dt(out[-1][1])).total_seconds() <= gap_min * 60:
            o = out[-1]; o[1] = ts; o[2] += n; o[3].update(ups); o[4].update(sts)
        else: out.append([ts, ts, n, C(ups), C(sts)])
    return [[a, b, n, dict(u), dict(st)] for a, b, n, u, st in out]


# ---------------------------------------------------------------- IP owner, offline  (old:324-350)
# IP owner (ASN/ISP/country) is matched OFFLINE from the public iptoasn.com dataset (public domain),
# so user IPs are not sent to third-party services. Only down to the network owner level, not persons.
IP2ASN_URL = 'https://iptoasn.com/data/ip2asn-v4.tsv.gz'


def ip_owner(ip, db):
    try: addr = ipaddress.ip_address(ip)
    except ValueError: return None
    if addr.is_private or addr.is_loopback: return dict(asn=None, cc='-', org='Jaringan Internal (IP Privat)')
    if not db or addr.version != 4: return None
    starts, rows = db
    i = bisect.bisect_right(starts, int(addr)) - 1
    if i < 0 or int(addr) > rows[i][0]: return None
    _, asn, cc, org = rows[i]
    return dict(asn=asn, cc=cc, org=org)


# ---------------------------------------------------------------- IP location and map, offline  (old:353-394)
# City location is matched OFFLINE from DB-IP City Lite (CC BY 4.0, attribution "IP Geolocation by DB-IP" required),
# same as the IP owner: no user IP is sent out.
DBIP_URL = 'https://download.db-ip.com/free/dbip-city-lite-{:%Y-%m}.csv.gz'
LAND_URL = 'https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_50m_land.geojson'  # public domain
# Destination IP in the log = pod IP (private), so the destination point on the map = location of this server's public IP
# (resolved from api-simpel4.ombudsman.go.id). In v2 both are configuration DEFAULT VALUES.
SERVER_IP = '103.170.104.228'
SERVER_FALLBACK = ['Jakarta', 'Jakarta', 'ID', -6.2, 106.82]


def ip_int(ip): return int.from_bytes(socket.inet_aton(ip), 'big')


def geo_scan(need, rows):
    """need = sorted [(int ip, ip)]; rows = sorted DB-IP CSV rows -> {ip: [city, province, country, lat, lon] | None}."""
    found, i = {}, 0
    for r in rows:
        if i == len(need) or ':' in r[0]: break  # done / reached the IPv6 section
        end = ip_int(r[1])
        while i < len(need) and need[i][0] <= end:
            found[need[i][1]] = [r[5], r[4], r[3], float(r[6]), float(r[7])] if need[i][0] >= ip_int(r[0]) else None
            i += 1
    for _, ip in need[i:]: found[ip] = None
    return found


# ---------------------------------------------------------------- region labels  (old:428-466)
# Region name labels on the map: countries from Natural Earth (public domain); Indonesian provinces & regencies/cities
# from GeoNames (CC BY 4.0). Province names in GeoNames mix English/Indonesian, so they are mapped from their admin1 code.
COUNTRIES_URL = 'https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_110m_admin_0_countries.geojson'
GEONAMES_URL = 'https://download.geonames.org/export/dump/ID.zip'
PROV = {
    '01': 'Aceh', '02': 'Bali', '03': 'Bengkulu', '04': 'DKI Jakarta', '05': 'Jambi', '07': 'Jawa Tengah', '08': 'Jawa Timur',
    '10': 'DI Yogyakarta', '11': 'Kalimantan Barat', '12': 'Kalimantan Selatan', '13': 'Kalimantan Tengah', '14': 'Kalimantan Timur',
    '15': 'Lampung', '17': 'Nusa Tenggara Barat', '18': 'Nusa Tenggara Timur', '21': 'Sulawesi Tengah', '22': 'Sulawesi Tenggara',
    '24': 'Sumatera Barat', '26': 'Sumatera Utara', '28': 'Maluku', '29': 'Maluku Utara', '30': 'Jawa Barat', '31': 'Sulawesi Utara',
    '32': 'Sumatera Selatan', '33': 'Banten', '34': 'Gorontalo', '35': 'Kepulauan Bangka Belitung', '36': 'Papua', '37': 'Riau',
    '38': 'Sulawesi Selatan', '39': 'Papua Barat', '40': 'Kepulauan Riau', '41': 'Sulawesi Barat', '42': 'Kalimantan Utara',
    'PD': 'Papua Barat Daya', 'PT': 'Papua Tengah', 'PE': 'Papua Pegunungan', 'PS': 'Papua Selatan',
}


def kab_name(n):
    """'Kabupaten Bogor' -> 'Kab. Bogor'; some GeoNames entries are in English ('Gresik Regency')."""
    n = re.sub(r'^(.*) Regency$', r'Kabupaten \1', n)
    n = re.sub(r'^(.*) City$', r'Kota \1', n)
    return n.replace('Kabupaten ', 'Kab. ')


# ---------------------------------------------------------------- file scanning  (old:505-516, piece of build())
DATE_DIR = re.compile(r'\d{4}-\d\d-\d\d')


def pod_name(svc, filename):
    """Pod name from the log file name (.gz suffix already removed)."""
    return re.sub(rf'^log_{re.escape(svc)}_|_\d{{4}}-.*$', '', filename)


def split_relpath(relpath):
    """'<date>/[ns/]<service>/<file>' -> (date, ns, service, file name without .gz), or None if not a valid log file."""
    parts = relpath.split(os.sep)
    if not DATE_DIR.fullmatch(parts[0]) or len(parts) < 3: return None
    return parts[0], '/'.join(parts[1:-2]) or '-', parts[-2], parts[-1].removesuffix('.gz')
