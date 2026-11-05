"""The Caddy origin guard is generated from the one list of Cloudflare ranges (tools/cloudflare_ips.py)."""
import importlib.util, os

from monishield.domain import client_address

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_guard_snippet_matches_the_range_list():
    spec = importlib.util.spec_from_file_location('cloudflare_ips', os.path.join(ROOT, 'tools', 'cloudflare_ips.py'))
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    committed = open(os.path.join(ROOT, 'deploy', 'caddy', 'cloudflare-only.caddy'), encoding='utf-8').read()
    assert committed == mod.snippet(client_address.CLOUDFLARE_IPS), 'run: python tools/cloudflare_ips.py'
    assert mod.python_literal(client_address.CLOUDFLARE_IPS).count("'") >= 2


def test_entrypoint_and_caddyfile_import_the_generated_folders():
    cf = open(os.path.join(ROOT, 'deploy', 'Caddyfile.letsencrypt'), encoding='utf-8').read()
    assert 'import /etc/caddy/generated/*.caddy' in cf and 'import /etc/caddy/generated/main/*.caddy' in cf


def _generate(tmp_path, name, **env):
    import subprocess
    src, out = os.path.join(ROOT, 'deploy', 'caddy'), tmp_path / name / 'generated'
    full = dict(os.environ, DOCKER_DOMAIN='m.example.com', DOCKER_ACME_EMAIL='a@example.com', CADDY_SRC=src, CADDY_OUT=str(out), PATH=os.environ['PATH'])
    full.pop('DOCKER_ACCESS_LOG', None)
    full.update(env)
    fake = tmp_path / name / 'bin'; fake.mkdir(parents=True)
    (fake / 'caddy').write_text('#!/bin/sh\nexit 0\n'); (fake / 'caddy').chmod(0o755)   # entrypoint ends with `exec caddy`
    full['PATH'] = f'{fake}:{full["PATH"]}'
    subprocess.run(['sh', os.path.join(src, 'entrypoint.sh'), 'run'], env=full, check=True, capture_output=True)
    return out


def test_trusted_proxies_snippet_matches_the_range_list():
    spec = importlib.util.spec_from_file_location('cloudflare_ips', os.path.join(ROOT, 'tools', 'cloudflare_ips.py'))
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    committed = open(os.path.join(ROOT, 'deploy', 'caddy', 'trusted-proxies.caddy'), encoding='utf-8').read()
    assert committed == mod.trusted_snippet(client_address.CLOUDFLARE_IPS), 'run: python tools/cloudflare_ips.py'
    assert 'client_ip_headers Cf-Connecting-Ip' in committed and 'trusted_proxies static 173.245.48.0/20 ' in committed


def test_access_log_snippet_removes_secrets_and_keeps_agent_and_referer():
    text = open(os.path.join(ROOT, 'deploy', 'caddy', 'access-log.caddy'), encoding='utf-8').read()
    for gone in ('request>headers>Cookie', 'request>headers>Authorization', 'request>headers>Proxy-Authorization',
                 'request>headers>X-Ms-Enc', 'resp_headers', 'request>tls'):
        assert f'{gone} delete' in text
    assert 'output stdout' in text and 'wrap json' in text
    code = '\n'.join(l for l in text.splitlines() if not l.lstrip().startswith('#'))
    assert 'User-Agent' not in code and 'Referer' not in code   # not deleted
    cf = open(os.path.join(ROOT, 'deploy', 'Caddyfile.letsencrypt'), encoding='utf-8').read()
    assert 'import /etc/caddy/generated/global/*.caddy' in cf.split('{$DOCKER_DOMAIN}')[0]   # inside the global options


def test_entrypoint_writes_the_access_log_unless_turned_off(tmp_path):
    out = _generate(tmp_path, 'on')
    assert (out / 'main' / 'access-log.caddy').is_file() and (out / 'global' / 'trusted-proxies.caddy').is_file()
    out = _generate(tmp_path, 'one', DOCKER_ACCESS_LOG='1')
    assert (out / 'main' / 'access-log.caddy').is_file()
    out = _generate(tmp_path, 'off', DOCKER_ACCESS_LOG='0')
    assert not (out / 'main' / 'access-log.caddy').exists() and not (out / 'global' / 'trusted-proxies.caddy').exists()


def test_ingest_site_has_no_access_log():
    text = open(os.path.join(ROOT, 'deploy', 'caddy', 'ingest.caddy'), encoding='utf-8').read()
    assert not any(l.strip().startswith('log') for l in text.splitlines())
