"""Rancher log message (cluster logging -> Kafka, fluentd) -> log line + its file location, like the S3 export.

    {"log": "<original line>", "stream": "stdout", "tag": "kubernetes.var.log.containers.<pod>_<ns>_<container>-<id>.log",
     "docker": {...}, "kubernetes": {"container_name": …, "namespace_name": …, "pod_name": …}, "time": 1515680329}

Folder date follows the S3 export: folder D holds logs from (D-1 00:00, D 00:00] WIB. Pure; the consumer is in
monishield/application/kafka_service.py and the Kafka adapter in monishield/infrastructure/kafka_client.py."""
import datetime, json, os, re

from monishield.domain import parse
from monishield.domain.errors import Fail

WIB = datetime.timedelta(hours=7)


NAME = re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]{0,252}')


TAG = re.compile(r'containers\.([^_]+)_([^_]+)_(.+?)-[0-9a-f]{12,64}\.log$')


class KafkaFail(Fail):
    pass


# ------------------------------------------------------------------ message -> log line
def service_of(container, pod, ns=''):
    """Service name as in the S3 folder. The container name is usually the same; if not (e.g. the ingress-nginx Helm chart
    uses container 'controller'), it is matched from the pod name prefix."""
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
            if t > 1e14: t /= 1e6        # microseconds
            elif t > 1e11: t /= 1e3      # milliseconds
            return datetime.datetime.fromtimestamp(t, datetime.timezone.utc)
        if isinstance(t, str) and t:
            d = datetime.datetime.fromisoformat(t.replace('Z', '+00:00'))
            return d if d.tzinfo else d.replace(tzinfo=datetime.timezone.utc)
    except (ValueError, OverflowError, OSError): pass
    if ts_ms: return datetime.datetime.fromtimestamp(ts_ms / 1000, datetime.timezone.utc)
    return datetime.datetime.now(datetime.timezone.utc)


def parse_message(value, ts_ms=None):
    """Kafka message bytes/str -> (dict(ns, svc, pod, line, t), None) or (None, reason)."""
    try: obj = json.loads(value)
    except (ValueError, UnicodeDecodeError): return None, 'not JSON'
    if not isinstance(obj, dict): return None, 'not a JSON object'
    line = obj.get('log', obj.get('message'))
    if not isinstance(line, str): return None, "no 'log' field"
    line = line.rstrip('\r\n')
    if not line.strip(): return None, 'empty line'
    k = obj.get('kubernetes') if isinstance(obj.get('kubernetes'), dict) else {}
    ns, container, pod = k.get('namespace_name'), k.get('container_name'), k.get('pod_name')
    if not (ns and container and pod) and isinstance(obj.get('tag'), str):
        m = TAG.search(obj['tag'])
        if m: pod, ns, container = pod or m[1], ns or m[2], container or m[3]
    if not (ns and container and pod): return None, 'no kubernetes.namespace_name/container_name/pod_name'
    if not all(isinstance(x, str) and NAME.fullmatch(x) for x in (ns, container, pod)): return None, 'invalid namespace/container/pod name'
    return dict(ns=ns, svc=service_of(container, pod, ns), pod=pod, line=line, t=_time(obj, ts_ms)), None


def folder_of(t):
    """Date folder as in the S3 export: (D-1 00:00, D 00:00] WIB -> D."""
    w = t.astimezone(datetime.timezone.utc).replace(tzinfo=None) + WIB
    return ((w - datetime.timedelta(microseconds=1)).date() + datetime.timedelta(days=1)).isoformat()


def relpath(rec, folder):
    return os.path.join(folder, rec['ns'], rec['svc'], f"log_{rec['svc']}_{rec['pod']}_{folder}-00-00.log")


def configured(cfg): return bool(cfg.kafka_brokers and cfg.kafka_topic)
