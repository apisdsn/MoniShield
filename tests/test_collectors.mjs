// Collectors page helpers (web/src/collectors.js): the checks mirror the server's rules.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { containerMetricsOff, checkName, checkPath, checkService, parseUnits, checkOptions, payload, sends, installSteps, keySteps, upgradeSteps, ago, counts, defaults, editable, shortVersion, fitCount } from '../web/src/collectors.js';

test('names follow the server rule', () => {
  for (const ok of ['a', 'web-01', '0x', 'a'.repeat(63)]) assert.equal(checkName(ok), '', ok);
  for (const bad of ['Web', '-a', 'a_b', 'a b', 'a'.repeat(64), 'é']) assert.equal(checkName(bad), 'invalid', bad);
  assert.equal(checkName(''), 'empty');
});

test('paths: absolute, no quotes or ${, no trailing slash, Windows drive letters', () => {
  assert.equal(checkPath('/var/log/app/*.log', 'linux'), '');
  assert.equal(checkPath('rel.log', 'linux'), 'absolute');
  assert.equal(checkPath('/a/"b".log', 'linux'), 'chars');
  assert.equal(checkPath('/a/${HOME}/b.log', 'linux'), 'chars');
  assert.equal(checkPath('/var/log/', 'linux'), 'dir');
  assert.equal(checkPath('/' + 'a'.repeat(600), 'linux'), 'long');
  assert.equal(checkPath('C:\\logs\\*.log', 'windows'), '');
  assert.equal(checkPath('/var/log/a.log', 'windows'), 'windows');
  assert.equal(checkPath('  ', 'linux'), 'empty');
});

test('service names and journald units', () => {
  assert.equal(checkService('www.nginx'), ''); assert.equal(checkService('bad name'), 'invalid'); assert.equal(checkService(''), 'empty');
  assert.deepEqual(parseUnits('ssh.service, cron.service\nssh.service'), ['ssh.service', 'cron.service']);
});

test('options: at least one input, errors per row', () => {
  assert.deepEqual(checkOptions('linux', defaults('linux')), {});
  assert.equal(checkOptions('linux', { files: [], journald: false, units: [] }).none, 'no_inputs');
  assert.equal(checkOptions('windows', { files: [], channels: [] }).none, 'no_inputs');
  assert.equal(checkOptions('docker', { files: [], journald: false, units: [], containers: true }).none, undefined);
  const e = checkOptions('linux', { files: [{ path: 'x', service: 'a' }, { path: '/a.log', service: '' }], journald: false, units: [] });
  assert.deepEqual(e.files, [{ path: 'absolute', service: '' }, { path: '', service: 'empty' }]);
  assert.equal(checkOptions('linux', { files: [], journald: true, units: ['a b'] }).units, 'invalid_unit');
  assert.equal(checkOptions('kubernetes', {}).none, undefined);
  assert.equal(checkOptions('linux', { files: Array(31).fill({ path: '/a.log', service: 'a' }), journald: true, units: [] }).toomany, 'too_many_files');
});

test('payload only holds what the platform has', () => {
  assert.deepEqual(payload('kubernetes', { files: [{ path: '/a', service: 'a' }], host_metrics: true }), { host_metrics: true });
  assert.deepEqual(payload('linux', { files: [{ path: ' /a.log ', service: 'a ' }], journald: false, units: ['x.service'], container_metrics: true }), { files: [{ path: '/a.log', service: 'a' }], journald: false, units: [], host_metrics: false });
  assert.deepEqual(payload('windows', { files: [], channels: ['security', 'application'], host_metrics: true }), { files: [], channels: ['application', 'security'], host_metrics: true });
  assert.equal(payload('docker', { files: [], journald: false, units: [], containers: true }).containers, true);
  assert.deepEqual(payload('docker', { files: [], journald: false, units: [], host_metrics: true, container_metrics: true }), { files: [], journald: false, units: [], host_metrics: true, container_metrics: true, containers: false });
  assert.deepEqual(editable('windows', null), { files: [], channels: ['application', 'system'], host_metrics: true });
});

test('chips', () => {
  assert.deepEqual(sends('kubernetes', {}), [{ key: 'pods' }]);
  assert.deepEqual(sends('kubernetes', { host_metrics: true }), [{ key: 'pods' }, { key: 'host_metrics' }]);
  assert.deepEqual(sends('docker', { containers: true, host_metrics: true, container_metrics: true }), [{ key: 'containers' }, { key: 'host_metrics' }, { key: 'container_metrics' }]);
  assert.deepEqual(sends('linux', { files: [1, 2], journald: true }), [{ key: 'journald' }, { key: 'files', n: 2 }]);
  assert.deepEqual(sends('windows', { files: [], channels: ['system'] }), [{ key: 'system' }]);
  assert.deepEqual(sends('docker', { files: [], journald: false, containers: true }), [{ key: 'containers' }]);
});

test('commands carry the token and the address', () => {
  const lin = installSteps('linux', 'https://logs.example.com', 'web-01', 'mse_1_x');
  assert.equal(lin[0].lines[0], 'curl -fsSLo install.sh https://logs.example.com/collector/install.sh');
  assert.equal(lin[1].lines[0], 'sudo sh install.sh --name web-01 --token mse_1_x');
  assert.ok(!JSON.stringify(lin).includes('| sh'));
  assert.ok(installSteps('windows', 'https://l.x', 'w', 'mse_1_x')[1].lines[0].includes('-Name w -Token mse_1_x'));
  const k = installSteps('kubernetes', 'https://l.x', 'k', 'mse_1_x');
  assert.deepEqual(k.map((s) => s.id), ['repo', 'enroll', 'secret', 'helm']);
  assert.ok(k[1].lines.join('\n').includes('"token":"mse_1_x"') && k[3].lines[0].includes('-f values.yaml'));
  assert.ok(keySteps('linux', 'msk_1_k')[0].lines[0].includes('monishield.env') && keySteps('windows', 'msk_1_k')[0].lines[1].includes('MONISHIELD_COLLECTOR_KEY=msk_1_k'));
  assert.ok(keySteps('kubernetes', "msk_1_k")[0].lines[0].includes('--from-literal'));
});

test('relative time and counts', () => {
  assert.deepEqual(ago(5), [5, 'second']); assert.deepEqual(ago(120), [2, 'minute']); assert.deepEqual(ago(7300), [2, 'hour']); assert.deepEqual(ago(200000), [2, 'day']); assert.deepEqual(ago(-3), [0, 'second']);
  assert.deepEqual(counts([{ status: 'online' }, { status: 'online' }, { status: 'late' }, { status: 'waiting' }, { status: 'revoked' }]), { online: 2, late: 1, offline: 0, waiting: 1, revoked: 1 });
});

test('upgrade command: no token, the installer with --upgrade', () => {
  const b = 'https://logs.example.com';
  for (const p of ['linux', 'docker']) {
    const [s] = upgradeSteps(p, b);
    assert.deepEqual(s.lines, [`curl -fsSLo install.sh ${b}/collector/install.sh`, 'sudo sh install.sh --upgrade']);
    assert.ok(!s.lines.join('').includes('mse_') && !s.lines.join('').includes('--token'));
  }
  assert.match(upgradeSteps('windows', b)[0].lines[1], /install\.ps1 -Upgrade$/);
  assert.deepEqual(upgradeSteps('kubernetes', b), []);
});

test('metric options: defaults, who can have container metrics, and "nothing chosen"', () => {
  assert.equal(defaults('linux').host_metrics, true);
  assert.deepEqual([defaults('docker').host_metrics, defaults('docker').container_metrics], [true, true]);
  assert.deepEqual(defaults('kubernetes'), { host_metrics: true });
  assert.equal(containerMetricsOff('docker'), ''); assert.equal(containerMetricsOff('linux'), 'host'); assert.equal(containerMetricsOff('windows'), 'host'); assert.equal(containerMetricsOff('kubernetes'), 'kubernetes');
  assert.deepEqual(editable('linux', { files: [], journald: true, units: [] }).host_metrics, false);              // a collector from before the metrics: off
  assert.equal('container_metrics' in editable('linux', { container_metrics: true }), false);
  const only = { files: [], journald: false, units: [], host_metrics: false };
  assert.equal(checkOptions('linux', only).none, 'no_inputs');
  assert.deepEqual(checkOptions('linux', { ...only, host_metrics: true }), {});                                      // metrics alone are an input
  assert.deepEqual(checkOptions('docker', { ...only, containers: false, container_metrics: true }), {});
});

// Groups
import { NO_GROUP, NONE_KEY, checkGroup, groupNames, groupItems, groupNote, statusTally, filterRows, groupPills, sections, foldAll } from '../web/src/collectors.js';

const R = (id, name, group, status, hosts = []) => ({ id, name, group, status, stats: { hosts } });
const ROWS = [R(1, 'web-01', 'Client B', 'online'), R(2, 'web-02', 'client a', 'offline'), R(3, 'db-01', 'Client A', 'late', ['dbhost']), R(4, 'test-vm', '', 'offline'),
  R(5, 'api-01', 'Client B', 'online', ['api-host']), R(6, 'new-1', 'Internal', 'waiting')];

test('group names follow the server rule', () => {
  for (const ok of ['', '  ', 'Client A', 'a', 'Team_1.north-2', 'x'.repeat(40)]) assert.equal(checkGroup(ok), '', ok);
  for (const bad of ['-a', '.a', 'a'.repeat(41), 'a/b', 'é']) assert.equal(checkGroup(bad), 'invalid', bad);
});

test('sections: alphabetical without regard to case, No Group last, empty sections left out', () => {
  assert.deepEqual(groupNames([{ group: 'b' }, { group: 'A' }, { group: '' }, { group: 'a2' }]), ['A', 'a2', 'b']);
  const g = groupItems([{ group: '', n: 1 }, { group: 'Zed', n: 2 }, { group: 'alpha', n: 3 }]);
  assert.deepEqual(g.map((x) => x.name), ['alpha', 'Zed', NO_GROUP]);
  assert.deepEqual(groupItems([]), []);
});

test('the note under the Group field', () => {
  assert.deepEqual(groupNote('  ', ['A']), { kind: 'none', name: '' });
  assert.deepEqual(groupNote('client a', ['Client A']), { kind: 'join', name: 'Client A' });
  assert.deepEqual(groupNote('New One', ['Client A']), { kind: 'new', name: 'New One' });
});

test('search by name or host, status filter and the counts', () => {
  assert.deepEqual(statusTally(ROWS), { all: 6, online: 2, late: 1, offline: 2 });
  assert.deepEqual(filterRows(ROWS, 'WEB', 'all').map((r) => r.id), [1, 2]);
  assert.deepEqual(filterRows(ROWS, 'api-host', 'all').map((r) => r.id), [5]);          // a host the collector reported
  assert.deepEqual(filterRows(ROWS, '', 'offline').map((r) => r.id), [2, 4]);
  assert.deepEqual(filterRows(ROWS, 'db', 'online'), []);
});

test('section pills: offline, late, otherwise all online', () => {
  assert.deepEqual(groupPills([R(1, 'a', '', 'online'), R(2, 'b', '', 'online')]), [{ key: 'all_online' }]);
  assert.deepEqual(groupPills([R(1, 'a', '', 'offline'), R(2, 'b', '', 'late'), R(3, 'c', '', 'offline')]), [{ key: 'offline', n: 2 }, { key: 'late', n: 1 }]);
});

test('sections to show: filters, folded state, a search opens every section', () => {
  // "client a" and "Client A" are two spellings here only because this helper does not merge them (the server does)
  const all = sections(ROWS, '', 'all', {});
  assert.deepEqual(all.map((s) => s.name), ['Client A', 'client a', 'Client B', 'Internal', NO_GROUP]);
  const some = sections(ROWS, '', 'offline', {});
  assert.deepEqual(some.map((s) => [s.name, s.rows.length, s.total]), [['client a', 1, 1], [NO_GROUP, 1, 1]]);      // totals count the whole group
  assert.deepEqual(sections(ROWS, '', 'all', { 'Client B': true, [NONE_KEY]: true }).map((s) => [s.name, s.open]).filter(([n]) => n === 'Client B' || n === NO_GROUP), [['Client B', false], [NO_GROUP, false]]);
  assert.equal(sections(ROWS, 'web-01', 'all', { 'Client B': true })[0].open, true);                              // searching opens it
  assert.deepEqual(sections(ROWS, 'nothing', 'all', {}), []);
  assert.deepEqual(foldAll(['A', NO_GROUP], true), { A: true, [NONE_KEY]: true });
  assert.deepEqual(foldAll(['A'], false), {});
});

test('shortVersion keeps only the collector version', () => {
  assert.equal(shortVersion('OpenTelemetry Collector Contrib/0.163.2 (linux/amd64)'), '0.163.2');
  assert.equal(shortVersion('0.163.2'), '0.163.2');
  assert.equal(shortVersion(null), '');
});

test('chips: all of them when they fit, else as many as leave room for the +N chip', () => {
  assert.equal(fitCount([80, 90], 200, 6, 36), 2);          // 176 fits
  assert.equal(fitCount([80, 90], 176, 6, 36), 2);          // exactly
  assert.equal(fitCount([80, 90, 70], 200, 6, 36), 1);      // 80 + 6 + 36 fits; 80 + 6 + 90 + 6 + 36 does not
  assert.equal(fitCount([80, 90, 70], 100, 6, 36), 0);      // only "+3"
  assert.equal(fitCount([], 0, 6, 36), 0);
  assert.equal(fitCount([120, 40], 150, 6, 36), 0);
});
