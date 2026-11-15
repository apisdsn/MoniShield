"""Business page (TRD §5.3)."""

from monishield.domain import analysis, services as profile
from monishield.infrastructure.queries import analysis as q_analysis
from monishield.infrastructure.queries.sql import H, _all, _one
from .tables import first, services


def business(cur, folder, cfg=None):
    svc, p = services(cur, folder), profile.current()
    prev = _one(cur, 'SELECT max(folder) FROM folder_state WHERE folder < ?', folder)
    biz = lambda f: dict(cur.execute('SELECT metric, n FROM agg_biz WHERE folder = ?', [f]).fetchall())
    has_prev = prev and _one(cur, 'SELECT count(*) FROM agg_service WHERE folder = ? AND service = ?', prev, p.events)
    pdf = cur.execute('SELECT coalesce(sum(ok), 0), coalesce(sum(fail), 0) FROM agg_report WHERE folder = ?', [folder]).fetchone()
    return dict(
        available=True, sources=sorted(s for s, n in svc.items() if n), prev_folder=str(prev) if prev else None,
        biz=biz(folder), biz_prev=biz(prev) if has_prev else None,     # None = events service absent in the previous folder
        pdf=dict(ok=pdf[0], fail=pdf[1]),
        login=dict(ok=_one(cur, 'SELECT coalesce(sum(ok), 0) FROM agg_login_ip WHERE folder = ?', folder),
                   users=_one(cur, 'SELECT coalesce(sum(users_ok), 0) FROM agg_service WHERE folder = ? AND service = ?', folder, p.auth)),
        mail=_all(cur, 'SELECT kind, n FROM agg_mail WHERE folder = ? ORDER BY n DESC, kind', folder),
        login_ok_by_hour=_all(cur, f"SELECT {H.format('hour_wib')}, ok FROM agg_login_hour WHERE folder = ? AND ok > 0 ORDER BY hour_wib", folder),
        tables={t: first(cur, t, folder) for t in ('activity', 'pdf-templates')},
        custom=_custom(cur, folder, prev, cfg))   # stage 62: the rules of Analysis Settings


def _custom(cur, folder, prev, cfg):
    """One count per business rule of Analysis Settings, today and in the previous folder (None when that folder has too few lines of the
    rule's service to compare), and, without rules, the endpoints that could become one."""
    st = analysis.of(cfg)
    prev = str(prev) if prev else None
    now_lines = q_analysis.service_lines(cur, folder)
    prev_lines = q_analysis.service_lines(cur, prev) if prev else {}
    rules = []
    for m in st.business:
        n = q_analysis.count_rule(cur, folder, m)
        comparable = bool(prev and now_lines.get(m.service) and prev_lines.get(m.service, 0) >= 0.5 * now_lines[m.service])
        rules.append(dict(m.public(), n=n, prev=q_analysis.count_rule(cur, prev, m) if comparable else None, comparable=comparable, has_logs=bool(now_lines.get(m.service))))
    return dict(rules=rules, prev_folder=prev,
                suggestions=q_analysis.suggestions(cur, folder, st) if not rules else [],
                access=(lambda a: a and a['service'])(q_analysis.access(cur, folder, st)))
