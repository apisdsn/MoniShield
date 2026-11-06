// Servers page helpers (web/src/servers.js): bar colours, card status, chart data, banner items.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { barTone, hostStatus, bars, axisLabel, fullLabel, points, alignTo, diskPercent, last, sparkPoints, bannerItems, usualBand, memoryText, memoryShare, pctText, rate, unusualValue, zText } from '../web/src/servers.js';
import { hostSections } from '../web/src/servers.js';
import { parse, build } from '../web/src/state.js';

test('bar colours: teal below 70, amber from 70, red from 85; no value has none', () => {
  assert.deepEqual([0, 69.9, 70, 84.9, 85, 100].map(barTone), ['ok', 'ok', 'warn', 'warn', 'err', 'err']);
  assert.equal(barTone(null), 'none');
});

test('card status: the collector state first, then disk, memory, CPU', () => {
  const ok = { status: 'online', cpu: 20, mem_used: 2, mem_total: 8, disks: [{ mount: '/', pct: 40 }] };
  assert.deepEqual(hostStatus(ok), { key: 'ok', level: 'ok' });
  assert.equal(hostStatus({ ...ok, status: 'offline' }).key, 'offline');
  assert.equal(hostStatus({ ...ok, status: 'late' }).level, 2);
  assert.equal(hostStatus({ ...ok, disks: [{ mount: '/data', pct: 90 }] }).key, 'disk_full');
  assert.equal(hostStatus({ ...ok, mem_used: 6 }).key, 'memory_high');
  assert.equal(hostStatus({ ...ok, cpu: 90 }).key, 'cpu_high');
  assert.equal(hostStatus({ ...ok, cpu: null }).key, 'no_data');
});

test('the three bars of a card', () => {
  const h = { cpu: 23, mem_used: 4, mem_total: 8, disks: [{ mount: '/data', pct: 10 }, { mount: '/', pct: 41 }] };
  assert.deepEqual(bars(h), [{ key: 'cpu', pct: 23 }, { key: 'memory', pct: 50 }, { key: 'disk', pct: 41 }]);
  assert.deepEqual(bars({ cpu: null, mem_used: null, mem_total: null, disks: [] }).map((b) => b.pct), [null, null, null]);
});

test('time labels follow the site zone and the language', () => {
  const t = '2026-11-05T03:05:00Z';
  assert.equal(axisLabel(t, '24h', 420, 'en'), '10:05');
  assert.equal(axisLabel(t, '1h', 420, 'id'), '10.05');
  assert.equal(axisLabel(t, '7d', 420, 'en'), '5 Nov 10:05');
  assert.equal(axisLabel(t, '30d', 420, 'id'), '5 Nov');
  assert.equal(fullLabel('2026-11-05T20:30:00Z', 420, 'WIB', 'en'), '6 Nov 03:30 WIB');
});

test('buckets become chart data', () => {
  const rows = [['a', 1], ['b', null], ['c', 3]];
  assert.deepEqual(points(rows), { t: ['a', 'c'], v: [1, 3] });
  assert.deepEqual(alignTo([['a'], ['c'], ['d']], [['a', 9], ['c', null]]), [9, null, null]);
  assert.deepEqual(diskPercent([['a', 50], ['b', 10]], [['a', 200]]), [['a', 25]]);
  assert.equal(last([['a', 1], ['b', null]]), 1);
  assert.equal(last([]), null);
});

test('sparkline points skip gaps and need two values', () => {
  assert.equal(sparkPoints([null, 5]), '');
  assert.equal(sparkPoints([1, null, 3], 100, 28, 2), '0.0,26.0 100.0,2.0');
  assert.equal(sparkPoints([4, 4], 100, 28, 2).split(' ').length, 2);
});

test('banner: at most three items, unusual first, then disks, and how many more', () => {
  const u = (n) => ({ host: 'h' + n, ctr: n % 2 ? 'c' + n : '', name: n % 2 ? 'mem_used' : 'cpu', current: 1, low: 1, high: 2, z: 4, cid: 1, collector: 'x', started: null });
  const out = bannerItems([u(1), u(2)], [{ host: 'd', mount: '/', pct: 95, cid: 1, collector: 'x' }, { host: 'e', mount: '/', pct: 91, cid: 1, collector: 'x' }]);
  assert.deepEqual(out.items.map((i) => i.kind), ['unusual', 'unusual', 'disk']);
  assert.equal(out.items[0].what, 'memory'); assert.equal(out.items[1].what, 'cpu'); assert.equal(out.more, 1);
  assert.deepEqual(bannerItems([], []), { items: [], more: 0 });
});

test('numbers in the banner and the containers table', () => {
  assert.equal(usualBand({ what: 'cpu', low: 8.2, high: 14.4 }, 'en'), '8.2–14%');
  const MB = 1024 * 1024;
  assert.equal(usualBand({ what: 'memory', low: 800 * MB, high: 900 * MB }, 'en'), '800–900 MB');
  assert.equal(usualBand({ what: 'memory', low: 764.1 * MB, high: 912.8 * MB }, 'en'), '760–910 MB');           // two significant digits
  assert.equal(usualBand({ what: 'memory', low: 0.8 * 1024 * MB, high: 1.04 * 1024 * MB }, 'en'), '0.8–1.0 GB');   // the unit of the larger value
  assert.equal(usualBand({ what: 'memory', low: 700 * MB, high: 1.2 * 1024 * MB }, 'id'), '0,7–1,2 GB');
  assert.equal(unusualValue({ what: 'memory' }, 1.7 * 1024 * MB, 'en'), '1.7 GB');
  assert.equal(unusualValue({ what: 'memory' }, 1736 * MB, 'en'), '1.7 GB');
  assert.equal(unusualValue({ what: 'memory' }, 48.4 * MB, 'en'), '48 MB');
  assert.equal(unusualValue({ what: 'cpu' }, 52.31, 'en'), '52%');
  assert.equal(zText(11.64, 'en'), '11.6'); assert.equal(zText(12, 'en'), '12.0'); assert.equal(zText(3.14159, 'id'), '3,1');
  assert.equal(memoryText({ mem_used: 48 * MB, mem_limit: 0 }, 'en', 'no limit'), '48 MB / no limit');
  assert.equal(memoryText({ mem_used: null }, 'en', 'x'), '–');
  assert.equal(memoryShare({ mem_used: 50, mem_limit: 200 }), 25);
  assert.equal(memoryShare({ mem_used: 50, mem_limit: 0 }), null);
  assert.equal(pctText(7.44, 'en'), '7.4'); assert.equal(pctText(23.2, 'en'), '23');
  assert.equal(rate(1024, 'en'), '1 KB/s');
});

test('Raw Logs link of a container: host as pod, container as service, after "#"', () => {
  const base = { folder: null, module: null, source: 'collector', service: null };
  const url = build({ ...base, tab: 'raw-logs', pod: 'web-01', svc: 'api' });
  assert.equal(url, '/raw-logs?source=collector#pod=web-01&svc=api');
  assert.equal(parse(url).svc, 'api');
  assert.equal(parse('/security?source=collector#svc=api').svc, null);
  assert.equal(parse('/servers').tab, 'servers');
});

test('host cards under group headings, with the group filter', () => {
  const hosts = [{ host: 'a', group: 'Client B' }, { host: 'b', group: 'Client A' }, { host: 'c', group: '' }, { host: 'd' }, { host: 'e', group: 'Client A' }];
  assert.deepEqual(hostSections(hosts).map((s) => [s.name, s.hosts.map((h) => h.host)]), [['Client A', ['b', 'e']], ['Client B', ['a']], ['', ['c', 'd']]]);
  assert.deepEqual(hostSections(hosts, 'Client B').map((s) => s.name), ['Client B']);
  assert.deepEqual(hostSections(hosts, '').map((s) => s.name), ['']);
  assert.equal(hostSections(hosts, 'Gone').length, 3);                      // a group that no longer exists shows everything
  assert.deepEqual(hostSections([]), []);
});

// Server Details (stage 61)
import { readFileSync } from 'node:fs';
import { detailTiles, diskIoSets, loadSets, pairBytes, upgradeKey, uptimeText } from '../web/src/servers.js';

const EN = JSON.parse(readFileSync(new URL('../web/src/i18n/en.json', import.meta.url), 'utf8'));
const tr = (key, p = {}) => EN[key].replace(/\{(\w+)\}/g, (_, k) => p[k]);
const DAY = 86400;

test('an uptime shows its two largest units', () => {
  assert.equal(uptimeText(12 * DAY + 4 * 3600 + 30, tr), '12 d 4 h');
  assert.equal(uptimeText(4 * 3600 + 12 * 60, tr), '4 h 12 min');
  assert.equal(uptimeText(35 * 60 + 5, tr), '35 min');
  assert.equal(uptimeText(10, tr), '0 min');
  assert.equal(uptimeText(null, tr), '–');
});

test('two sizes share their unit when they have the same one', () => {
  const GB = 1024 ** 3;
  assert.equal(pairBytes(1.3 * GB, 1.9 * GB, 'en'), '1.3 / 1.9 GB');
  assert.equal(pairBytes(800 * 1024 ** 2, 1.9 * GB, 'en'), '800 MB / 1.9 GB');
  assert.equal(pairBytes(null, 1, 'en'), '–');
});

const DETAILS = {
  uptime_s: 12 * DAY + 4 * 3600, booted_at: '2026-10-25T03:02:00Z', cores: 2, load: { m1: 0.42, m5: 0.38, m15: 0.35 }, memory: { used: 1.3 * 1024 ** 3, total: 1.9 * 1024 ** 3 },
  disk: { mount: '/', used: 21 * 1024 ** 3, total: 40 * 1024 ** 3 }, containers: { running: 8, stopped: 0, restarts_24h: 0 }, collector: { version: '0.163.2', name: 'docker-host-01', group: 'Internal', last_seen: null },
  os: { name: 'Ubuntu 24.04.5 LTS', kernel: 'Linux 6.8.0-138-generic', arch: 'amd64' },
};

test('the eight tiles of a Docker host', () => {
  const t = detailTiles(DETAILS, tr, 'en', 420);
  assert.deepEqual(t.map((x) => x.key), ['uptime', 'load', 'cpu', 'memory', 'disk', 'containers', 'collector', 'os']);
  assert.deepEqual(t.map((x) => [x.value, x.sub]), [
    ['12 d 4 h', 'Since 25 Oct 10:02'], ['0.42 · 0.38 · 0.35', 'Of 2 cores'], ['2 cores', 'amd64'], ['1.3 / 1.9 GB', '614.4 MB free'], ['21 / 40 GB', '19 GB free'],
    ['8 running', '0 stopped · 0 restarts in 24 h'], ['0.163.2', 'docker-host-01 · Internal'], ['Ubuntu 24.04.5 LTS', 'Linux 6.8.0-138-generic']]);
  assert.equal(t[4].label, 'Disk /');
});

test('without containers the tile is left out, a missing value is a dash and one core is singular', () => {
  const t = detailTiles({ ...DETAILS, containers: null, cores: 1, restarts: 0 }, tr, 'id', 420);
  assert.equal(t.length, 7);
  const none = detailTiles({ uptime_s: null, booted_at: null, cores: null, load: { m1: null, m5: null, m15: null }, memory: null, disk: null, containers: null, collector: {}, os: {} }, tr, 'en', 0);
  assert.deepEqual(none.map((x) => x.value), ['–', '–', '–', '–', '–', '–', '–']);
  assert.deepEqual(none.map((x) => x.sub), ['', '', '', '', '', '', '']);
  assert.equal(detailTiles({ ...DETAILS, cores: 1 }, tr, 'en', 0)[2].value, '1 core');
  assert.equal(detailTiles({ ...DETAILS, containers: { running: 1, stopped: 2, restarts_24h: 1 } }, tr, 'en', 0)[5].sub, '2 stopped · 1 restart in 24 h');
});

test('an old collector: load of 1 minute only, no cores line in the chart', () => {
  const t = detailTiles({ ...DETAILS, cores: null, load: { m1: 0.5, m5: null, m15: null } }, tr, 'en', 0);
  assert.equal(t[1].value, '0.50 · – · –');
  const s = { load: { m1: [['a', 1], ['b', 2]], m5: [['a', 1.5]], m15: [], cores: null }, disk_io: { read: [['a', 10], ['b', 20]], write: [['b', 5]] } };
  assert.deepEqual(loadSets(s, tr).sets.map((x) => x.label), ['1 min', '5 min', '15 min']);
  assert.deepEqual(loadSets({ ...s, load: { ...s.load, cores: 4 } }, tr).sets.at(-1), { label: 'Cores', data: [4, 4], color: '--muted', dashed: true });
  assert.deepEqual(diskIoSets(s, tr).sets.map((x) => x.data), [[10, 20], [null, 5]]);
});

test('the upgrade hint names the command of the platform', () => {
  assert.equal(upgradeKey('linux'), 'sv.dt.upgrade_text');
  assert.equal(upgradeKey('docker'), 'sv.dt.upgrade_text');
  assert.equal(upgradeKey('windows'), 'sv.dt.upgrade_win_text');
  assert.equal(upgradeKey('kubernetes'), 'sv.dt.upgrade_k8s_text');
  assert.match(EN['sv.dt.upgrade_text'], /install\.sh --upgrade/);
  assert.match(EN['sv.dt.upgrade_win_text'], /install\.ps1 -Upgrade/);
});
