// Page addresses (web/src/state.js): personal data (an IP, a search text) after "#", old addresses still read.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { parse, build } from '../web/src/state.js';

const base = { folder: '2026-10-30', module: null, source: 's3' };

test('IP and search text go after "#"', () => {
  assert.equal(build({ ...base, tab: 'ip', service: '203.0.113.5' }), '/ips?folder=2026-10-30#ip=203.0.113.5');
  assert.equal(build({ ...base, tab: 'security', q: 'rina@example.com' }), '/security?folder=2026-10-30#search=rina%40example.com');
  assert.equal(build({ ...base, tab: 'raw-logs', q: 'verify-otp', source: 'kafka' }), '/raw-logs?folder=2026-10-30&source=kafka#search=verify-otp');
  assert.equal(build({ ...base, tab: 'overview' }), '/overview?folder=2026-10-30');
});

test('the new addresses are read back', () => {
  const r = parse('/ips?folder=2026-10-30#ip=203.0.113.5&search=GET');
  assert.deepEqual([r.tab, r.service, r.folder, r.q], ['ip', '203.0.113.5', '2026-10-30', 'GET']);
  assert.equal(parse('/raw-logs?folder=2026-10-30#search=a%20b').q, 'a b');
  for (const u of ['/ips?folder=2026-10-30#ip=2001:db8::1', '/ips/203.0.113.5?folder=2026-10-30']) assert.equal(build(parse(u)).startsWith('/ips?folder=2026-10-30#ip='), true);
});

test('old addresses are still read', () => {
  const r = parse('/ips/203.0.113.5?folder=2026-10-30&search=x');
  assert.deepEqual([r.tab, r.service, r.q], ['ip', '203.0.113.5', 'x']);
  assert.equal(build(r), '/ips?folder=2026-10-30#ip=203.0.113.5&search=x');
});

test('a plain anchor is not read as data; /ips without an IP opens the Overview', () => {
  assert.deepEqual([parse('/security?folder=2026-10-30#main').tab, parse('/security?folder=2026-10-30#main').q], ['security', null]);
  assert.equal(parse('/ips?folder=2026-10-30').tab, 'overview');
});

test('sign-in keeps the data after "#" outside ?next=', () => {
  const r = parse('/login?next=%2Fips%3Ffolder%3D2026-10-30#ip=203.0.113.5');
  assert.deepEqual([r.tab, r.service, r.folder], ['ip', '203.0.113.5', '2026-10-30']);
});
