// Tab, folder, and map module <-> address (DRD §1.3, U1). Clean English paths (owner request 2026-10-12), no "#":
//   /<tab>?folder=YYYY-MM-DD&module=<module>&search=<text>   tabs: TABS below
//   /services/<name>?folder=…   one service        /ips/<ip>?folder=…   IP profile (the IP is kept in `service`)
//   /admin/users, /admin/ingest                       admin screens
//   /password, /email, /admin/configuration, /admin/notifications   open a pop-up over the Overview (App.svelte)
// ?search=<text> fills the target table's filter from the global search (dropped when switching tabs).
// The server answers every such path with the web app (interfaces/api/app.py, SpaFiles). Links inside the app are
// followed without reloading the page (History API). Old links from notifications and bookmarks (#/peta, #/keamanan,
// #/layanan/<name>, #/security, ?modul=, ?cari=) are turned into the new path in the address bar.
// Language and theme are NOT in the address (per browser).
import { writable, get } from 'svelte/store';

export const TABS = ['overview', 'command-center', 'trends', 'security', 'root-causes', 'availability', 'pods', 'business', 'tracing'];
export const ADMIN = ['admin/users', 'admin/ingest'];
const DIALOGS = ['password', 'email', 'admin/configuration', 'admin/notifications'];
const ALIAS = { peta: 'command-center', tren: 'trends', keamanan: 'security', 'akar-masalah': 'root-causes', ketersediaan: 'availability',
                pod: 'pods', bisnis: 'business', pelacakan: 'tracing', 'admin/user': 'admin/users', sandi: 'password',
                'admin/konfigurasi': 'admin/configuration', 'admin/notifikasi': 'admin/notifications' };
const SERVER = /^\/(api|map|swagger|assets|fonts)(\/|$)/;   // paths the server answers itself (never app pages)

/** "/security?folder=…" (or an old "#/keamanan?…") -> {tab, service, folder, module, q}. */
export function parse(address) {
  const h = (address || '').replace(/^#?\/?/, '');
  const [path, query = ''] = h.split('?');
  const q = new URLSearchParams(query);
  let tab = decodeURIComponent(path.replace(/\/+$/, '') || 'overview');
  let service = null;
  tab = ALIAS[tab] || tab;
  if (tab.startsWith('ips/') || tab.startsWith('ip/')) { service = tab.slice(tab.indexOf('/') + 1); tab = 'ip'; }
  else if (tab.startsWith('services/') || tab.startsWith('layanan/')) { service = tab.slice(tab.indexOf('/') + 1); tab = 'service'; }
  else if (!TABS.includes(tab) && !ADMIN.includes(tab) && !DIALOGS.includes(tab)) tab = 'overview';   // unknown address
  return { tab, service, folder: q.get('folder') || null, module: q.get('module') || q.get('modul') || null, q: q.get('search') || q.get('cari') || null };
}

export function build({ tab, service, folder, module, q = null }) {
  const path = tab === 'service' ? `services/${encodeURIComponent(service)}` : tab === 'ip' ? `ips/${encodeURIComponent(service)}` : tab;
  const qs = new URLSearchParams();
  if (folder) qs.set('folder', folder);   // also in Trends and admin screens: the folder is kept when returning to a data page
  if (module && tab === 'command-center') qs.set('module', module);
  if (q) qs.set('search', q);
  const s = qs.toString();
  return `/${path}${s ? '?' + s : ''}`;
}

// an old hash address ("#/peta", "#keamanan") wins over the path; other fragments (#main, skip links) are not addresses
const legacyHash = () => {
  const h = location.hash;
  return h.startsWith('#/') || ALIAS[h.slice(1)] || TABS.includes(h.slice(1)) ? h : null;
};
const here = () => (typeof location === 'undefined' ? '' : legacyHash() || location.pathname + location.search);

/** Old or loose address -> the canonical path in the address bar, without a history entry. ?next= (sign-in return) is kept. */
function canonical() {
  if (typeof location === 'undefined' || new URLSearchParams(location.search).has('next')) return;
  const url = build(parse(here()));
  if (url !== location.pathname + location.search + location.hash) history.replaceState(null, '', url);
}
canonical();
export const route = writable(parse(here()));

/** Navigate: adds to history (the back button works). replace=true for automatic corrections (missing folder, etc.). */
export function go(patch, { replace = false } = {}) {
  const next = { ...get(route), ...patch };
  if (patch.tab && patch.tab !== 'service' && patch.tab !== 'ip') next.service = null;
  if (patch.tab && !('q' in patch)) next.q = null;
  const url = build(next);
  if (url !== location.pathname + location.search) (replace ? history.replaceState : history.pushState).call(history, null, '', url);
  route.set(parse(url));
}

// back/forward buttons and links: one update per real change
function sync() {
  canonical();
  const r = parse(here());
  if (JSON.stringify(r) !== JSON.stringify(get(route))) route.set(r);
}
// a click on an app link (<a href="/security?…">) changes the page without reloading; new tabs, downloads and
// server paths (/api/…, /map/…) are left to the browser
function follow(e) {
  if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
  const a = e.target.closest?.('a[href]');
  if (!a || a.target || a.hasAttribute('download') || a.origin !== location.origin || SERVER.test(a.pathname)) return;
  if (a.getAttribute('href').startsWith('#')) return;   // in-page fragment (skip links)
  e.preventDefault();
  if (a.pathname + a.search !== location.pathname + location.search) history.pushState(null, '', a.pathname + a.search);
  sync();
}
if (typeof window !== 'undefined') {
  window.addEventListener('popstate', sync);
  window.addEventListener('hashchange', sync);
  document.addEventListener('click', follow);
}
