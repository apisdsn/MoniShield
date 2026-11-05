"""Configuration of the OpenTelemetry Collector for one registered collector (docs/12-collector.md, step 5).

`normalize(platform, options)` checks the log inputs an admin chose; `build(platform, base_url, options, version)` writes the
collector's YAML (for Kubernetes: the values file of the official Helm chart). Only LOG inputs exist; metrics and endpoint
checks come with part 2. The log body stays the original line: no parsing operator is used, except the `container` operator
that unwraps Docker's JSON-file format. The collector's key is never part of the text: the exporter reads it from the
environment variable MONISHIELD_COLLECTOR_KEY (a systemd environment file, a service environment, a Kubernetes secret).
Pure: standard library and monishield.domain only; the YAML is written by a tiny emitter for this fixed structure.
"""
import json, re

from monishield.domain import kafka_message
from monishield.domain.errors import Fail

CHANNELS = ('application', 'system', 'security')   # Windows Event Log
MAX_FILES, MAX_UNITS, MAX_PATH = 30, 30, 500
KEY_ENV = 'MONISHIELD_COLLECTOR_KEY'
UNIT = re.compile(r'[A-Za-z0-9:_.@\\-]{1,200}')    # a systemd unit name such as ssh.service or user@1000.service
BASE_URL = re.compile(r'https?://[A-Za-z0-9]([A-Za-z0-9.-]{0,251}[A-Za-z0-9])?(:\d{1,5})?(/[A-Za-z0-9._~/-]*)?')
WIN_PATH = re.compile(r'[A-Za-z]:[\\/]|\\\\')
DOCKER_SOCKET = 'unix:///var/run/docker.sock'
DOCKER_LOG = '/var/lib/docker/containers/`container_id`/`container_id`-json.log'   # backticks: receiver_creator fills in the id
HELM_CHART = ('open-telemetry', 'https://open-telemetry.github.io/opentelemetry-helm-charts', 'open-telemetry/opentelemetry-collector')
QUEUE_DIRS = dict(linux='/var/lib/otelcol-contrib/queue', docker='/var/lib/otelcol-contrib/queue',
                  windows='C:\\ProgramData\\OpenTelemetry Collector\\queue', kubernetes='/var/lib/otelcol-queue')
KUBE_QUEUE_HOST = '/var/lib/otelcol-monishield/queue'
# A batch must stay far below the receiver's raw limit (S4_COLLECTOR_MAX_RAW_MB, 16 MB): 1000 lines of 64 KB would be 64 MB, but
# real lines are a few hundred bytes; the receiver cuts a line at 64 KB and a batch that is too big gets a final 413.
BATCH = dict(send_batch_size=500, send_batch_max_size=1000, timeout='5s')


def default_options(platform):
    """What a new collector sends when the admin changes nothing."""
    return dict(linux=dict(files=[], journald=True, units=[]), docker=dict(files=[], journald=False, units=[], containers=True),
                windows=dict(files=[], channels=['application', 'system']), kubernetes={}).get(platform) or {}


def _bad(code, message): raise Fail(code, message)


def _path(p, platform):
    if not isinstance(p, str) or not p.strip(): _bad('invalid_path', 'A file path is empty.')
    p = p.strip()
    if len(p) > MAX_PATH: _bad('invalid_path', f'A file path is longer than {MAX_PATH} characters.')
    if any(ord(c) < 32 or ord(c) == 127 for c in p) or '"' in p or "'" in p or '`' in p or '${' in p:
        _bad('invalid_path', 'A file path must not contain quotes, control characters or "${".')
    if platform == 'windows':
        if not WIN_PATH.match(p): _bad('invalid_path', 'A Windows file path must start with a drive letter, for example C:\\logs\\*.log.')
    elif not p.startswith('/'): _bad('invalid_path', 'A file path must be absolute and start with "/".')
    if p.endswith(('/', '\\')): _bad('invalid_path', 'A file path must name files, for example /var/log/app/*.log.')
    return p


def _service(s):
    if not isinstance(s, str) or not kafka_message.NAME.fullmatch(s):
        _bad('invalid_service', 'A service name uses letters, digits, dot, underscore and hyphen, and starts with a letter or digit.')
    return s


def _files(items, platform):
    if items is None: return []
    if not isinstance(items, list): _bad('invalid_options', 'files must be a list.')
    if len(items) > MAX_FILES: _bad('too_many_files', f'At most {MAX_FILES} file groups.')
    out = []
    for it in items:
        if not isinstance(it, dict): _bad('invalid_options', 'A file group needs a path and a service name.')
        out.append(dict(path=_path(it.get('path'), platform), service=_service(it.get('service'))))
    return out


def _flag(options, key):
    v = options.get(key, False)
    if not isinstance(v, bool): _bad('invalid_options', f'{key} must be true or false.')
    return v


def _units(items):
    if items is None: return []
    if not isinstance(items, list) or not all(isinstance(u, str) for u in items): _bad('invalid_options', 'units must be a list of names.')
    if len(items) > MAX_UNITS: _bad('invalid_options', f'At most {MAX_UNITS} journald units.')
    for u in items:
        if not UNIT.fullmatch(u): _bad('invalid_unit', 'A journald unit is a systemd unit name such as ssh.service.')
    return list(dict.fromkeys(items))


def normalize(platform, options):
    """The options in their canonical form, or Fail. `options` None means the defaults of the platform."""
    if options is None: return default_options(platform)
    if not isinstance(options, dict): _bad('invalid_options', 'options must be an object.')
    known = {'kubernetes': set(), 'windows': {'files', 'channels'}, 'linux': {'files', 'journald', 'units'},
             'docker': {'files', 'journald', 'units', 'containers'}}[platform]
    if extra := sorted(set(options) - known): _bad('invalid_options', f'Not an option of a {platform} collector: {", ".join(map(str, extra))}.')
    if platform == 'kubernetes': return {}
    out = dict(files=_files(options.get('files'), platform))
    if platform == 'windows':
        ch = options.get('channels', [])
        if not isinstance(ch, list) or not all(c in CHANNELS for c in ch): _bad('invalid_channel', f'Channels can be: {", ".join(CHANNELS)}.')
        out['channels'] = [c for c in CHANNELS if c in ch]
        has = bool(out['channels'])
    else:
        out['journald'], out['units'] = _flag(options, 'journald'), _units(options.get('units'))
        if out['units'] and not out['journald']: _bad('invalid_options', 'Journald units need journald to be on.')
        has = out['journald']
        if platform == 'docker':
            out['containers'] = _flag(options, 'containers')
            has = has or out['containers']
    if not (has or out['files']): _bad('no_inputs', 'Choose at least one log input.')
    return out


def base_url(url):
    """The address of MoniShield as the collector reaches it: scheme and host (and an optional path), no trailing slash."""
    u = (url or '').strip().rstrip('/')
    if not BASE_URL.fullmatch(u): _bad('invalid_url', 'The receiver address must look like https://logs.example.com.')
    return u


# YAML writer (strings are always double quoted, with the escapes of JSON, which YAML reads the same way)
KEY = re.compile(r'[A-Za-z_][A-Za-z0-9_./-]*')


def _scalar(v):
    if isinstance(v, bool): return 'true' if v else 'false'
    if isinstance(v, int): return str(v)
    if v is None: return 'null'
    return json.dumps(v, ensure_ascii=False)


def _key(k): return k if KEY.fullmatch(k) else json.dumps(k, ensure_ascii=False)


def emit(value, indent=0):
    """dict / list / scalar -> YAML lines. An empty dict or list is written inline."""
    pad, out = '  ' * indent, []
    if isinstance(value, dict):
        for k, v in value.items():
            if isinstance(v, (dict, list)) and v: out.append(f'{pad}{_key(k)}:'); out.extend(emit(v, indent + 1))
            else: out.append(f'{pad}{_key(k)}: ' + ('{}' if isinstance(v, dict) else '[]' if isinstance(v, list) else _scalar(v)))
    else:
        for v in value:
            if isinstance(v, dict) and v:
                inner = emit(v, indent + 1)
                out.append(f'{pad}- {inner[0].lstrip()}'); out.extend(inner[1:])
            elif isinstance(v, list) and v: out.append(f'{pad}-'); out.extend(emit(v, indent + 1))
            else: out.append(f'{pad}- ' + ('{}' if isinstance(v, dict) else '[]' if isinstance(v, list) else _scalar(v)))
    return out


# Pieces
def exporter(base):
    return {'otlphttp/monishield': dict(
        endpoint=base + '/api/collector', encoding='json', compression='gzip',
        headers={'Authorization': 'Bearer ${env:' + KEY_ENV + '}'},   # the collector replaces this with the variable's value
        retry_on_failure=dict(enabled=True, initial_interval='5s', max_interval='60s', max_elapsed_time='0s'),   # 0 = never give up
        sending_queue=dict(enabled=True, storage='file_storage'))}


def extensions(queue_dir): return {'file_storage': dict(directory=queue_dir, create_directory=True, timeout='10s')}


def docker_extensions(): return {'docker_observer': dict(endpoint=DOCKER_SOCKET)}


def processors(): return {'resourcedetection': dict(detectors=['system'], system=dict(hostname_sources=['os'])), 'batch': dict(BATCH)}


def _file_receiver(group):
    return dict(include=[group['path']], start_at='end', include_file_name=True, include_file_path=False,
                resource={'service.name': group['service']})


def _docker_receiver():
    # docker_observer watches the Docker socket; receiver_creator starts one filelog per discovered container, so the service is
    # the container's name (not the id the log folder is named by). The `container` operator unwraps Docker's JSON-file format and
    # is the only operator, so the body stays the original line. Backticked words are the endpoint's fields (checked with 0.163).
    return dict(watch_observers=['docker_observer'], receivers=dict(filelog=dict(
        rule='type == "container"',
        config=dict(include=[DOCKER_LOG], start_at='end', include_file_name=False, include_file_path=False,
                    operators=[dict(type='container', id='container-parser', format='docker', add_metadata_from_filepath=False)]),
        resource_attributes={'container.name': '`name`', 'container.id': '`container_id`', 'container.image.name': '`image`'})))


def _receivers(platform, o):
    """-> {receiver id: its settings}"""
    r = {}
    for i, g in enumerate(o.get('files', []), 1): r[f'filelog/{i}'] = _file_receiver(g)
    if o.get('journald'):
        r['journald'] = dict(start_at='end', **(dict(units=o['units']) if o['units'] else {}))
    if o.get('containers'): r['receiver_creator/docker'] = _docker_receiver()
    for c in o.get('channels', []): r[f'windowseventlog/{c}'] = dict(channel=c, start_at='end')
    return r


def host_config(platform, base, o):
    receivers = _receivers(platform, o)
    ext = extensions(QUEUE_DIRS[platform])
    if o.get('containers'): ext.update(docker_extensions())
    return dict(extensions=ext, receivers=receivers, processors=processors(), exporters=exporter(base),
                service=dict(extensions=list(ext), pipelines=dict(logs=dict(
                    receivers=list(receivers), processors=['resourcedetection', 'batch'], exporters=['otlphttp/monishield']))))


def helm_values(base, version):
    """Values for open-telemetry/opentelemetry-collector (daemonset): the chart's presets read the pod logs and add the pod, namespace
    and container names, the exporter and queue are ours. The chart's own traces/metrics pipelines and their receivers are removed."""
    off = {'enabled': False}
    return dict(
        mode='daemonset', fullnameOverride='monishield-collector',
        image=dict(repository='otel/opentelemetry-collector-contrib', tag=version), command=dict(name='otelcol-contrib'),
        presets=dict(logsCollection=dict(enabled=True, includeCollectorLogs=False), kubernetesAttributes=dict(enabled=True)),
        ports={k: off for k in ('otlp', 'otlp-http', 'jaeger-compact', 'jaeger-thrift', 'jaeger-grpc', 'zipkin')},
        service=off,
        securityContext=dict(runAsUser=0, runAsGroup=0),   # to read the pod log files and write the queue directory
        extraEnvs=[dict(name=KEY_ENV, valueFrom=dict(secretKeyRef=dict(name='monishield-collector', key='key')))],
        extraVolumes=[dict(name='monishield-queue', hostPath=dict(path=KUBE_QUEUE_HOST, type='DirectoryOrCreate'))],
        extraVolumeMounts=[dict(name='monishield-queue', mountPath=QUEUE_DIRS['kubernetes'])],
        config=dict(
            receivers={k: None for k in ('otlp', 'jaeger', 'prometheus', 'zipkin')},
            extensions=extensions(QUEUE_DIRS['kubernetes']), processors=processors(), exporters=exporter(base),
            service=dict(extensions=['health_check', 'file_storage'], pipelines=dict(
                logs=dict(receivers=[], processors=['memory_limiter', 'resourcedetection', 'batch'], exporters=['otlphttp/monishield']),
                traces=None, metrics=None))))


def build(platform, receiver_url, options=None, version=''):
    """The YAML text for a collector. `receiver_url` = MoniShield's address (see base_url); `version` is used by Kubernetes only."""
    if platform not in QUEUE_DIRS: _bad('invalid_platform', 'Unknown platform.')
    base, o = base_url(receiver_url), normalize(platform, options)
    head = ['# Written by MoniShield. Changes are overwritten the next time the configuration is downloaded.',
            f'# The collector key is not in this file: it is read from the environment variable {KEY_ENV}.']
    body = helm_values(base, version) if platform == 'kubernetes' else host_config(platform, base, o)
    return '\n'.join(head + emit(body)) + '\n'
