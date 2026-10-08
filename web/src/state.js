// Tab, folder, and map module <-> address (DRD §1.3, U1). Address form: #/<tab>?folder=YYYY-MM-DD&modul=<module>
// Analysis tabs use the old slugs (#keamanan from the old system still opens); services: #/layanan/<name>;
// account/admin screens: #/sandi, #/admin/user, #/admin/ingest. Language and theme are NOT in the address (per browser).
// Stage 24: IP profile #/ip/<ip>?folder=… (the IP is stored in `service`, the page target); ?cari=<text> fills the target table's
// filter from the global search (dropped when switching tabs through normal navigation).
// Examples: #/keamanan?folder=2026-10-06, #/layanan/coredns?folder=2026-09-29, #/peta?folder=2026-10-06&modul=om-be-report
import { writable, get } from 'svelte/store';

export const TABS = ['overview', 'peta', 'tren', 'keamanan', 'akar-masalah', 'ketersediaan', 'pod', 'bisnis', 'pelacakan'];
export const ADMIN = ['admin/user', 'admin/ingest', 'admin/konfigurasi', 'admin/notifikasi'];
const OTHER = ['sandi', ...ADMIN];

export function parse(hash) {
  const h = (hash || '').replace(/^#\/?/, '');
  const [path, query = ''] = h.split('?');
  const q = new URLSearchParams(query);
  let tab = decodeURIComponent(path || 'overview');
  let service = null;
  if (tab.startsWith('ip/')) { service = tab.slice(3); tab = 'ip'; }
  else if (tab.startsWith('layanan/')) { service = tab.slice(8); tab = 'layanan'; }
  else if (!TABS.includes(tab) && !OTHER.includes(tab)) { service = tab; tab = 'layanan'; }   // old address: #<service-name>
  return { tab, service, folder: q.get('folder') || null, module: q.get('modul') || null, q: q.get('cari') || null };
}

export function build({ tab, service, folder, module, q = null }) {
  const path = tab === 'layanan' || tab === 'ip' ? `${tab}/${encodeURIComponent(service)}` : tab;
  const qs = new URLSearchParams();
  if (folder) qs.set('folder', folder);   // also in Trends and admin screens: the folder is kept when returning to a data page
  if (module && tab === 'peta') qs.set('modul', module);
  if (q) qs.set('cari', q);
  const s = qs.toString();
  return `#/${path}${s ? '?' + s : ''}`;
}

export const route = writable(parse(typeof location !== 'undefined' ? location.hash : ''));

/** Navigate: adds to history (the back button works). replace=true for automatic corrections (missing folder, etc.). */
export function go(patch, { replace = false } = {}) {
  const next = { ...get(route), ...patch };
  if (patch.tab && patch.tab !== 'layanan' && patch.tab !== 'ip') next.service = null;
  if (patch.tab && !('q' in patch)) next.q = null;
  const url = build(next);
  if (url !== location.hash) (replace ? history.replaceState : history.pushState).call(history, null, '', url);
  route.set(parse(url));
}

// plain links (<a href="#/...">), back/forward buttons: one update per real change
function sync() {
  const r = parse(location.hash);
  if (JSON.stringify(r) !== JSON.stringify(get(route))) route.set(r);
}
if (typeof window !== 'undefined') {
  window.addEventListener('popstate', sync);
  window.addEventListener('hashchange', sync);
}
