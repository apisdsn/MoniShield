// Display helpers shared by the analysis pages of stage 62 (Availability, Root Causes, Request Tracing, Containers, Business, Analysis Settings).
const NAMES = { 'caddy-json': 'Caddy JSON', 'nginx-combined': 'nginx combined', 'apache-combined': 'Apache combined', 'nginx-frontend': 'nginx', 'ingress-nginx': 'ingress-nginx',
                json: 'JSON', logfmt: 'logfmt', syslog: 'syslog', regex: 'regex', plain: 'plain text', 'spring-boot': 'Spring Boot', 'events-json': 'events JSON', coredns: 'CoreDNS' };

/** A format preset -> the name people know it by ("caddy-json" -> "Caddy JSON"); unknown presets are shown as they are. */
export const formatName = (f) => NAMES[f] || f || '';

/** Percent with a sensible number of digits: 0,92%, 1,4%, 90,2%, 100%. */
export function share(a, b, num, lang) {
  if (!b) return '–';
  const p = (a / b) * 100;
  return `${num(p, lang, p === 0 || p >= 10 ? (p === 100 || p === 0 ? 0 : 1) : p >= 1 ? 1 : 2)}%`;
}

/** The match of a business rule as one line: "POST /api/orders · 2xx" is built by the page with its own words; this gives the parts. */
export const ruleParts = (r) => [r.method, r.path].filter(Boolean).join(' ');
