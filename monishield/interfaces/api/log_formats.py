"""Log Formats page (admin): how each service logs. The work is in monishield/application/log_format_service.py.
  GET  /api/v1/admin/log-formats             the rules in use + the services of the last 7 days of every source
  POST /api/v1/admin/log-formats/suggest     {source, namespace, service}: the format that reads the most of the service's last 200 lines
  POST /api/v1/admin/log-formats/test        {source, namespace, service, rule}: the last 5 entries read with that rule (nothing is saved)
  PUT  /api/v1/admin/log-formats             {rules: [...]}: validate, write log-formats.toml, use the rules at once
  POST /api/v1/admin/log-formats/read-today  {source}: read today's folder of the source again with the rules
Lines can hold personal data, so suggest and test are POST (the web UI sends an encrypted body); the audit log records who looked at
which service, never the lines."""
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from monishield.application import log_format_service as svc
from .admin import _audit
from .common import client_ip, require_admin

router = APIRouter(prefix='/api/v1/admin/log-formats')


@router.get('')
def get_rules(request: Request, admin=Depends(require_admin)): return svc.view(request.app.state)


class ServiceBody(BaseModel):
    source: str = 's3'
    namespace: str | None = None
    service: str


class TestBody(ServiceBody):
    rule: dict


@router.post('/suggest')
def suggest(body: ServiceBody, request: Request, admin=Depends(require_admin)):
    r = svc.suggest(request.app.state, body.source, body.namespace, body.service)
    _audit(request, admin, 'log_formats.suggest', f'source={body.source} service={body.service}')
    return r


@router.post('/test')
def test(body: TestBody, request: Request, admin=Depends(require_admin)):
    r = svc.test(request.app.state, body.source, body.namespace, body.service, body.rule)
    _audit(request, admin, 'log_formats.test', f'source={body.source} service={body.service} format={body.rule.get("format")}')
    return r


class RulesBody(BaseModel):
    rules: list[dict]


@router.put('')
def put_rules(body: RulesBody, request: Request, admin=Depends(require_admin)):
    return svc.save(request.app.state, body.rules, admin, client_ip(request))


class SourceBody(BaseModel):
    source: str = 's3'


@router.post('/read-today', status_code=202)
def read_today(body: SourceBody, request: Request, admin=Depends(require_admin)):
    return svc.read_today(request.app.state, body.source, admin, client_ip(request))
