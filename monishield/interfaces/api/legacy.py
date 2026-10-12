"""Old API paths (renamed 2026-10-12 to English REST names) keep working for one release: the path is rewritten to the
new one before routing, and the answer carries `Deprecation: true` and a `Link: <new path>; rel="successor-version"`
header (RFC 9745 / RFC 8288). Scripts and cron jobs should move to the new paths (docs/03-trd.md, CHANGELOG).
The renamed folder delete (POST .../delete -> DELETE) keeps an explicit old route in admin.py instead."""
import re

# (method or None for any, old path pattern, new path template)
RULES = [
    ('GET', re.compile(r'^/api/admin/ingest/status$'), '/api/admin/ingest'),
    (None, re.compile(r'^/api/admin/import(/.*)?$'), r'/api/admin/imports\1'),
    (None, re.compile(r'^/api/admin/upload(/.*)?$'), r'/api/admin/uploads\1'),
    ('GET', re.compile(r'^/api/folders/([^/]+)/command$'), r'/api/folders/\1/command-center'),
    ('GET', re.compile(r'^/api/folders/([^/]+)/rootcause$'), r'/api/folders/\1/root-causes'),
    (None, re.compile(r'^/api/me/email/start$'), '/api/me/email/change'),
    ('POST', re.compile(r'^/api/me/email/confirm$'), '/api/me/email/change/confirm'),
    (None, re.compile(r'^/api/admin/users/(\d+)/email$'), r'/api/admin/users/\1/email/change'),
]


def successor(method, path):
    """New path for an old one, or None."""
    for m, rx, new in RULES:
        if (m is None or m == method) and rx.match(path): return rx.sub(new, path).replace('\\1', '')
    return None


class LegacyPaths:
    """ASGI middleware: rewrites old paths (see RULES) and marks the answer as deprecated."""

    def __init__(self, app): self.app = app

    async def __call__(self, scope, receive, send):
        new = successor(scope.get('method'), scope.get('path', '')) if scope['type'] == 'http' else None
        if not new: return await self.app(scope, receive, send)
        scope = dict(scope, path=new, raw_path=new.encode())

        async def marked(message):
            if message['type'] == 'http.response.start':
                message = dict(message, headers=list(message.get('headers', [])) + [
                    (b'deprecation', b'true'), (b'link', f'<{new}>; rel="successor-version"'.encode())])
            await send(message)
        await self.app(scope, receive, marked)
