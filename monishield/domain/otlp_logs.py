"""OTLP/HTTP JSON logs request (OpenTelemetry Collector `otlphttp`, encoding json) -> log lines + their place in the inbox.

    {"resourceLogs": [{"resource": {"attributes": [...]}, "scopeLogs": [{"logRecords": [
        {"timeUnixNano": "1730728536000000000", "body": {"stringValue": "<original line>"}, "attributes": [...]}]}]}]}

Every record becomes what the Kafka consumer makes (namespace, service, pod or host, line, time) plus a relative path in
the S3 folder layout, one file per host or pod per local hour. Kubernetes records get the same service names as the Kafka
source (`kafka_message.service_of`). Anything malformed is a rejected record with a reason, never an exception.
Pure: standard library and monishield.domain only; the receiver is in a later step (docs/12-collector.md)."""
import base64, binascii, datetime, json, os, re

from monishield.domain import kafka_message, timezone

MAX_RECORDS = 10000                     # per request; a collector sends batches far below this
MAX_LINE_BYTES = 64 * 1024
CUT = ' [cut]'
FUTURE = datetime.timedelta(minutes=5)  # a client clock further ahead than this is wrong: use the receive time
MAX_FILE_NAME = 255                     # bytes in most file systems
MAX_DEPTH = 16                          # nesting of AnyValue; deeper is malformed, not a recursion error
EPOCH = datetime.datetime(1970, 1, 1, tzinfo=datetime.timezone.utc)
SYSLOG_DAEMON = 3 * 8                   # journald lines are written as RFC 5424 with facility daemon


class Bad(ValueError):
    """A part of the request that cannot be used; the message is the reason counted in `rejected`."""


# AnyValue and attributes
def _int(v):
    if isinstance(v, int) and not isinstance(v, bool): return v
    if isinstance(v, str) and re.fullmatch(r'-?\d{1,20}', v): return int(v)     # int64 travels as a JSON string
    raise Bad('malformed value')


def _scalar(kind, v):
    if kind == 'stringValue' and isinstance(v, str): return v
    if kind == 'boolValue' and isinstance(v, bool): return v
    if kind == 'intValue': return _int(v)
    if kind == 'doubleValue' and isinstance(v, (int, float)) and not isinstance(v, bool): return v
    if kind == 'bytesValue' and isinstance(v, str):
        try: return base64.b64decode(v, validate=True).decode('utf-8')
        except (binascii.Error, UnicodeDecodeError): raise Bad('malformed value') from None
    raise Bad('malformed value')


def _values(v):
    if v is None: return []
    if not isinstance(v, dict) or not isinstance(v.get('values', []), list): raise Bad('malformed value')
    return v.get('values', [])


def any_value(v, depth=0):
    """AnyValue -> str / int / float / bool / list / dict, or None for an empty one. Bad when it is malformed."""
    if not isinstance(v, dict) or depth > MAX_DEPTH or len(v) > 1: raise Bad('malformed value')
    if not v: return None
    (kind, inner), = v.items()
    if kind == 'arrayValue': return [any_value(x, depth + 1) for x in _values(inner)]
    if kind == 'kvlistValue': return pairs(_values(inner), depth + 1)
    return _scalar(kind, inner)


def pairs(items, depth=0):
    """[{key, value}, ...] (attributes or a kvlist) -> dict in the received order; a repeated key keeps the last value."""
    if items is None: return {}
    if not isinstance(items, list): raise Bad('malformed attributes')
    out = {}
    for kv in items:
        if not isinstance(kv, dict) or not isinstance(kv.get('key'), str): raise Bad('malformed attributes')
        out[kv['key']] = any_value(kv.get('value', {}), depth)
    return out


# Names
def _text(v):
    """A non-empty string, else None (an attribute of another type is treated as missing)."""
    return v.strip() if isinstance(v, str) and v.strip() else None


def _clean(v):
    """Light clean-up of a name that must stay as the client wrote it; None when absent."""
    v = _text(v)
    return re.sub(r'[ /]', '-', v) if v else None


def _slug(v):
    """Lower-case name for values that are free text (Windows channel, file stem)."""
    return re.sub(r'[^a-z0-9._-]+', '-', v.lower()).strip('-._')


def _name(v):
    if not (isinstance(v, str) and kafka_message.NAME.fullmatch(v)): raise Bad('invalid name')
    return v


ROTATION = re.compile(r'\.(?:gz|bz2|xz|zip|old|bak)$|\.\d+$|(?:^|[-_.])\d{4}-?\d\d-?\d\d$', re.I)
EXTENSION = re.compile(r'\.[A-Za-z][A-Za-z0-9]{0,5}$')


def _unrotate(s):
    while (n := ROTATION.sub('', s)) != s: s = n
    return s


def file_stem(path):
    """'/var/log/app-2026-11-04.log' -> 'app'; 'access.log.1' -> 'access'; '' when nothing is left."""
    s = re.split(r'[/\\]', path.strip())[-1]
    return _slug(_unrotate(EXTENSION.sub('', _unrotate(s))))


# Line and time
def text_line(s):
    """The line as the client wrote it: one trailing newline removed, Windows line ends inside turned into \\n."""
    if s.endswith('\r\n'): s = s[:-2]
    elif s.endswith('\n'): s = s[:-1]
    return s.replace('\r\n', '\n')


def cut_line(s):
    b = s.encode('utf-8')
    if len(b) <= MAX_LINE_BYTES: return s
    keep = MAX_LINE_BYTES - len(CUT.encode())
    return b[:keep].decode('utf-8', 'ignore') + CUT          # 'ignore' drops a character cut in half


def compact(v): return json.dumps(v, ensure_ascii=False, separators=(',', ':'))


def _nano(v):
    n = _int(v) if v is not None else 0
    if n < 0: raise Bad('invalid time')
    return n


def time_of(rec, now):
    """timeUnixNano, else observedTimeUnixNano, else now; a time far in the future becomes now (aware UTC)."""
    try:
        n = _nano(rec.get('timeUnixNano')) or _nano(rec.get('observedTimeUnixNano'))
        t = EPOCH + datetime.timedelta(microseconds=n // 1000) if n else now
    except (Bad, OverflowError): raise Bad('invalid time') from None
    return now if t > now + FUTURE else t


def syslog_line(t, host, app, pid, priority, msg):
    """RFC 5424 line that the `syslog` preset reads: a journald MESSAGE has no time or level of its own."""
    pri = SYSLOG_DAEMON + (priority if isinstance(priority, int) and 0 <= priority <= 7 else 6)
    stamp = t.astimezone(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.') + f'{t.microsecond // 1000:03d}Z'
    return f'<{pri}>1 {stamp} {host} {app} {pid} - - {msg}'


# One record
def _body(rec):
    if 'body' not in rec: raise Bad('missing body')
    b = any_value(rec['body'])
    if b is None: raise Bad('missing body')
    return b


def _priority(v):
    try: return _int(v)
    except Bad: return None


def _slug_keep(v):
    """Like _slug but keeps the case: unit names such as 'user@1000' are valid on the client and must not be rejected."""
    return re.sub(r'[^A-Za-z0-9._-]+', '-', v).strip('-._')


def _journald_service(body):
    unit = _slug_keep((_text(body.get('_SYSTEMD_UNIT')) or '').removesuffix('.service'))
    return unit or _slug_keep(_text(body.get('SYSLOG_IDENTIFIER')) or '') or 'journald'


def _journald(body, t, host, svc):
    pid = str(body.get('_PID', ''))
    pid = pid if re.fullmatch(r'\d{1,10}', pid) else '-'
    return syslog_line(t, host, svc, pid, _priority(body.get('PRIORITY')), text_line(body['MESSAGE']))


def _where(attrs, body, t, collector):
    """(namespace, service, pod, line) by the first matching source kind; names are checked by the caller."""
    host = _clean(attrs.get('host.name'))
    k8s = [_text(attrs.get(k)) for k in ('k8s.namespace.name', 'k8s.pod.name', 'k8s.container.name')]
    if all(k8s):
        ns, pod, container = k8s
        return ns, kafka_message.service_of(container, pod, ns), pod, _plain(body)
    if isinstance(body, dict) and _text(body.get('channel')) and 'event_id' in body:                 # Windows Event Log
        host = host or _clean(body.get('computer')) or collector
        return host, 'windows-' + _slug(body['channel']), host, compact(body)
    if isinstance(body, dict) and isinstance(body.get('MESSAGE'), str):                               # journald
        host, svc = _name(host or _clean(body.get('_HOSTNAME')) or collector), _journald_service(body)
        return host, svc, host, _journald(body, t, host, svc)
    host = host or collector
    if container := _clean(attrs.get('container.name')): return host, container, host, _plain(body)      # Docker
    svc = _clean(attrs.get('service.name')) or file_stem(_text(attrs.get('log.file.name')) or '') or 'app'
    return host, svc, host, _plain(body)


def _plain(body):
    return text_line(body) if isinstance(body, str) else compact(body)


def read_record(rec, res_attrs, collector, now):
    """One logRecord -> dict(ns, svc, pod, line, t, relpath). Bad with the reason when it cannot be used."""
    if not isinstance(rec, dict): raise Bad('malformed record')
    attrs = {**res_attrs, **pairs(rec.get('attributes'))}          # a record's own attribute wins over its resource's
    body, t = _body(rec), time_of(rec, now)
    ns, svc, pod, line = _where(attrs, body, t, collector)
    ns, svc, pod = _name(ns), _name(svc), _name(pod)
    if not line.strip(): raise Bad('empty line')
    folder = kafka_message.folder_of(t)
    name = f'log_{svc}_{pod}_{folder}-{timezone.current().local(t).hour:02d}-00.log'
    if len(name.encode()) > MAX_FILE_NAME: raise Bad('invalid name')
    return dict(ns=ns, svc=svc, pod=pod, line=cut_line(line), t=t, relpath=os.path.join(folder, ns, svc, name))


# Request
def _list(v):
    if v is None: return []
    if not isinstance(v, list): raise Bad('malformed request')
    return v


def _records(payload):
    """Yield (resource attributes or the reason it is bad, logRecord) for every record of the request."""
    if not isinstance(payload, dict): raise Bad('malformed request')
    for res in _list(payload.get('resourceLogs')):
        try:
            if not isinstance(res, dict): raise Bad('malformed request')
            resource = {} if res.get('resource') is None else res['resource']
            if not isinstance(resource, dict): raise Bad('malformed request')
            attrs = pairs(resource.get('attributes'))
            scopes = _list(res.get('scopeLogs'))
        except Bad as e:
            yield e, None
            continue
        for scope in scopes:
            try:
                if not isinstance(scope, dict): raise Bad('malformed request')
                recs = _list(scope.get('logRecords'))
            except Bad as e:
                yield e, None
                continue
            for rec in recs: yield attrs, rec


def parse_logs(payload, collector, now):
    """Decoded OTLP/JSON logs request -> (records, rejected). `rejected` maps a reason to the number of records."""
    records, rejected = [], {}
    def reject(reason): rejected[reason] = rejected.get(reason, 0) + 1
    try:
        for attrs, rec in _records(payload):
            if isinstance(attrs, Bad): reject(str(attrs))
            elif len(records) + sum(rejected.values()) >= MAX_RECORDS: reject('too many records')
            else:
                try: records.append(read_record(rec, attrs, collector, now))
                except Bad as e: reject(str(e))
    except Bad as e:
        reject(str(e))
    return records, rejected


def partial_success(rejected):
    """OTLP JSON answer: {} when everything was taken, else the number of rejected records and why."""
    n = sum(rejected.values())
    if not n: return {}
    why = ', '.join(f'{r} ({c})' for r, c in sorted(rejected.items(), key=lambda x: -x[1]))
    return {'partialSuccess': {'rejectedLogRecords': str(n), 'errorMessage': f'{n} log records rejected: {why}'}}
