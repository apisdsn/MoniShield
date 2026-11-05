"""Servers page (docs/13-metrics.md): what the collectors report about servers and containers. Read only, for every signed-in
user like the Pods page. Host and container names and numbers are not personal data, so these are plain GET reads.

  GET /api/v1/servers?range=1h|24h|7d|30d            servers with their current values, unusual values, disks that are almost full
  GET /api/v1/servers/host?cid=&host=&range=         the charts of one server and its containers
"""
import datetime, re

from fastapi import APIRouter, Depends, Query, Request

from monishield.domain import kafka_message
from monishield.infrastructure.queries import servers as q_servers
from .common import ApiError, require_user_ready

router = APIRouter(prefix='/api/v1', dependencies=[Depends(require_user_ready)])


def _now(): return datetime.datetime.now(datetime.timezone.utc)


def _range(value):
    if value not in q_servers.RANGES: raise ApiError(400, 'invalid_parameter', 'range must be 1h, 24h, 7d or 30d.')
    return value


def _collectors(request):
    """The registered collectors that can have metrics (not one that is waiting for its first contact)."""
    return [c for c in request.app.state.collectors.list() if c['status'] != 'waiting']


@router.get('/servers')
def servers(request: Request, range: str = Query('24h')):
    rng = _range(range)
    cur = request.app.state.metrics.cursor()
    try: return q_servers.overview(cur, _collectors(request), _now(), rng)
    finally: cur.close()


@router.get('/servers/host')
def server(request: Request, cid: int = Query(..., ge=1), host: str = Query(..., max_length=253), range: str = Query('24h')):
    rng = _range(range)
    if not kafka_message.NAME.fullmatch(host): raise ApiError(404, 'not_found', 'Server not found.')
    collector = next((c for c in _collectors(request) if c['id'] == cid), None)
    if not collector: raise ApiError(404, 'not_found', 'Server not found.')
    cur = request.app.state.metrics.cursor()
    try: out = q_servers.host(cur, collector, host, _now(), rng)
    finally: cur.close()
    if out is None: raise ApiError(404, 'not_found', 'Server not found.')
    return out
