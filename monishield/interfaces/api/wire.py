"""Encrypted request and response bodies for the web UI (monishield/infrastructure/wirecrypto.py).
  POST /api/crypto/handshake   {pub: browser ECDH key} -> {enabled, kid, pub: server ECDH key}; public (needed before sign-in)

A request carrying `X-MS-Enc: <key id>` has an encrypted body (application/octet-stream) and gets its JSON response
encrypted the same way (header `X-MS-Enc: 1`). Requests without the header are served as plain JSON, so Swagger, the
cron job and curl keep working. Non-JSON responses (CSV, block list, files) and the live map stream are not touched.
Errors of the encryption itself are plain JSON: {"error": {"code": "enc_key_unknown" | "enc_invalid"}}; the browser
agrees on a new key and repeats the request once.
"""
import json

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from monishield.domain.errors import Fail
from monishield.infrastructure.wirecrypto import WireError
from .common import public

router = APIRouter(prefix='/api/crypto')
HEADER = b'x-ms-enc'


class Handshake(BaseModel):
    pub: str


@router.post('/handshake', dependencies=[Depends(public)])
def handshake(body: Handshake, request: Request):
    st = request.app.state
    if not st.cfg.api_encryption: return dict(enabled=False)
    try: kid, pub = st.wire.handshake(body.pub[:200])
    except WireError as e: raise Fail(e.code, 'Invalid public key.', 400) from None
    return dict(enabled=True, kid=kid, pub=pub)


def _aad(kind, scope): return f"{kind} {scope['method']} {scope['path']}".encode()


class PayloadCrypto:
    """ASGI middleware: decrypts request bodies and encrypts JSON responses of requests that carry X-MS-Enc."""

    def __init__(self, app, state): self.app, self.state = app, state

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or not scope['path'].startswith('/api/'): return await self.app(scope, receive, send)
        kid = next((v.decode('latin-1') for k, v in scope['headers'] if k == HEADER), None)
        if not kid or not self.state.cfg.api_encryption: return await self.app(scope, receive, send)
        wire = self.state.wire

        body, more = b'', True
        while more:
            msg = await receive()
            if msg['type'] == 'http.disconnect': return
            body += msg.get('body', b''); more = msg.get('more_body', False)
        try:
            plain = wire.open(kid, body, _aad('req', scope)) if body else b''
        except WireError as e: return await _send_json(send, 400, dict(error=dict(code=e.code, message='Encrypted request could not be read; the page agrees on a new key.')))
        headers = [(k, v) for k, v in scope['headers'] if k not in (b'content-type', b'content-length', HEADER)]
        if plain: headers += [(b'content-type', b'application/json'), (b'content-length', str(len(plain)).encode())]
        scope = dict(scope, headers=headers)
        sent = False

        async def receive_plain():
            nonlocal sent
            if sent: return {'type': 'http.disconnect'}
            sent = True
            return {'type': 'http.request', 'body': plain, 'more_body': False}

        start, chunks = None, []

        async def send_sealed(msg):
            nonlocal start
            if msg['type'] == 'http.response.start':
                ctype = dict(msg.get('headers', [])).get(b'content-type', b'')
                if not ctype.startswith(b'application/json'): start = False; return await send(msg)   # files, CSV, streams: untouched
                start = msg; return
            if start is False: return await send(msg)
            chunks.append(msg.get('body', b''))
            if msg.get('more_body'): return
            try: data = wire.seal(kid, b''.join(chunks), _aad('resp', scope))
            except WireError as e: return await _send_json(send, 400, dict(error=dict(code=e.code, message='Encryption key expired.')))
            hdr = [(k, v) for k, v in start.get('headers', []) if k not in (b'content-type', b'content-length')]
            hdr += [(b'content-type', b'application/octet-stream'), (b'content-length', str(len(data)).encode()), (HEADER, b'1')]
            await send(dict(start, headers=hdr))
            await send({'type': 'http.response.body', 'body': data})

        await self.app(scope, receive_plain, send_sealed)


async def _send_json(send, status, obj):
    data = json.dumps(obj).encode()
    await send({'type': 'http.response.start', 'status': status,
                'headers': [(b'content-type', b'application/json'), (b'content-length', str(len(data)).encode()), (b'cache-control', b'no-store')]})
    await send({'type': 'http.response.body', 'body': data})
