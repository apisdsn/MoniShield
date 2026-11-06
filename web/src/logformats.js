// Log Formats page helpers (web/src/pages/LogFormats.svelte). Pure: no DOM, no stores. `override` follows
// monishield/domain/log_formats.py (override); both run the cases of tests/fixtures/override_cases.json.

/** Default kind of each preset (monishield/domain/log_formats.py, PRESETS). */
export const PRESET_KIND = {
  'ingress-nginx': 'http', 'nginx-frontend': 'http', coredns: 'app', 'events-json': 'app', 'spring-boot': 'app', 'nginx-combined': 'http',
  'caddy-json': 'http', 'apache-combined': 'http', json: 'app', logfmt: 'app', syslog: 'app', regex: 'app', auto: null, plain: 'app',
};
export const FEATURES = ['logins', 'pdf', 'tracing'];
export const DURATION_UNITS = ['ms', 's', 'us', 'ns'];
const MATCH = /^(?:[A-Za-z0-9*?._-]+\/)?[A-Za-z0-9*?._-]+$/;

const glob = (g) => new RegExp('^' + g.replace(/[.+^${}()|[\]\\]/g, '\\$&').replace(/\*/g, '.*').replace(/\?/g, '.') + '$');

/** Does the rule match the service (and namespace)? Like fnmatch: `*` and `?`, case sensitive. */
export function ruleMatches(rule, ns, service) {
  const m = rule.match, cut = m.indexOf('/');
  if (cut >= 0 && !glob(m.slice(0, cut)).test(ns || '')) return false;
  return glob(m.slice(cut + 1)).test(service || '');
}

/** Position of the first rule that matches, or -1. */
export const matchIndex = (rules, ns, service) => rules.findIndex((r) => ruleMatches(r, ns, service));

/** `namespace/service`, or `service` when there is no namespace or it cannot be written in a rule; null when neither can. */
export function overrideKey(ns, service) {
  for (const key of [ns ? `${ns}/${service}` : null, service]) if (key && MATCH.test(key) && !/[*?]/.test(key)) return key;
  return null;
}

export const blankRule = (match, format) => ({ match, format, kind: PRESET_KIND[format] ?? null, fields: {}, pattern: '', time_format: 'iso', multiline: '', levels: {},
                                              tag: '', features: [], ip_header: '', duration_unit: 'ms' });

/** Rules after choosing preset `fmt` for one service: a rule `namespace/service` above the rule that reads it now; again = the same
 *  rule is edited; the format the rule below already gives removes it. null when the service cannot be named in a rule. */
export function override(rules, ns, service, fmt) {
  const key = overrideKey(ns, service);
  if (key === null || !(fmt in PRESET_KIND) || fmt === 'regex' || fmt === 'auto') return null;
  const out = [...rules];
  const own = out.findIndex((r) => r.match === key);
  const below = out.slice(own >= 0 ? own + 1 : 0).find((r) => ruleMatches(r, ns, service));
  if (below && below.format === fmt) { if (own >= 0) out.splice(own, 1); return out; }
  if (own >= 0) out[own] = blankRule(key, fmt);
  else out.splice(Math.max(0, out.findIndex((r) => ruleMatches(r, ns, service))), 0, blankRule(key, fmt));
  return out;
}

const norm = (r) => JSON.stringify(r);

/** How many changes the draft holds against the saved rules: rules changed, added, removed, plus one when the order differs. */
export function changeCount(saved, draft) {
  const old = new Map(saved.map((r) => [r.match, norm(r)])), now = new Map(draft.map((r) => [r.match, norm(r)]));
  let n = 0;
  for (const [m, j] of now) if (!old.has(m) || old.get(m) !== j) n++;
  for (const m of old.keys()) if (!now.has(m)) n++;
  const common = (list, other) => list.filter((r) => other.has(r.match)).map((r) => r.match).join('\n');
  if (common(saved, now) !== common(draft, old)) n++;
  return n;
}

/** Move rule i up (-1) or down (+1). The last rule `*` stays last and nothing moves below it; null when the move is not possible. */
export function moveRule(rules, i, dir) {
  const j = i + dir, last = rules.length - 1;
  if (i < 0 || i >= last || j < 0 || j >= last) return null;
  const out = [...rules];
  [out[i], out[j]] = [out[j], out[i]];
  return out;
}

/** Remove rule i; never the last rule (the catch-all). */
export const removeRule = (rules, i) => (i < 0 || i >= rules.length - 1 ? null : rules.filter((_, k) => k !== i));

/** Insert a new rule above the catch-all (the last rule) or replace rule i. */
export function putRule(rules, i, rule) {
  const out = [...rules];
  if (i >= 0) out[i] = rule; else out.splice(Math.max(0, out.length - 1), 0, rule);
  return out;
}

/** Text of a table `{a: "b"}` as lines `a = b`, and back. parseLines gives {map} or {error: line number}. */
export const formatLines = (o) => Object.entries(o || {}).map(([k, v]) => `${k} = ${v}`).join('\n');
export function parseLines(text) {
  const map = {};
  const lines = String(text || '').split('\n');
  for (let i = 0; i < lines.length; i++) {
    const l = lines[i].trim();
    if (!l) continue;
    const m = /^([^=\s][^=]*?)\s*=\s*(\S.*)$/.exec(l);
    if (!m) return { error: i + 1 };
    map[m[1]] = m[2].trim();
  }
  return { map };
}

/** Formats a service can be set to from the select: the formats that need no settings, plus the one in use (a regex rule, say). */
export const optionsFor = (formats, current) => (current && !formats.includes(current) ? [...formats, current] : formats);

/** Services list after the toolbar: text search (name, host), source, only those that read badly. */
export function filterServices(rows, { q = '', source = 'all', bad = false } = {}) {
  const needle = q.trim().toLowerCase();
  return rows.filter((r) => (source === 'all' || r.source === source) && (!bad || r.bad)
    && (!needle || r.service.toLowerCase().includes(needle) || (r.namespace || '').toLowerCase().includes(needle)));
}

/** Does the service read badly: under `limit` percent of its lines read, or another format would read it better. */
export const readsBadly = (pct, suggested, limit = 95) => (pct !== null && pct !== undefined && pct < limit) || !!suggested;

/** Percent text: "99.8%"; whole numbers without decimals. */
export const pctText = (p, lang = 'en') => (p === null || p === undefined ? '' : `${new Intl.NumberFormat(lang === 'id' ? 'id-ID' : 'en-US', { maximumFractionDigits: 1 }).format(p)}%`);
