"""Aturan sistem lama, DISALIN APA ADANYA dari build_dashboard.py (TRD §4.1).

Jangan "dirapikan": kesetaraan angka dengan sistem lama bergantung pada regex dan fungsi ini persis sama.
tests/test_rules.py membandingkan modul ini dengan build_dashboard.py selama file lama masih ada.
Catatan `# lama:NN` = nomor baris asal di build_dashboard.py.

Yang sengaja berbeda dari aslinya hanya:
- fetch(), load_ip2asn(), dan map_labels() (unduhan + pembacaan berkas) dipindah ke monishield/infrastructure/refdata.py
  dan menerima path berkas (aslinya memakai konstanta ROOT/.cache); modul ini murni;
- pola yang di sistem lama ditulis langsung di dalam parse() diberi nama di sini (isi polanya sama);
- pod_name() dan split_relpath() adalah potongan build() yang dijadikan fungsi.
"""
import bisect, collections, datetime, functools, ipaddress, os, re, socket
from urllib.parse import unquote_plus

C = collections.Counter  # lama:11

# ---------------------------------------------------------------- pola baris log  (lama:13-24)
NGINX = re.compile(r'(\S+) - \S+ \[(\d+)/(\w+)/(\d+):(\d+:\d+):\d+ [^\]]+\] "(\S+) (\S+)[^"]*" (\d{3}) (\d+) "[^"]*" "([^"]*)" \d+ ([\d.]+) \[([^\]]*)\]')
FE = re.compile(r'\S+ - \S+ \[(\d+)/(\w+)/(\d+):(\d+:\d+):\d+ [^\]]+\] "(\S+) (\S+)[^"]*" (\d{3}) \d+ "[^"]*" "[^"]*" "([^",]*)')
JAVA = re.compile(r'(\d{4}-\d\d-\d\d \d\d:\d\d):\d\d\.\d+ +(\w+) \d+ --- \[([^\]]+)\] (\S+) *: (.*)')
NGX_TAIL = re.compile(r'\] \[[^\]]*\] (.+) ([0-9a-f]{32})$')  # upstream_addr len time status req_id (bisa berisi retry 'a, b')
BIZ_EP = {  # endpoint simpel-loop -> metrik bisnis (hanya respons 2xx)
    'POST /tx-laporan': 'Laporan Dibuat', 'POST /tx-laporan/registrasi': 'Registrasi Laporan',
    'POST /tx-laporan/request-otp': 'OTP Diminta', 'POST /tx-laporan/verify-otp': 'OTP Terverifikasi',
    'POST /tx-file-upload': 'File Diunggah', 'POST /files': 'File Diunggah', 'POST /tx-lampiran': 'Lampiran Ditambahkan',
}
NGX_ERR = re.compile(r'\d{4}/\d\d/\d\d \d\d:\d\d:\d\d \[(\w+)\] \d+#\d+: \*\d+ (.*?)(?:, client:|$)')
MON = {m: i for i, m in enumerate('Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec'.split(), 1)}

# Pola yang di sistem lama ditulis langsung di dalam parse(); isinya sama, hanya diberi nama.
SL_LINE = re.compile(r'\[OM-(\w+)\] (.*)')                                  # lama:172
SL_NOTIF = re.compile(r'Notification email sent successfully (\w+)')         # lama:203
SL_MAIL = re.compile(r'mail', re.I)                                         # lama:204
COREDNS = re.compile(r'\[(\w+)\] plugin/errors: \d+ (\S+) (\w+): (.*)')      # lama:209
COREDNS_ADDR = re.compile(r'[\d.]+:\d+')                                    # lama:212
NGX_UPSTREAM = re.compile(r'upstream: "https?://([^/"]+)')                   # lama:152
NGX_ERR_TS = re.compile(r'(\d{4})/(\d\d)/(\d\d) (\d\d:\d\d)')                # lama:154
NGX_ERR_REQ = re.compile(r'request: "(\S+ \S+)')                             # lama:154
NGX_ERRNO = re.compile(r'\(\d+: ')                                          # lama:155
SPRING_STARTED = re.compile(r'Started (\w+) in ([\d.]+) seconds')           # lama:222
SPRING_JWT = re.compile(r'JWT token is expired: .* a difference of (\d+) milliseconds')  # lama:223
SPRING_PDF = re.compile(r'(\S+) pdf path')                                  # lama:225
SPRING_EXC = re.compile(r'[\w.$]+(Exception|Error)\b')                      # lama:236

# ---------------------------------------------------------------- klasifikasi serangan  (lama:32-43)
# Indikasi serangan pada URL (setelah URL-decode). Urutan = prioritas, match pertama yang dipakai.
# ponytail: signature regex sederhana, bisa false positive/negative; pakai WAF (ModSecurity/CRS) untuk deteksi serius.
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

# Base URL production per upstream (lama:46-53). Di v2 ini NILAI BAWAAN konfigurasi (config.py), bukan konstanta.
HOSTS = {
    'om-be-simpel-loop-3000': 'https://api-simpel4.ombudsman.go.id',
    'om-be-appsmanager-3000': 'https://appsmanager-simpel4.ombudsman.go.id',
    'om-be-referensi-3000': 'https://reference-simpel4.ombudsman.go.id',
    'om-be-report-3000': 'https://report-simpel4.ombudsman.go.id',
    'om-fe-inhouse-3000': 'https://simpel4.ombudsman.go.id',            # dari referer aset same-origin
    'cattle-system-rancher-80': 'https://rancher-prd.ombudsman.go.id',  # dari referer UI Rancher
}
LOGIN_FAIL = re.compile(r"Invalid password for user/email: '([^']*)' from IP: ([\d.]+)")  # lama:54
LOGIN_LOCK = re.compile(r"due to 3 failed login attempts for user/email: '([^']*)' from IP: ([\d.]+)")
LOGIN_OK = re.compile(r"User '([^']*)' successfully logged in from IP: ([\d.]+)")


@functools.lru_cache(maxsize=200_000)  # URL banyak berulang (aset, endpoint polling)
def path_attack(path):  # lama:59
    p = unquote_plus(unquote_plus(path))  # tangani double-encoding
    return next((name for name, rx in ATTACKS if rx.search(p)), None)


def classify(path, ua):  # lama:65
    if cat := path_attack(path): return cat
    if '${' in unquote_plus(ua): return 'Log4Shell / RCE'  # payload lookup ${...} di User-Agent; pola ';id' dll. tidak dipakai (UA Instagram berisi '; id;')
    if SCANNER_UA.search(ua): return 'UA tool/scanner otomatis'


# ---------------------------------------------------------------- normalisasi  (lama:82-94)
def norm(msg):
    """Samakan pesan yang hanya beda angka/id/waktu agar bisa dihitung sebagai satu jenis."""
    msg = re.sub(r"'[^']*@[^']*'", "'<email>'", msg)
    msg = re.sub(r'\d{4}-\d\d-\d\dT[\d:]+Z', '<ts>', msg)
    msg = re.sub(r'\b[0-9a-f]{16,}\b', '<id>', msg)
    msg = re.sub(r'\b\d+(\.\d+)?\b', '#', msg)
    return msg[:220]


def path_key(p):
    p = p.split('?')[0]
    p = re.sub(r'/[0-9a-f-]{16,}', '/:id', p)
    return re.sub(r'/\d+', '/:n', p)[:120]


# ---------------------------------------------------------------- JWT, akun, insiden  (lama:242-281)
def jwt_bucket(ms):
    for lim, name in ((5 * 60e3, '< 5 Menit'), (3600e3, '5–60 Menit'), (86400e3, '1–24 Jam'), (7 * 86400e3, '1–7 Hari')):
        if ms < lim: return name
    return '> 7 Hari'


def dt(ts): return datetime.datetime.strptime(ts, '%Y-%m-%d %H:%M')


def accounts(lev, window_min=60):
    """Per akun: gagal/sukses, IP, dan tanda bahaya 'sukses setelah beberapa kali gagal' (indikasi akun dibobol)."""
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
    """Kelompokkan menit-menit ber-5xx yang berdekatan (jeda <= gap_min) menjadi satu insiden."""
    per_min = collections.defaultdict(lambda: [0, C(), C()])
    for (ts, up, st), n in inc.items(): p = per_min[ts]; p[0] += n; p[1][up] += n; p[2][st] += n
    out = []
    for ts in sorted(per_min):
        n, ups, sts = per_min[ts]
        if out and (dt(ts) - dt(out[-1][1])).total_seconds() <= gap_min * 60:
            o = out[-1]; o[1] = ts; o[2] += n; o[3].update(ups); o[4].update(sts)
        else: out.append([ts, ts, n, C(ups), C(sts)])
    return [[a, b, n, dict(u), dict(st)] for a, b, n, u, st in out]


# ---------------------------------------------------------------- pemilik IP, offline  (lama:324-350)
# Pemilik IP (ASN/ISP/negara) dicocokkan OFFLINE dari dataset publik iptoasn.com (public domain),
# jadi IP pengguna tidak dikirim ke layanan pihak ketiga. Hanya sampai tingkat pemilik jaringan, bukan orang.
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


# ---------------------------------------------------------------- lokasi IP dan peta, offline  (lama:353-394)
# Lokasi kota dicocokkan OFFLINE dari DB-IP City Lite (CC BY 4.0, wajib atribusi "IP Geolocation by DB-IP"),
# sama seperti pemilik IP: tidak ada IP pengguna yang dikirim keluar.
DBIP_URL = 'https://download.db-ip.com/free/dbip-city-lite-{:%Y-%m}.csv.gz'
LAND_URL = 'https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_50m_land.geojson'  # public domain
# IP tujuan di log = IP pod (privat), jadi titik tujuan di peta = lokasi IP publik server ini
# (hasil resolve api-simpel4.ombudsman.go.id). Di v2 keduanya NILAI BAWAAN konfigurasi.
SERVER_IP = '103.170.104.228'
SERVER_FALLBACK = ['Jakarta', 'Jakarta', 'ID', -6.2, 106.82]


def ip_int(ip): return int.from_bytes(socket.inet_aton(ip), 'big')


def geo_scan(need, rows):
    """need = [(int ip, ip)] terurut; rows = baris CSV DB-IP terurut -> {ip: [kota, provinsi, negara, lat, lon] | None}."""
    found, i = {}, 0
    for r in rows:
        if i == len(need) or ':' in r[0]: break  # selesai / masuk bagian IPv6
        end = ip_int(r[1])
        while i < len(need) and need[i][0] <= end:
            found[need[i][1]] = [r[5], r[4], r[3], float(r[6]), float(r[7])] if need[i][0] >= ip_int(r[0]) else None
            i += 1
    for _, ip in need[i:]: found[ip] = None
    return found


# ---------------------------------------------------------------- label wilayah  (lama:428-466)
# Label nama wilayah di peta: negara dari Natural Earth (public domain); provinsi & kabupaten/kota Indonesia
# dari GeoNames (CC BY 4.0). Nama provinsi di GeoNames campur Inggris/Indonesia, jadi dipetakan dari kode admin1-nya.
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
    """'Kabupaten Bogor' -> 'Kab. Bogor'; beberapa entri GeoNames berbahasa Inggris ('Gresik Regency')."""
    n = re.sub(r'^(.*) Regency$', r'Kabupaten \1', n)
    n = re.sub(r'^(.*) City$', r'Kota \1', n)
    return n.replace('Kabupaten ', 'Kab. ')


# ---------------------------------------------------------------- pemindaian file  (lama:505-516, potongan build())
DATE_DIR = re.compile(r'\d{4}-\d\d-\d\d')


def pod_name(svc, filename):
    """Nama pod dari nama file log (akhiran .gz sudah dibuang)."""
    return re.sub(rf'^log_{re.escape(svc)}_|_\d{{4}}-.*$', '', filename)


def split_relpath(relpath):
    """'<tanggal>/[ns/]<layanan>/<file>' -> (tanggal, ns, layanan, nama file tanpa .gz), atau None bila bukan file log sah."""
    parts = relpath.split(os.sep)
    if not DATE_DIR.fullmatch(parts[0]) or len(parts) < 3: return None
    return parts[0], '/'.join(parts[1:-2]) or '-', parts[-2], parts[-1].removesuffix('.gz')
