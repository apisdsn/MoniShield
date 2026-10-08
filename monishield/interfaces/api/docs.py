"""Interactive API documentation (owner request 2026-10-07): Swagger UI at /api/docs and the schema at /api/openapi.json.
Only for users signed in through the same login page (session cookie) who have changed their initial password; not
signed in -> redirected to the login page and then back here. "Try it out" uses that session, so every route still obeys
its role (a regular user sees admin routes but gets 403). Swagger UI assets come from our own server (CSP 'self')."""
from fastapi import APIRouter, Depends, Request
from fastapi.openapi.utils import get_openapi
from fastapi.responses import HTMLResponse, RedirectResponse

from monishield import __version__
from .common import ApiError, public, require_user, require_user_ready

router = APIRouter(prefix='/api')

DESCRIPTION = """MoniShield log and security dashboard. All times are UTC unless stated otherwise; log folder = WIB date (YYYY-MM-DD).

**Sign in**: open the MoniShield login page with the same account; this page uses the session cookie automatically.
Requests that change data (POST/PUT/PATCH/DELETE) must carry the `X-Requested-With` header (added automatically
here). The **machine token** (`S4_JOB_TOKEN`) only works for the ingest and import routes: *Authorize* button → `jobToken`.

Roles: `admin` for the `/api/admin/*` routes, otherwise any signed-in user. Errors always have the form
`{"error": {"code": "...", "message": "..."}}`."""

# Swagger groups by whole-segment path prefix (first match wins; /api/me is not /api/meta); order = display order
TAGS = [('/api/auth', 'Sign-in & session'), ('/api/me', 'Sign-in & session'), ('/api/admin/users', 'Users (admin)'),
        ('/api/admin/import', 'S3 import & sync (admin)'), ('/api/admin/upload', 'Folder upload (admin)'),
        ('/api/admin/kafka', 'Kafka (admin)'), ('/api/live', 'Realtime (Kafka)'),
        ('/api/admin', 'Ingest, folder & audit (admin)'), ('/api/folders/{folder}/tables', 'Tables'),
        ('/api/folders', 'Folder pages'), ('/api', 'General')]

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>API · MoniShield</title><link rel="icon" href="/favicon.svg"><link rel="stylesheet" href="/swagger/swagger-ui.css">
<style>body{margin:0}.topbar{display:none}.mshead{display:flex;align-items:center;gap:12px;padding:12px 20px;background:#0b1015;color:#e6edf3;font:600 15px system-ui,sans-serif}
.mshead a{color:#2dd4bf;margin-left:auto;font-weight:500;text-decoration:none}</style></head>
<body><div class="mshead"><svg width="26" height="26" viewBox="0 0 32 32" aria-hidden="true"><path d="M16 2l12 4.5v8.2c0 7.3-5 13.4-12 15.3C9 28.1 4 22 4 14.7V6.5z" fill="#2dd4bf"/>
<path d="M10 21V11l6 6 6-6v10" fill="none" stroke="#04201c" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/></svg>MoniShield API<a href="/">&larr; Dashboard</a></div><div id="swagger-ui"></div>
<script src="/swagger/swagger-ui-bundle.js"></script><script src="/swagger/init.js"></script></body></html>"""


def schema(app):
    """OpenAPI schema with the sign-in methods MoniShield uses (built once, stored on the app)."""
    if not getattr(app.state, 'openapi', None):
        s = get_openapi(title='MoniShield API', version=__version__, description=DESCRIPTION, routes=app.routes)
        s.setdefault('components', {})['securitySchemes'] = {
            'session': {'type': 'apiKey', 'in': 'cookie', 'name': 's4_session', 'description': 'Cookie from the login page (automatic).'},
            'jobToken': {'type': 'http', 'scheme': 'bearer', 'description': 'S4_JOB_TOKEN, only for ingest/import routes.'}}
        s['security'] = [{'session': []}]
        for path, ops in s.get('paths', {}).items():
            for op in ops.values():
                if isinstance(op, dict): op['tags'] = [next(t for pre, t in TAGS if path == pre or path.startswith(pre + '/'))]
        s['tags'] = [dict(name=t) for t in dict.fromkeys(t for _, t in TAGS)]
        app.state.openapi = s
    return app.state.openapi


@router.get('/docs', include_in_schema=False, dependencies=[Depends(public)])
def docs(request: Request):
    """Not signed in / initial password not changed -> login page with ?next=/api/docs (the SPA returns here afterwards)."""
    try: require_user_ready(require_user(request))
    except ApiError: return RedirectResponse('/?next=/api/docs', status_code=303)
    return HTMLResponse(PAGE, headers={'Cache-Control': 'no-store'})


@router.get('/openapi.json', include_in_schema=False)
def openapi(request: Request, user=Depends(require_user_ready)):
    return schema(request.app)
