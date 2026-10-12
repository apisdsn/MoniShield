"""FastAPI application: ONE process owns DuckDB (TRD K1), login + roles, security headers, static files.

Run with a single worker only: more than one worker = more than one DuckDB writer process.
"""
import contextlib, dataclasses, os

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.routing import APIRoute
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from monishield import __version__
from monishield.application import account_service, alert_service, import_service, ingest_service, kafka_service, password_service, retention_service, settings_service
from monishield.domain import detect
from monishield.infrastructure import auth as authmod, config, db, envfile, importer, inbox, kafka_client, letter, logfolders, mailer, notify_channels, refdata, uploads, warehouse, wirecrypto
from monishield.domain.errors import Fail
from monishield.interfaces.api import admin, config_api, docs, kafka, meta, notify, pages, session, upload, users, wire as payload
from .common import ROLE_DEPS

WORKERS = 1  # a constant, not configuration (TRD §7.2)
CSP = ("default-src 'self'; img-src 'self' data: blob:; worker-src 'self' blob:; style-src 'self' 'unsafe-inline'; "
       "object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'")
HEADERS = {'Content-Security-Policy': CSP, 'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'no-referrer', 'X-Frame-Options': 'DENY'}
ROUTERS = (meta.router, session.router, payload.router, users.router, admin.router, upload.router, docs.router, notify.router, config_api.router, kafka.router, pages.router)


def _deps(dependant):
    for d in dependant.dependencies:
        yield d.call
        yield from _deps(d)


def check_roles(routers):
    """Secure by default: every route must declare a role; otherwise the app refuses to start (TRD §8.3).

    Checked on the routers (not app.routes): FastAPI stores included routers lazily.
    """
    routes = [r for router in routers for r in router.routes]
    bare = [f'{sorted(r.methods)} {r.path}' for r in routes if not isinstance(r, APIRoute) or not set(_deps(r.dependant)) & set(ROLE_DEPS)]
    if bare: raise RuntimeError(f'routes without a role declaration: {bare}')
    return routes


def wire(state, cfg, env_path):
    """Composition root: infrastructure adapters + application services on `state` (= the services' ctx; see
    monishield/application/ports.py). The DuckDB connection (state.con) and accounts (state.auth) are opened at server start."""
    state.cfg, state.settings_pending, state.snapshot_error = cfg, [], None
    state.env = envfile.EnvStore(env_path)
    state.warehouse = warehouse.DuckWarehouse(state)
    state.logfolders = logfolders.LogFolders(cfg)
    state.s3 = importer.S3Gateway(cfg)
    state.channels = notify_channels.Channels()
    state.mailer = mailer.Mailer(cfg)
    state.kafka_client = kafka_client.KafkaClient()
    state.inbox = inbox.Spool
    state.uploads = uploads.Uploads(cfg)
    state.maxmind = refdata.probe_maxmind
    state.wire = wirecrypto.WireCrypto(ttl_hours=cfg.session_max_hours)
    state.ingest = ingest_service.IngestService(state)
    state.imports = import_service.ImportService(state)
    state.alerts = alert_service.Notifier(state)
    state.kafka = kafka_service.KafkaFeed(state)
    state.retention = retention_service.RetentionService(state)
    state.resets = password_service.PasswordResets(state)
    state.emails = account_service.EmailChanges(state)
    return state


def _error(status, code, message): return JSONResponse(dict(error=dict(code=code, message=message)), status_code=status)


def create_app(cfg=None, env_path=None):
    """env_path = the .env file written by the Configuration page. Default: v2/.env when the configuration is read here; when
    the caller passes `cfg` (tests, embedding) without env_path, it is written next to its state_dir so v2/.env is untouched."""
    loaded = cfg is None
    cfg = dataclasses.replace(cfg or config.load())   # own copy: values from the page are applied to this object
    env_path = env_path or (config.DOTENV if loaded else os.path.join(cfg.state_dir, '.env'))

    @contextlib.asynccontextmanager
    async def lifespan(app):
        os.makedirs(cfg.state_dir, exist_ok=True)
        app.state.con = db.open(cfg.db_path)
        if len(cfg.jwt_secret) < authmod.JWT_SECRET_MIN:
            raise RuntimeError(f'S4_JWT_SECRET is required (at least {authmod.JWT_SECRET_MIN} random characters); see .env.example')
        app.state.auth = authmod.Auth(cfg.auth_url, cfg.jwt_secret, cfg.session_idle_minutes, cfg.session_max_hours)
        app.state.auth.bootstrap_admin(cfg.admin_user, cfg.admin_password)
        settings_service.migrate(app.state)   # old settings in the account database -> .env (once)
        app.state.ingest.snapshot(missing_only=True)   # DbGate gets a copy right away, without waiting for ingest
        if cfg.ingest_on_start: app.state.ingest.start(by='(server start)')
        app.state.imports.start_watch()
        app.state.alerts.start()
        app.state.kafka.start()   # logs from Kafka (when S4_KAFKA_BROKERS + S4_KAFKA_TOPIC are set)
        app.state.retention.start()   # daily cleanup when S4_RETENTION_DAYS / S4_RETENTION_INBOX_DAYS are set
        yield
        app.state.retention.stop()
        app.state.imports.stop_watch()
        app.state.alerts.stop()
        app.state.kafka.stop()
        app.state.imports.wait(timeout=600)
        app.state.ingest.wait(timeout=600)
        app.state.auth.close()
        app.state.con.close()

    app = FastAPI(title='MoniShield', version=__version__, lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    wire(app.state, cfg, env_path)
    detect.use(cfg)   # CRS paranoia level for derive via the API (Stage 21)
    check_roles(ROUTERS)
    for r in ROUTERS: app.include_router(r)

    @app.middleware('http')
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        for k, v in HEADERS.items(): response.headers.setdefault(k, v)
        if request.url.path.startswith('/api'): response.headers.setdefault('Cache-Control', 'no-store')
        return response

    app.add_middleware(payload.PayloadCrypto, state=app.state)   # encrypted bodies for the web UI (X-MS-Enc)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request, exc):
        d = exc.detail if isinstance(exc.detail, dict) else dict(code={404: 'not_found', 405: 'method_not_allowed'}.get(exc.status_code, 'error'), message=str(exc.detail))
        return _error(exc.status_code, d['code'], d['message'])

    @app.exception_handler(Fail)
    async def domain_error(request, exc):   # domain/application errors (accounts, queries, import, …) -> the same JSON as ApiError
        # an outside service failed (S3, Kafka, MaxMind, mail server): 424, not 502/504, because Cloudflare and other
        # proxies replace a 502/504 answer with their own error page and the real message never reaches the screen
        return _error(424 if exc.status in (502, 504) else exc.status, exc.code, exc.message)

    @app.exception_handler(RequestValidationError)
    async def bad_request(request, exc):  # input values are not echoed back
        fields = ', '.join(sorted({str(e['loc'][-1]) for e in exc.errors()}))
        return _error(400, 'invalid_parameter', f'Invalid parameter: {fields}.')

    @app.get('/mail-logo.png', include_in_schema=False)
    def mail_logo():   # public: the logo in emails (monishield/infrastructure/letter.py), no data
        return FileResponse(letter.LOGO, media_type='image/png', headers={'Cache-Control': 'public, max-age=86400'})

    # Static files: map (built by ingest) and the built web app. No log data; data only goes through /api.
    os.makedirs(os.path.join(cfg.data_dir, 'map'), exist_ok=True)
    app.mount('/map', StaticFiles(directory=os.path.join(cfg.data_dir, 'map')), name='map')
    dist = os.path.join(config.V2_DIR, 'web', 'dist')
    if os.path.isdir(dist): app.mount('/', StaticFiles(directory=dist, html=True), name='web')
    return app
