"""Configuration of the OpenTelemetry Collector for one registered collector (docs/12-collector.md, step 5).

`normalize(platform, options)` checks the inputs an admin chose; `build(platform, base_url, options, version)` writes the
collector's YAML (for Kubernetes: the values file of the official Helm chart). Inputs are logs and, since stage 56, server
metrics (`host_metrics`, every platform) and container metrics (`container_metrics`, Docker hosts); endpoint checks come
later. The log body stays the original line: no parsing operator is used, except the `container` operator
that unwraps Docker's JSON-file format. Metrics never include process data (no `process` scraper: command lines are personal data). The collector's key is never part of the text: the exporter reads it from the
environment variable MONISHIELD_COLLECTOR_KEY (a systemd environment file, a service environment, a Kubernetes secret).
Pure: standard library and monishield.domain only; the YAML is written by a tiny emitter for this fixed structure.
"""
import json, re

from monishield.domain import kafka_message
from monishield.domain.errors import Fail

CHANNELS = ('application', 'system', 'security')   # Windows Event Log
MAX_FILES, MAX_UNITS, MAX_PATH = 30, 30, 500
KEY_ENV = 'MONISHIELD_COLLECTOR_KEY'
NODE_ENV = 'K8S_NODE_NAME'   # the node's name for the Kubernetes pod, from the downward API
UNIT = re.compile(r'[A-Za-z0-9:_.@\\-]{1,200}')    # a systemd unit name such as ssh.service or user@1000.service
BASE_URL = re.compile(r'https?://[A-Za-z0-9]([A-Za-z0-9.-]{0,251}[A-Za-z0-9])?(:\d{1,5})?(/[A-Za-z0-9._~/-]*)?')
WIN_PATH = re.compile(r'[A-Za-z]:[\\/]|\\\\')
DOCKER_LINKS = '/var/lib/otelcol-contrib/containers'   # name-based links to Docker's log files, kept by docker-names.sh
HELM_CHART = ('open-telemetry', 'https://open-telemetry.github.io/opentelemetry-helm-charts', 'open-telemetry/opentelemetry-collector')
QUEUE_DIRS = dict(linux='/var/lib/otelcol-contrib/queue', docker='/var/lib/otelcol-contrib/queue',
                  windows='C:\\ProgramData\\OpenTelemetry Collector\\queue', kubernetes='/var/lib/otelcol-queue')
KUBE_QUEUE_HOST = '/var/lib/otelcol-monishield/queue'
# A batch must stay far below the receiver's raw limit (S4_COLLECTOR_MAX_RAW_MB, 16 MB): 1000 lines of 64 KB would be 64 MB, but
# real lines are a few hundred bytes; the receiver cuts a line at 64 KB and a batch that is too big gets a final 413.
BATCH = dict(send_batch_size=500, send_batch_max_size=1000, timeout='5s')
METRIC_INTERVAL = '30s'
# Metrics are small: a scrape is some tens to a few hundred points. No maximum size, so a batch never splits one host's points.
METRIC_BATCH = dict(send_batch_size=8192, timeout='10s')
METRIC_OPTIONS = ('host_metrics', 'container_metrics')
# Mounts that are not storage of the server itself, and network devices that only copy traffic of the real one.
SKIP_FS_TYPES = ['autofs', 'binfmt_misc', 'bpf', 'cgroup', 'cgroup2', 'configfs', 'debugfs', 'devpts', 'devtmpfs', 'fusectl', 'hugetlbfs',
                 'iso9660', 'mqueue', 'nsfs', 'overlay', 'proc', 'procfs', 'pstore', 'rpc_pipefs', 'securityfs', 'selinuxfs', 'squashfs',
                 'sysfs', 'tracefs', 'tmpfs']
SKIP_MOUNTS = ['^/var/lib/docker/.*', '^/run/.*', '^/snap/.*', '^/boot/efi$']
SKIP_MOUNTS_NODE = SKIP_MOUNTS + ['^/var/lib/kubelet/.*', '^/var/lib/containerd/.*', '^/dev($|/)', '^/proc($|/)', '^/sys($|/)']
SKIP_DEVICES = ['^lo$', '^veth.*', '^br-.*', '^docker\\d*$', '^cali.*', '^flannel.*', '^cni.*', '^vxlan.*']
DOCKER_SOCKET = 'unix:///var/run/docker.sock'
HOSTFS = '/hostfs'    # where the Helm values mount the node's root file system


def default_options(platform):
    """What a new collector sends when the admin changes nothing."""
    return dict(linux=dict(files=[], journald=True, units=[], host_metrics=True),
                docker=dict(files=[], journald=False, units=[], containers=True, host_metrics=True, container_metrics=True),
                windows=dict(files=[], channels=['application', 'system'], host_metrics=True), kubernetes=dict(host_metrics=True)).get(platform) or {}


def stored(platform, options):
    """The options of a collector that is already registered. Options saved before the metric inputs existed (or never saved)
    send no metrics: an existing collector must not start on its own; the admin turns them on and runs the upgrade command."""
    if options is None: return normalize(platform, {**default_options(platform), **{k: False for k in METRIC_OPTIONS if k in default_options(platform)}})
    return normalize(platform, options)


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
    """The options in their canonical form, or Fail. `options` None means the defaults of the platform. A metric option that
    is missing is off (see `stored`)."""
    if options is None: return default_options(platform)
    if not isinstance(options, dict): _bad('invalid_options', 'options must be an object.')
    known = {'kubernetes': set(), 'windows': {'files', 'channels'}, 'linux': {'files', 'journald', 'units'},
             'docker': {'files', 'journald', 'units', 'containers', 'container_metrics'}}[platform] | {'host_metrics'}
    if platform != 'docker' and options.get('container_metrics') is False: options = {k: v for k, v in options.items() if k != 'container_metrics'}
    elif platform != 'docker' and 'container_metrics' in options: _bad('invalid_options', 'Container metrics are only available for Docker hosts.')
    if extra := sorted(set(options) - known): _bad('invalid_options', f'Not an option of a {platform} collector: {", ".join(map(str, extra))}.')
    out = {} if platform == 'kubernetes' else dict(files=_files(options.get('files'), platform))
    metrics = dict(host_metrics=_flag(options, 'host_metrics'))
    if platform == 'docker': metrics['container_metrics'] = _flag(options, 'container_metrics')
    if platform == 'kubernetes': return metrics
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
    if not (has or out['files'] or any(metrics.values())): _bad('no_inputs', 'Choose at least one input.')
    return {**out, **metrics}


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
def exporter(base, metrics=False):
    """One exporter for both signals: `endpoint` + /v1/logs for logs, `metrics_endpoint` for metrics (the same headers, retry and queue)."""
    return {'otlphttp/monishield': dict(
        endpoint=base + '/api/collector', **(dict(metrics_endpoint=base + '/api/collector/v1/metrics') if metrics else {}), encoding='json', compression='gzip',
        headers={'Authorization': 'Bearer ${env:' + KEY_ENV + '}'},   # the collector replaces this with the variable's value
        retry_on_failure=dict(enabled=True, initial_interval='5s', max_interval='60s', max_elapsed_time='0s'),   # 0 = never give up
        sending_queue=dict(enabled=True, storage='file_storage'))}


def extensions(queue_dir): return {'file_storage': dict(directory=queue_dir, create_directory=True, timeout='10s')}


def has_logs(platform, o):
    """Kubernetes always reads the pod logs; the other platforms read what the admin chose."""
    return platform == 'kubernetes' or bool(o.get('files') or o.get('journald') or o.get('containers') or o.get('channels'))


def has_metrics(o): return bool(o.get('host_metrics') or o.get('container_metrics'))


def processors(platform='', o=None):
    """Shared processors. With metrics: the operating system's description for the server's card (not on Kubernetes, where the
    detector would describe the collector's image), the batch for metrics, and the metric transform that keeps one CPU
    value per state (the per-core points are not used)."""
    p = {'resourcedetection': dict(detectors=['system'], system=dict(hostname_sources=['os'])), 'batch': dict(BATCH)}
    if has_metrics(o or {}):
        if platform != 'kubernetes': p['resourcedetection']['system']['resource_attributes'] = {'os.description': {'enabled': True}}
        p['metricstransform/monishield'] = dict(transforms=[dict(
            include='system.cpu.utilization', action='update',
            operations=[dict(action='aggregate_labels', label_set=['state'], aggregation_type='mean')])])
        p['batch/metrics'] = dict(METRIC_BATCH)
    return p


def _file_receiver(group):
    return dict(include=[group['path']], start_at='end', include_file_name=True, include_file_path=False,
                resource={'service.name': group['service']})


def _docker_receiver():
    # Docker names its log files by container id. The helper docker-names.sh (installed with the collector, run every 15 seconds)
    # keeps `<container name>.log` links to them in DOCKER_LINKS, so the file name is the container name. The `container` operator
    # unwraps Docker's JSON-file format and is the only parser, so the body stays the original line; one `add` copies the file name
    # (without `.log`) to `container.name`. start_at beginning + storage: a new link is read from its first line, and the saved offsets
    # keep a restart from reading a file twice (a file is told apart by its first bytes, not by its path). exclude_older_than: the first
    # run on a host whose containers ran for months does not send their history; only files written in the last day are read.
    return dict(include=[DOCKER_LINKS + '/*.log'], start_at='beginning', exclude_older_than='24h', storage='file_storage', include_file_name=True, include_file_path=False,
                operators=[dict(type='container', id='container-parser', format='docker', add_metadata_from_filepath=False),
                           dict(type='add', id='container-name', field='resource["container.name"]',
                                value='EXPR(attributes["log.file.name"][:-4])')])


def _receivers(platform, o):
    """-> {receiver id: its settings}"""
    r = {}
    for i, g in enumerate(o.get('files', []), 1): r[f'filelog/{i}'] = _file_receiver(g)
    if o.get('journald'):
        r['journald'] = dict(start_at='end', **(dict(units=o['units']) if o['units'] else {}))
    if o.get('containers'): r['filelog/docker'] = _docker_receiver()
    for c in o.get('channels', []): r[f'windowseventlog/{c}'] = dict(channel=c, start_at='end')
    return r


def _off(*names): return {n: {'enabled': False} for n in names}


def hostmetrics(platform):
    """The hostmetrics receiver: CPU, memory, load, file systems and network traffic. Never the process scrapers (command lines
    are personal data). Only the metrics MoniShield uses are on, so a scrape is a few dozen points."""
    node = platform == 'kubernetes'
    fs = dict(metrics=_off('system.filesystem.inodes.usage'))
    if platform != 'windows':
        fs.update(exclude_fs_types=dict(match_type='strict', fs_types=list(SKIP_FS_TYPES)),
                  exclude_mount_points=dict(match_type='regexp', mount_points=list(SKIP_MOUNTS_NODE if node else SKIP_MOUNTS)))
    scrapers = dict(
        cpu=dict(metrics={'system.cpu.utilization': {'enabled': True}, **_off('system.cpu.time', 'system.cpu.logical.count')}),
        memory=dict(metrics={'system.memory.limit': {'enabled': True}}),
        load=dict(metrics=_off('system.cpu.load_average.5m', 'system.cpu.load_average.15m')),
        filesystem=fs)
    # A Kubernetes node's collector runs in a pod: the network scraper would read the pod's own interface, not the node's.
    if not node:
        scrapers['network'] = dict(metrics=_off('system.network.packets', 'system.network.dropped', 'system.network.errors', 'system.network.connections'),
                                   exclude=dict(match_type='regexp', interfaces=list(SKIP_DEVICES)))
    return dict(collection_interval=METRIC_INTERVAL, **(dict(root_path=HOSTFS) if node else {}), scrapers=scrapers)


def docker_stats():
    """Container CPU, memory and network traffic from the Docker socket (the collector runs as root on a Docker host)."""
    return dict(endpoint=DOCKER_SOCKET, collection_interval=METRIC_INTERVAL, metrics={
        'container.restarts': {'enabled': True},
        **_off('container.cpu.usage.kernelmode', 'container.cpu.usage.total', 'container.cpu.usage.usermode', 'container.memory.file',
               'container.memory.percent', 'container.network.io.usage.rx_dropped', 'container.network.io.usage.tx_dropped',
               'container.blockio.io_service_bytes_recursive')})


def _metric_receivers(platform, o):
    r = {}
    if o.get('host_metrics'): r['hostmetrics'] = hostmetrics(platform)
    if o.get('container_metrics'): r['docker_stats'] = docker_stats()
    return r


def host_config(platform, base, o):
    receivers, metric_receivers = _receivers(platform, o), _metric_receivers(platform, o)
    pipelines = {}
    if has_logs(platform, o):
        pipelines['logs'] = dict(receivers=list(receivers), processors=['resourcedetection', 'batch'], exporters=['otlphttp/monishield'])
    if metric_receivers:
        pipelines['metrics'] = dict(receivers=list(metric_receivers), processors=['resourcedetection', 'metricstransform/monishield', 'batch/metrics'],
                                    exporters=['otlphttp/monishield'])
    return dict(extensions=extensions(QUEUE_DIRS[platform]), receivers={**receivers, **metric_receivers}, processors=processors(platform, o),
                exporters=exporter(base, bool(metric_receivers)), service=dict(extensions=['file_storage'], pipelines=pipelines))


def helm_values(base, version, o=None):
    """Values for open-telemetry/opentelemetry-collector (daemonset): the chart's presets read the pod logs and add the pod, namespace
    and container names, the exporter and queue are ours. The chart's own traces/metrics pipelines and their receivers are removed.
    With server metrics on, the node's root file system is mounted read-only at /hostfs for the hostmetrics receiver and the node's
    name (from the downward API) becomes `k8s.node.name`: inside the pod the detected host name is the pod's. The chart's
    `hostMetrics` preset is not used because it also switches on the disk and network scrapers (the network one would read the
    pod's interface, not the node's)."""
    o = o or {}
    metrics = bool(o.get('host_metrics'))
    off = {'enabled': False}
    node_env = [dict(name=NODE_ENV, valueFrom=dict(fieldRef=dict(fieldPath='spec.nodeName')))] if metrics else []
    node_volumes = [dict(name='hostfs', hostPath=dict(path='/'))] if metrics else []
    node_mounts = [dict(name='hostfs', mountPath=HOSTFS, readOnly=True, mountPropagation='HostToContainer')] if metrics else []
    procs = processors('kubernetes', o)
    if metrics: procs['resource/node'] = dict(attributes=[dict(key='k8s.node.name', value='${env:' + NODE_ENV + '}', action='upsert')])
    pipelines = dict(
        logs=dict(receivers=[], processors=['memory_limiter', 'resourcedetection', 'batch'], exporters=['otlphttp/monishield']),
        traces=None, metrics=dict(receivers=['hostmetrics'], processors=['memory_limiter', 'resourcedetection', 'resource/node', 'metricstransform/monishield', 'batch/metrics'],
                                  exporters=['otlphttp/monishield']) if metrics else None)
    return dict(
        mode='daemonset', fullnameOverride='monishield-collector',
        image=dict(repository='otel/opentelemetry-collector-contrib', tag=version), command=dict(name='otelcol-contrib'),
        presets=dict(logsCollection=dict(enabled=True, includeCollectorLogs=False), kubernetesAttributes=dict(enabled=True)),
        ports={k: off for k in ('otlp', 'otlp-http', 'jaeger-compact', 'jaeger-thrift', 'jaeger-grpc', 'zipkin')},
        service=off,
        securityContext=dict(runAsUser=0, runAsGroup=0),   # to read the pod log files and write the queue directory
        extraEnvs=[dict(name=KEY_ENV, valueFrom=dict(secretKeyRef=dict(name='monishield-collector', key='key'))), *node_env],
        extraVolumes=[dict(name='monishield-queue', hostPath=dict(path=KUBE_QUEUE_HOST, type='DirectoryOrCreate')), *node_volumes],
        extraVolumeMounts=[dict(name='monishield-queue', mountPath=QUEUE_DIRS['kubernetes']), *node_mounts],
        config=dict(
            receivers={**{k: None for k in ('otlp', 'jaeger', 'prometheus', 'zipkin')}, **({'hostmetrics': hostmetrics('kubernetes')} if metrics else {})},
            extensions=extensions(QUEUE_DIRS['kubernetes']), processors=procs, exporters=exporter(base, metrics),
            service=dict(extensions=['health_check', 'file_storage'], pipelines=pipelines)))


def build(platform, receiver_url, options=None, version=''):
    """The YAML text for a collector. `receiver_url` = MoniShield's address (see base_url); `version` is used by Kubernetes only."""
    if platform not in QUEUE_DIRS: _bad('invalid_platform', 'Unknown platform.')
    base, o = base_url(receiver_url), normalize(platform, options)
    head = ['# Written by MoniShield. Changes are overwritten the next time the configuration is downloaded.',
            f'# The collector key is not in this file: it is read from the environment variable {KEY_ENV}.']
    body = helm_values(base, version, o) if platform == 'kubernetes' else host_config(platform, base, o)
    return '\n'.join(head + emit(body)) + '\n'
