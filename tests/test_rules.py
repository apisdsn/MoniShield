"""rules.py harus identik dengan build_dashboard.py (TRD §4.1, §9.2).

(a) isi demo() sistem lama; (b) definisi pola sama persis; (c) hasil fungsi sama atas masukan nyata dari log.
Bagian (b) dan (c) dilewati bila build_dashboard.py tidak ada.
"""
import csv, glob, gzip, itertools, json, os, re

import pytest

from monishield.domain import rules
from conftest import ROOT, log_files

NGINX_FOLDERS = ('2026-09-29', '2026-09-30', '2026-10-03', '2026-10-05', '2026-10-06')
CACHE = os.path.join(ROOT, '.cache')
FE_UA = re.compile(r'" \d{3} \d+ "[^"]*" "([^"]*)" "')  # User-Agent di access log frontend


# ------------------------------------------------------------------ (a) demo() lama
def test_demo_geo_scan():
    rows = [['1.0.0.0', '1.0.0.255', 'OC', 'AU', 'Queensland', 'Brisbane', '-27.5', '153.0'],
            ['1.0.2.0', '1.0.2.255', 'AS', 'ID', 'Jakarta', 'Jakarta', '-6.2', '106.8'], ['2001::', '2001::1', '', '', '', '', '0', '0']]
    need = sorted((rules.ip_int(i), i) for i in ('1.0.0.7', '1.0.1.9', '1.0.2.255', '9.9.9.9'))
    assert rules.geo_scan(need, rows) == {'1.0.0.7': ['Brisbane', 'Queensland', 'AU', -27.5, 153.0], '1.0.1.9': None,
                                          '1.0.2.255': ['Jakarta', 'Jakarta', 'ID', -6.2, 106.8], '9.9.9.9': None}


def test_demo_kab_name():
    assert (rules.kab_name('Kabupaten Bogor'), rules.kab_name('Gresik Regency'), rules.kab_name('Kota Sabang')) == ('Kab. Bogor', 'Kab. Gresik', 'Kota Sabang')


def test_demo_baris_nginx_dengan_retry():
    """Baris contoh demo(): pola cocok dan pod yang menjawab = alamat terakhir (parser-nya diuji di Tahap 3)."""
    line = ('1.2.3.4 - - [04/Oct/2026:17:00:34 +0000] "GET / HTTP/1.1" 200 6599 "-" "x" 355 0.001 '
            '[ombudsman-ombudsman-om-fe-inhouse-3000] [] 10.42.1.1:3000, 10.42.2.2:3000 0, 6599 0.000, 0.001 502, 200 ' + 'a' * 32)
    m = rules.NGINX.match(line); tm = rules.NGX_TAIL.search(line.rstrip())
    assert m.group(1, 6, 7, 8, 12) == ('1.2.3.4', 'GET', '/', '200', 'ombudsman-ombudsman-om-fe-inhouse-3000')
    assert tm[1].replace(', ', ',').split(' ')[0].split(',')[-1] == '10.42.2.2:3000' and tm[2] == 'a' * 32


def test_pemindaian_file():
    assert rules.pod_name('om-be-report', 'log_om-be-report_om-be-report-866586bb75-bqfd6_2026-09-26-00-00.log') == 'om-be-report-866586bb75-bqfd6'
    assert rules.split_relpath(os.path.join('2026-09-29', 'ombudsman', 'om-be-report', 'a.log.gz')) == ('2026-09-29', 'ombudsman', 'om-be-report', 'a.log')
    assert rules.split_relpath(os.path.join('2026-09-26', 'om-be-report', 'a.log')) == ('2026-09-26', '-', 'om-be-report', 'a.log')
    assert rules.split_relpath(os.path.join('recovery-file', 'x', 'a.log')) is None
    assert rules.split_relpath(os.path.join('2026-09-26', 'a.log')) is None


# ------------------------------------------------------------------ (b) definisi sama persis
def test_pola_dan_tabel_sama(old):
    for name in ('NGINX', 'FE', 'JAVA', 'NGX_TAIL', 'NGX_ERR', 'SCANNER_UA', 'LOGIN_FAIL', 'LOGIN_LOCK', 'LOGIN_OK'):
        a, b = getattr(rules, name), getattr(old, name)
        assert (a.pattern, a.flags) == (b.pattern, b.flags), name
    assert [(n, r.pattern, r.flags) for n, r in rules.ATTACKS] == [(n, r.pattern, r.flags) for n, r in old.ATTACKS]
    for name in ('BIZ_EP', 'MON', 'HOSTS', 'PROV', 'SERVER_IP', 'SERVER_FALLBACK', 'IP2ASN_URL', 'DBIP_URL', 'LAND_URL', 'COUNTRIES_URL', 'GEONAMES_URL'):
        assert getattr(rules, name) == getattr(old, name), name


def test_pola_dalam_parse_sama_dengan_sumber_lama(old):
    """Pola yang di sistem lama ditulis langsung di parse(): teks polanya harus ada di sumber lama."""
    src = open(old.__file__, encoding='utf-8').read()
    for name in ('SL_LINE', 'SL_NOTIF', 'COREDNS', 'COREDNS_ADDR', 'NGX_UPSTREAM', 'NGX_ERR_TS', 'NGX_ERR_REQ', 'NGX_ERRNO',
                 'SPRING_STARTED', 'SPRING_JWT', 'SPRING_PDF', 'SPRING_EXC'):
        assert f"r'{getattr(rules, name).pattern}'" in src, name


# ------------------------------------------------------------------ (c) hasil sama atas masukan nyata
@pytest.fixture(scope='session')
def real(old):
    """Path, UA, IP, dan pesan dari log nyata; statistik mentah parser lama untuk akun dan insiden."""
    pairs, ips, msgs, jwt_ms, lev, inc = set(), set(), set(), set(), {}, {}
    for d in NGINX_FOLDERS:
        s = old.new_stats()
        for f in log_files('nginx-ingress-controller', (d,)):
            for line in open(f, errors='replace'):
                old.parse('nginx-ingress-controller', line, s)
                if m := old.NGINX.match(line): pairs.add((m[7], m[10])); ips.add(m[1])
                elif m := old.NGX_ERR.match(line): msgs.add(m[2])
        inc[d] = dict(s['inc'])
    for d in ('2026-09-29', '2026-09-30', '2026-10-03', '2026-10-06'):
        s = old.new_stats()
        for svc in ('om-be-appsmanager', 'om-be-referensi', 'om-be-report'):
            for f in log_files(svc, (d,)):
                for line in open(f, errors='replace'):
                    if svc == 'om-be-appsmanager': old.parse(svc, line, s)
                    if (m := old.JAVA.match(line)) and m[2] in ('ERROR', 'WARN'):
                        msgs.add(f'{m[4].split(".")[-1]}: {m[5]}')
                        if j := re.search(r'a difference of (\d+) milliseconds', m[5]): jwt_ms.add(int(j[1]))
        lev[d] = list(s['lev'])
    uas = {u for _, u in pairs}
    for f in glob.glob(os.path.join(ROOT, '2026-*', '**', 'om-fe-inhouse', '*.log'), recursive=True):  # UA tambahan: log nginx saja < 500 UA unik
        for line in open(f, errors='replace'):
            if m := FE_UA.search(line): uas.add(m[1])
    for f in log_files('om-be-simpel-loop', ('2026-09-29',)) + log_files('coredns'):
        for line in open(f, errors='replace'):
            if 'http.request.failed' in line or 'plugin/errors' in line: msgs.add(line.strip())
    return dict(pairs=sorted(pairs), uas=sorted(uas), ips=sorted(ips), msgs=sorted(msgs), jwt_ms=sorted(jwt_ms), lev=lev, inc=inc)


def test_cukup_masukan_nyata(real):
    paths = {p for p, _ in real['pairs']}; uas = real['uas']
    assert len(paths) >= 5000 and len(uas) >= 500 and len(real['msgs']) >= 500, (len(paths), len(uas), len(real['msgs']))


SERANGAN = ["/?id=1 union select 1,2", "/x?q=%2527%2520or%25201", "/<script>alert(1)</script>", "/a/../../etc/passwd", "/${jndi:ldap://x/a}",
            "/.env", "/.git/config", "/wp-login.php", "/index.php", "/cgi-bin/test.cgi", "/backup.sql", "/actuator/health", "/aman/saja"]
UA_UJI = ["sqlmap/1.7", "curl/8.1", "python-requests/2.31", "${jndi:ldap://x}", "Mozilla/5.0 (Instagram 1; id; x)", "Uptime-Kuma/2.0.2", "-"]


def test_classify_sama(old, real):
    pairs = real['pairs'] + list(itertools.product(SERANGAN, UA_UJI)) + [('/', u) for u in real['uas']] + [('/.env', u) for u in real['uas']]
    beda = [(p, u) for p, u in pairs if rules.classify(p, u) != old.classify(p, u)]
    assert not beda, beda[:3]
    assert {rules.classify(p, 'x') for p in SERANGAN} >= {n for n, _ in rules.ATTACKS} | {None}  # semua kategori teruji
    assert sum(1 for p, u in real['pairs'] if rules.classify(p, u)) > 100  # log nyata memang berisi serangan


def test_path_key_sama(old, real):
    paths = {p for p, _ in real['pairs']} | set(SERANGAN)
    assert all(rules.path_key(p) == old.path_key(p) for p in paths)
    assert rules.path_key('/tx-laporan/7906a995-b889-48ae-ac6f-f5e60c580953/file/12?x=1') == '/tx-laporan/:id/file/:n'


def test_norm_sama(old, real):
    assert all(rules.norm(m) == old.norm(m) for m in real['msgs'])
    assert rules.norm("user 'a.b@ombudsman.go.id' at 2026-09-25T23:22:35Z id 69dda3958192b7ac11f28e3e2dc2f10c took 12.5 ms") == \
        "user '<email>' at <ts> id <id> took # ms"


def test_jwt_bucket_sama(old, real):
    batas = [0, 1, 299_999, 300_000, 3_599_999, 3_600_000, 86_399_999, 86_400_000, 604_799_999, 604_800_000, 10**12]
    assert len(real['jwt_ms']) > 100
    assert all(rules.jwt_bucket(ms) == old.jwt_bucket(ms) for ms in batas + real['jwt_ms'])
    assert [rules.jwt_bucket(ms) for ms in (0, 300_000, 3_600_000, 86_400_000, 604_800_000)] == ['< 5 Menit', '5–60 Menit', '1–24 Jam', '1–7 Hari', '> 7 Hari']


def test_accounts_sama(old, real):
    assert sum(len(v) for v in real['lev'].values()) > 500
    for d, lev in real['lev'].items():
        assert rules.accounts(lev) == old.accounts(lev), d
    assert sum(len(rules.accounts(v)) for v in real['lev'].values()) > 50  # memang ada akun yang dianalisis


def test_incidents_sama(old, real):
    for d, inc in real['inc'].items():
        assert rules.incidents(inc) == old.incidents(inc), d
    assert [len(rules.incidents(real['inc'][d])) for d in ('2026-09-29', '2026-09-30')] == [7, 10]  # inv. §7.1


def test_ip_owner_sama(old, real):
    path = os.path.join(CACHE, 'ip2asn-v4.tsv.gz')
    if not os.path.exists(path): pytest.skip('cache ip2asn tidak ada')
    db = rules.load_ip2asn(path, max_age_days=10**6)  # umur tak terbatas: uji tidak boleh mengunduh
    old_db = getattr(old, '_db_uji', None) or old.load_ip2asn(max_age_days=10**6)
    assert db == old_db
    ips = real['ips'] + ['10.0.0.1', '127.0.0.1', '192.168.1.1', '0.0.0.0', '255.255.255.255', '2001:db8::1', 'bukan-ip', '']
    assert all(rules.ip_owner(ip, db) == old.ip_owner(ip, old_db) for ip in ips)
    assert rules.ip_owner('10.0.0.1', db) == dict(asn=None, cc='-', org='Jaringan Internal (IP Privat)')
    assert sum(1 for ip in real['ips'] if rules.ip_owner(ip, db)) > 1000


def test_geo_scan_sama(old, real):
    path = os.path.join(CACHE, 'dbip-city-lite.csv.gz')
    if not os.path.exists(path): pytest.skip('cache DB-IP tidak ada')
    need = sorted((rules.ip_int(ip), ip) for ip in real['ips'] if re.fullmatch(r'[\d.]+', ip))
    with gzip.open(path, 'rt', encoding='utf-8', newline='') as fh: a = rules.geo_scan(need, csv.reader(fh))
    with gzip.open(path, 'rt', encoding='utf-8', newline='') as fh: b = old.geo_scan(need, csv.reader(fh))
    assert a == b and sum(1 for v in a.values() if v) > 1000
    cache = json.load(open(os.path.join(CACHE, 'geo.json')))  # hasil sistem lama untuk IP yang sama
    assert all(a[ip] == cache[ip] for ip in a if ip in cache)


def test_map_labels_sama(old):
    files = os.path.join(CACHE, 'ne_110m_countries.geojson'), os.path.join(CACHE, 'geonames-ID.zip')
    if not all(map(os.path.exists, files)): pytest.skip('cache label peta tidak ada')
    out = rules.map_labels(*files)
    assert out == old.map_labels() and {k: len(v) for k, v in out.items()} == dict(c=177, p=38, k=514)
