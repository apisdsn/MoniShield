// Collectors page helpers (web/src/collectors.js): the checks mirror the server's rules.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { checkName, checkPath, checkService, parseUnits, checkOptions, payload, sends, installSteps, keySteps, upgradeSteps, ago, counts, defaults, editable } from '../web/src/collectors.js';

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
  assert.deepEqual(payload('kubernetes', { files: [{ path: '/a', service: 'a' }] }), {});
  assert.deepEqual(payload('linux', { files: [{ path: ' /a.log ', service: 'a ' }], journald: false, units: ['x.service'] }), { files: [{ path: '/a.log', service: 'a' }], journald: false, units: [] });
  assert.deepEqual(payload('windows', { files: [], channels: ['security', 'application'] }), { files: [], channels: ['application', 'security'] });
  assert.equal(payload('docker', { files: [], journald: false, units: [], containers: true }).containers, true);
  assert.deepEqual(editable('windows', null), { files: [], channels: ['application', 'system'] });
});

test('chips', () => {
  assert.deepEqual(sends('kubernetes', {}), [{ key: 'pods' }]);
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
