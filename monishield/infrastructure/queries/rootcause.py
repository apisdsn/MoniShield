"""Root Cause page (TRD §5.3)."""

from monishield.infrastructure.queries.sql import _all, _one
from .tables import first, services

JWT_OLD = ('1–24 Jam', '1–7 Hari', '> 7 Hari')


def rootcause(cur, folder):
    jwt, refresh = {}, {}
    for s, b, n in _all(cur, 'SELECT service, bucket, n FROM agg_jwt WHERE folder = ? ORDER BY service', folder):
        if b == 'Refresh Token Kedaluwarsa': refresh[s] = n     # TRD §4.4 item 10: now shown
        else: jwt.setdefault(s, {})[b] = n
    pdf = cur.execute('SELECT coalesce(sum(ok), 0), coalesce(sum(fail), 0), count(*) FILTER (WHERE fail > 0) FROM agg_report WHERE folder = ?', [folder]).fetchone()
    return dict(
        available=True, sources=sorted(s for s, n in services(cur, folder).items() if n),
        jwt=jwt, jwt_total=sum(n for d in jwt.values() for n in d.values()), jwt_over_1h=sum(d.get(b, 0) for d in jwt.values() for b in JWT_OLD), refresh_expired=refresh,
        pdf=dict(ok=pdf[0], fail=pdf[1], templates_failed=pdf[2]),
        dns_total=_one(cur, 'SELECT coalesce(sum(n), 0) FROM v_dns WHERE folder = ?', folder),
        upstream_errors_total=_one(cur, 'SELECT count(*) FROM v_upstream_error WHERE folder = ?', folder),
        upstream_error_kinds=_all(cur, 'SELECT kind, count(*) FROM v_upstream_error WHERE folder = ? GROUP BY kind ORDER BY 2 DESC, 1', folder),
        tables={t: first(cur, t, folder) for t in ('c401', 'pdf-templates', 'dns')})
