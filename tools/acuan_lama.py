#!/usr/bin/env python3
"""Reference numbers from the OLD build, for the v2 equivalence test -> v2/docs/00-acuan.json.

  python3 v2/tools/acuan_lama.py

Runs build_dashboard.build() as is (dashboard.html is rewritten too) and captures the RAW
statistics before the top-N cut, because numbers such as the unique IP count are not in dashboard.html.
Re-run whenever there is a new log folder: the numbers in 00-acuan.json only hold for the folder contents at that time.
"""
import json, os, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
import build_dashboard as bd  # noqa: E402

cap = {}
_correlate = bd.correlate
bd.correlate = lambda data: (cap.update(data=data), _correlate(data))[1]  # build() does not return the raw data
t0 = time.time(); bd.build(); seconds = round(time.time() - t0, 1)

html = open(os.path.join(ROOT, 'dashboard.html'), encoding='utf-8').read()
D = json.JSONDecoder().raw_decode(html, html.index('const D = ') + 10)[0]
tot = lambda c: sum(c.values())

days = {}
for day, v in sorted(cap['data'].items()):
    files = [f for f in D['files'] if f['date'] == day]
    days[day] = dict(_file=dict(jumlah=len(files), kosong=sum(not f['lines'] for f in files), byte=sum(f['size'] for f in files)))
    for svc, s in sorted(v.items()):
        st = s['status']
        days[day][svc] = dict(
            # --- core: lines, requests, errors, unique IPs, IP flows ---
            lines=s['lines'], err=s['err'], warn=s['warn'], req=tot(st),
            s4=sum(n for c, n in st.items() if c[0] == '4'), s5=sum(n for c, n in st.items() if c[0] == '5'),
            ip_unik=len(s['ips']), alur_ip=len(s['flow']), alur_ip_asal=len({k[0] for k in s['flow']}),
            # --- supporting, per feature ---
            jam=len(s['hour']), jam_total=tot(s['hour']), endpoint_unik=len(s['paths']), pesan_unik=len(s['msgs']),
            endpoint_min5=sum(len(x) >= 5 for x in s['dur'].values()), level=dict(s['extra']),
            serangan_req=tot(s['atk_cat']), serangan_kategori=dict(s['atk_cat']), serangan_url=len(s['atk']), serangan_ip=len(s['atk_ip']),
            ip_4xx=len(s['ip4']), klien_401=len(s['c401']), total_5xx_upstream=tot(s['up5']), insiden_5xx=len(bd.incidents(s['inc'])),
            pod_backend=len(s['pod']), retry=tot(s['retry']), error_koneksi_pod=len(s['uperr']), uptime_kuma=tot(s['uk']), uptime_kuma_gagal=tot(s['ukf']),
            event_simpel_loop=len(s['sl']), korelasi=s.get('corr'), jejak=len(s.get('trace', [])), lambat_1dtk=len(s['slow']),
            bisnis=dict(s['biz']), email_notifikasi=tot(s['mail']), aktivitas=tot(s['act']),
            restart=len(s['restart']), jwt=dict(s['jwt']), pdf_sukses=sum(x[0] for x in s['rep'].values()), pdf_gagal=sum(x[1] for x in s['rep'].values()),
            login_ip=len(s['login']), login_gagal=sum(u['fail'] for u in s['login'].values()), login_reset=sum(u['lock'] for u in s['login'].values()),
            login_sukses=sum(e[3] == 'ok' for e in s['lev']), akun_dianalisis=len(bd.accounts(s['lev'])),
        )
        # Values that SHOULD be shown after the definition fixes of TRD §4.4 (used by test E4).
        # Item 2: the hourly error count must equal the Error KPI (the old one only counted 5xx).
        # Item 4: the simpel-loop level distribution uses the effective level, so ERROR/WARN = Error/Warning KPI.
        # Item 9: 'slow >= 5 s' = all slow traces that did not fail (the old one only status 2xx).
        tr = s.get('trace') or []
        days[day][svc]['seharusnya'] = dict(
            herr_total=s['err'] if svc in ('nginx-ingress-controller', 'om-fe-inhouse') or svc.startswith('om-be-') and svc != 'om-be-simpel-loop' else None,
            level_error=s['err'] if svc == 'om-be-simpel-loop' else None,
            level_warn=s['warn'] if svc == 'om-be-simpel-loop' else None,
            # counted from the correlated events, NOT from s['trace'], which is already cut to 300 rows
            lambat_5dtk=sum(1 for e in s.get('sl', []) if e[0] in bd.REQ and not e[4] and e[3] >= 5000),
        )
        days[day][svc]['lama'] = dict(   # what ACTUALLY showed in the old dashboard (after the top-N cut)
            lambat_5dtk=sum(r[4] for r in tr if str(r[1]).startswith('2')),
            herr_total=sum(s['herr'].values()),
        )

out = dict(
    meta=dict(dibuat=time.strftime('%Y-%m-%d %H:%M'), python=sys.version.split()[0], detik_build=seconds, byte_dashboard_html=len(html.encode()),
              request_id_nginx=len(bd.REQ), file_log=len(D['files']), ip_dengan_pemilik=len(D['ipinfo']), ip_dengan_lokasi=len(D['geo']),
              label_peta={k: len(x) for k, x in D['labels'].items()}, server=D['server']),
    days=days)
dst = os.path.join(ROOT, 'v2', 'docs', '00-acuan.json')
json.dump(out, open(dst, 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
print('->', os.path.relpath(dst, ROOT), out['meta'], file=sys.stderr)
