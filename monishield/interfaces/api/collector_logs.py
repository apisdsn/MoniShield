"""Receiver for the OpenTelemetry Collector (docs/12-collector.md, step 3).
  POST /api/collector/v1/logs   OTLP/HTTP log batches as JSON (otlphttp exporter: encoding json, compression gzip)

A machine client: it authenticates with its own key (`Authorization: Bearer msk_…`), so there is no session and no CSRF
check, and the batches are not audited. The status codes are chosen for the exporter's retry rules: it retries 429, 502,
503 and 504 (and keeps the data in its queue) and drops the batch on other 4xx, so a batch that can never succeed must not
get a retryable code and a temporary problem must not get a final one. The line files are on disk before the 200.
"""
import datetime, json, zlib

from fastapi import APIRouter, Depends, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from .common import ApiError, require_collector

router = APIRouter(prefix='/api/collector/v1')
MB = 1024 * 1024
PIECE = 256 * 1024   # gunzip output is taken in pieces of this size, so a bomb is stopped early


def _too_large(): return ApiError(413, 'body_too_large', 'The request is too large; send smaller batches.')


def _bad_body(): return ApiError(400, 'invalid_body', 'The request body is not valid OTLP JSON.')


def check_type(request: Request):
    ctype = request.headers.get('content-type', '').split(';')[0].strip().lower()
    if ctype == 'application/json': return
    hint = 'Send OTLP as JSON (exporter setting encoding: json).'
    raise ApiError(415, 'unsupported_media_type', hint if ctype == 'application/x-protobuf' else f'Content-Type must be application/json. {hint}')


def check_encoding(request: Request):
    """-> 'gzip' or 'identity'."""
    enc = request.headers.get('content-encoding', 'identity').strip().lower() or 'identity'
    if enc not in ('gzip', 'identity'): raise ApiError(415, 'unsupported_media_type', 'Content-Encoding must be gzip or identity (exporter setting compression: gzip).')
    return enc


async def read_body(request: Request, limit):
    """The body as sent, never more than `limit` bytes in memory: Content-Length is refused up front, and the stream is
    counted as it arrives because a chunked request has no Content-Length."""
    declared = request.headers.get('content-length')
    if declared is not None:
        if not declared.isdigit(): raise _bad_body()
        if int(declared) > limit: raise _too_large()
    chunks, size = [], 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > limit: raise _too_large()
        chunks.append(chunk)
    return b''.join(chunks)


def gunzip(data, limit):
    """Decompress in pieces and stop as soon as the output passes `limit` (a zip bomb never gets built in memory)."""
    d, out, size, rest = zlib.decompressobj(16 + zlib.MAX_WBITS), [], 0, data
    try:
        while not d.eof:
            piece = d.decompress(rest, PIECE)
            size += len(piece)
            if size > limit: raise _too_large()
            out.append(piece); rest = d.unconsumed_tail
            if not piece and not rest: break   # nothing more can come out: cut off, or done
        if not d.eof or d.unused_data: raise _bad_body()   # cut off, or something after the gzip member
    except zlib.error: raise _bad_body() from None
    return b''.join(out)


def decode(raw):
    try: payload = json.loads(raw.decode('utf-8'))
    except (UnicodeDecodeError, ValueError, RecursionError): raise _bad_body() from None
    if not isinstance(payload, dict): raise _bad_body()
    return payload


def store(feed, collector, body, encoding, max_raw):
    """The CPU and disk work of a request (runs in a worker thread, not on the event loop). -> the OTLP answer."""
    raw = gunzip(body, max_raw) if encoding == 'gzip' else body
    if len(raw) > max_raw: raise _too_large()
    payload = decode(raw)
    if feed.space_low(): raise ApiError(503, 'disk_full', 'The server is low on disk space; keep the data and retry later.', {'Retry-After': '60'})
    try: answer, _ = feed.receive(collector, payload, datetime.datetime.now(datetime.timezone.utc))
    except OSError: raise ApiError(503, 'storage_error', 'The server could not store the lines; retry later.', {'Retry-After': '60'}) from None
    return answer


@router.post('/logs')
async def receive_logs(request: Request, collector=Depends(require_collector)):
    st, cfg = request.app.state, request.app.state.cfg
    check_type(request)
    encoding = check_encoding(request)
    # before reading the body: a collector over its limit should cost as little as possible
    if not st.collector_rates.hit(collector['id'], cfg.collector_rate_per_min):
        raise ApiError(429, 'rate_limited', 'Too many requests from this collector; slow down.', {'Retry-After': '30'})
    # reading and storing hold the memory (a raw body becomes about ten times as many bytes of objects): few at a time
    if not st.collector_slots.take(cfg.collector_max_concurrent):
        raise ApiError(503, 'busy', 'The server is busy; retry shortly.', {'Retry-After': '5'})
    try:
        body = await read_body(request, cfg.collector_max_body_mb * MB)
        answer = await run_in_threadpool(store, st.collector_feed, collector, body, encoding, cfg.collector_max_raw_mb * MB)
    finally: st.collector_slots.release()
    return JSONResponse(answer)
