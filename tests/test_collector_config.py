"""Collector configuration (docs/12-collector.md, step 5): the YAML per platform, validation, quoting, the install scripts.
The real `otelcol-contrib validate` runs when the binary is there (py tools/fetch_otelcol.py) and is skipped otherwise."""
import os, re, shutil, subprocess, sys

import pytest

from monishield.domain import collector_config as cc
from monishield.domain.config_model import Config
from monishield.domain.errors import Fail
from monishield.infrastructure import collector_scripts

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = 'https://logs.example.com'
VERSION = Config().collector_otel_version
KEY = 'msk_7_' + 'K' * 43
FILES = [dict(path='/var/log/app/*.log', service='app'), dict(path='/srv/www/logs/access.log', service='www.nginx')]


def code(fn, *a, **kw):
    with pytest.raises(Fail) as e: fn(*a, **kw)
    return e.value.code


def build(platform='linux', options=None): return cc.build(platform, BASE, options, VERSION)


# Options
def test_defaults_per_platform():
    assert cc.normalize('linux', None) == dict(files=[], journald=True, units=[], host_metrics=True)
    assert cc.normalize('docker', None)['containers'] is True and cc.normalize('windows', None)['channels'] == ['application', 'system']
    assert cc.normalize('docker', None)['host_metrics'] is True and cc.normalize('docker', None)['container_metrics'] is True
    assert cc.normalize('windows', None)['host_metrics'] is True and 'container_metrics' not in cc.normalize('linux', None)
    assert cc.normalize('kubernetes', None) == dict(host_metrics=True) and cc.normalize('kubernetes', {}) == dict(host_metrics=False)


def test_normalize_is_canonical():
    o = cc.normalize('linux', dict(files=[dict(path=' /var/log/a.log ', service='a')], units=['ssh.service', 'ssh.service'], journald=True))
    assert o == dict(files=[dict(path='/var/log/a.log', service='a')], journald=True, units=['ssh.service'], host_metrics=False)
    assert cc.normalize('windows', dict(channels=['security', 'application']))['channels'] == ['application', 'security']


@pytest.mark.parametrize('platform,options,expected', [
    ('linux', dict(files=[dict(path='relative/a.log', service='a')]), 'invalid_path'),
    ('linux', dict(files=[dict(path='/var/log/a.log\nb', service='a')]), 'invalid_path'),
    ('linux', dict(files=[dict(path='/var/log/"a".log', service='a')]), 'invalid_path'),
    ('linux', dict(files=[dict(path="/var/log/a'.log", service='a')]), 'invalid_path'),
    ('linux', dict(files=[dict(path='/var/log/${env:HOME}/a.log', service='a')]), 'invalid_path'),
    ('linux', dict(files=[dict(path='/var/log/', service='a')]), 'invalid_path'),
    ('linux', dict(files=[dict(path='/' + 'a' * 600, service='a')]), 'invalid_path'),
    ('linux', dict(files=[dict(path='', service='a')]), 'invalid_path'),
    ('linux', dict(files=[dict(path='C:\\logs\\a.log', service='a')]), 'invalid_path'),
    ('windows', dict(files=[dict(path='/var/log/a.log', service='a')], channels=['system']), 'invalid_path'),
    ('linux', dict(files=[dict(path='/var/log/a.log', service='bad name')]), 'invalid_service'),
    ('linux', dict(files=[dict(path='/var/log/a.log', service='')]), 'invalid_service'),
    ('linux', dict(files=[dict(path='/var/log/a.log', service='a/b')]), 'invalid_service'),
    ('linux', dict(files=[dict(path='/var/log/a.log', service='x' * 300)]), 'invalid_service'),
    ('linux', dict(files=[dict(path='/var/log/a.log')]), 'invalid_service'),
    ('linux', dict(files=[dict(path='/var/log/a.log', service='a')] * 31), 'too_many_files'),
    ('linux', dict(files='/var/log/a.log'), 'invalid_options'),
    ('linux', dict(files=['/var/log/a.log']), 'invalid_options'),
    ('linux', dict(journald='yes'), 'invalid_options'),
    ('linux', dict(journald=False, units=['ssh.service'], files=FILES), 'invalid_options'),
    ('linux', dict(journald=True, units=['ssh service']), 'invalid_unit'),
    ('linux', dict(journald=True, units=['a\nb']), 'invalid_unit'),
    ('linux', dict(journald=True, units=['u%d.service' % i for i in range(31)]), 'invalid_options'),
    ('linux', dict(journald=False, files=[]), 'no_inputs'),
    ('linux', dict(containers=True), 'invalid_options'),      # not an option of a Linux collector
    ('docker', dict(journald=False, containers=False, files=[]), 'no_inputs'),
    ('windows', dict(channels=[]), 'no_inputs'),
    ('windows', dict(channels=['security', 'bogus']), 'invalid_channel'),
    ('windows', dict(journald=True), 'invalid_options'),
    ('kubernetes', dict(files=FILES), 'invalid_options'),
])
def test_bad_options(platform, options, expected): assert code(cc.normalize, platform, options) == expected


def test_options_must_be_an_object(): assert code(cc.normalize, 'linux', ['x']) == 'invalid_options'


def test_receiver_url():
    assert cc.base_url('https://logs.example.com/') == 'https://logs.example.com'
    assert cc.base_url('http://10.0.0.5:8000') == 'http://10.0.0.5:8000'
    for bad in ('', 'logs.example.com', 'ftp://x.com', 'https://x.com"; rm -rf /', 'https://x .com', 'https://x.com\nA: b', "https://x.com/'", 'https://', 'https://a.com:abc'):
        assert code(cc.base_url, bad) == 'invalid_url', bad


# YAML
def test_linux_files_and_journald():
    y = build('linux', dict(files=FILES, journald=True, units=['ssh.service', 'cron.service']))
    assert '  file_log/1:\n    include:\n      - "/var/log/app/*.log"\n    start_at: "end"\n    include_file_name: true' in y
    assert '    resource:\n      service.name: "app"' in y and '      service.name: "www.nginx"' in y and '  file_log/2:' in y
    assert '  journald:\n    start_at: "end"\n    units:\n      - "ssh.service"\n      - "cron.service"' in y
    assert 'receivers:\n        - "file_log/1"\n        - "file_log/2"\n        - "journald"' in y
    assert 'directory: "/var/lib/otelcol-contrib/queue"' in y
    assert 'operators' not in y and 'regex_parser' not in y and 'json_parser' not in y     # the body stays the original line


def test_docker_names_come_from_the_name_links():
    y = build('docker', dict(containers=True, journald=False, files=[]))
    assert '  file_log/docker:\n    include:\n      - "/var/lib/otelcol-contrib/containers/*.log"' in y
    assert 'exclude_older_than: "24h"' in y and 'start_at: "beginning"' in y and 'storage: "file_storage"' in y and 'include_file_name: true' in y
    assert 'container.name' in y and 'attributes[\\"log.file.name\\"][:-4]' in y            # the file name without .log
    assert y.count('type:') == 2 and 'type: "container"' in y and 'format: "docker"' in y and 'add_metadata_from_filepath: false' in y
    assert 'parser' not in y.replace('container-parser', '')                                   # the body stays the original line
    assert 'docker_observer' not in y and 'receiver_creator' not in y and 'docker.sock' not in y and 'service:\n  extensions:\n    - "file_storage"\n  pipelines' in y


def test_docker_receiver_is_only_there_when_containers_are_on():
    y = build('docker', dict(containers=False, journald=True, units=[], files=[]))
    assert 'file_log/docker' not in y and 'containers/*.log' not in y
    assert 'containers/*.log' not in build('linux')


def test_windows_channels_and_files():
    y = build('windows', dict(channels=['application', 'security'], files=[dict(path='C:\\inetpub\\logs\\*.log', service='iis')]))
    assert 'windows_event_log/application:\n    channel: "application"' in y and 'windows_event_log/security:' in y and 'windows_event_log/system' not in y
    assert 'include:\n      - "C:\\\\inetpub\\\\logs\\\\*.log"' in y                      # backslashes escaped in a double quoted string
    assert 'directory: "C:\\\\ProgramData\\\\OpenTelemetry Collector\\\\queue"' in y


@pytest.mark.parametrize('platform', ['linux', 'windows', 'docker'])
def test_common_parts_and_the_key_is_never_in_the_text(platform):
    y = build(platform)
    assert 'resource_detection:\n    detectors:\n      - "system"' in y
    assert 'send_batch_size: 500\n    send_batch_max_size: 1000\n    timeout: "5s"' in y
    for line in ('logs_endpoint: "https://logs.example.com/api/v1/collector/logs"', 'encoding: "json"', 'compression: "gzip"',
                 'Authorization: "Bearer ${env:MONISHIELD_COLLECTOR_KEY}"', 'retry_on_failure:\n      enabled: true',
                 'sending_queue:\n      enabled: true\n      storage: "file_storage"', 'file_storage:\n    directory:'):
        assert line in y, line
    assert 'msk_' not in y and 'mse_' not in y
    # full addresses: a base `endpoint` would get the exporter's own /v1/logs suffix appended (a double v1)
    assert not re.search(r'^\s+endpoint: "https', y, re.M) and '/v1/logs' not in y and '/v1/metrics' not in y and y.count('/api/v1/collector/logs') == 1
    assert 'processors:\n        - "resource_detection"\n        - "batch"' in y


def test_batch_stays_far_below_the_receiver_limit():
    assert cc.BATCH['send_batch_max_size'] <= 1000 and cc.BATCH['send_batch_size'] <= cc.BATCH['send_batch_max_size']
    # 1000 lines cut at the receiver's 64 KB would still be under its raw limit only for ordinary lines; the cap keeps it far below
    assert cc.BATCH['send_batch_max_size'] * 4096 < Config().collector_max_raw_mb * 1024 * 1024


def test_kubernetes_values():
    y = build('kubernetes')
    for line in ('mode: "daemonset"', 'repository: "otel/opentelemetry-collector-contrib"', f'tag: "{VERSION}"', 'logsCollection:\n    enabled: true',
                 'kubernetesAttributes:\n    enabled: true', 'name: "otelcol-contrib"', 'logs_endpoint: "https://logs.example.com/api/v1/collector/logs"',
                 'storage: "file_storage"', 'secretKeyRef:\n        name: "monishield-collector"\n        key: "key"', 'hostPath:', 'traces: null'):
        assert line in y, line
    assert 'msk_' not in y and 'Bearer ${env:MONISHIELD_COLLECTOR_KEY}' in y and 'file_log' not in y     # the chart's preset adds the receiver


def test_quoting_keeps_odd_values_inside_one_string():
    nasty = dict(path='/srv/a b/#x: y/{a,b}/*.log', service='svc.v1')
    y = build('linux', dict(files=[nasty], journald=False))
    assert '- "/srv/a b/#x: y/{a,b}/*.log"' in y
    assert cc.emit(dict(k='a: b # c', n=None, t=True, i=3, e=[], d={})) == ['k: "a: b # c"', 'n: null', 't: true', 'i: 3', 'e: []', 'd: {}']
    assert cc.emit([dict(a=1, b=[dict(c=2)])]) == ['- a: 1', '  b:', '    - c: 2']


def test_unknown_platform_and_bad_url():
    assert code(cc.build, 'mac', BASE, None, VERSION) == 'invalid_platform'
    assert code(cc.build, 'linux', 'nonsense', None, VERSION) == 'invalid_url'


# Metric inputs (stage 56)
METRIC_OPTIONS = {
    'linux': dict(files=[], journald=True, units=[], host_metrics=True),
    'docker': dict(files=[], journald=False, units=[], containers=True, host_metrics=True, container_metrics=True),
    'windows': dict(files=[], channels=['application'], host_metrics=True),
}


def test_metric_options_are_booleans_and_missing_means_off():
    assert cc.normalize('linux', dict(journald=True))['host_metrics'] is False
    assert cc.normalize('docker', dict(containers=True)) == dict(files=[], journald=False, units=[], containers=True, host_metrics=False, container_metrics=False)
    assert cc.normalize('windows', dict(channels=['system'], host_metrics=True))['host_metrics'] is True
    assert code(cc.normalize, 'linux', dict(journald=True, host_metrics='yes')) == 'invalid_options'
    assert code(cc.normalize, 'docker', dict(containers=True, container_metrics=1)) == 'invalid_options'


@pytest.mark.parametrize('platform', ['linux', 'windows', 'kubernetes'])
def test_container_metrics_belong_to_docker_hosts(platform):
    assert code(cc.normalize, platform, dict(container_metrics=True, host_metrics=True)) == 'invalid_options'
    assert 'container_metrics' not in cc.normalize(platform, dict(container_metrics=False, host_metrics=True))      # off is accepted, and dropped


def test_metrics_alone_are_an_input_but_nothing_at_all_is_not():
    assert cc.normalize('linux', dict(journald=False, host_metrics=True))['host_metrics'] is True
    assert cc.normalize('docker', dict(journald=False, containers=False, container_metrics=True))['container_metrics'] is True
    assert code(cc.normalize, 'linux', dict(journald=False, host_metrics=False)) == 'no_inputs'
    assert code(cc.normalize, 'docker', dict(journald=False, containers=False, host_metrics=False, container_metrics=False)) == 'no_inputs'


def test_collectors_made_before_the_metrics_send_none():
    for platform in cc.QUEUE_DIRS:
        o = cc.stored(platform, None)
        assert o['host_metrics'] is False and not o.get('container_metrics'), platform
        assert cc.stored(platform, {k: v for k, v in cc.default_options(platform).items() if 'metrics' not in k}) == o
    assert cc.stored('linux', dict(journald=True, host_metrics=True))['host_metrics'] is True
    assert 'metrics' not in build('linux', cc.stored('linux', None)).replace('host_metrics', '')       # no metrics pipeline, no metrics endpoint


def test_metrics_off_leaves_the_log_configuration_as_it_was():
    for platform, options in (('linux', dict(journald=True, host_metrics=False)), ('windows', dict(channels=['system'], host_metrics=False)),
                              ('docker', dict(containers=True, host_metrics=False, container_metrics=False)), ('kubernetes', dict(host_metrics=False))):
        y = build(platform, options)
        assert 'host_metrics' not in y and 'docker_stats' not in y and 'metrics_endpoint' not in y and 'metrics_transform' not in y and 'batch/metrics' not in y
        assert 'os.description' not in y and 'metrics:\n' not in y.replace('host_metrics', '')


def test_linux_metrics_pipeline():
    y = build('linux', METRIC_OPTIONS['linux'])
    assert 'metrics_endpoint: "https://logs.example.com/api/v1/collector/metrics"' in y and 'logs_endpoint: "https://logs.example.com/api/v1/collector/logs"' in y
    assert '  host_metrics:\n    collection_interval: "30s"' in y and 'docker_stats' not in y and 'root_path' not in y
    assert ('    metrics:\n      receivers:\n        - "host_metrics"\n      processors:\n        - "resource_detection"\n        - "metrics_transform/monishield"\n'
            '        - "batch/metrics"\n      exporters:\n        - "otlp_http/monishield"') in y
    assert 'logs:\n      receivers:\n        - "journald"' in y
    for part in ('system.cpu.utilization:\n            enabled: true', 'system.cpu.time:\n            enabled: false', 'system.memory.limit:\n            enabled: true',
                 'system.cpu.load_average.5m:\n            enabled: true', 'system.cpu.load_average.15m:\n            enabled: true',
                 'system.cpu.logical.count:\n            enabled: true', 'system.uptime:\n            enabled: true', 'system.disk.operations:\n            enabled: false',
                 'system.disk.io_time:\n            enabled: false', 'system.disk.merged:\n            enabled: false', '- "^loop\\\\d+$"', '- "^dm-\\\\d+$"',
                 '- "^nvme\\\\d+n\\\\d+p\\\\d+$"', 'system.filesystem.inodes.usage:\n            enabled: false',
                 'system.network.packets:\n            enabled: false', '- "^docker\\\\d*$"', '- "^/var/lib/docker/.*"', '- "^/boot/efi$"', '- "tmpfs"',
                 'aggregation_type: "mean"', 'label_set:\n              - "state"', 'os.description:\n          enabled: true'):
        assert part in y, part
    assert 'process' not in y.replace('processors', '')                                       # never the process scrapers
    assert 'system.disk.io:' not in y                                                          # the one disk metric left on is not named


def test_windows_has_no_mount_excludes_and_docker_stats_is_docker_only():
    y = build('windows', METRIC_OPTIONS['windows'])
    assert 'host_metrics' in y and 'exclude_mount_points' not in y and 'exclude_fs_types' not in y and '"^lo$"' in y and 'docker_stats' not in y
    assert 'disk:' in y and 'system.disk.operations:\n            enabled: false' in y and '^loop' not in y and 'system.uptime' in y
    y = build('docker', METRIC_OPTIONS['docker'])
    assert '  docker_stats:\n    endpoint: "unix:///var/run/docker.sock"\n    collection_interval: "30s"' in y and 'container.restarts:\n        enabled: true' in y
    assert 'api_version' not in y and '        - "host_metrics"\n        - "docker_stats"' in y
    only = build('docker', dict(files=[], journald=False, units=[], containers=False, host_metrics=False, container_metrics=True))
    assert '  docker_stats:' in only and 'host_metrics' not in only and 'logs:' not in only and 'file_log' not in only


def test_metrics_only_collector_has_no_logs_pipeline():
    y = build('linux', dict(files=[], journald=False, units=[], host_metrics=True))
    assert 'service:\n  extensions:\n    - "file_storage"\n  pipelines:\n    metrics:' in y and 'logs:' not in y


def test_kubernetes_node_metrics_values():
    y = build('kubernetes', dict(host_metrics=True))
    for part in ('host_metrics:\n      collection_interval: "30s"\n      root_path: "/hostfs"', 'name: "K8S_NODE_NAME"', 'fieldPath: "spec.nodeName"',
                 'mountPath: "/hostfs"', 'readOnly: true', 'mountPropagation: "HostToContainer"', 'resource/node:', 'key: "k8s.node.name"',
                 'value: "${env:K8S_NODE_NAME}"', 'metrics_endpoint: "https://logs.example.com/api/v1/collector/metrics"', '- "^/var/lib/kubelet/.*"'):
        assert part in y, part
    assert ('metrics:\n        receivers:\n          - "host_metrics"\n        processors:\n          - "memory_limiter"\n          - "resource_detection"\n'
            '          - "resource/node"\n          - "metrics_transform/monishield"\n          - "batch/metrics"') in y
    assert 'disk:' in y and 'system.disk.operations:\n              enabled: false' in y and 'system.uptime' in y and '"^loop' in y
    assert 'network:' not in y and 'hostMetrics' not in y and 'os.description' not in y and 'traces: null' in y
    off = build('kubernetes', dict(host_metrics=False))
    assert 'host_metrics' not in off and 'hostfs' not in off and 'K8S_NODE_NAME' not in off and 'metrics: null' in off and 'metrics_endpoint' not in off


# The real collector
def otelcol():
    path = os.path.join(ROOT, 'tools', 'otelcol', VERSION, 'otelcol-contrib')
    return path if os.access(path, os.X_OK) else None


def validate(binary, tmp_path, text, **env):
    f = tmp_path / 'config.yaml'
    f.write_text(text, encoding='utf-8')
    r = subprocess.run([binary, 'validate', f'--config={f}'], env=dict(os.environ, MONISHIELD_COLLECTOR_KEY='dummy-key-for-validate', **env), capture_output=True, text=True, timeout=120)
    return r.returncode, r.stdout + r.stderr


@pytest.mark.skipif(not otelcol(), reason='run tools/fetch_otelcol.py to download otelcol-contrib')
@pytest.mark.parametrize('platform,options', [
    ('linux', dict(files=FILES, journald=True, units=['ssh.service'])),
    ('linux', dict(files=FILES[:1], journald=False)),
    ('linux', None),
    ('docker', dict(files=[], journald=False, containers=True)),
    ('docker', dict(files=FILES, journald=True, units=[], containers=True)),
    ('windows', dict(files=[dict(path='C:\\inetpub\\logs\\*.log', service='iis')], channels=[])),
])
def test_real_collector_accepts_the_config(tmp_path, platform, options):
    code_, out = validate(otelcol(), tmp_path, build(platform, options))
    assert code_ == 0, out


METRIC_CASES = [
    ('linux', METRIC_OPTIONS['linux']),
    ('linux', dict(files=[], journald=False, units=[], host_metrics=True)),                       # metrics only
    ('docker', METRIC_OPTIONS['docker']),
    ('docker', dict(files=[], journald=True, units=[], containers=False, host_metrics=False, container_metrics=True)),
    ('docker', dict(files=FILES, journald=False, units=[], containers=True, host_metrics=True, container_metrics=False)),
]


@pytest.mark.skipif(not otelcol(), reason='run tools/fetch_otelcol.py to download otelcol-contrib')
@pytest.mark.parametrize('platform,options', METRIC_CASES)
def test_real_collector_accepts_the_metric_config(tmp_path, platform, options):
    code_, out = validate(otelcol(), tmp_path, build(platform, options))
    assert code_ == 0, out


@pytest.mark.skipif(not otelcol(), reason='run tools/fetch_otelcol.py to download otelcol-contrib')
def test_real_collector_reads_the_windows_metric_settings(tmp_path):
    # Linux can read the whole file and builds the receivers; the Windows file system paths are not checked, the keys are.
    code_, out = validate(otelcol(), tmp_path, build('windows', dict(files=[], channels=['application'], host_metrics=True)))
    assert 'unknown' not in out and 'invalid keys' not in out and ('only supported on Windows' in out or code_ == 0), out
    code_, out = validate(otelcol(), tmp_path, build('windows', dict(files=[], channels=[], host_metrics=True)))
    assert code_ == 0, out


@pytest.mark.skipif(not otelcol(), reason='run tools/fetch_otelcol.py to download otelcol-contrib')
def test_real_collector_accepts_the_kubernetes_metric_pipeline(tmp_path):
    # The Helm chart merges these values into its own configuration; the part that is ours is checked as a collector file of its own:
    # the chart's memory_limiter and pre-set log receiver are stood in for, the rest is exactly what the values hold.
    cfg = cc.helm_values(BASE, VERSION, cc.normalize('kubernetes', dict(host_metrics=True)))['config']
    cfg['receivers'] = {k: v for k, v in cfg['receivers'].items() if v is not None}
    cfg['receivers']['host_metrics']['root_path'] = str(tmp_path)       # the real collector checks that the folder exists
    cfg['receivers']['file_log'] = dict(include=['/var/log/pods/*/*/*.log'])
    cfg['processors']['memory_limiter'] = dict(check_interval='5s', limit_percentage=80, spike_limit_percentage=25)
    cfg['service']['extensions'] = ['file_storage']
    cfg['service']['pipelines'] = {k: v for k, v in cfg['service']['pipelines'].items() if v is not None}
    cfg['service']['pipelines']['logs']['receivers'] = ['file_log']
    code_, out = validate(otelcol(), tmp_path, '\n'.join(cc.emit(cfg)) + '\n', K8S_NODE_NAME='node-1')     # the pod's downward API sets it
    assert code_ == 0, out
    assert 'resource/node' in cfg['processors'] and cfg['service']['pipelines']['metrics']['receivers'] == ['host_metrics']


@pytest.mark.skipif(not otelcol(), reason='run tools/fetch_otelcol.py to download otelcol-contrib')
def test_real_collector_reads_the_windows_event_log_settings(tmp_path):
    # The Windows Event Log receiver can only be created on Windows; on Linux the collector reads and checks the whole
    # configuration first and then refuses to build that receiver. Any other complaint would be a mistake in our YAML.
    code_, out = validate(otelcol(), tmp_path, build('windows', dict(channels=['application', 'system', 'security'])))
    assert code_ == 1 and 'only supported on Windows' in out and 'unknown' not in out and 'invalid keys' not in out, out


@pytest.mark.skipif(not otelcol(), reason='run tools/fetch_otelcol.py to download otelcol-contrib')
def test_real_collector_refuses_a_broken_config(tmp_path):
    assert validate(otelcol(), tmp_path, build('linux').replace('start_at: "end"', 'start_at: "middle"'))[0] != 0


# Install scripts
def render(name='install.sh', version=VERSION, url=BASE): return collector_scripts.render(name, version, url)


def test_scripts_are_filled_in_and_hold_no_secret():
    for name in collector_scripts.SCRIPTS:
        text = render(name)
        assert VERSION in text and BASE in text and '@@' not in text
        assert not re.search(r'ms[ek]_\d+_[A-Za-z0-9_-]{43}', text) and 'curl | sh' not in text and '| sh' not in text and '| bash' not in text
        assert 'AKIA' not in text and 'Co-Authored' not in text
    assert 'sha256' in render('install.sh') and 'Get-FileHash' in render('install.ps1')


def test_install_sh_carries_the_docker_name_helper(tmp_path):
    text = render('install.sh')
    helper = open(os.path.join(ROOT, 'monishield', 'infrastructure', 'assets', 'collector', 'docker-names.sh'), encoding='utf-8').read()
    assert helper.rstrip('\n') in text and '@@' not in text and text.count('MONISHIELD_DOCKER_NAMES') == 2
    for part in ('OnBootSec=5s', 'OnUnitActiveSec=15s', 'AccuracySec=1s', 'RestrictAddressFamilies=AF_UNIX', 'ExecStartPre=-', "HELPER_DIR='/usr/local/lib/monishield'",
                 'monishield-docker-names.timer'):
        assert part in text, part
    # the drop-in: After= is a [Unit] key; the Docker drop-in holds it, the others stay [Service] only
    assert "printf '[Unit]\\nAfter=docker.service\\n\\n[Service]\\nEnvironmentFile=%s/monishield.env\\nUser=root" in text
    assert "if [ \"$PLATFORM\" = docker ]; then printf '[Unit]\\nAfter=docker.service\\n\\n'; fi" in text
    assert 'Service]\\nEnvironmentFile=%s/monishield.env\\nAfter=' not in text and "printf 'After=docker.service" not in text
    # the heredoc writes the helper back byte for byte
    out = tmp_path / 'out.sh'
    start, end = text.index("<<'MONISHIELD_DOCKER_NAMES'\n") + len("<<'MONISHIELD_DOCKER_NAMES'\n"), text.index('\nMONISHIELD_DOCKER_NAMES\n')
    out.write_text(text[start:end] + '\n')
    assert out.read_text() == helper


def test_script_rejects_values_that_would_end_up_in_commands():
    with pytest.raises(Fail): render(url='https://x.com";id;"')
    with pytest.raises(ValueError): render(version='1.0;id')
    with pytest.raises(ValueError): render(version='')
    with pytest.raises(KeyError): render('other.sh')


@pytest.fixture
def script(tmp_path):
    p = tmp_path / 'install.sh'
    p.write_text(render())
    return p


def run_sh(script, *args, shell='sh'): return subprocess.run([shell, str(script), *args], capture_output=True, text=True, timeout=60)


@pytest.mark.skipif(not shutil.which('bash'), reason='bash needed')
def test_install_sh_syntax(script):
    for shell in ('bash', 'sh'):
        r = subprocess.run([shell, '-n', str(script)], capture_output=True, text=True)
        assert r.returncode == 0, r.stderr


@pytest.mark.skipif(not shutil.which('sh'), reason='sh needed')
def test_install_sh_dry_run_changes_nothing(script):
    r = run_sh(script, '--name', 'web-01', '--token', 'mse_7_' + 'A' * 43, '--dry-run')
    assert r.returncode == 0, r.stderr
    for part in (f'otelcol-contrib {VERSION}', f'{BASE}/api/v1/collector/enroll', 'X-Requested-With: monishield-collector', '/etc/otelcol-contrib/config.yaml',
                 '(mode 0640)', 'monishield.env', '(mode 0600)', 'SHA-256', '.sha256', '/var/lib/otelcol-contrib/queue', 'enable and restart',
                 'for a Docker collector', 'docker-names.sh', 'every 15 s'):
        assert part in r.stdout, part
    assert 'mse_7_' not in r.stdout and 'mse_7_' not in r.stderr                                  # the token is never echoed
    r = run_sh(script, '--name', 'web-01', '--token', 'mse_7_' + 'A' * 43, '--url', 'https://other.example.org', '--dry-run')
    assert 'https://other.example.org/api/v1/collector/enroll' in r.stdout


KEY = 'msk_7_' + 'B' * 43


@pytest.mark.skipif(not shutil.which('sh'), reason='sh needed')
def test_upgrade_dry_run_reads_the_installed_key_and_changes_nothing(script, tmp_path):
    conf = tmp_path / 'conf'; conf.mkdir()
    (conf / 'monishield.env').write_text(f'MONISHIELD_COLLECTOR_KEY={KEY}\n')
    r = run_sh(script, '--upgrade', '--dry-run', '--conf-dir', str(conf))
    assert r.returncode == 0, r.stderr
    for part in (f'{BASE}/api/v1/collector/config', 'Bearer token', 'otelcol-contrib validate', 'docker-names.sh', 'would restart', 'Upgrading the collector in place'):
        assert part in r.stdout, part
    assert KEY not in r.stdout and KEY not in r.stderr and sorted(p.name for p in conf.iterdir()) == ['monishield.env']
    r = run_sh(script, '--upgrade', '--dry-run', '--conf-dir', str(conf), '--url', 'https://other.example.org')
    assert 'https://other.example.org/api/v1/collector/config' in r.stdout


@pytest.mark.skipif(not shutil.which('sh'), reason='sh needed')
@pytest.mark.parametrize('content,message', [
    (None, 'no collector key is installed'),
    ('OTHER=1\n', 'holds no collector key'),
    ('MONISHIELD_COLLECTOR_KEY=abc\n', 'holds no collector key'),
    ('MONISHIELD_COLLECTOR_KEY=msk_1_a;id\n', 'unexpected characters'),
])
def test_upgrade_refuses_without_a_usable_key(script, tmp_path, content, message):
    conf = tmp_path / 'conf'; conf.mkdir()
    if content is not None: (conf / 'monishield.env').write_text(content)
    # a real run checks for root first, so without root (CI) only the dry run reaches the key checks
    for extra in ([], ['--dry-run']) if os.geteuid() == 0 else (['--dry-run'],):
        r = run_sh(script, '--upgrade', '--conf-dir', str(conf), *extra)
        assert r.returncode == 1 and message in r.stderr and not r.stdout


@pytest.mark.skipif(not shutil.which('sh'), reason='sh needed')
def test_upgrade_takes_no_name_or_token(script, tmp_path):
    r = run_sh(script, '--upgrade', '--name', 'web', '--conf-dir', str(tmp_path))
    assert r.returncode == 1 and 'takes no --name' in r.stderr


@pytest.mark.skipif(not shutil.which('sh'), reason='sh needed')
@pytest.mark.parametrize('args,message', [
    ([], '--name is required'),
    (['--name', 'Web 01', '--token', 'mse_1_x'], 'lowercase'),
    (['--name', 'web', '--token', 'abc'], 'enrollment token'),
    (['--name', 'web', '--token', 'mse_1_a;id'], 'characters'),
    (['--name', 'web', '--token', 'mse_1_a', '--url', 'ftp://x'], 'https://'),
    (['--name', 'web', '--token', 'mse_1_a', '--url', 'https://x.com/$(id)'], 'not allowed'),
    (['--name', 'web', '--token', 'mse_1_a', '--bogus'], 'unknown option'),
    (['--name'], 'needs a value'),
])
def test_install_sh_refuses_bad_arguments(script, args, message):
    r = run_sh(script, *args)
    assert r.returncode == 1 and message in r.stderr and not r.stdout


@pytest.mark.skipif(not shutil.which('sh') or os.geteuid() == 0, reason='needs a non-root user')
def test_install_sh_refuses_without_root(script):
    r = run_sh(script, '--name', 'web', '--token', 'mse_1_a')
    assert r.returncode == 1 and 'as root' in r.stderr


def test_install_ps1_has_the_same_flow():
    t = render('install.ps1')
    for part in ('-DryRun', 'Get-FileHash', 'msiexec.exe', 'X-Requested-With', 'monishield-collector', 'Restart-Service', 'HKLM:\\SYSTEM\\CurrentControlSet\\Services',
                 'MultiString', 'S-1-5-18', 'validate'):
        assert part in t, part
    assert f"$Version = '{VERSION}'" in t and f"[string]$Url = '{BASE}'" in t


def run_a_while(binary, tmp_path, text, seconds=4):
    """Start the real collector, let it build its pipelines, stop it, and return what it logged."""
    f = tmp_path / 'run.yaml'
    f.write_text(text.replace(cc.QUEUE_DIRS['linux'], str(tmp_path / 'queue')), encoding='utf-8')
    p = subprocess.Popen([binary, f'--config={f}'], env=dict(os.environ, MONISHIELD_COLLECTOR_KEY='dummy-key-for-run'), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try: out, _ = p.communicate(timeout=seconds)
    except subprocess.TimeoutExpired:
        p.terminate()
        out, _ = p.communicate(timeout=30)
    return out


@pytest.mark.skipif(not otelcol(), reason='run tools/fetch_otelcol.py to download otelcol-contrib')
def test_real_collector_logs_no_deprecated_component_names(tmp_path):
    # `validate` accepts the old aliases silently; only a real start logs '"x" alias is deprecated'.
    out = run_a_while(otelcol(), tmp_path, build('linux', dict(files=FILES[:1], journald=False, units=[], host_metrics=True)))
    assert 'Everything is ready' in out, out
    assert 'deprecated' not in out, out
    win = run_a_while(otelcol(), tmp_path, build('windows', dict(files=[], channels=['application'], host_metrics=False)))
    assert 'deprecated' not in win and 'only supported on Windows' in win, win


@pytest.mark.skipif(not shutil.which('sh'), reason='sh needed')
def test_upgrade_tells_docker_from_the_new_config_and_an_old_one():
    # install.sh --upgrade decides by this pattern; a config written with the old component names must be recognised the same way
    script = open(os.path.join(ROOT, 'monishield', 'infrastructure', 'assets', 'collector', 'install.sh'), encoding='utf-8').read()
    pattern = re.search(r"grep -qE '([^']+)' \"\$\{WORK\}/config.yaml\"", script).group(1)
    old = '  docker_stats:\n    endpoint: "unix:///var/run/docker.sock"\n  filelog/docker:\n    include:\n      - "/var/lib/otelcol-contrib/containers/*.log"\nexporters:\n  otlphttp/monishield: {}\n'
    new = build('docker', dict(files=[], journald=False, units=[], containers=True, host_metrics=False, container_metrics=True))
    plain = build('linux', dict(files=FILES[:1], journald=False, units=[], host_metrics=True))
    for text, want in ((old, True), (new, True), (plain, False)):
        r = subprocess.run(['grep', '-qE', pattern], input=text, text=True)
        assert (r.returncode == 0) == want
