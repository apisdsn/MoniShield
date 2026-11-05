// Servers page helpers (web/src/servers.js): bar colours, card status, chart data, banner items.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { barTone, hostStatus, bars, axisLabel, fullLabel, points, alignTo, diskPercent, last, sparkPoints, bannerItems, usualBand, memoryText, memoryShare, pctText, rate } from '../web/src/servers.js';
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
