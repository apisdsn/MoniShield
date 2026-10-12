// Tab, folder, and map module <-> address (DRD §1.3, U1). English addresses (owner request 2026-10-12):
//   #/<tab>?folder=YYYY-MM-DD&module=<module>&search=<text>   tabs: TABS below
//   #/services/<name>?folder=…   one service        #/ips/<ip>?folder=…   IP profile (the IP is kept in `service`)
//   #/admin/users, #/admin/ingest                     admin screens
// ?search=<text> fills the target table's filter from the global search (dropped when switching tabs).
// Older addresses keep working and are rewritten (ALIAS): the Indonesian slugs of the old system (#/keamanan, #/peta,
// #/layanan/<name>, #/ip/<ip>, ?modul=, ?cari=, #<service-name>), and #/sandi, #/email, #/admin/konfigurasi,
// #/admin/notifikasi, which open a pop-up (App.svelte). Language and theme are NOT in the address (per browser).
import { writable, get } from 'svelte/store';

export const TABS = ['overview', 'command-center', 'trends', 'security', 'root-causes', 'availability', 'pods', 'business', 'tracing'];
export const ADMIN = ['admin/users', 'admin/ingest'];
const DIALOGS = ['password', 'email', 'admin/configuration', 'admin/notifications'];   // open a pop-up over the Overview
const ALIAS = { peta: 'command-center', tren: 'trends', keamanan: 'security', 'akar-masalah': 'root-causes', ketersediaan: 'availability',
                pod: 'pods', bisnis: 'business', pelacakan: 'tracing', 'admin/user': 'admin/users', sandi: 'password',
                'admin/konfigurasi': 'admin/configuration', 'admin/notifikasi': 'admin/notifications' };

export function parse(hash) {
  const h = (hash || '').replace(/^#\/?/, '');
  const [path, query = ''] = h.split('?');
  const q = new URLSearchParams(query);
  let tab = decodeURIComponent(path || 'overview');
  let service = null;
  tab = ALIAS[tab] || tab;
  if (tab.startsWith('ips/') || tab.startsWith('ip/')) { service = tab.slice(tab.indexOf('/') + 1); tab = 'ip'; }
  else if (tab.startsWith('services/') || tab.startsWith('layanan/')) { service = tab.slice(tab.indexOf('/') + 1); tab = 'service'; }
  else if (!TABS.includes(tab) && !ADMIN.includes(tab) && !DIALOGS.includes(tab)) { service = tab; tab = 'service'; }   // old address: #<service-name>
  return { tab, service, folder: q.get('folder') || null, module: q.get('module') || q.get('modul') || null, q: q.get('search') || q.get('cari') || null };
}

export function build({ tab, service, folder, module, q = null }) {
  const path = tab === 'service' ? `services/${encodeURIComponent(service)}` : tab === 'ip' ? `ips/${encodeURIComponent(service)}` : tab;
  const qs = new URLSearchParams();
  if (folder) qs.set('folder', folder);   // also in Trends and admin screens: the folder is kept when returning to a data page
  if (module && tab === 'command-center') qs.set('module', module);
  if (q) qs.set('search', q);
  const s = qs.toString();
  return `#/${path}${s ? '?' + s : ''}`;
}

/** Old or loose address (#/peta, #keamanan, ?modul=…) -> the English one in the address bar, without a history entry. */
function canonical() {
  if (typeof location === 'undefined' || !location.hash) return;
  const url = build(parse(location.hash));
  if (url !== location.hash) history.replaceState(null, '', url);
}
canonical();
export const route = writable(parse(typeof location !== 'undefined' ? location.hash : ''));

/** Navigate: adds to history (the back button works). replace=true for automatic corrections (missing folder, etc.). */
export function go(patch, { replace = false } = {}) {
  const next = { ...get(route), ...patch };
  if (patch.tab && patch.tab !== 'service' && patch.tab !== 'ip') next.service = null;
  if (patch.tab && !('q' in patch)) next.q = null;
  const url = build(next);
  if (url !== location.hash) (replace ? history.replaceState : history.pushState).call(history, null, '', url);
  route.set(parse(url));
}

// plain links (<a href="#/...">), back/forward buttons: one update per real change
function sync() {
  canonical();
  const r = parse(location.hash);
  if (JSON.stringify(r) !== JSON.stringify(get(route))) route.set(r);
}
if (typeof window !== 'undefined') {
  window.addEventListener('popstate', sync);
  window.addEventListener('hashchange', sync);
}
