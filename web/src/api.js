// Single gateway to /api (TRD §5). The HttpOnly session cookie is sent by the browser; every data-changing request carries
// X-Requested-With (CSRF, TRD §8.2). 401 mid-use -> Login screen "Sesi Anda berakhir" (DRD §6.7);
// 403 -> coded error (e.g. "tidak punya akses"); server unreachable -> "Tidak tersambung" band + automatic
// retry every 5 seconds for 1 minute, then manual.
import { writable, get } from 'svelte/store';
import { forget, open, seal, wireKey } from './wire.js';

export class ApiError extends Error {
  constructor(status, code, message) { super(message || code); this.status = status; this.code = code; }
}

/** 'ok' | 'expired' (session ended mid-use). Observed by App.svelte. */
export const session = writable('ok');
/** null = connected; {auto: bool} = not connected (auto: still retrying automatically). */
export const offline = writable(null);
/** Time (ms) of the last successful request: basis for the idle-session warning (DRD §6.9). */
export const lastActivity = writable(Date.now());

let retryTimer = null;

async function request(method, path, body, retried = false) {
  const headers = { Accept: 'application/json' };
  if (method !== 'GET') headers['X-Requested-With'] = 'monishield-web';
  let payload = body === undefined ? undefined : JSON.stringify(body);
  const k = await wireKey();   // encrypted bodies when the server agreed on a key (wire.js)
  if (k) {
    headers['X-MS-Enc'] = k.kid;
    if (payload !== undefined) { payload = await seal(k, method, path, payload); headers['Content-Type'] = 'application/octet-stream'; }
  } else if (payload !== undefined) headers['Content-Type'] = 'application/json';
  let r;
  try {
    r = await fetch(path, { method, headers, credentials: 'same-origin', body: payload });
  } catch (e) {
    startRetry();
    throw new ApiError(0, 'network', e.message);
  }
  if (get(offline)) stopRetry();
  let data = null;
  try { data = k && r.headers.get('X-MS-Enc') ? await open(k, method, path, await r.arrayBuffer()) : await r.json(); } catch { /* not JSON */ }
  if (r.ok) { lastActivity.set(Date.now()); return data; }
  const err = data?.error || {};
  if (k && !retried && (err.code === 'enc_key_unknown' || err.code === 'enc_invalid')) { forget(); return request(method, path, body, true); }
  if (r.status === 401 && path !== '/api/auth/login' && path !== '/api/me') session.set('expired');
  throw new ApiError(r.status, err.code || String(r.status), err.message);
}

/** Upload a raw body (File/Blob) with byte progress; XHR because fetch gives no upload progress.
 *  signal (AbortSignal) cancels an upload in progress. */
function putFile(path, blob, onprogress = null, signal = null) {
  return new Promise((resolve, reject) => {
    const x = new XMLHttpRequest();
    x.open('PUT', path);
    x.setRequestHeader('X-Requested-With', 'monishield-web');
    x.setRequestHeader('Content-Type', 'application/octet-stream');
    x.setRequestHeader('Accept', 'application/json');
    if (onprogress) x.upload.onprogress = (e) => onprogress(e.loaded);
    x.onload = () => {
      let d = null;
      try { d = JSON.parse(x.responseText); } catch { /* not JSON */ }
      if (x.status >= 200 && x.status < 300) { lastActivity.set(Date.now()); return resolve(d); }
      if (x.status === 401) session.set('expired');
      reject(new ApiError(x.status, d?.error?.code || String(x.status), d?.error?.message));
    };
    x.onerror = () => reject(new ApiError(0, 'network', 'network'));
    x.onabort = () => reject(new ApiError(0, 'aborted', 'aborted'));
    signal?.addEventListener('abort', () => x.abort(), { once: true });
    x.send(blob);
  });
}

export const api = {
  putFile,
  get: (path) => request('GET', path),
  post: (path, body = {}) => request('POST', path, body),
  patch: (path, body = {}) => request('PATCH', path, body),
  put: (path, body = {}) => request('PUT', path, body),
  del: (path) => request('DELETE', path),
};

/** Path to the table endpoint (TRD §5.4); empty parameters are not sent. */
export function tablePath(folder, table, params = {}) {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== null && v !== undefined && v !== '') q.set(k, v);
  const s = q.toString();
  return `/api/folders/${encodeURIComponent(folder)}/tables/${encodeURIComponent(table)}${s ? '?' + s : ''}`;
}

// ---------------------------------------------------------------- not connected
const RETRY_MS = 5000, RETRY_FOR_MS = 60000;
let retryStart = 0;
const listeners = new Set();
/** Called when the connection recovers (App reloads the active tab). */
export const onReconnect = (fn) => (listeners.add(fn), () => listeners.delete(fn));

function startRetry() {
  if (retryTimer || get(offline)?.auto === false) return;
  retryStart = Date.now();
  offline.set({ auto: true });
  retryTimer = setInterval(probe, RETRY_MS);
}
function stopRetry() {
  clearInterval(retryTimer); retryTimer = null;
  offline.set(null);
  listeners.forEach((fn) => fn());
}
async function probe() {
  try {
    const r = await fetch('/api/health', { credentials: 'same-origin' });
    if (r.ok) return stopRetry();
  } catch { /* still down */ }
  if (Date.now() - retryStart >= RETRY_FOR_MS) { clearInterval(retryTimer); retryTimer = null; offline.set({ auto: false }); }
}
/** "Coba lagi" (Try again) button in the band. */
export async function retryNow() {
  try {
    const r = await fetch('/api/health', { credentials: 'same-origin' });
    if (r.ok) return stopRetry();
  } catch { /* still down */ }
  offline.set({ auto: false });
}
