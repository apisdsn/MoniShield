"""Pesan log Rancher (cluster logging -> Kafka, fluentd) -> baris log + lokasi berkasnya, seperti ekspor S3.

    {"log": "<baris asli>", "stream": "stdout", "tag": "kubernetes.var.log.containers.<pod>_<ns>_<container>-<id>.log",
     "docker": {...}, "kubernetes": {"container_name": …, "namespace_name": …, "pod_name": …}, "time": 1515680329}

Tanggal folder mengikuti ekspor S3: folder D berisi log (D-1 00:00, D 00:00] WIB. Murni; konsumen ada di
monishield/application/kafka_service.py dan adapter Kafka di monishield/infrastructure/kafka_client.py."""
import datetime, json, os, re

from monishield.domain import parse
from monishield.domain.errors import Fail

WIB = datetime.timedelta(hours=7)


NAME = re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]{0,252}')


TAG = re.compile(r'containers\.([^_]+)_([^_]+)_(.+?)-[0-9a-f]{12,64}\.log$')


class KafkaFail(Fail):
    pass


# ------------------------------------------------------------------ pesan -> baris log
def service_of(container, pod, ns=''):
    """Nama layanan seperti folder S3. Nama container biasanya sudah sama; bila tidak (mis. ingress-nginx Helm memakai
    container 'controller'), dicocokkan dari awalan nama pod."""
    if parse.known_service(container): return container
    for s in list(parse.PARSERS) + list(parse.SPRING_SVCS):
        if pod.startswith(s + '-'): return s
    if container == 'controller' and 'ingress' in ns: return parse.NGINX_SVC
    return container


def _time(obj, ts_ms):
    t = obj.get('time', obj.get('@timestamp'))
    try:
        if isinstance(t, (int, float)) or (isinstance(t, str) and re.fullmatch(r'\d+(\.\d+)?', t)):
            t = float(t)
            if t > 1e14: t /= 1e6        # mikrodetik
            elif t > 1e11: t /= 1e3      # milidetik
            return datetime.datetime.fromtimestamp(t, datetime.timezone.utc)
        if isinstance(t, str) and t:
            d = datetime.datetime.fromisoformat(t.replace('Z', '+00:00'))
            return d if d.tzinfo else d.replace(tzinfo=datetime.timezone.utc)
    except (ValueError, OverflowError, OSError): pass
    if ts_ms: return datetime.datetime.fromtimestamp(ts_ms / 1000, datetime.timezone.utc)
    return datetime.datetime.now(datetime.timezone.utc)


def parse_message(value, ts_ms=None):
    """bytes/str pesan Kafka -> (dict(ns, svc, pod, line, t), None) atau (None, alasan)."""
    try: obj = json.loads(value)
    except (ValueError, UnicodeDecodeError): return None, 'bukan JSON'
    if not isinstance(obj, dict): return None, 'bukan objek JSON'
    line = obj.get('log', obj.get('message'))
    if not isinstance(line, str): return None, "tanpa kolom 'log'"
    line = line.rstrip('\r\n')
    if not line.strip(): return None, 'baris kosong'
    k = obj.get('kubernetes') if isinstance(obj.get('kubernetes'), dict) else {}
    ns, container, pod = k.get('namespace_name'), k.get('container_name'), k.get('pod_name')
    if not (ns and container and pod) and isinstance(obj.get('tag'), str):
        m = TAG.search(obj['tag'])
        if m: pod, ns, container = pod or m[1], ns or m[2], container or m[3]
    if not (ns and container and pod): return None, 'tanpa kubernetes.namespace_name/container_name/pod_name'
    if not all(isinstance(x, str) and NAME.fullmatch(x) for x in (ns, container, pod)): return None, 'nama namespace/container/pod tidak sah'
    return dict(ns=ns, svc=service_of(container, pod, ns), pod=pod, line=line, t=_time(obj, ts_ms)), None


def folder_of(t):
    """Folder tanggal seperti ekspor S3: (D-1 00:00, D 00:00] WIB -> D."""
    w = t.astimezone(datetime.timezone.utc).replace(tzinfo=None) + WIB
    return ((w - datetime.timedelta(microseconds=1)).date() + datetime.timedelta(days=1)).isoformat()


def relpath(rec, folder):
    return os.path.join(folder, rec['ns'], rec['svc'], f"log_{rec['svc']}_{rec['pod']}_{folder}-00-00.log")


def configured(cfg): return bool(cfg.kafka_brokers and cfg.kafka_topic)
