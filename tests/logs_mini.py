"""Small synthetic log folder built from real lines in fixtures/lines (used by the ingest and aggregate tests).

  2026-01-01/                     (no namespace, like folders 09-26 and 09-27)
    auth-service/  log_…_pod-a_….log
    web-frontend/      log_…_pod-f_….log
  2026-01-02/
    ingress-nginx/nginx-ingress-controller/  log_…_pod-n_….log
    kube-system/coredns/                     log_…_pod-d_….log
    tenant/event-api/             log_…_pod-s_….log + identical .log.gz
    tenant/report-service/                  log_…_pod-r_….log.gz only
    tenant/reference-service/               log_…_pod-x_….log   (corrupt file)
    tenant/auth-service/             log_…_pod-e_….log   (empty)
    tenant/unknown-service/                  log_…_pod-u_….log   (unknown service)
"""
import gzip, os

LINES = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fixtures', 'lines')


def lines(name): return open(os.path.join(LINES, name + '.txt'), encoding='utf-8').read()


def log_path(root, folder, ns, service, pod, ext='.log'):
    return os.path.join(root, folder, *([ns] if ns else []), service, f'log_{service}_{pod}_{folder}-00-00{ext}')


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if path.endswith('.gz'):
        with gzip.open(path, 'wb') as fh: fh.write(text.encode('utf-8'))
    else:
        with open(path, 'w', encoding='utf-8') as fh: fh.write(text)
    return path


def build(root):
    root = str(root); a, b = '2026-01-01', '2026-01-02'
    write(log_path(root, a, None, 'auth-service', 'pod-a'), lines('auth-service'))
    write(log_path(root, a, None, 'web-frontend', 'pod-f'), lines('web-frontend'))
    write(log_path(root, b, 'ingress-nginx', 'nginx-ingress-controller', 'pod-n'), lines('nginx-ingress-controller'))
    write(log_path(root, b, 'kube-system', 'coredns', 'pod-d'), lines('coredns'))
    write(log_path(root, b, 'tenant', 'event-api', 'pod-s'), lines('event-api'))
    write(log_path(root, b, 'tenant', 'event-api', 'pod-s', '.log.gz'), lines('event-api'))
    write(log_path(root, b, 'tenant', 'report-service', 'pod-r', '.log.gz'), lines('report-service'))
    write(log_path(root, b, 'tenant', 'reference-service', 'pod-x'), lines('corrupt'))
    write(log_path(root, b, 'tenant', 'auth-service', 'pod-e'), '')
    write(log_path(root, b, 'tenant', 'unknown-service', 'pod-u'), lines('auth-service'))
    write(os.path.join(root, 'recovery-file', 'x', 'ignored.log'), 'ignored: the top folder is not a date\n')
    write(os.path.join(root, b, 'loose.log'), 'ignored: fewer than 3 path parts\n')
    return root
