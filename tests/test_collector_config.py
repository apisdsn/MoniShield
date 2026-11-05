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
    assert cc.normalize('linux', None) == dict(files=[], journald=True, units=[])
    assert cc.normalize('docker', None)['containers'] is True and cc.normalize('windows', None)['channels'] == ['application', 'system']
    assert cc.normalize('kubernetes', None) == {} and cc.normalize('kubernetes', {}) == {}


def test_normalize_is_canonical():
    o = cc.normalize('linux', dict(files=[dict(path=' /var/log/a.log ', service='a')], units=['ssh.service', 'ssh.service'], journald=True))
    assert o == dict(files=[dict(path='/var/log/a.log', service='a')], journald=True, units=['ssh.service'])
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
    assert '  filelog/1:\n    include:\n      - "/var/log/app/*.log"\n    start_at: "end"\n    include_file_name: true' in y
    assert '    resource:\n      service.name: "app"' in y and '      service.name: "www.nginx"' in y and '  filelog/2:' in y
    assert '  journald:\n    start_at: "end"\n    units:\n      - "ssh.service"\n      - "cron.service"' in y
    assert 'receivers:\n        - "filelog/1"\n        - "filelog/2"\n        - "journald"' in y
    assert 'directory: "/var/lib/otelcol-contrib/queue"' in y
    assert 'operators' not in y and 'regex_parser' not in y and 'json_parser' not in y     # the body stays the original line


def test_docker_uses_only_the_container_operator():
    y = build('docker', dict(containers=True, journald=False, files=[]))
    assert 'include:\n      - "/var/lib/docker/containers/*/*-json.log"' in y and 'type: "container"' in y
    assert 'container.name' in y and y.count('type:') == 2 and 'type: "add"' in y
    assert 'parser' not in y.replace('container-parser', '')


def test_windows_channels_and_files():
    y = build('windows', dict(channels=['application', 'security'], files=[dict(path='C:\\inetpub\\logs\\*.log', service='iis')]))
    assert 'windowseventlog/application:\n    channel: "application"' in y and 'windowseventlog/security:' in y and 'windowseventlog/system' not in y
    assert 'include:\n      - "C:\\\\inetpub\\\\logs\\\\*.log"' in y                      # backslashes escaped in a double quoted string
    assert 'directory: "C:\\\\ProgramData\\\\OpenTelemetry Collector\\\\queue"' in y


@pytest.mark.parametrize('platform', ['linux', 'windows', 'docker'])
def test_common_parts_and_the_key_is_never_in_the_text(platform):
    y = build(platform)
    assert 'resourcedetection:\n    detectors:\n      - "system"' in y
    assert 'send_batch_size: 500\n    send_batch_max_size: 1000\n    timeout: "5s"' in y
    for line in ('endpoint: "https://logs.example.com/api/collector"', 'encoding: "json"', 'compression: "gzip"',
                 'Authorization: "Bearer ${env:MONISHIELD_COLLECTOR_KEY}"', 'retry_on_failure:\n      enabled: true',
                 'sending_queue:\n      enabled: true\n      storage: "file_storage"', 'file_storage:\n    directory:'):
        assert line in y, line
    assert 'msk_' not in y and 'mse_' not in y
    assert 'processors:\n        - "resourcedetection"\n        - "batch"' in y


def test_batch_stays_far_below_the_receiver_limit():
    assert cc.BATCH['send_batch_max_size'] <= 1000 and cc.BATCH['send_batch_size'] <= cc.BATCH['send_batch_max_size']
    # 1000 lines cut at the receiver's 64 KB would still be under its raw limit only for ordinary lines; the cap keeps it far below
    assert cc.BATCH['send_batch_max_size'] * 4096 < Config().collector_max_raw_mb * 1024 * 1024


def test_kubernetes_values():
    y = build('kubernetes')
    for line in ('mode: "daemonset"', 'repository: "otel/opentelemetry-collector-contrib"', f'tag: "{VERSION}"', 'logsCollection:\n    enabled: true',
                 'kubernetesAttributes:\n    enabled: true', 'name: "otelcol-contrib"', 'endpoint: "https://logs.example.com/api/collector"',
                 'storage: "file_storage"', 'secretKeyRef:\n        name: "monishield-collector"\n        key: "key"', 'hostPath:', 'traces: null'):
        assert line in y, line
    assert 'msk_' not in y and 'Bearer ${env:MONISHIELD_COLLECTOR_KEY}' in y and 'filelog' not in y     # the chart's preset adds the receiver


def test_quoting_keeps_odd_values_inside_one_string():
    nasty = dict(path='/srv/a b/#x: y/{a,b}/*.log', service='svc.v1')
    y = build('linux', dict(files=[nasty], journald=False))
    assert '- "/srv/a b/#x: y/{a,b}/*.log"' in y
    assert cc.emit(dict(k='a: b # c', n=None, t=True, i=3, e=[], d={})) == ['k: "a: b # c"', 'n: null', 't: true', 'i: 3', 'e: []', 'd: {}']
    assert cc.emit([dict(a=1, b=[dict(c=2)])]) == ['- a: 1', '  b:', '    - c: 2']


def test_unknown_platform_and_bad_url():
    assert code(cc.build, 'mac', BASE, None, VERSION) == 'invalid_platform'
    assert code(cc.build, 'linux', 'nonsense', None, VERSION) == 'invalid_url'


# The real collector
def otelcol():
    path = os.path.join(ROOT, 'tools', 'otelcol', VERSION, 'otelcol-contrib')
    return path if os.access(path, os.X_OK) else None


def validate(binary, tmp_path, text):
    f = tmp_path / 'config.yaml'
    f.write_text(text, encoding='utf-8')
    r = subprocess.run([binary, 'validate', f'--config={f}'], env=dict(os.environ, MONISHIELD_COLLECTOR_KEY='dummy-key-for-validate'), capture_output=True, text=True, timeout=120)
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
    for part in (f'otelcol-contrib {VERSION}', f'{BASE}/api/collector/enroll', 'X-Requested-With: monishield-collector', '/etc/otelcol-contrib/config.yaml',
                 '(mode 0640)', 'monishield.env', '(mode 0600)', 'SHA-256', '.sha256', '/var/lib/otelcol-contrib/queue', 'enable and restart'):
        assert part in r.stdout, part
    assert 'mse_7_' not in r.stdout and 'mse_7_' not in r.stderr                                  # the token is never echoed
    r = run_sh(script, '--name', 'web-01', '--token', 'mse_7_' + 'A' * 43, '--url', 'https://other.example.org', '--dry-run')
    assert 'https://other.example.org/api/collector/enroll' in r.stdout


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
