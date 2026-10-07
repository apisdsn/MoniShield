"""Command Center (Tahap 22, DRD §12, TRD §12): layar peta dunia + KPI utama + "yang perlu perhatian".

Satu endpoint untuk seluruh halaman (TRD §12: kelak sumbernya bisa ditambah aliran Kafka tanpa mengubah tampilan).
Datanya dari agregat folder yang sudah ada (peta = respons Peta IP); tidak ada perhitungan baru. Butir perhatian
dikirim sebagai kunci + angka, teksnya dari kamus (dua bahasa).
Tahap 24: KPI folder sebelumnya (perubahan ▲/▼), grafik per jam (request, 5xx, serangan), dan butir perhatian tambahan
(pod restart, uptime gagal, PDF gagal, lonjakan JWT kedaluwarsa, layanan yang error-nya melonjak).
2026-10-07: pembanding rata-rata folder sebanding (`baseline`), dipakai juga oleh notifikasi (monishield/alerts.py).
"""
from fastapi import APIRouter, Depends, Request

from .common import cursor, folder_param, require_user_ready, H, _all, _one
from .map import ipmap
from .tables import NG, SEV_SQL

router = APIRouter(prefix='/api', dependencies=[Depends(require_user_ready)])

# ASUMSI (Tahap 24): ambang "lonjakan" dibanding folder sebelumnya = minimal 2× DAN bertambah minimal N
JUMP_FACTOR, JUMP_MIN_ERR, JUMP_MIN_JWT = 2, 50, 20


def _kpi(cur, folder, crs):
    """Angka satu folder: KPI utama + bahan butir perhatian. Semua dari agregat halaman asalnya."""
    U, I = ('agg_crs_url', 'agg_crs_ip') if crs else ('agg_attack_url', 'agg_attack_ip')
    sev = 'severity' if crs else SEV_SQL
    ng = cur.execute('SELECT requests, n5xx, lines FROM agg_service WHERE folder = ? AND service = ? AND lines > 0', [folder, NG]).fetchone()
    err, lines, corrupt = cur.execute('SELECT coalesce(sum(err), 0), coalesce(sum(lines), 0), coalesce(sum(files_corrupt), 0) FROM agg_service WHERE folder = ?',
                                      [folder]).fetchone()
    atk_req, crit_req = cur.execute(f'SELECT coalesce(sum(hits), 0), coalesce(sum(hits) FILTER (WHERE {sev} = 3), 0) FROM {U} WHERE folder = ?', [folder]).fetchone()
    login_ips, resets = cur.execute('SELECT count(*), coalesce(sum(lock), 0) FROM agg_login_ip WHERE folder = ? AND (fail > 0 OR lock > 0)', [folder]).fetchone()
    up = _all(cur, 'SELECT kind, count(*) FROM v_upstream_error WHERE folder = ? GROUP BY kind ORDER BY 2 DESC, 1', folder)
    pdf_fail, pdf_tpl = cur.execute('SELECT coalesce(sum(fail), 0), count(*) FILTER (WHERE fail > 0) FROM agg_report WHERE folder = ?', [folder]).fetchone()
    uk_n, uk_fail = cur.execute('SELECT coalesce(sum(n), 0), coalesce(sum(fail), 0) FROM agg_uk_hour WHERE folder = ?', [folder]).fetchone()
    return dict(
        kpi=dict(requests=ng[0] if ng else None, n5xx=ng[1] if ng else None, errors=err, upstream_errors=sum(n for _, n in up),
                 attack_ips=_one(cur, f'SELECT count(*) FROM {I} WHERE folder = ?', folder), login_fail_ips=login_ips),
        ng_lines=ng[2] if ng else 0, lines=lines, corrupt=corrupt, atk_req=atk_req, crit_req=crit_req, resets=resets, up=up,
        top5=cur.execute('SELECT upstream, n5xx FROM agg_upstream WHERE folder = ? AND n5xx > 0 ORDER BY n5xx DESC, upstream LIMIT 1', [folder]).fetchone(),
        restarts=_one(cur, 'SELECT count(*) FROM v_restart WHERE folder = ?', folder), pdf_fail=pdf_fail, pdf_tpl=pdf_tpl, uk_n=uk_n, uk_fail=uk_fail,
        jwt=_one(cur, "SELECT coalesce(sum(n), 0) FROM agg_jwt WHERE folder = ? AND bucket <> 'Refresh Token Kedaluwarsa'", folder),
        svc={s: (e, ln) for s, e, ln in _all(cur, 'SELECT service, err, lines FROM agg_service WHERE folder = ?', folder)})


# Pembanding rata-rata (permintaan pemilik 2026-10-07, saran 5): lebih adil daripada hanya folder kemarin. Rata-rata
# dari folder SEBELUMNYA (maks. WINDOW) yang sebanding: baris log ≥ 50 % folder ini (KPI ingress: baris ingress).
# Kurang dari MIN_FOLDERS folder sebanding -> tidak ada rata-rata (pemanggil memakai folder kemarin).
WINDOW, MIN_FOLDERS = 7, 3
NGX_KEYS = {'requests', 'n5xx', 'upstream_errors', 'attack_ips'}


def baseline(cur, folder, crs, a):
    """-> dict(window, folders, n_all, n_nginx, kpi={kunci: rata-rata|None}, atk_req, jwt, svc={layanan: err rata-rata})."""
    prev = [str(r[0]) for r in cur.execute('SELECT folder FROM folder_state WHERE folder < ? ORDER BY folder DESC LIMIT ?', [folder, WINDOW]).fetchall()]
    ks = [_kpi(cur, f, crs) for f in prev]
    ok_all = [k for k in ks if a['lines'] and k['lines'] >= 0.5 * a['lines']]
    ok_ngx = [k for k in ks if a['ng_lines'] and k['ng_lines'] >= 0.5 * a['ng_lines']]

    def avg(vals):
        vals = [v for v in vals if v is not None]
        return round(sum(vals) / len(vals), 1) if len(vals) >= MIN_FOLDERS else None
    kpi = {key: avg([k['kpi'][key] for k in (ok_ngx if key in NGX_KEYS else ok_all)]) for key in a['kpi']}
    svc = {s: avg([k['svc'].get(s, (0, 0))[0] for k in ok_all]) for s in a['svc']}
    return dict(window=WINDOW, folders=prev, n_all=len(ok_all), n_nginx=len(ok_ngx), kpi=kpi,
                atk_req=avg([k['atk_req'] for k in ok_ngx]), jwt=avg([k['jwt'] for k in ok_all]), svc=svc)


def _jump(cur_n, prev_n, min_add):
    return prev_n is not None and cur_n >= JUMP_FACTOR * prev_n and cur_n - prev_n >= min_add


@router.get('/folders/{folder}/command')
def command(request: Request, folder: str = Depends(folder_param), cur=Depends(cursor)):
    crs = request.app.state.cfg.attack_rules == 'crs'
    a = _kpi(cur, folder, crs)
    prev_f = cur.execute('SELECT max(folder) FROM folder_state WHERE folder < ?', [folder]).fetchone()[0]
    p = _kpi(cur, prev_f, crs) if prev_f else None
    base = baseline(cur, folder, crs, a)
    use_avg = base['n_all'] >= MIN_FOLDERS   # lonjakan dinilai terhadap rata-rata bila cukup folder sebanding

    att = []   # urutan: merah dulu, lalu kuning; tiap butir menaut ke halaman yang menjelaskannya
    if a['atk_req']: att.append(dict(key='attack_critical' if a['crit_req'] else 'attack', tone='err' if a['crit_req'] else 'warn', tab='keamanan',
                                     n=a['crit_req'] or a['atk_req'], ips=a['kpi']['attack_ips']))
    if a['up']: att.append(dict(key='upstream', tone='err', tab='akar-masalah', n=a['kpi']['upstream_errors'], kind=a['up'][0][0]))
    if a['kpi']['n5xx']: att.append(dict(key='n5xx', tone='err', tab='ketersediaan', n=a['kpi']['n5xx'],
                                         upstream=a['top5'][0] if a['top5'] else None, top=a['top5'][1] if a['top5'] else 0))
    if a['uk_fail']: att.append(dict(key='uptime', tone='err', tab='ketersediaan', n=a['uk_fail'], total=a['uk_n']))
    # layanan yang error-nya melonjak vs rata-rata folder sebanding (atau folder sebelumnya bila belum cukup data)
    naik = []
    for s, (e, ln) in a['svc'].items():
        if use_avg: pe = base['svc'].get(s)
        else:
            pe, pl = p['svc'].get(s, (None, 0)) if p else (None, 0)
            if pl < 0.5 * ln: pe = None
        if pe is not None and _jump(e, pe, JUMP_MIN_ERR): naik.append((e - pe, s, e, pe))
    for _, s, e, pe in sorted(naik, reverse=True)[:3]:
        att.append(dict(key='svc_jump', tone='err', tab='layanan', service=s, n=e, prev=pe, prev_folder=str(prev_f),
                        basis='avg' if use_avg else 'prev', days=base['n_all']))
    if a['kpi']['login_fail_ips']: att.append(dict(key='login', tone='warn', tab='keamanan', n=a['kpi']['login_fail_ips'], resets=a['resets']))
    if a['restarts']: att.append(dict(key='restarts', tone='warn', tab='pod', n=a['restarts']))
    if a['pdf_fail']: att.append(dict(key='pdf', tone='warn', tab='akar-masalah', n=a['pdf_fail'], templates=a['pdf_tpl']))
    # lonjakan JWT kedaluwarsa: hanya bila folder kemarin sebanding (baris ≥ 50 % hari ini)
    jb = base['jwt'] if use_avg else (p['jwt'] if p and p['lines'] >= 0.5 * a['lines'] else None)
    if jb is not None and _jump(a['jwt'], jb, JUMP_MIN_JWT):
        att.append(dict(key='jwt', tone='warn', tab='akar-masalah', n=a['jwt'], prev=jb, prev_folder=str(prev_f), basis='avg' if use_avg else 'prev', days=base['n_all']))
    if a['corrupt']: att.append(dict(key='files', tone='warn', tab='pod', n=a['corrupt']))
    att.sort(key=lambda x: x['tone'] != 'err')

    # per jam (WIB): request ingress, 5xx (dari tabel mentah seperti halaman Ketersediaan), request serangan
    hr = 'agg_crs_hour' if crs else 'agg_attack_hour'
    req = dict(_all(cur, f"SELECT {H.format('hour_wib')}, total FROM agg_hour WHERE folder = ? AND service = ? AND total > 0", folder, NG))
    n5 = dict(_all(cur, f"""SELECT {H.format("date_trunc('hour', ts_utc + INTERVAL 7 HOUR)")} AS h, count(*) FROM nginx_access
                           WHERE folder = ? AND status BETWEEN 500 AND 599 GROUP BY h""", folder)) if req else {}
    atk = dict(_all(cur, f"SELECT {H.format('hour_wib')}, n FROM {hr} WHERE folder = ?", folder))
    hours = sorted(set(req) | set(n5) | set(atk))

    return dict(available=True, scheme='crs' if crs else 'lama', kpi=a['kpi'],
                prev=dict(folder=str(prev_f), kpi=p['kpi'],
                          comparable=dict(nginx=bool(a['ng_lines']) and p['ng_lines'] >= 0.5 * a['ng_lines'], all=p['lines'] >= 0.5 * a['lines'])) if p else None,
                baseline=dict(window=base['window'], n_all=base['n_all'], n_nginx=base['n_nginx'], kpi=base['kpi'], folders=base['folders']),
                by_hour=dict(hours=hours, requests=[req.get(h, 0) for h in hours], n5xx=[n5.get(h, 0) for h in hours], attacks=[atk.get(h, 0) for h in hours]),
                attention=att, map=ipmap(request, folder, cur))
