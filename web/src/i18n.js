// Two languages from keyed dictionaries (DRD §6.3, U15): UI text is fetched via t('key'), not replaced in the DOM
// after render, so log data is never "translated". Both dictionaries' keys are checked to match by
// tools/cek_i18n.mjs. Parameters are written {name}.
import { derived, writable } from 'svelte/store';
import id from './i18n/id.json';
import en from './i18n/en.json';
import { load, save } from './store.js';

const KAMUS = { id, en };

export const lang = writable(load('lang', 'id') === 'en' ? 'en' : 'id');   // default ID (old)
lang.subscribe((l) => {
  save('lang', l);
  if (typeof document !== 'undefined') document.documentElement.lang = l;
});

export function translate(l, key, params) {
  let s = KAMUS[l][key] ?? KAMUS.id[key];
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
