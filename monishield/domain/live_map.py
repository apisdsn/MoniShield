"""Live map from access lines (Stage 57): which client address and module an access line stands for.

The address is only used to look up coordinates in memory; the live stream carries coordinates, counts and the module (docs/12-collector.md,
"Live map"). Pure: standard library only. Lines are read with the reader of the service's http rule (domain/formats.py); the two
legacy http presets (ingress-nginx, nginx-frontend) have their own readers in domain/parse.py and are handled here.
"""
import re

from . import formats, rules

UPSTREAM = re.compile(r'\[([^\]]*)\] \[')   # ingress-nginx: [namespace-service-port] [upstream address]


def line_reader(rule, prefix=''):
    """Rule of kind http -> function(line) -> (client address, module or None), or None when the line is no access line.
    None for a rule that cannot name a client (an app rule, a format without a reader)."""
    if rule is None or rule.kind != 'http': return None
    if rule.format == 'ingress-nginx':
        def nginx(line):
            ip = line.split(' ', 1)[0]
            if not rules.NGINX.match(line) or not ip: return None
            return ip, (UPSTREAM.search(line) or [None, ''])[1].replace(prefix, '') or None
        return nginx
    if rule.format == 'nginx-frontend':
        def frontend(line):
            m = rules.FE.match(line)
            return (m[8].strip(), None) if m else None
        return frontend
    try: read = formats.reader(rule)
    except ValueError: return None   # `auto` and the like: no reader to take the client from

    def common(line):
        d = read(line)
        return (d['ip'], d.get('upstream')) if d and d.get('ip') else None
    return common
