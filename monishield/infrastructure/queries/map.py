"""Halaman Peta IP (TRD §5.3)."""

from monishield.infrastructure.queries.sql import _all, _no, reject
from .tables import first

MOD = "regexp_replace(upstream, '-\\d+$', '')"


def ipmap(cur, folder, module=None):
    module = module or None
    modules = [r[0] for r in _all(cur, f'SELECT DISTINCT {MOD} FROM agg_flow WHERE folder = ? ORDER BY 1', folder)]
    if not modules: return _no('no_nginx')
    if module is not None and module not in modules: raise reject(404, 'not_found', 'Modul tidak ditemukan.')
    src = f"""FROM agg_flow f LEFT JOIN ip_info i USING (ip) WHERE f.folder = $f AND (CAST($m AS VARCHAR) IS NULL OR {MOD} = $m)"""
    p = dict(f=folder, m=module)
    k = cur.execute(f"""SELECT count(DISTINCT f.ip), count(DISTINCT (i.lat, i.lon)) FILTER (WHERE i.lat IS NOT NULL), count(DISTINCT i.country) FILTER (WHERE i.lat IS NOT NULL),
                               count(DISTINCT {MOD}), count(DISTINCT f.pod), coalesce(sum(f.n), 0),
                               coalesce(sum(f.n) FILTER (WHERE i.lat IS NOT NULL AND i.country <> 'ID'), 0), coalesce(sum(f.n) FILTER (WHERE i.lat IS NULL), 0) {src}""", p).fetchone()
    loc = f"{src} AND i.lat IS NOT NULL GROUP BY ALL"
    points = {(lat, lon): dict(lat=lat, lon=lon, city=city, region=region, cc=cc, ips=ips, requests=n, modules={})
              for lat, lon, city, region, cc, ips, n in cur.execute(
                  f"SELECT i.lat, i.lon, any_value(i.city), any_value(i.region), any_value(i.country), count(DISTINCT f.ip), sum(f.n)::BIGINT {src} AND i.lat IS NOT NULL GROUP BY i.lat, i.lon", p).fetchall()}
    for lat, lon, m, n in cur.execute(f"SELECT i.lat, i.lon, {MOD}, sum(f.n)::BIGINT {loc}", p).fetchall(): points[lat, lon]['modules'][m] = n
    points = sorted(points.values(), key=lambda x: (x['requests'], x['lat'], x['lon']))   # terbesar digambar terakhir, seperti lama
    return dict(available=True, module=module, modules=modules,
                kpi=dict(source_ips=k[0], locations=k[1], countries=k[2], modules=k[3], dest_pods=k[4], requests=k[5]),
                abroad_requests=k[6], unlocated_requests=k[7], points=points, tables=dict(flows=first(cur, 'flows', folder, module=module)))
