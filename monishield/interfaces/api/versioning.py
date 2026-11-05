"""API versions (docs/08-architecture.md, "API versions"): every endpoint lives under /api/v1; only /api/health (healthcheck, deploy
script), /collector/install.* (downloads), the page routes and static files have no version.

For ONE release the browser API also answers its old unversioned address, so a tab that was left open during the deploy keeps working
until it reloads: `/api/<x>` is rewritten to `/api/v1/<x>` and the answer carries `Deprecation: true` (and a `Link` to the new
address). The collector machine API is NOT aliased: the old `/api/collector/...` addresses answer 404 (a collector is updated with
`install.sh --upgrade`, which already uses the new ones). The wire encryption of an old tab was sealed with the address it sent, so the
address as sent is kept in `scope['sent_path']` and the encryption uses that one (interfaces/api/wire.py). Remove this module and
its line in app.py in the next release ("Next" in docs/09-status.md)."""
API = '/api/v1'
UNVERSIONED = ('/api/health',)             # operational endpoints
NOT_ALIASED = ('/api/collector/',)         # the machine API of collectors


def successor(path):
    """The versioned address an old browser path moves to, or None when the path is not aliased (already versioned, operational,
    the collector machine API, or not an API path at all)."""
    if not path.startswith('/api/') or path.startswith(API + '/') or path in UNVERSIONED or path.startswith(NOT_ALIASED): return None
    return API + path[len('/api'):]


class OldPathAlias:
    """ASGI middleware, outermost (before the wire middleware): rewrites an old browser path and marks the answer deprecated."""

    def __init__(self, app): self.app = app

    async def __call__(self, scope, receive, send):
        new = successor(scope['path']) if scope['type'] == 'http' else None
        if new is None: return await self.app(scope, receive, send)
        scope = dict(scope, sent_path=scope['path'], path=new, raw_path=new.encode())

        async def send_marked(msg):
            if msg['type'] == 'http.response.start':
                msg = dict(msg, headers=[*msg.get('headers', []), (b'deprecation', b'true'),
                                         (b'link', f'<{new}>; rel="successor-version"'.encode())])
            await send(msg)
        await self.app(scope, receive, send_marked)
