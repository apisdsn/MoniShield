// Two languages from keyed dictionaries (DRD §6.3, U15): UI text is fetched via t('key'), not replaced in the DOM
// after render, so log data is never "translated". Both dictionaries' keys are checked to match by
// tools/check_i18n.mjs. Parameters are written {name}.
import { derived, writable } from 'svelte/store';
import id from './i18n/id.json';
import en from './i18n/en.json';
import { load, save } from './store.js';

const DICTS = { id, en };

// Language: ?lang=en|id in the address (optional, e.g. a shared link) > the saved choice > the browser's language (first
// visit, like the server's link preview in interfaces/api/home_meta.py) > Indonesian
const asked = typeof location !== 'undefined' ? new URLSearchParams(location.search).get('lang') : null;
function browserLang() {
  if (typeof navigator === 'undefined') return 'id';
  for (const l of navigator.languages || [navigator.language || '']) { const t = String(l).slice(0, 2).toLowerCase(); if (t === 'id' || t === 'en') return t; }
  return 'id';
}
const saved = load('lang', null);
export const lang = writable(asked === 'en' || asked === 'id' ? asked : saved === 'en' || saved === 'id' ? saved : browserLang());
lang.subscribe((l) => {
  save('lang', l);
  if (typeof document !== 'undefined') document.documentElement.lang = l;
  if (asked && typeof location !== 'undefined') {   // keep ?lang= in step with the switch, so a reload or a copied link matches
    const q = new URLSearchParams(location.search);
    if (q.get('lang') !== l) { q.set('lang', l); history.replaceState(history.state, '', `${location.pathname}?${q}${location.hash}`); }
  }
});

export function translate(l, key, params) {
  let s = DICTS[l][key] ?? DICTS.id[key];
  if (s === undefined) {
    if (import.meta.env?.DEV) console.warn('kunci i18n tidak ada:', key);
    return key;
  }
  if (params) s = s.replace(/\{(\w+)\}/g, (m, k) => (params[k] ?? m));
  return s;
}

/** In components: $t(key, {param}). */
export const t = derived(lang, (l) => (key, params) => translate(l, key, params));

/** Country name from the ISO code (old: Intl.DisplayNames). */
export const countryName = derived(lang, (l) => {
  let dn;
  try { dn = new Intl.DisplayNames([l === 'en' ? 'en' : 'id'], { type: 'region' }); } catch { dn = null; }
  return (cc) => (cc && dn ? dn.of(cc) || cc : cc);
});
