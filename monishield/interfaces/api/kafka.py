"""Log dari Kafka (monishield/kafka_in.py).
  GET  /api/admin/kafka          status konsumen: tersambung?, pesan diterima/ditulis/dilewati per layanan, 50 pesan terakhir
  POST /api/admin/kafka/peek     "Cek pesan": n pesan TERAKHIR dari topic (tanpa grup konsumen; tidak menggeser posisi baca)
  POST /api/admin/kafka/ingest   ingest sekarang (tanpa menunggu jeda S4_KAFKA_INGEST_MINUTES)
  GET  /api/live/map             Server-Sent Events untuk animasi peta realtime: {p: [[lat, lon, jumlah, modul], …]} per
                                 detik. Hanya koordinat lokasi (dari basis data IP lokal), tanpa alamat IP. 204 bila Kafka mati.
"""
import asyncio, json

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel

from monishield.infrastructure import kafka_in
from .admin import _audit
from .common import ApiError, require_admin, require_user_ready

router = APIRouter()


@router.get('/api/admin/kafka')
def kafka_status(request: Request, admin=Depends(require_admin)):
    return request.app.state.kafka.status()


class PeekBody(BaseModel):
    n: int = 10


@router.post('/api/admin/kafka/peek')
def kafka_peek(request: Request, body: PeekBody = PeekBody(), admin=Depends(require_admin)):
    try: r = kafka_in.peek(request.app.state.cfg, max(1, min(50, body.n)))
    except kafka_in.KafkaFail as e:
        _audit(request, admin, 'kafka.peek', f'gagal ({e.code})')
        raise ApiError(e.status, e.code, e.message) from None
    _audit(request, admin, 'kafka.peek', f"{r['topic']}: {len(r['messages'])} pesan")
    return r


@router.post('/api/admin/kafka/ingest')
def kafka_ingest(request: Request, admin=Depends(require_admin)):
    feed = request.app.state.kafka
    if not feed.pending: raise ApiError(400, 'kafka_nothing', 'Belum ada baris baru dari Kafka sejak ingest terakhir.')
    if not feed.maybe_ingest(force=True): raise ApiError(409, 'ingest_running', 'Ingest lain sedang berjalan; coba lagi sebentar.')
    _audit(request, admin, 'kafka.ingest', 'ingest folder dari Kafka')
    return dict(started=True)


@router.get('/api/live/map')
async def live_map(request: Request, user=Depends(require_user_ready)):
    feed = request.app.state.kafka
    if not (feed.thread and feed.thread.is_alive()): return Response(status_code=204)   # EventSource tidak menyambung ulang

    async def events():
        seq, _ = feed.live.since(10 ** 12)          # mulai dari sekarang
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
            if not (feed.thread and feed.thread.is_alive()): yield 'event: end\ndata: {}\n\n'; break
            await asyncio.sleep(1)
    return StreamingResponse(events(), media_type='text/event-stream', headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})
