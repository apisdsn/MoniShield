// Servers page helpers (docs/13-metrics.md): what the cards, the banner, the charts and the containers table show, worked out from
// the answers of POST /api/v1/servers and /api/v1/servers/host. Pure: no DOM, no stores; the time zone and the language come in as arguments.
import { bytes, locale, num } from './format.js';
import { groupItems } from './collectors.js';

export const RANGES = ['1h', '24h', '7d', '30d'];
export const WARN_AT = 70, HIGH_AT = 85, FULL_AT = 90;       // percent: amber, red, "disk almost full" (the server uses the same 90)
export const MAX_BANNER = 3;
const MONTHS = { id: ['Jan', 'Feb', 'Mar', 'Apr', 'Mei', 'Jun', 'Jul', 'Agu', 'Sep', 'Okt', 'Nov', 'Des'], en: ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'] };

/** Colour step of a bar: ok (teal) below 70 %, warn (amber) from 70, err (red) from 85. The number is always shown next to the bar. */
export const barTone = (pct) => (pct === null || pct === undefined ? 'none' : pct >= HIGH_AT ? 'err' : pct >= WARN_AT ? 'warn' : 'ok');

export const share = (used, total) => (used === null || used === undefined || !total ? null : Math.min(100, Math.max(0, (used / total) * 100)));

/** The percent as text without decimals above 10: 7.4 -> "7.4", 23.2 -> "23". */
export const pctText = (p, lang) => (p === null || p === undefined ? '–' : num(p < 10 ? Math.round(p * 10) / 10 : Math.round(p), lang));

/** Bytes per second: "1.8 MB/s". */
export const rate = (n, lang) => (n === null || n === undefined ? '–' : `${bytes(n, lang)}/s`);

/** The disk to show on a card: "/" else the first mount point (the server sorts "/" first). */
export const mainDisk = (h) => (h.disks || []).find((d) => d.mount === '/') || (h.disks || [])[0] || null;

/**
 * What a card says about a server, as a key for the badge: the collector's own state first (a server that is not reporting is not
 * "OK"), then the worst of the disk (90 % or more), the memory and the CPU (70 % or more, where the bar turns amber). -> {key, level}; level is the SeverityTag level ('ok', 2 or 3).
 */
export function hostStatus(h) {
  if (['offline', 'late', 'revoked'].includes(h.status)) return { key: h.status, level: h.status === 'late' ? 2 : 3 };
  const disk = (h.disks || []).some((d) => d.pct !== null && d.pct >= FULL_AT);
  if (disk) return { key: 'disk_full', level: 3 };
  const mem = share(h.mem_used, h.mem_total), cpu = h.cpu;
  if (mem !== null && mem >= WARN_AT) return { key: 'memory_high', level: 2 };
  if (cpu !== null && cpu !== undefined && cpu >= WARN_AT) return { key: 'cpu_high', level: 2 };
  if (cpu === null || cpu === undefined) return { key: 'no_data', level: 1 };
  return { key: 'ok', level: 'ok' };
}

/** The three bars of a card: [{key, pct}]; pct null when there is no current value. */
export function bars(h) {
  const d = mainDisk(h);
  return [{ key: 'cpu', pct: h.cpu ?? null }, { key: 'memory', pct: share(h.mem_used, h.mem_total) }, { key: 'disk', pct: d ? d.pct : null }];
}

export const hostKey = (h) => `${h.cid}/${h.host}`;

// Time
const local = (iso, tzMin) => new Date(Date.parse(iso) + tzMin * 60e3).toISOString();   // "2026-11-05T10:05:00.000Z" shifted to the site's zone
const clock = (iso, tzMin, lang) => local(iso, tzMin).slice(11, 16).replace(':', lang === 'en' ? ':' : '.');
const day = (iso, tzMin, lang) => { const l = local(iso, tzMin); return `${+l.slice(8, 10)} ${MONTHS[lang === 'en' ? 'en' : 'id'][+l.slice(5, 7) - 1]}`; };

/** A label on the time axis of a chart: the clock for 1 h and 24 h, the day (and the clock for 7 d) for the longer ranges. */
export function axisLabel(iso, range, tzMin, lang) {
  if (range === '1h' || range === '24h') return clock(iso, tzMin, lang);
  return range === '7d' ? `${day(iso, tzMin, lang)} ${clock(iso, tzMin, lang)}` : day(iso, tzMin, lang);
}

/** The full time in a tooltip: "5 Nov 10:05 WIB". */
export const fullLabel = (iso, tzMin, tzLabel, lang) => `${day(iso, tzMin, lang)} ${clock(iso, tzMin, lang)} ${tzLabel}`;

/** The time of "Started 10:05" in the banner and "Last seen …": the clock in the site's zone. */
export const clockAt = (iso, tzMin, lang) => (iso ? clock(iso, tzMin, lang) : '');

// Charts
/** [[iso, value], …] -> {t: [iso], v: [value]}; points without a value are dropped. */
export function points(rows) {
  const t = [], v = [];
  for (const [at, value] of rows || []) if (value !== null && value !== undefined) { t.push(at); v.push(value); }
  return { t, v };
}

/** The values of `other` at the times of `base` (null where `other` has none): the chart's second line shares the first one's axis. */
export function alignTo(base, other) {
  const by = new Map((other || []).map(([at, value]) => [at, value]));
  return (base || []).map(([at]) => by.get(at) ?? null);
}

/** Disk used as percent of the total, point by point. */
export function diskPercent(used, total) {
  const tot = new Map((total || []).map(([at, value]) => [at, value]));
  return (used || []).filter(([at, v]) => v !== null && tot.get(at)).map(([at, v]) => [at, share(v, tot.get(at))]);
}

/** The newest value of a series, or null. */
export const last = (rows) => { for (let i = (rows || []).length - 1; i >= 0; i--) if (rows[i][1] !== null && rows[i][1] !== undefined) return rows[i][1]; return null; };

/** SVG polyline points for a small chart of `values` (oldest first; null = a gap that is skipped), on a w x h box. '' when under two values. */
export function sparkPoints(values, w = 100, h = 28, pad = 2) {
  const known = (values || []).map((v, i) => [i, v]).filter(([, v]) => v !== null && v !== undefined);
  if (known.length < 2) return '';
  const lo = Math.min(...known.map(([, v]) => v)), hi = Math.max(...known.map(([, v]) => v)), span = hi - lo || 1;
  const n = values.length - 1;
  return known.map(([i, v]) => `${((i * w) / n).toFixed(1)},${(h - pad - ((v - lo) / span) * (h - 2 * pad)).toFixed(1)}`).join(' ');
}

// Containers
/** "1.7 GB / 2.0 GB", "48 MB / no limit" (the text for "no limit" comes in, it is translated). */
export function memoryText(c, lang, noLimit) {
  if (c.mem_used === null || c.mem_used === undefined) return '–';
  return `${bytes(c.mem_used, lang)} / ${c.mem_limit ? bytes(c.mem_limit, lang) : noLimit}`;
}
export const memoryShare = (c) => share(c.mem_used, c.mem_limit);

// The banner above the cards
/** One sentence part of the banner: what is unusual, in numbers the banner text puts together. */
function memOrCpu(u) { return u.name === 'mem_used' ? 'memory' : 'cpu'; }

/**
 * Unusual values and almost-full disks for the banner: at most `max` items (worst first, the disks after the unusual values), and
 * how many more there are. -> {items: [{kind: 'unusual' | 'disk', …}], more}.
 */
export function bannerItems(unusual, diskFull, max = MAX_BANNER) {
  const all = [
    ...(unusual || []).map((u) => ({ kind: 'unusual', what: memOrCpu(u), host: u.host, ctr: u.ctr || '', collector: u.collector, cid: u.cid, current: u.current, low: u.low, high: u.high, z: u.z, started: u.started })),
    ...(diskFull || []).map((d) => ({ kind: 'disk', host: d.host, ctr: '', collector: d.collector, cid: d.cid, mount: d.mount, pct: d.pct })),
  ];
  return { items: all.slice(0, max), more: Math.max(0, all.length - max) };
}

/** Two significant digits in the unit that fits the larger of the values: 764 MB and 913 MB -> "760–910 MB", 0.8 and 1.0 GB -> "0.8–1.0 GB". */
function roundedBytes(values, lang) {
  const top = Math.max(...values);
  let i = 0;
  while (top / 1024 ** i >= 1024 && i < 3) i++;
  const unit = ['B', 'KB', 'MB', 'GB'][i];
  const text = values.map((v) => {
    const x = Number((v / 1024 ** i).toPrecision(2));
    return (x >= 10 ? Math.round(x) : x).toLocaleString(locale(lang), x >= 10 ? { maximumFractionDigits: 0 } : { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  });
  return { text, unit };
}

/** A value of an unusual item in its unit: a share of CPU in percent, memory in bytes with two significant digits ("1.7 GB"). */
export function unusualValue(item, v, lang) {
  if (item.what !== 'memory') return `${pctText(v, lang)}%`;
  const { text, unit } = roundedBytes([v], lang);
  return `${text[0]} ${unit}`;
}
/** "760–910 MB" or "8.2–14%": the usual band, with the unit once. */
export function usualBand(item, lang) {
  if (item.what !== 'memory') return `${pctText(item.low, lang)}–${pctText(item.high, lang)}%`;
  const { text, unit } = roundedBytes([item.low, item.high], lang);
  return `${text[0]}–${text[1]} ${unit}`;
}

/** The distance from the usual value in standard deviations, always with one decimal ("12.0"). */
export const zText = (z, lang) => num(Math.round(z * 10) / 10, lang, 1);

// Groups
/** The host cards under their group headings: [{name, hosts}] (group names alphabetical, "No Group" = '' last). `pick` is 'all' or one group;
 *  a group that no longer exists counts as 'all'. */
export function hostSections(hosts, pick = 'all') {
  const all = groupItems((hosts || []).map((h) => ({ ...h, group: h.group || '' }))).map((g) => ({ name: g.name, hosts: g.items }));
  return pick === 'all' || !all.some((g) => g.name === pick) ? all : all.filter((g) => g.name === pick);
}

// Server Details (stage 61)
/** "12 d 4 h", "4 h 12 min", "35 min": the two largest units of an uptime (the texts come from the dictionary through `tr`). */
export function uptimeText(seconds, tr) {
  if (seconds === null || seconds === undefined) return '–';
  const m = Math.floor(seconds / 60), h = Math.floor(m / 60), d = Math.floor(h / 24);
  if (d) return tr('sv.dt.up_dh', { d, h: h % 24 });
  return h ? tr('sv.dt.up_hm', { h, m: m % 60 }) : tr('sv.dt.up_m', { m });
}

/** "1.3 / 1.9 GB" when both sizes have the same unit, else "800 MB / 1.9 GB"; '–' without a value. */
export function pairBytes(used, total, lang) {
  if (used === null || used === undefined || total === null || total === undefined) return '–';
  const a = bytes(used, lang), b = bytes(total, lang), ua = a.slice(a.lastIndexOf(' ') + 1);
  return ua === b.slice(b.lastIndexOf(' ') + 1) ? `${a.slice(0, a.lastIndexOf(' '))} / ${b}` : `${a} / ${b}`;
}

/** The text that tells an admin how to get the new numbers from a collector configuration of before stage 61. */
export const upgradeKey = (platform) => (platform === 'windows' ? 'sv.dt.upgrade_win_text' : platform === 'kubernetes' ? 'sv.dt.upgrade_k8s_text' : 'sv.dt.upgrade_text');

/**
 * The tiles of the Server Details card: [{key, label, value, sub}]. `d` = the `details` of POST /api/v1/servers/host, `tr` = translate(key, params),
 * `tzMin` = the site's offset in minutes. A missing value is '–' and an empty `sub` is ''. The Containers tile exists only on a Docker host
 * (`d.containers` is null elsewhere).
 */
export function detailTiles(d, tr, lang, tzMin) {
  const dash = '–', one = (n, k, k1) => (n === 1 ? tr(k1) : tr(k, { n: num(n, lang) }));
  const cores = d.cores, load = d.load || {}, mem = d.memory, disk = d.disk, os = d.os || {}, col = d.collector || {};
  const free = (x) => (x ? tr('sv.dt.free_cap', { size: bytes(Math.max(0, x.total - x.used), lang) }) : '');
  const tiles = [
    { key: 'uptime', label: tr('sv.dt.uptime'), value: uptimeText(d.uptime_s, tr), sub: d.booted_at ? tr('sv.dt.since_cap', { time: axisLabel(d.booted_at, '7d', tzMin, lang) }) : '' },
    { key: 'load', label: tr('sv.dt.load'), value: [load.m1, load.m5, load.m15].every((v) => v === null || v === undefined) ? dash : [load.m1, load.m5, load.m15].map((v) => num(v, lang, 2)).join(' · '),
      sub: cores ? one(cores, 'sv.dt.of_cores_cap', 'sv.dt.of_cores_one_cap') : '' },
    { key: 'cpu', label: tr('sv.dt.cpu'), value: cores ? one(cores, 'sv.dt.cores_count', 'sv.dt.cores_one_count') : dash, sub: os.arch || '' },
    { key: 'memory', label: tr('sv.dt.memory'), value: mem ? pairBytes(mem.used, mem.total, lang) : dash, sub: free(mem) },
    { key: 'disk', label: tr('sv.dt.disk', { mount: disk ? disk.mount : '/' }), value: disk ? pairBytes(disk.used, disk.total, lang) : dash, sub: free(disk) },
  ];
  const c = d.containers;
  if (c) {
    const r = c.restarts_24h || 0;
    tiles.push({ key: 'containers', label: tr('sv.dt.containers'), value: tr('sv.dt.running_cap', { n: num(c.running, lang) }),
      sub: `${tr('sv.dt.stopped_cap', { n: num(c.stopped, lang) })} · ${r === 1 ? tr('sv.dt.restart_one_cap') : tr('sv.dt.restarts_cap', { n: num(r, lang) })}` });
  }
  tiles.push({ key: 'collector', label: tr('sv.dt.collector'), value: col.version || dash, sub: [col.name, col.group].filter(Boolean).join(' · ') },
    { key: 'os', label: tr('sv.dt.os'), value: os.name || dash, sub: os.kernel || '' });
  return tiles;
}

/** The Load Average chart: three lines and the dashed core count (null until the server sends the number of cores). */
export function loadSets(series, tr) {
  const l = series.load || {};
  const base = (l.m1 || []).filter(([, v]) => v !== null);
  const sets = [{ label: tr('sv.l.m1'), data: points(l.m1).v, color: '--c1' }, { label: tr('sv.l.m5'), data: alignTo(base, l.m5), color: '--c2' }, { label: tr('sv.l.m15'), data: alignTo(base, l.m15), color: '--c3' }];
  if (l.cores) sets.push({ label: tr('sv.l.cores'), data: base.map(() => l.cores), color: '--muted', dashed: true });
  return { base, sets };
}

/** The Disk I/O chart: bytes read and written per second. */
export function diskIoSets(series, tr) {
  const io = series.disk_io || {};
  const base = (io.read || []).filter(([, v]) => v !== null);
  return { base, sets: [{ label: tr('sv.l.read'), data: points(io.read).v, color: '--c1' }, { label: tr('sv.l.written'), data: alignTo(base, io.write), color: '--c2' }] };
}
