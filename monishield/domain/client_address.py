"""The address of the person behind a request (audit log, login limits per IP).

Behind Cloudflare the address our own proxy sees is a Cloudflare server, shared by many visitors; the visitor's own
address is in the `CF-Connecting-IP` header. That header is believed ONLY when the request really came from a Cloudflare
address (S4_CLOUDFLARE_IPS), because anyone who reaches the server directly can send it. Pure: no third-party imports.
"""
import functools, ipaddress

# Cloudflare's published ranges (https://www.cloudflare.com/ips/); S4_CLOUDFLARE_IPS overrides them.
CLOUDFLARE_IPS = ('173.245.48.0/20,103.21.244.0/22,103.22.200.0/22,103.31.4.0/22,141.101.64.0/18,108.162.192.0/18,'
                  '190.93.240.0/20,188.114.96.0/20,197.234.240.0/22,198.41.128.0/17,162.158.0.0/15,104.16.0.0/13,'
                  '104.24.0.0/14,172.64.0.0/13,131.0.72.0/22,2400:cb00::/32,2606:4700::/32,2803:f800::/32,2405:b500::/32,'
                  '2405:8100::/32,2a06:98c0::/29,2c0f:f248::/32')


@functools.lru_cache(maxsize=8)
def networks(text):
    """'cidr, cidr, …' -> tuple of networks. ValueError on a bad entry."""
    return tuple(ipaddress.ip_network(x.strip(), strict=False) for x in text.split(',') if x.strip())


def _ip(text):
    try: return ipaddress.ip_address((text or '').strip())
    except ValueError: return None


def real_client(peer, cf_connecting_ip, trust_cloudflare, ranges=CLOUDFLARE_IPS):
    """peer = the address our own proxy saw (or the socket peer without a proxy). -> the visitor's address as text."""
    if not trust_cloudflare: return peer
    p, c = _ip(peer), _ip(cf_connecting_ip)
    if p is None or c is None: return peer
    return str(c) if any(p in n for n in networks(ranges)) else peer
