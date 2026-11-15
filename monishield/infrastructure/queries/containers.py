"""Containers page (stage 62): the services of a collector folder that are Docker containers seen in the Servers metrics, with the log
lines of the folder next to what the metrics say (image, restarts). Kubernetes data keeps the Pods page."""
import datetime

from monishield.infrastructure.queries import servers as q_servers

RESTART_WINDOW = datetime.timedelta(hours=24)


def containers(folder_cur, metrics_cur, collectors, folder, now):
    """-> dict(available, kpi, hosts). `collectors` = [dict(id, name, platform, status)]; only Docker hosts count. Unavailable (with a reason)
    without a Docker collector or without a container the metrics know."""
    docker = [c for c in collectors if c['platform'] == 'docker']
    if not docker: return dict(available=False, reason='no_docker_hosts')
    n = q_servers._naive(now)
    by_id = {c['id']: c for c in docker}
    rows = [r for r in q_servers.targets(metrics_cur, sorted(by_id)) if r[2]]
    if not rows: return dict(available=False, reason='no_containers')
    lines = {s: (ln, err, warn) for s, ln, err, warn in folder_cur.execute('SELECT service, lines, err, warn FROM agg_service WHERE folder = ?', [folder]).fetchall()}
    restarts = {}
    for cid, host, ctr, d in metrics_cur.execute(
            f"SELECT cid, host, ctr, arg_max(v, t) - arg_min(v, t) FROM metric_point WHERE name = 'restarts' AND ctr <> '' AND t >= ? AND cid IN ({q_servers._marks(sorted(by_id))}) GROUP BY ALL",
            [n - RESTART_WINDOW, *sorted(by_id)]).fetchall():
        restarts[cid, host, ctr] = int(max(0.0, d or 0.0))
    hosts = {}
    for cid, host, ctr, _os, image, _first, last in rows:
        ln, err, warn = lines.get(ctr, (0, 0, 0))
        running = n - last <= q_servers.RUNNING
        hosts.setdefault((cid, host), []).append(dict(container=ctr, image=image, lines=ln, err=err, warn=warn, restarts=restarts.get((cid, host, ctr), 0), running=running))
    out = [dict(cid=cid, collector=by_id[cid]['name'], host=host, rows=sorted(rs, key=lambda r: r['container'])) for (cid, host), rs in sorted(hosts.items(), key=lambda kv: kv[0][1])]
    every = [r for h in out for r in h['rows']]
    running = [r for r in every if r['running']]
    return dict(available=True, hosts=out, kpi=dict(
        containers=len(every), running=len(running), with_logs=sum(1 for r in every if r['lines']), without_logs=[r['container'] for r in running if not r['lines']],
        err=sum(r['err'] for r in every), err_containers=sum(1 for r in every if r['err']), restarts=sum(r['restarts'] for r in every)))
