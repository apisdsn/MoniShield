// Satu pintu ke /api (TRD §5). Cookie sesi HttpOnly dikirim browser; setiap permintaan yang mengubah data membawa
// X-Requested-With (CSRF, TRD §8.2). 401 di tengah pemakaian -> layar Masuk "Sesi Anda berakhir" (DRD §6.7);
// 403 -> galat ber-kode (mis. "tidak punya akses"); server tak terjangkau -> pita "Tidak tersambung" + coba lagi
// otomatis tiap 5 detik selama 1 menit, lalu manual.
import { writable, get } from 'svelte/store';

export class ApiError extends Error {
  constructor(status, code, message) { super(message || code); this.status = status; this.code = code; }
}

/** 'ok' | 'expired' (sesi habis di tengah pemakaian). Diamati App.svelte. */
export const session = writable('ok');
/** null = tersambung; {auto: bool} = tidak tersambung (auto: masih mencoba otomatis). */
export const offline = writable(null);
/** Waktu (ms) permintaan terakhir yang berhasil: dasar peringatan sesi menganggur (DRD §6.9). */
export const lastActivity = writable(Date.now());

let retryTimer = null;

async function request(method, path, body) {
  const headers = { Accept: 'application/json' };
  if (method !== 'GET') headers['X-Requested-With'] = 'monishield-web';
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  let r;
  try {
    r = await fetch(path, { method, headers, credentials: 'same-origin', body: body === undefined ? undefined : JSON.stringify(body) });
  } catch (e) {
    startRetry();
    throw new ApiError(0, 'network', e.message);
  }
  if (get(offline)) stopRetry();
  let data = null;
  try { data = await r.json(); } catch { /* bukan JSON */ }
  if (r.ok) { lastActivity.set(Date.now()); return data; }
  const err = data?.error || {};
  if (r.status === 401 && path !== '/api/auth/login' && path !== '/api/me') session.set('expired');
  throw new ApiError(r.status, err.code || String(r.status), err.message);
}

/** Unggah badan mentah (File/Blob) dengan kemajuan byte; XHR karena fetch tidak memberi kemajuan unggah.
 *  signal (AbortSignal) membatalkan unggahan yang sedang berjalan. */
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
      try { d = JSON.parse(x.responseText); } catch { /* bukan JSON */ }
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
  del: (path) => request('DELETE', path),
};

/** Path ke endpoint tabel (TRD §5.4); parameter kosong tidak dikirim. */
export function tablePath(folder, table, params = {}) {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== null && v !== undefined && v !== '') q.set(k, v);
  const s = q.toString();
  return `/api/folders/${encodeURIComponent(folder)}/tables/${encodeURIComponent(table)}${s ? '?' + s : ''}`;
}

// ---------------------------------------------------------------- tidak tersambung
const RETRY_MS = 5000, RETRY_FOR_MS = 60000;
let retryStart = 0;
const listeners = new Set();
/** Dipanggil saat sambungan pulih (App memuat ulang tab aktif). */
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
  } catch { /* masih mati */ }
  if (Date.now() - retryStart >= RETRY_FOR_MS) { clearInterval(retryTimer); retryTimer = null; offline.set({ auto: false }); }
}
/** Tombol "Coba lagi" di pita. */
export async function retryNow() {
  try {
    const r = await fetch('/api/health', { credentials: 'same-origin' });
    if (r.ok) return stopRetry();
  } catch { /* masih mati */ }
  offline.set({ auto: false });
}
