"""Servers page (docs/13-metrics.md): what the collectors report about servers and containers. Read only, for every signed-in
user like the Pods page. The names of the servers and containers are site data, so the reads are POST: their parameters travel in the JSON body, which
the web UI encrypts (interfaces/api/wire.py), and no host name stands in a URL, a proxy log or the network panel.

  POST /api/v1/servers        {range: 1h|24h|7d|30d}          servers with their current values, unusual values, disks that are almost full
  POST /api/v1/servers/host   {cid, host, range}              the charts of one server and its containers
"""
import datetime, re

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

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


class RangeBody(BaseModel):
    range: str = '24h'


class HostBody(RangeBody):
    cid: int = Field(ge=1)
    host: str = Field(max_length=253)


@router.post('/servers')
def servers(request: Request, body: RangeBody = RangeBody()):
    rng = _range(body.range)
    cur = request.app.state.metrics.cursor()
    try: return q_servers.overview(cur, _collectors(request), _now(), rng)
    finally: cur.close()


@router.post('/servers/host')
def server(request: Request, body: HostBody):
    cid, host, rng = body.cid, body.host, _range(body.range)
    if not kafka_message.NAME.fullmatch(host): raise ApiError(404, 'not_found', 'Server not found.')
    collector = next((c for c in _collectors(request) if c['id'] == cid), None)
    if not collector: raise ApiError(404, 'not_found', 'Server not found.')
    cur = request.app.state.metrics.cursor()
    try: out = q_servers.host(cur, collector, host, _now(), rng)
    finally: cur.close()
    if out is None: raise ApiError(404, 'not_found', 'Server not found.')
    return out
