// Tab, folder, and map module <-> address (DRD §1.3, U1). Clean English paths (owner request 2026-10-12), no "#":
//   /<tab>?folder=YYYY-MM-DD&module=<module>&search=<text>   tabs: TABS below
// ?source=kafka shows the Kafka data source (own database); no ?source = S3. It stays when moving between pages.
//   /services/<name>?folder=…   one service        /ips/<ip>?folder=…   IP profile (the IP is kept in `service`)
//   /admin/users, /admin/ingest                       admin screens
//   /password, /email, /admin/configuration, /admin/notifications   open a pop-up over the Overview (App.svelte)
//   /login?next=<app address>   sign-in page (App.svelte); afterwards the app goes to `next` (only an app address)
//   /   public home page (pages/Landing.svelte, no sign-in): what MoniShield is, the coarse traffic map, "Sign in"
// ?search=<text> fills the target table's filter from the global search (dropped when switching tabs).
// The server answers every such path with the web app (interfaces/api/app.py, SpaFiles). Links inside the app are
// followed without reloading the page (History API). Unknown paths open the Overview; links marked data-reload
// (between the home page and the app) load the page anew.
// Language and theme are NOT in the address (per browser).
import { writable, get } from 'svelte/store';
import { setSource } from './api.js';

export const TABS = ['overview', 'command-center', 'trends', 'security', 'root-causes', 'availability', 'pods', 'business', 'tracing', 'raw-logs'];
export const ADMIN = ['admin/users', 'admin/ingest'];
const DIALOGS = ['password', 'email', 'admin/configuration', 'admin/notifications'];
const SERVER = /^\/(api|map|swagger|assets|fonts)(\/|$)/;   // paths the server answers itself (never app pages)

/** ?next= of the sign-in page -> an app address to go to afterwards; anything else (other sites "//x", server paths,
 *  the sign-in page itself) -> /overview. Not an open redirect. */
export function safeNext(n) {
  return typeof n === 'string' && /^\/(?![/\\])/.test(n) && !SERVER.test(n) && !/^\/login(\/|\?|$)/.test(n) ? n : '/overview';
}

/** "/security?folder=…" -> {tab, service, folder, module, q, source}. /login?next=… -> the page it returns to. */
export function parse(address) {
  const h = (address || '').replace(/^\//, '');
  const [path, query = ''] = h.split('?');
  const q = new URLSearchParams(query);
  if (path.replace(/\/+$/, '') === 'login') return parse(safeNext(q.get('next')));
  if (!path.replace(/\/+$/, '')) return { tab: 'home', service: null, folder: null, module: null, q: null, source: 's3' };
  let tab = decodeURIComponent(path.replace(/\/+$/, ''));
  let service = null;
  if (tab.startsWith('ips/')) { service = tab.slice(4); tab = 'ip'; }
  else if (tab.startsWith('services/')) { service = tab.slice(9); tab = 'service'; }
  else if (!TABS.includes(tab) && !ADMIN.includes(tab) && !DIALOGS.includes(tab)) tab = 'overview';   // unknown address
  return { tab, service, folder: q.get('folder') || null, module: q.get('module') || null, q: q.get('search') || null, source: q.get('source') === 'kafka' ? 'kafka' : 's3' };
}

export function build({ tab, service, folder, module, q = null, source }) {
  if (tab === 'home') return '/';
  const path = tab === 'service' ? `services/${encodeURIComponent(service)}` : tab === 'ip' ? `ips/${encodeURIComponent(service)}` : tab;
  const qs = new URLSearchParams();
  if (folder) qs.set('folder', folder);   // also in Trends and admin screens: the folder is kept when returning to a data page
  if (module && tab === 'command-center') qs.set('module', module);
  if (q) qs.set('search', q);
  if ((source ?? get(route).source) === 'kafka') qs.set('source', 'kafka');   // links inside the page keep the data source
  const s = qs.toString();
  return `/${path}${s ? '?' + s : ''}`;
}

const here = () => (typeof location === 'undefined' ? '' : location.pathname + location.search);

/** Loose address (/, trailing slash, unknown page) -> the canonical path in the address bar, without a history entry.
 *  ?next= (return after sign-in) is kept. */
function canonical() {
  if (typeof location === 'undefined' || location.pathname === '/login' || new URLSearchParams(location.search).has('next')) return;
  const url = build(parse(here()));
  if (url !== location.pathname + location.search) history.replaceState(null, '', url + location.hash);
}
canonical();
export const route = writable(parse(here()));
route.subscribe((r) => setSource(r.source));   // the API client follows the address (before any page asks for data)

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
  if (!a || a.target || a.hasAttribute('download') || a.hasAttribute('data-reload') || a.origin !== location.origin || SERVER.test(a.pathname)) return;
  if (a.getAttribute('href').startsWith('#')) return;   // in-page fragment (skip links)
  e.preventDefault();
  if (a.pathname + a.search !== location.pathname + location.search) history.pushState(null, '', a.pathname + a.search);
  sync();
}
if (typeof window !== 'undefined') {
  window.addEventListener('popstate', sync);
  document.addEventListener('click', follow);
}
