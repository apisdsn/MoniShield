// Encrypted request/response bodies (server side: monishield/interfaces/api/wire.py). Once per page load the browser agrees
// on an AES-256-GCM key with the server (ECDH P-256 + HKDF-SHA256, WebCrypto; the private key never leaves this tab).
// Each body = 12-byte nonce + ciphertext, bound to "req|resp METHOD /path". Without WebCrypto (plain http on a LAN
// address) or when the server turned it off (S4_API_ENCRYPTION=false), requests stay plain JSON.
const INFO = new TextEncoder().encode('monishield-api-v1');
let keyP = null;
const OFF = 'off';   // turned off by the server or no WebCrypto: remembered for this page load

const b64 = (u8) => btoa(String.fromCharCode(...u8));
const unb64 = (s) => Uint8Array.from(atob(s), (c) => c.charCodeAt(0));

async function handshake() {
  const subtle = globalThis.crypto?.subtle;
  if (!subtle) return OFF;
  try {
    const kp = await subtle.generateKey({ name: 'ECDH', namedCurve: 'P-256' }, false, ['deriveBits']);
    const pub = new Uint8Array(await subtle.exportKey('raw', kp.publicKey));
    const r = await fetch('/api/crypto/handshake', {
      method: 'POST', credentials: 'same-origin', body: JSON.stringify({ pub: b64(pub) }),
      headers: { Accept: 'application/json', 'Content-Type': 'application/json', 'X-Requested-With': 'monishield-web' },
    });
    if (!r.ok) return null;
    const d = await r.json();
    if (!d.enabled) return OFF;
    const peer = await subtle.importKey('raw', unb64(d.pub), { name: 'ECDH', namedCurve: 'P-256' }, false, []);
    const bits = await subtle.deriveBits({ name: 'ECDH', public: peer }, kp.privateKey, 256);
    const hk = await subtle.importKey('raw', bits, 'HKDF', false, ['deriveKey']);
    const key = await subtle.deriveKey({ name: 'HKDF', hash: 'SHA-256', salt: new Uint8Array(0), info: INFO }, hk,
      { name: 'AES-GCM', length: 256 }, false, ['encrypt', 'decrypt']);
    return { kid: d.kid, key };
  } catch {
    return null;   // server unreachable or no WebCrypto: plain JSON this time, a new try on the next forget()
  }
}

/** {kid, key} or null (plain JSON). */
export async function wireKey() {
  keyP ||= handshake().then((k) => (k || (keyP = null, null)));
  const k = await keyP;
  return k === OFF ? null : k;
}
/** Server lost the key (restart, expiry): agree on a new one. */
export function forget() { keyP = null; }

const aad = (kind, method, path) => new TextEncoder().encode(`${kind} ${method} ${path.split('?')[0]}`);

export async function seal(k, method, path, text) {
  const nonce = crypto.getRandomValues(new Uint8Array(12));
  const ct = new Uint8Array(await crypto.subtle.encrypt({ name: 'AES-GCM', iv: nonce, additionalData: aad('req', method, path) }, k.key, new TextEncoder().encode(text)));
  const out = new Uint8Array(12 + ct.length);
  out.set(nonce); out.set(ct, 12);
  return out;
}

export async function open(k, method, path, buf) {
  const u8 = new Uint8Array(buf);
  const pt = await crypto.subtle.decrypt({ name: 'AES-GCM', iv: u8.slice(0, 12), additionalData: aad('resp', method, path) }, k.key, u8.slice(12));
  return JSON.parse(new TextDecoder().decode(pt));
}
