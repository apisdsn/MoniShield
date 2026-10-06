"""Folder log buatan kecil dari baris asli di fixtures/lines (dipakai uji ingest dan uji agregat).

  2026-01-01/                     (tanpa namespace, seperti folder 09-26 dan 09-27)
    om-be-appsmanager/  log_…_pod-a_….log
    om-fe-inhouse/      log_…_pod-f_….log
  2026-01-02/
    ingress-nginx/nginx-ingress-controller/  log_…_pod-n_….log
    kube-system/coredns/                     log_…_pod-d_….log
    ombudsman/om-be-simpel-loop/             log_…_pod-s_….log + .log.gz identik
    ombudsman/om-be-report/                  log_…_pod-r_….log.gz saja
    ombudsman/om-be-referensi/               log_…_pod-x_….log   (file rusak)
    ombudsman/om-be-appsmanager/             log_…_pod-e_….log   (kosong)
    ombudsman/layanan-baru/                  log_…_pod-u_….log   (layanan tak dikenal)
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
    write(log_path(root, a, None, 'om-be-appsmanager', 'pod-a'), lines('om-be-appsmanager'))
    write(log_path(root, a, None, 'om-fe-inhouse', 'pod-f'), lines('om-fe-inhouse'))
    write(log_path(root, b, 'ingress-nginx', 'nginx-ingress-controller', 'pod-n'), lines('nginx-ingress-controller'))
    write(log_path(root, b, 'kube-system', 'coredns', 'pod-d'), lines('coredns'))
    write(log_path(root, b, 'ombudsman', 'om-be-simpel-loop', 'pod-s'), lines('om-be-simpel-loop'))
    write(log_path(root, b, 'ombudsman', 'om-be-simpel-loop', 'pod-s', '.log.gz'), lines('om-be-simpel-loop'))
    write(log_path(root, b, 'ombudsman', 'om-be-report', 'pod-r', '.log.gz'), lines('om-be-report'))
    write(log_path(root, b, 'ombudsman', 'om-be-referensi', 'pod-x'), lines('rusak'))
    write(log_path(root, b, 'ombudsman', 'om-be-appsmanager', 'pod-e'), '')
    write(log_path(root, b, 'ombudsman', 'layanan-baru', 'pod-u'), lines('om-be-appsmanager'))
    write(os.path.join(root, 'recovery-file', 'x', 'bukan.log'), 'diabaikan: folder teratas bukan tanggal\n')
    write(os.path.join(root, b, 'lepas.log'), 'diabaikan: kurang dari 3 komponen path\n')
    return root
