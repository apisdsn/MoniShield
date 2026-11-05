"""Logs from Kafka (monishield/application/kafka_service.py).
  GET  /api/v1/admin/kafka          consumer status: connected?, messages received/written/skipped per service, last 50 messages
  POST /api/v1/admin/kafka/peek     "Check messages": the LAST n messages of the topic (no consumer group; does not move the read position)
  POST /api/v1/admin/kafka/ingest   ingest now (without waiting for the S4_KAFKA_INGEST_MINUTES interval)
  GET  /api/v1/live/map             Server-Sent Events for the realtime map animation: {p: [[lat, lon, count, module], …]} per
                                 second. Location coordinates only (from the local IP database), no IP addresses. ?source=kafka (default) or
                                 ?source=collector picks the hub; 204 when that source is not running.
  GET  /api/v1/public/map           public (home page): coarse request origins, live (last minute) or of the newest folder;
                                 cells of ~55 km, no IP addresses (monishield/domain/public_map.py). {enabled: false} when turned off.
"""
import asyncio, json

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel

from monishield.application import sources
from monishield.domain.errors import Fail
from .admin import _audit
from .common import public, require_admin, require_user_ready

router = APIRouter()


@router.get('/api/v1/admin/kafka')
def kafka_status(request: Request, admin=Depends(require_admin)):
    return request.app.state.kafka.status()


class PeekBody(BaseModel):
    n: int = 10


@router.post('/api/v1/admin/kafka/peek')
def kafka_peek(request: Request, body: PeekBody = PeekBody(), admin=Depends(require_admin)):
    try: r = request.app.state.kafka.peek(max(1, min(50, body.n)))
    except Fail as e:
        _audit(request, admin, 'kafka.peek', f'failed ({e.code})'); raise
    _audit(request, admin, 'kafka.peek', f"{r['topic']}: {len(r['messages'])} messages")
    return r


@router.post('/api/v1/admin/kafka/ingest')
def kafka_ingest(request: Request, admin=Depends(require_admin)):
    request.app.state.kafka.ingest_now()
    _audit(request, admin, 'kafka.ingest', 'ingest folder from Kafka')
    return dict(started=True)


@router.get('/api/v1/public/map', dependencies=[Depends(public)])
def public_map(request: Request, response: Response):
    response.headers['Cache-Control'] = 'no-store'
    return request.app.state.public_map.snapshot()


def live_feed(request, source):
    """The feed (with its `live` hub, `running()` and `live_folder()`) of the page's source, or None when it is not running."""
    st = request.app.state
    feed = {sources.KAFKA: getattr(st, 'kafka', None), sources.COLLECTOR: getattr(st, 'collector_feed', None)}.get(source)
    return feed if feed is not None and feed.running() else None


@router.get('/api/v1/live/map')
async def live_map(request: Request, user=Depends(require_user_ready)):
    feed = live_feed(request, request.query_params.get('source') or sources.KAFKA)   # no ?source=: Kafka, as before the collector had a map
    if feed is None: return Response(status_code=204)   # EventSource does not reconnect

    async def events():
        seq, _ = feed.live.since(10 ** 12)          # start from now
        folder, idle = None, 0
        while not await request.is_disconnected():
            if folder != (f := feed.live_folder()):
                folder = f
                yield f'event: hello\ndata: {json.dumps(dict(live=True, folder=f))}\n\n'
            seq, pts = feed.live.since(seq)
            if pts: idle = 0; yield f'data: {json.dumps(dict(p=pts))}\n\n'
            else:
                idle += 1
                if idle % 15 == 0: yield ': ping\n\n'
            if not feed.running(): yield 'event: end\ndata: {}\n\n'; break
            await asyncio.sleep(1)
    return StreamingResponse(events(), media_type='text/event-stream', headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})
