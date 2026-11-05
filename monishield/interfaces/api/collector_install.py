"""Install scripts for collectors (docs/12-collector.md, step 5). Public: they hold no secret (the enrollment token is an
argument of the script), so a server can fetch them with curl before anything is trusted. Filled in with the pinned
otelcol-contrib version and this server's receiver address."""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import PlainTextResponse

from monishield.infrastructure import collector_scripts

from .collectors import receiver_url
from .common import public

router = APIRouter(prefix='/collector')


def _script(name, request: Request):
    text = collector_scripts.render(name, request.app.state.cfg.collector_otel_version, receiver_url(request))
    return PlainTextResponse(text, media_type=collector_scripts.SCRIPTS[name] + '; charset=utf-8',
                             headers={'Cache-Control': 'no-store', 'Content-Disposition': f'attachment; filename="{name}"'})


@router.get('/install.sh', dependencies=[Depends(public)])
def install_sh(request: Request): return _script('install.sh', request)


@router.get('/install.ps1', dependencies=[Depends(public)])
def install_ps1(request: Request): return _script('install.ps1', request)
