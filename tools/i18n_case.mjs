// Capitalisation of the UI text (docs/08-architecture.md, "UI text"): labels are Title Case, sentences are sentence case.
// Used by tools/check_i18n.mjs; `titleCase` is also what rewrites a wrong label (see "Fixing" in that file).
//
// A key holds a LABEL (page and card titles, section headings, buttons, tabs, menu items, column headers, field labels, badges)
// unless one of these makes it a SENTENCE or a fragment, which keep sentence case:
//   - the last-but-one or last part of its name is one of SENTENCE_PARTS (`.hint`, `.text`, `.note`, `.ph` (placeholder), `.err`, `.done` …)
//   - the key is listed in tools/i18n_sentence_keys.json (the few that the other rules cannot tell)
//   - the text ends with . ? ! : … , or starts with a lower-case letter or a placeholder ({n} requests), or has more than 7 words
//   - it holds a message placeholder ({msg}, {list}) or a quoted one
// Name a new key with one of the parts above when it is a sentence, and the check stays quiet; otherwise write it in Title Case.
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

export const SMALL = {
  en: new Set(['a', 'an', 'and', 'as', 'at', 'by', 'for', 'in', 'of', 'on', 'or', 'the', 'to', 'with']),
  id: new Set(['di', 'ke', 'dari', 'dan', 'atau', 'yang', 'untuk', 'per', 'dengan']),
};
// Product names and acronyms keep their form, in both languages (matched without regard to case; the listed spelling is written).
export const KEEP = ['MoniShield', 'S3', 'Kafka', 'CPU', 'RAM', 'SMTP', 'IP', 'IPs', 'URL', 'URLs', 'HTTP', 'HTTPS', 'ID', 'EN', 'JWT', 'JWTs', 'API', 'DNS', 'OTP', 'OTPs', 'CSV', 'PDF',
  'UTC', 'WIB', 'TLS', 'SASL', 'STS', 'CRS', 'CAPEC', 'OWASP', 'ASN', 'GeoIP', 'GeoLite2', 'MaxMind', 'Docker', 'Kubernetes', 'Linux', 'Windows', 'Telegram', 'Discord', 'Swagger', 'Rancher',
  'Longhorn', 'values.yaml', 'config.yaml', 'Uptime-Kuma', 'Log4Shell', 'WordPress', 'CMS', 'PHP', 'CGI', 'SQLi', 'XSS', 'LFI', 'RCE', 'UA', 'AWS', 'GCS', 'R2', 'MinIO', 'Wasabi', 'CVE', 'ms', 'nginx',
  'journald', 'ingress-nginx', 'coredns', 'requestId', 'requestIds', 'env', '.env', 'e.g.', 'vs', 'UTF-8', 'HTML', 'SQL', 'JSON', 'YAML', 'Helm', 'Ctrl+K'];
const KEEP_BY_LOWER = new Map(KEEP.map((w) => [w.toLowerCase(), w]));
// after a number these are units, not words ("Last 24 h", "5 min")
const UNITS = new Set(['h', 'd', 'min', 's', 'ms', 'kb', 'mb', 'gb', 'x']);

// A part of the key counts when it is one of these or ends with `_<one of these>` (`cpu_cap`, `delete_aria`, `upgrade_hint`).
export const SENTENCE_PARTS = new Set(['hint', 'hints', 'text', 'note', 'notes', 'intro', 'desc', 'ph', 'err', 'error', 'msg', 'sub', 'toast', 'done', 'saved', 'cleared', 'why',
  'help', 'tip', 'lead', 'count', 'count_one', 'aria', 'cap', 'body']);
// Of these, a full sentence ends with a period (the check below); `ph` (placeholders) and `err` fragments are left alone.
const PERIOD_PARTS = new Set(['hint', 'hints', 'text', 'note', 'notes', 'intro', 'desc', 'toast', 'done', 'saved', 'cleared', 'why', 'help', 'tip', 'lead', 'body']);
const DIR = dirname(fileURLToPath(import.meta.url));
const LISTS = JSON.parse(readFileSync(join(DIR, 'i18n_sentence_keys.json'), 'utf8'));
export const PERIOD_KEYS = new Set(LISTS.sentences);
export const SENTENCE_KEYS = new Set([...LISTS.keys, ...LISTS.sentences]);

const words = (s) => s.split(/\s+/).filter((w) => /[\p{L}\p{N}]/u.test(w));

const isSentencePart = (p) => SENTENCE_PARTS.has(p) || SENTENCE_PARTS.has(p.slice(p.lastIndexOf('_') + 1));
const isPeriodPart = (p) => PERIOD_PARTS.has(p) || PERIOD_PARTS.has(p.slice(p.lastIndexOf('_') + 1));

/** Is this key's text a label (Title Case) rather than a sentence or a fragment? `key` is the dictionary key, `value` the English text. */
export function isLabel(key, value) {
  const v = String(value).trim();
  if (!v || SENTENCE_KEYS.has(key)) return false;
  const parts = key.split('.');
  if (parts.some(isSentencePart) || parts[0] === 'err' || key.startsWith('imp.err.') || key.startsWith('adm.err.')) return false;
  if (/[.?!:…,;]$/.test(v) || /^[^\p{Lu}\p{N}]/u.test(v)) return false;        // a sentence, or a fragment that starts in lower case or with a placeholder
  if (/\{(msg|list|q)\}|'\{/.test(v) || words(v).length > 7) return false;
  return true;
}

function capitalize(w) { return w[0].toLocaleUpperCase() + w.slice(1); }

/** One word (no spaces): Title Case unless it keeps its form. `first` = the first word of the text, `small` = the small words of the language. */
function word(w, first, small, prev) {
  const m = /^([^\p{L}\p{N}{.]*)(.*?)([^\p{L}\p{N}}]*)$/u.exec(w);
  const [, lead, core, tail] = m;
  if (!core) return w;
  if (core.startsWith('{')) return w;                                         // a placeholder
  const keep = KEEP_BY_LOWER.get(core.toLowerCase());
  if (keep) return lead + keep + tail;
  if (/^\p{N}/u.test(core)) return w;                                         // 5xx, 401, 24, 2xx
  if (prev && /^\p{N}/u.test(prev) && UNITS.has(core.toLowerCase())) return w;   // 24 h
  if (/\p{Lu}/u.test(core.slice(1))) return w;                                // mixed case such as requestId, SQLi, McAfee
  if (core.includes('-') || core.includes('/')) {
    // hyphenated and slashed compounds: each part on its own, small words inside stay small
    return lead + core.split(/([-/])/).map((p, i) => (p === '-' || p === '/' || !p ? p : word(p, first && i === 0, small, null))).join('') + tail;
  }
  if (!first && small.has(core.toLowerCase())) return lead + core.toLowerCase() + tail;
  if (/^\p{Lu}+$/u.test(core)) return w;                                      // an acronym that is not listed (SSL)
  return lead + capitalize(core) + tail;
}

/** Title Case of a text in `lang` ('en' | 'id'): small words stay lower case unless first; product names, acronyms and placeholders keep their form. */
export function titleCase(text, lang) {
  const small = SMALL[lang] || SMALL.en;
  const parts = String(text).split(/(\s+)/);
  let firstDone = false, prev = null;
  return parts.map((p) => {
    if (!p.trim()) return p;
    const hasLetter = /[\p{L}\p{N}]/u.test(p);
    if (!hasLetter) return p;
    const out = word(p, !firstDone, small, prev);
    firstDone = true; prev = p;
    return out;
  }).join('');
}

/** The keys whose text is a label but is not in Title Case: [{key, lang, value, want}]. `en` and `id` are the two dictionaries. */
export function labelProblems(en, id) {
  const out = [];
  for (const [key, value] of Object.entries(en)) {
    if (!isLabel(key, value)) continue;
    for (const [lang, dict] of [['en', en], ['id', id]]) {
      const v = dict[key];
      if (v === undefined || /[.?!:…,;]$/.test(v.trim()) || /^[^\p{Lu}\p{N}]/u.test(v.trim())) continue;   // a sentence or fragment in this language
      const want = titleCase(v, lang);
      if (want !== v) out.push({ key, lang, value: v, want });
    }
  }
  return out;
}

/** A sentence in a description, hint, note or message part of the key (4 words or more, starting in upper case) ends with a period. */
export function needsPeriod(key, value) {
  const v = String(value).trim();
  if (!/^\p{Lu}/u.test(v) || /[.?!:…]$/.test(v) || key.split('.').includes('ph')) return false;     // a placeholder has no period
  if (PERIOD_KEYS.has(key)) return true;
  return !LISTS.keys.includes(key) && key.split('.').some(isPeriodPart) && words(v).length >= 4;
}

/** [{key, lang, value, want}] for the sentences that lack their period. */
export function periodProblems(en, id) {
  const out = [];
  for (const [key, value] of Object.entries(en)) {
    for (const [lang, dict] of [['en', en], ['id', id]]) {
      const v = dict[key];
      if (v !== undefined && needsPeriod(key, en[key]) && !/[.?!:…]$/.test(v.trim())) out.push({ key, lang, value: v, want: v.trimEnd() + '.' });
    }
  }
  return out;
}
