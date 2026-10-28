"""The visitor's address behind a proxy and behind Cloudflare (domain/client_address.py, interfaces/api/common.client_ip)."""
import dataclasses, types

import pytest
from starlette.requests import Request

from monishield.domain import client_address as ca
from monishield.infrastructure import config
from monishield.interfaces.api import common

CF_EDGE, VISITOR, ATTACKER = '162.158.163.115', '203.0.113.7', '198.51.100.9'


def test_cloudflare_header_only_from_cloudflare_addresses():
    assert ca.real_client(CF_EDGE, VISITOR, True) == VISITOR
    assert ca.real_client('2606:4700::1', '2001:db8::5', True) == '2001:db8::5'
    assert ca.real_client(ATTACKER, VISITOR, True) == ATTACKER          # sent straight to the server: header ignored
    assert ca.real_client(CF_EDGE, VISITOR, False) == CF_EDGE           # switched off
    assert ca.real_client(CF_EDGE, 'not-an-ip', True) == CF_EDGE        # junk header
    assert ca.real_client(CF_EDGE, None, True) == CF_EDGE
    assert ca.real_client(None, VISITOR, True) is None
    assert ca.real_client('10.0.0.5', VISITOR, True, '10.0.0.0/8') == VISITOR   # own range list


def request(cfg, headers, peer='172.18.0.5'):
    scope = dict(type='http', method='GET', path='/', headers=[(k.lower().encode(), v.encode()) for k, v in headers.items()],
                 client=(peer, 1234), app=types.SimpleNamespace(state=types.SimpleNamespace(cfg=cfg)))
    return Request(scope)


def test_client_ip_behind_caddy_and_cloudflare():
    cfg = dataclasses.replace(config.Config(), trust_proxy=True, trust_cloudflare=True)
    # Caddy appends the address it saw (the Cloudflare server) as the LAST X-Forwarded-For entry
    assert common.client_ip(request(cfg, {'X-Forwarded-For': f'{VISITOR}, {CF_EDGE}', 'CF-Connecting-IP': VISITOR})) == VISITOR
    # someone bypassing Cloudflare forges both headers: the last hop is their own address, so the header is not believed
    assert common.client_ip(request(cfg, {'X-Forwarded-For': f'{VISITOR}, {ATTACKER}', 'CF-Connecting-IP': VISITOR})) == ATTACKER
    off = dataclasses.replace(cfg, trust_cloudflare=False)
    assert common.client_ip(request(off, {'X-Forwarded-For': CF_EDGE, 'CF-Connecting-IP': VISITOR})) == CF_EDGE
    direct = dataclasses.replace(cfg, trust_proxy=False)          # no proxy: the socket peer
    assert common.client_ip(request(direct, {'CF-Connecting-IP': VISITOR}, peer=CF_EDGE)) == VISITOR
    assert common.client_ip(request(direct, {'CF-Connecting-IP': VISITOR}, peer=ATTACKER)) == ATTACKER


def test_cloudflare_settings_from_env():
    c = config.load(env={'S4_TRUST_CLOUDFLARE': 'true', 'S4_CLOUDFLARE_IPS': ''}, dotenv=False)
    assert c.trust_cloudflare and c.cloudflare_ips == ca.CLOUDFLARE_IPS     # empty = the built-in list
    assert config.load(env={'S4_CLOUDFLARE_IPS': '10.0.0.0/8, 192.0.2.0/24'}, dotenv=False).cloudflare_ips == '10.0.0.0/8, 192.0.2.0/24'
    with pytest.raises(SystemExit, match='S4_CLOUDFLARE_IPS'): config.load(env={'S4_CLOUDFLARE_IPS': '10.0.0.0/33'}, dotenv=False)
