"""Aplikasi FastAPI: SATU proses pemilik DuckDB (TRD K1), login + peran, header keamanan, berkas statis.

Jalankan dengan satu worker saja: lebih dari satu worker = lebih dari satu proses penulis DuckDB.
"""
import contextlib, os

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from .. import __version__, auth as authmod, config, db, detect, upload as uploadmod
from . import (admin, availability, business, command, ips, map, meta, overview, pods, rootcause, security, service, session, tables, tracing,
               search, trends, upload, users)
from .common import ROLE_DEPS

WORKERS = 1  # konstanta, bukan konfigurasi (TRD §7.2)
CSP = ("default-src 'self'; img-src 'self' data: blob:; worker-src 'self' blob:; style-src 'self' 'unsafe-inline'; "
       "object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'")
HEADERS = {'Content-Security-Policy': CSP, 'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'no-referrer', 'X-Frame-Options': 'DENY'}
PAGES = (overview, command, ips, search, map, trends, security, rootcause, availability, pods, business, tracing, service)   # satu modul per halaman (TRD §5.3)
ROUTERS = (meta.router, session.router, users.router, admin.router, upload.router, *(m.router for m in PAGES), tables.router)


def _deps(dependant):
    for d in dependant.dependencies:
        yield d.call
        yield from _deps(d)


def check_roles(routers):
    """Aman secara bawaan: setiap rute harus mendeklarasikan peran; kalau tidak, aplikasi menolak mulai (TRD §8.3).

    Diperiksa pada router (bukan app.routes): FastAPI menyimpan router yang disertakan secara malas.
    """
    routes = [r for router in routers for r in router.routes]
    bare = [f'{sorted(r.methods)} {r.path}' for r in routes if not isinstance(r, APIRoute) or not set(_deps(r.dependant)) & set(ROLE_DEPS)]
    if bare: raise RuntimeError(f'rute tanpa deklarasi peran: {bare}')
    return routes


def _error(status, code, message): return JSONResponse(dict(error=dict(code=code, message=message)), status_code=status)


def create_app(cfg=None):
    cfg = cfg or config.load()

    @contextlib.asynccontextmanager
    async def lifespan(app):
        os.makedirs(cfg.state_dir, exist_ok=True)
        app.state.con = db.open(cfg.db_path)
        if len(cfg.jwt_secret) < authmod.JWT_SECRET_MIN:
            raise RuntimeError(f'S4_JWT_SECRET wajib diisi (minimal {authmod.JWT_SECRET_MIN} karakter acak); lihat .env.example')
        app.state.auth = authmod.Auth(cfg.auth_url, cfg.jwt_secret, cfg.session_idle_minutes, cfg.session_max_hours)
        app.state.auth.bootstrap_admin(cfg.admin_user, cfg.admin_password)
        if cfg.duckdb_snapshot and not os.path.exists(db.snapshot_path(cfg)):   # DbGate langsung punya salinan, tanpa menunggu ingest
            cur = app.state.con.cursor()
            try: admin._snapshot(app, cur)
            finally: cur.close()
        if cfg.ingest_on_start: app.state.ingest.start(by='(mulai server)')
        app.state.imports.start_watch()
        yield
        app.state.imports.stop_watch()
        app.state.imports.wait(timeout=600)
        app.state.ingest.wait(timeout=600)
        app.state.auth.close()
        app.state.con.close()

    app = FastAPI(title='MoniShield', version=__version__, lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.cfg = cfg
    detect.use(cfg)   # tingkat paranoia CRS untuk derive lewat API (Tahap 21)
    app.state.ingest = admin.IngestManager(app)
    app.state.imports = admin.ImportManager(app)
    app.state.uploads = uploadmod.Uploads(cfg)
    check_roles(ROUTERS)
    for r in ROUTERS: app.include_router(r)

    @app.middleware('http')
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        for k, v in HEADERS.items(): response.headers.setdefault(k, v)
        if request.url.path.startswith('/api'): response.headers.setdefault('Cache-Control', 'no-store')
        return response

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request, exc):
        d = exc.detail if isinstance(exc.detail, dict) else dict(code={404: 'not_found', 405: 'method_not_allowed'}.get(exc.status_code, 'error'), message=str(exc.detail))
        return _error(exc.status_code, d['code'], d['message'])

    @app.exception_handler(authmod.AuthError)
    async def auth_error(request, exc): return _error(exc.status, exc.code, exc.message)

    @app.exception_handler(RequestValidationError)
    async def bad_request(request, exc):  # nilai masukan tidak dipantulkan kembali
        fields = ', '.join(sorted({str(e['loc'][-1]) for e in exc.errors()}))
        return _error(400, 'invalid_parameter', f'Parameter tidak sah: {fields}.')

    # Berkas statis: peta (dibuat ingest) dan aplikasi web hasil build. Tidak memuat data log; data hanya lewat /api.
    os.makedirs(os.path.join(cfg.data_dir, 'map'), exist_ok=True)
    app.mount('/map', StaticFiles(directory=os.path.join(cfg.data_dir, 'map')), name='map')
    dist = os.path.join(config.V2_DIR, 'web', 'dist')
    if os.path.isdir(dist): app.mount('/', StaticFiles(directory=dist, html=True), name='web')
    return app
