// Tab, folder, dan modul peta <-> alamat (DRD §1.3, U1). Bentuk alamat: #/<tab>?folder=YYYY-MM-DD&modul=<modul>
// Tab analisis memakai slug lama (#keamanan dari sistem lama tetap terbuka); layanan: #/layanan/<nama>;
// layar akun/admin: #/sandi, #/admin/user, #/admin/ingest. Bahasa dan tema TIDAK masuk alamat (per browser).
// Contoh: #/keamanan?folder=2026-10-06, #/layanan/coredns?folder=2026-09-29, #/peta?folder=2026-10-06&modul=om-be-report
import { writable, get } from 'svelte/store';

export const TABS = ['overview', 'peta', 'tren', 'keamanan', 'akar-masalah', 'ketersediaan', 'pod', 'bisnis', 'pelacakan'];
export const ADMIN = ['admin/user', 'admin/ingest'];
const OTHER = ['sandi', ...ADMIN];

export function parse(hash) {
  const h = (hash || '').replace(/^#\/?/, '');
  const [path, query = ''] = h.split('?');
  const q = new URLSearchParams(query);
  let tab = decodeURIComponent(path || 'overview');
  let service = null;
  if (tab.startsWith('layanan/')) { service = tab.slice(8); tab = 'layanan'; }
  else if (!TABS.includes(tab) && !OTHER.includes(tab)) { service = tab; tab = 'layanan'; }   // alamat lama: #<nama-layanan>
  return { tab, service, folder: q.get('folder') || null, module: q.get('modul') || null };
}

export function build({ tab, service, folder, module }) {
  const path = tab === 'layanan' ? `layanan/${encodeURIComponent(service)}` : tab;
  const q = new URLSearchParams();
  if (folder) q.set('folder', folder);   // juga di Tren dan layar admin: folder tetap saat kembali ke halaman data
  if (module && tab === 'peta') q.set('modul', module);
  const s = q.toString();
  return `#/${path}${s ? '?' + s : ''}`;
}

export const route = writable(parse(typeof location !== 'undefined' ? location.hash : ''));

/** Pindah: menambah riwayat (tombol kembali berfungsi). replace=true untuk koreksi otomatis (folder tidak ada, dll.). */
export function go(patch, { replace = false } = {}) {
  const next = { ...get(route), ...patch };
  if (patch.tab && patch.tab !== 'layanan') next.service = null;
  const url = build(next);
  if (url !== location.hash) (replace ? history.replaceState : history.pushState).call(history, null, '', url);
  route.set(parse(url));
}

// tautan biasa (<a href="#/...">), tombol kembali/maju: satu pembaruan per perubahan nyata
function sync() {
  const r = parse(location.hash);
  if (JSON.stringify(r) !== JSON.stringify(get(route))) route.set(r);
}
if (typeof window !== 'undefined') {
  window.addEventListener('popstate', sync);
  window.addEventListener('hashchange', sync);
}
