"""Command Center (Tahap 22, DRD §12, TRD §12): layar peta dunia + KPI utama + "yang perlu perhatian".

Satu endpoint untuk seluruh halaman (TRD §12: kelak sumbernya bisa ditambah aliran Kafka tanpa mengubah tampilan).
Datanya dari agregat folder yang sudah ada (peta = respons Peta IP); tidak ada perhitungan baru. Butir perhatian
dikirim sebagai kunci + angka, teksnya dari kamus (dua bahasa).
"""
from fastapi import APIRouter, Depends, Request

from .common import cursor, folder_param, require_user_ready, _all, _one
from .map import ipmap
from .tables import NG, SEV_SQL

router = APIRouter(prefix='/api', dependencies=[Depends(require_user_ready)])


@router.get('/folders/{folder}/command')
def command(request: Request, folder: str = Depends(folder_param), cur=Depends(cursor)):
    crs = request.app.state.cfg.attack_rules == 'crs'
    U, I = ('agg_crs_url', 'agg_crs_ip') if crs else ('agg_attack_url', 'agg_attack_ip')
    sev = 'severity' if crs else SEV_SQL
    ng = cur.execute('SELECT requests, n5xx FROM agg_service WHERE folder = ? AND service = ? AND lines > 0', [folder, NG]).fetchone()
    err, corrupt = cur.execute('SELECT coalesce(sum(err), 0), coalesce(sum(files_corrupt), 0) FROM agg_service WHERE folder = ?', [folder]).fetchone()
    atk_req, crit_req = cur.execute(f'SELECT coalesce(sum(hits), 0), coalesce(sum(hits) FILTER (WHERE {sev} = 3), 0) FROM {U} WHERE folder = ?', [folder]).fetchone()
    atk_ips = _one(cur, f'SELECT count(*) FROM {I} WHERE folder = ?', folder)
    login_ips, resets = cur.execute('SELECT count(*), coalesce(sum(lock), 0) FROM agg_login_ip WHERE folder = ? AND (fail > 0 OR lock > 0)', [folder]).fetchone()
    up = _all(cur, 'SELECT kind, count(*) FROM v_upstream_error WHERE folder = ? GROUP BY kind ORDER BY 2 DESC, 1', folder)
    top5 = cur.execute('SELECT upstream, n5xx FROM agg_upstream WHERE folder = ? AND n5xx > 0 ORDER BY n5xx DESC, upstream LIMIT 1', [folder]).fetchone()

    att = []   # urutan: merah dulu, lalu kuning; tiap butir menaut ke halaman yang menjelaskannya
    if atk_req: att.append(dict(key='attack_critical' if crit_req else 'attack', tone='err' if crit_req else 'warn', tab='keamanan',
                                n=crit_req or atk_req, ips=atk_ips))
    if up: att.append(dict(key='upstream', tone='err', tab='akar-masalah', n=sum(n for _, n in up), kind=up[0][0]))
    if ng and ng[1]: att.append(dict(key='n5xx', tone='err', tab='ketersediaan', n=ng[1], upstream=top5[0] if top5 else None, top=top5[1] if top5 else 0))
    if login_ips: att.append(dict(key='login', tone='warn', tab='keamanan', n=login_ips, resets=resets))
    if corrupt: att.append(dict(key='files', tone='warn', tab='pod', n=corrupt))
    att.sort(key=lambda a: a['tone'] != 'err')

    return dict(available=True, scheme='crs' if crs else 'lama',
                kpi=dict(requests=ng[0] if ng else None, n5xx=ng[1] if ng else None, errors=err, upstream_errors=sum(n for _, n in up),
                         attack_ips=atk_ips, login_fail_ips=login_ips),
                attention=att, map=ipmap(request, folder, cur))
