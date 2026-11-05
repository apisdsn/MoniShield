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
