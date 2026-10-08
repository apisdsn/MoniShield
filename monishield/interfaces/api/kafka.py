"""Logs from Kafka (monishield/application/kafka_service.py).
  GET  /api/admin/kafka          consumer status: connected?, messages received/written/skipped per service, last 50 messages
  POST /api/admin/kafka/peek     "Check messages": the LAST n messages of the topic (no consumer group; does not move the read position)
  POST /api/admin/kafka/ingest   ingest now (without waiting for the S4_KAFKA_INGEST_MINUTES interval)
  GET  /api/live/map             Server-Sent Events for the realtime map animation: {p: [[lat, lon, count, module], …]} per
                                 second. Location coordinates only (from the local IP database), no IP addresses. 204 when Kafka is off.
"""
import asyncio, json

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel

from monishield.domain.errors import Fail
from .admin import _audit
from .common import require_admin, require_user_ready

router = APIRouter()


@router.get('/api/admin/kafka')
def kafka_status(request: Request, admin=Depends(require_admin)):
    return request.app.state.kafka.status()


class PeekBody(BaseModel):
    n: int = 10


@router.post('/api/admin/kafka/peek')
def kafka_peek(request: Request, body: PeekBody = PeekBody(), admin=Depends(require_admin)):
    try: r = request.app.state.kafka.peek(max(1, min(50, body.n)))
    except Fail as e:
        _audit(request, admin, 'kafka.peek', f'failed ({e.code})'); raise
    _audit(request, admin, 'kafka.peek', f"{r['topic']}: {len(r['messages'])} messages")
    return r


@router.post('/api/admin/kafka/ingest')
def kafka_ingest(request: Request, admin=Depends(require_admin)):
    request.app.state.kafka.ingest_now()
    _audit(request, admin, 'kafka.ingest', 'ingest folder from Kafka')
    return dict(started=True)


@router.get('/api/live/map')
async def live_map(request: Request, user=Depends(require_user_ready)):
    feed = request.app.state.kafka
    if not feed.running(): return Response(status_code=204)   # EventSource does not reconnect

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
