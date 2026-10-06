"""Halaman Keamanan (TRD §5.3)."""
import re

from fastapi import APIRouter, Depends

from .common import cursor, folder_param, require_user_ready, AM, H, _all, _has
from .tables import NG, SEV, SEV_SQL, cells, first, services

CLOUD = re.compile(r'CLOUD|OCEAN|AMAZON|AWS|AZURE|MICROSOFT|HETZNER|OVH|LINODE|VULTR|ALIBABA|TENCENT|HOSTING|DATACENTER', re.I)  # lama: temuan 5

router = APIRouter(prefix='/api', dependencies=[Depends(require_user_ready)])


@router.get('/folders/{folder}/security')
def security(folder: str = Depends(folder_param), cur=Depends(cursor)):
    svc = services(cur, folder)
    atk = _all(cur, f'SELECT category, {SEV_SQL}, hits, top_ip, status_counts, upstreams FROM agg_attack_url WHERE folder = ?', folder)
    aip = _all(cur, 'SELECT a.ip, a.hits, a.cats, i.org FROM agg_attack_ip a LEFT JOIN ip_info i USING (ip) WHERE a.folder = ? ORDER BY a.hits DESC, a.ip', folder)
    login = _all(cur, """SELECT l.ip, l.fail, l.lock, l.accounts, i.org FROM agg_login_ip l LEFT JOIN ip_info i USING (ip)
                         WHERE l.folder = ? AND (l.fail > 0 OR l.lock > 0) ORDER BY l.lock DESC, l.fail DESC, l.ip""", folder)
    acct = _all(cur, 'SELECT account, flags FROM agg_account WHERE folder = ?', folder)
    ok2 = lambda st: any(c.startswith('2') for c in st)
    kategori = lambda c: [r for r in atk if r[0] == c]
    ringkas = lambda rs: dict(hits=sum(r[2] for r in rs), ips=sorted({r[3] for r in rs}), upstreams=sorted({u for r in rs for u in r[5]}),
                              statuses=sorted({c for r in rs for c in r[4]}))
    per_cat, per_org = {}, {}
    for r in atk: per_cat[r[0]] = per_cat.get(r[0], 0) + r[2]
    for ip, hits, cats, org in aip: per_org[org or 'Tidak diketahui'] = per_org.get(org or 'Tidak diketahui', 0) + hits
    urut = lambda d, n=None: [list(x) for x in sorted(d.items(), key=lambda kv: (-kv[1], kv[0]))[:n]]
    top = cells(cur, [dict(ip=ip, hits=hits, max_severity=max(SEV.get(c, 1) for c in cats)) for ip, hits, cats, org in aip[:10]], ('ip',))
    top_login = cells(cur, [dict(ip=r[0], fail=r[1]) for r in sorted(login, key=lambda r: (-r[1], r[0]))[:10] if r[1]], ('ip',))
    return dict(
        available=True, nginx=_has(svc, NG), appsmanager=_has(svc, AM),
        kpi=dict(attack_requests=sum(r[2] for r in atk), attack_ips=len(aip), critical_hits=sum(r[2] for r in atk if r[1] == 3),
                 attack_urls_2xx=sum(1 for r in atk if r[1] >= 2 and ok2(r[4])), login_fail_ips=len(login),
                 accounts_ok_after_fail=sum('Sukses Setelah ≥3 Gagal' in f for _, f in acct), accounts_ok_other_ip=sum('Sukses Dari IP Berbeda' in f for _, f in acct),
                 resets=sum(r[2] for r in login)),
        by_category=[[c, n, SEV.get(c, 1)] for c, n in urut(per_cat)],
        by_hour=_all(cur, f"SELECT {H.format('hour_wib')}, n FROM agg_attack_hour WHERE folder = ? ORDER BY hour_wib", folder),
        top_ips=top, by_owner=urut(per_org, 10),
        login_by_hour=_all(cur, f"SELECT {H.format('hour_wib')}, fail FROM agg_login_hour WHERE folder = ? AND fail > 0 ORDER BY hour_wib", folder),
        login_top_ips=[dict(**r['ip'], fail=r['fail']) for r in top_login],
        findings=dict(
            log4shell=ringkas(kategori('Log4Shell / RCE')) if kategori('Log4Shell / RCE') else None,
            by_critical_category=[dict(category=c, **ringkas(kategori(c))) for c in ('SQL Injection', 'XSS', 'Path Traversal / LFI') if kategori(c)],
            rancher_probe_hits=sum(r[2] for r in atk if r[1] >= 2 and any('rancher' in u for u in r[5])),
            cloud_owners=sorted({org for ip, hits, cats, org in aip if org and CLOUD.search(org) and any(SEV.get(c, 1) >= 2 for c in cats)}),
            ombudsman_login_ips=[r[0] for r in login if r[4] and 'OMBUDSMAN' in r[4].upper()],
            multi_account_ips=[r[0] for r in login if len({u.split('@')[0] for u in r[3]}) >= 3],
            accounts_other_ip=[a for a, f in acct if 'Sukses Dari IP Berbeda' in f]),
        tables={t: first(cur, t, folder) for t in ('attack-urls', 'attack-ips', 'accounts', 'login-ips', 'ip-4xx')})
