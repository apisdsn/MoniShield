"""Pencarian global di header (Tahap 24 butir 6): IP, akun, requestId, potongan URL dalam satu folder.

GET /api/search?q=…&folder=YYYY-MM-DD  ->  {q, folder, results: [{type, label, sub, n, target}]}
target = {tab, service?, q?}: halaman tujuan; frontend menyusun alamatnya dan mengisi filter tabel di sana.
Hanya membaca agregat dan tabel log folder itu; tidak ada yang dikirim ke luar.
"""
import re


from monishield.infrastructure.queries.sql import _all, reject
from .tables import NG

PER_TYPE = 5


def _like(s):
    return '%' + s.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'


def search(cur, params):
    q = (params.get('q') or '').strip()
    if not 2 <= len(q) <= 200: raise reject(400, 'invalid_parameter', 'Parameter tidak sah: q (2–200 karakter).')
    folder = params.get('folder')
    if folder:
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', folder) or not cur.execute('SELECT 1 FROM folder_state WHERE folder = ?', [folder]).fetchone():
            raise reject(404, 'not_found', 'Folder tidak ditemukan.')
    else:
        folder = str(cur.execute('SELECT max(folder) FROM folder_state').fetchone()[0] or '')
        if not folder: return dict(q=q, folder=None, results=[])
    out, like = [], _like(q)

    if re.fullmatch(r'[0-9A-Fa-f.:]+', q):   # IP utuh atau awalannya
        for ip, n, org in _all(cur, f"""SELECT a.ip, sum(a.requests), any_value(i.org) FROM agg_ip a LEFT JOIN ip_info i USING (ip)
                                        WHERE a.folder = ? AND a.ip LIKE ? ESCAPE '\\' GROUP BY a.ip ORDER BY 2 DESC, 1 LIMIT {PER_TYPE}""",
                               folder, _like(q)[1:]):
            out.append(dict(type='ip', label=ip, sub=org, n=int(n), target=dict(tab='ip', service=ip)))
    for acc, fail, ok in _all(cur, f"""SELECT account, fail, ok FROM agg_account WHERE folder = ? AND account ILIKE ? ESCAPE '\\'
                                       ORDER BY fail DESC, account LIMIT {PER_TYPE}""", folder, like):
        out.append(dict(type='account', label=acc, n=fail, ok=ok, target=dict(tab='keamanan', q=acc)))
    if len(q) >= 6 and re.fullmatch(r'[0-9A-Za-z-]+', q):   # requestId (ekor log ingress)
        for rid, ip, m, p, st in _all(cur, f"""SELECT request_id, ip, method, path_key, status FROM nginx_access
                                               WHERE folder = ? AND request_id LIKE ? ESCAPE '\\' ORDER BY ts_utc LIMIT {PER_TYPE}""",
                                      folder, _like(q)[1:]):
            out.append(dict(type='request', label=rid, sub=f'{m} {p} · {st}', ip=ip, target=dict(tab='ip', service=ip, q=rid)))
    if not re.fullmatch(r'[0-9.:]+', q):   # potongan URL/endpoint di layanan mana pun
        for svc, key, n in _all(cur, f"""SELECT service, key, requests FROM agg_endpoint WHERE folder = ? AND key ILIKE ? ESCAPE '\\'
                                         ORDER BY (service = '{NG}') DESC, requests DESC, key LIMIT {PER_TYPE}""", folder, like):
            out.append(dict(type='url', label=key, sub=svc, n=n, target=dict(tab='layanan', service=svc, q=key)))
    return dict(q=q, folder=folder, results=out)
