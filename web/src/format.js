// Display formatters: counterparts of tWIB, dur, tRange, dLabel, fmt, dlt in dashboard_template.html (inv. §2.0).
// Pure functions: the language always comes via the `lang` argument ('id' | 'en'), so they can be tested without a browser.
// Time input from the API is already WIB in the old format: 'YYYY-MM-DD HH:MM' (minute) or 'YYYY-MM-DD HH' (hour).

const MONTHS_ID = ['Jan', 'Feb', 'Mar', 'Apr', 'Mei', 'Jun', 'Jul', 'Agu', 'Sep', 'Okt', 'Nov', 'Des'];
const MONTHS_EN = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

export const locale = (lang) => (lang === 'en' ? 'en-US' : 'id-ID');

/** Numbers: 1.234 / 1,234; fractions rounded to 3 digits like the old tables. null -> '–' (U16). */
export function num(n, lang, digits) {
  if (n === null || n === undefined || Number.isNaN(n)) return '–';
  const v = digits === undefined ? +(+n).toFixed(3) : n;
  return v.toLocaleString(locale(lang), digits === undefined ? undefined : { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

/** '2026-09-28 06:03' -> '28 Sep 2026 06.03 WIB' (EN 06:03); '2026-09-28 06' -> '28 Sep 06.00'. */
export function tWIB(s, lang) {
  if (!s) return '-';
  const [d, hm = ''] = s.split(' ');
  const [y, m, dd] = d.split('-');
  const sep = lang === 'en' ? ':' : '.';
  const monthName = (lang === 'en' ? MONTHS_EN : MONTHS_ID)[m - 1];
  return hm.length === 2 ? `${+dd} ${monthName} ${hm}${sep}00` : `${+dd} ${monthName} ${y} ${hm.replace(':', sep)} WIB`;
}

/** Date only: '2026-10-06' -> '6 Okt 2026'. */
export const dLabel = (d, lang) => tWIB(`${d} 00:00`, lang).replace(/ 00[.:]00 WIB$/, '');

const FOLDER = /^\d{4}-\d{2}-\d{2}$/;
const shift = (d, n) => { const t = new Date(`${d}T00:00:00Z`); t.setUTCDate(t.getUTCDate() + n); return t.toISOString().slice(0, 10); };

/** Folder name -> the day its logs cover. A folder holds (D-1 00:00, D 00:00] WIB for S3 and Kafka alike, so the folder
 *  '2026-10-21' is the logs of '2026-10-20'. Everything shown to people uses the log day; the folder name stays in addresses. */
export const logDay = (folder) => shift(folder, -1);

/** The day of the logs -> the folder that holds it (inverse of logDay). */
export const folderOfDay = (day) => shift(day, 1);

/** Folder name -> label of its log day: '2026-10-21' -> '20 Okt 2026'. Anything that is not a date folder is returned as is. */
export const fLabel = (folder, lang) => (FOLDER.test(folder || '') ? dLabel(logDay(folder), lang) : folder ?? '');

/** Origin of a folder (API `source`) -> the label key suffix: 's3' | 'kafka' (a folder holds one source);
 *  null for the main log folder and uploads (no marker). */
export const folderTag = (source) => (source === 's3' || source === 'kafka' ? source : null);

/** Date without year: '2026-10-05 09:00' -> '5 Okt'. */
function dShort(s, lang) {
  const [, m, dd] = s.slice(0, 10).split('-');
  return `${+dd} ${(lang === 'en' ? MONTHS_EN : MONTHS_ID)[m - 1]}`;
}

/** Time only: '2026-10-05 09:00' -> '09.00' / '09:00'. */
export const hm = (s, lang) => s.slice(11, 16).replace(':', lang === 'en' ? ':' : '.');

/** Time range, merged when the dates are the same (old). */
export function tRange(a, b, lang) {
  if (!a || !b) return tWIB(a || b, lang);
  if (a === b) return tWIB(a, lang);
  if (a.slice(0, 10) === b.slice(0, 10)) return `${tWIB(a, lang).replace(' WIB', '')} – ${hm(b, lang)} WIB`;
  return `${tWIB(a, lang)} – ${tWIB(b, lang)}`;
}

/** Log content range for the subtitle (U2): '5 Okt 09.00–6 Okt 00.59 WIB'; single date: '6 Okt 00.00–23.59 WIB'. */
export function logRange(a, b, lang) {
  if (!a || !b) return null;
  return a.slice(0, 10) === b.slice(0, 10)
    ? `${dShort(a, lang)} ${hm(a, lang)}–${hm(b, lang)} WIB`
    : `${dShort(a, lang)} ${hm(a, lang)}–${dShort(b, lang)} ${hm(b, lang)} WIB`;
}

/** Duration in seconds: '850 ms' / '2,35 dtk' / '1 mnt 52 dtk' (EN: s, min). */
export function dur(s, lang) {
  if (s === null || s === undefined) return '–';
  const en = lang === 'en';
  if (s < 1) return `${num(Math.round(s * 1000), lang)} ms`;
  if (s < 60) return `${(+s.toFixed(2)).toLocaleString(locale(lang))} ${en ? 's' : 'dtk'}`;
  return `${Math.floor(s / 60)} ${en ? 'min' : 'mnt'} ${Math.round(s % 60)} ${en ? 's' : 'dtk'}`;
}

/** Duration in milliseconds (API data shape). */
/** UTC time from the account/ingest server ('YYYY-MM-DD HH:MM[:SS]') -> 'YYYY-MM-DD HH:MM' WIB (UTC+7), for tWIB(). */
export function utcToWib(s) {
  if (!/^\d{4}-\d\d-\d\d[ T]\d\d:\d\d/.test(s || '')) return null;
  const d = new Date(s.slice(0, 16).replace(' ', 'T') + ':00Z');
  if (Number.isNaN(+d)) return null;
  return new Date(+d + 7 * 3600e3).toISOString().slice(0, 16).replace('T', ' ');
}

export const durMs = (ms, lang) => (ms === null || ms === undefined ? '–' : dur(ms / 1000, lang));

/** File size: 1.536 -> '1,5 KB'. */
export function bytes(n, lang) {
  if (n === null || n === undefined) return '–';
  const u = ['B', 'KB', 'MB', 'GB'];
  let i = 0;
  while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
  return `${(+n.toFixed(i ? 1 : 0)).toLocaleString(locale(lang))} ${u[i]}`;
}

/** Percent: 0,1234 -> '12,3%'. */
export const pct = (x, lang, digits = 1) =>
  x === null || x === undefined ? '–' : `${(x * 100).toLocaleString(locale(lang), { minimumFractionDigits: digits, maximumFractionDigits: digits })}%`;

/**
 * Change vs the previous folder (old: dlt). Returns {kind, text, tone} or null.
 * kind: 'up' | 'down' | 'same' | 'new' | 'incomplete'; tone: 'bad' | 'good' | null (color is not the only cue: text is always present).
 * `good`: going up is good. `comparable`: the previous folder's log lines >= 50 % of this folder (computed by the caller).
 * `label`: comparison name other than a folder date (N-day average, 2026-10-07).
 */
export function delta(cur, prev, prevFolder, lang, { good = false, comparable = true, label = null } = {}) {
  if (prev === null || prev === undefined) return null;
  const en = lang === 'en', since = label || fLabel(prevFolder, lang);   // the day the previous folder's logs cover   // label: comparison other than a folder, e.g. "rata-rata 7 hari" (7-day average)
  if (label && !comparable) return null;
  if (!comparable) return { kind: 'incomplete', tone: null, text: en ? `${since} log incomplete, not compared` : `Log ${since} tidak lengkap, tidak dibandingkan` };
  if (!prev) return cur ? { kind: 'new', tone: null, text: en ? `New (${since}: 0)` : `Baru (${since}: 0)`, short: en ? 'New' : 'Baru', rest: `${since}: 0` } : null;
  const p = ((cur - prev) / prev) * 100;
  if (Math.abs(p) < 0.5) return { kind: 'same', tone: null, text: en ? `≈ Same as ${since}` : `≈ Sama dengan ${since}` };
  const isUp = p > 0;
  return {
    kind: isUp ? 'up' : 'down',
    tone: isUp !== good ? 'bad' : 'good',
    text: `${isUp ? '▲' : '▼'} ${Math.abs(p).toFixed(0)}% vs ${since}`,
    short: `${isUp ? '▲' : '▼'} ${Math.abs(p).toFixed(0)}%`,     // badge next to the KPI number (reference style)
    rest: `vs ${since}`,
    spoken: en ? `${isUp ? 'up' : 'down'} ${Math.abs(p).toFixed(0)}% vs ${since}` : `${isUp ? 'naik' : 'turun'} ${Math.abs(p).toFixed(0)}% dibanding ${since}`,
  };
}

/** System names (service, pod, namespace, host, upstream, module): always lowercase as in the cluster, not affected by
 *  the UI's Capitalize Each Word text (owner decision 2026-10-06; old: tc() capitalized service names).
 *  In elements that capitalize via CSS, wrap them with class "sys". */
export const sysName = (s) => String(s ?? '').toLowerCase();

/** Truncate labels (horizontal bar chart: 48, narrow screen 28). */
export const cut = (s, n) => (String(s).length > n ? String(s).slice(0, n - 1) + '…' : String(s));

/** ASSUMPTION (DRD §6.6 "practically empty"): a folder with fewer log lines than this is flagged as incomplete (the corrupt
 *  file count is mentioned too). Corrupt files alone are not enough: even full folders often have 1–3 files with corrupt lines. */
export const SPARSE_LINES = 1000;
