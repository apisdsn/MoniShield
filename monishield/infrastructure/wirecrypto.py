"""Encrypted API payloads between the web UI and the server (owner request 2026-10-08), on top of HTTPS.

Key agreement once per page load: the browser sends an ephemeral ECDH P-256 public key, the server answers with its own
ephemeral key and a random key id; both derive the same AES-256-GCM key with HKDF-SHA256 (info "monishield-api-v1").
Each request/response body is then nonce (12 bytes) + ciphertext + tag, bound to the method and path (AAD), so a body
cannot be replayed on another endpoint. The server keeps only {key id: AES key} in memory (bounded, with an expiry);
after a restart the browser simply agrees on a new key.

Cost: one ECDH exchange per page load (well under a millisecond) and AES-GCM per body (OpenSSL, hardware AES), which is
small next to the database queries.

What it protects against: PASSIVE readers of decrypted traffic, i.e. the browser's network panel, screenshots of it, and
proxy or CDN logs that record request/response bodies.

What it does NOT protect against:
- An ACTIVE man in the middle (e.g. an office proxy that inspects TLS). The handshake is not authenticated, so such a
  proxy can swap the ECDH keys on both sides, or answer {"enabled": false} so the browser silently falls back to plain
  JSON (web/src/wire.js). A signing key would not help: the JavaScript bundle arrives over the same path.
- Whoever controls the tab: the user, browser extensions and any XSS in the page can read the key and the plain data.
- The server itself, which sees everything in plain form.
- Anything outside JSON bodies: URLs (paths, query strings), headers, cookies, and non-JSON responses (CSV, files, the
  block list, the live map stream) are not encrypted.
It is not an access control either: requests without X-MS-Enc are served as plain JSON (Swagger, cron, curl).
HTTPS remains the transport protection; this layer only keeps bodies out of passive logs.
"""
import base64, collections, os, threading, time

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

INFO = b'monishield-api-v1'
NONCE = 12


class WireError(Exception):
    """code: 'enc_key_unknown' (agree on a new key) or 'enc_invalid' (body cannot be decrypted)."""

    def __init__(self, code): super().__init__(code); self.code = code


def b64(data): return base64.b64encode(data).decode()


def unb64(text): return base64.b64decode(text, validate=True)


def derive(shared):
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=INFO).derive(shared)


class WireCrypto:
    def __init__(self, ttl_hours=12, max_keys=5000):
        self.ttl, self.max = ttl_hours * 3600, max_keys
        self._keys, self._lock = collections.OrderedDict(), threading.Lock()

    def handshake(self, client_pub_b64):
        """Browser public key (raw uncompressed P-256, base64) -> (key id, server public key base64)."""
        try:
            peer = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), unb64(client_pub_b64))
        except (ValueError, TypeError): raise WireError('enc_invalid') from None
        mine = ec.generate_private_key(ec.SECP256R1())
        key = AESGCM(derive(mine.exchange(ec.ECDH(), peer)))
        kid = base64.urlsafe_b64encode(os.urandom(16)).decode().rstrip('=')
        with self._lock:
            self._keys[kid] = (key, time.monotonic() + self.ttl)
            while len(self._keys) > self.max: self._keys.popitem(last=False)
        return kid, b64(mine.public_key().public_bytes(Encoding.X962, PublicFormat.UncompressedPoint))

    def _key(self, kid):
        with self._lock:
            hit = self._keys.get(kid)
            if not hit or hit[1] < time.monotonic():
                self._keys.pop(kid, None); raise WireError('enc_key_unknown')
            self._keys.move_to_end(kid)
            return hit[0]

    def open(self, kid, blob, aad):
        key = self._key(kid)
        if len(blob) <= NONCE: raise WireError('enc_invalid')
        try: return key.decrypt(blob[:NONCE], blob[NONCE:], aad)
        except InvalidTag: raise WireError('enc_invalid') from None

    def seal(self, kid, data, aad):
        nonce = os.urandom(NONCE)
        return nonce + self._key(kid).encrypt(nonce, data, aad)
