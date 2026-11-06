// Log Formats page helpers (web/src/logformats.js). The override cases are shared with tests/test_log_formats_page.py.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { PRESET_KIND, ruleMatches, matchIndex, overrideKey, blankRule, override, changeCount, moveRule, removeRule, putRule, formatLines, parseLines, optionsFor, filterServices, readsBadly, pctText } from '../web/src/logformats.js';

const CASES = JSON.parse(readFileSync(new URL('./fixtures/override_cases.json', import.meta.url)));
const rules = (list) => list.map(([m, f]) => blankRule(m, f));

for (const c of CASES) {
  test(`override: ${c.name}`, () => {
    const [ns, svc, fmt] = c.set;
    const got = override(rules(c.rules), ns, svc, fmt);
    assert.deepEqual(got.map((r) => [r.match, r.format]), c.expect);
    assert.equal(got[matchIndex(got, ns, svc)].format, fmt);
  });
}

test('override refuses what a rule cannot say', () => {
  assert.equal(override(rules([['*', 'plain']]), null, 'a b', 'json'), null);
  assert.equal(override(rules([['*', 'plain']]), null, 'a', 'regex'), null);
  assert.equal(PRESET_KIND['caddy-json'], 'http');
});

test('matching: globs, namespace, first rule wins, case sensitive', () => {
  const r = rules([['VM-23/*', 'plain'], ['web-*', 'nginx-combined'], ['*', 'spring-boot']]);
  assert.equal(r[matchIndex(r, 'VM-23', 'anything')].format, 'plain');
  assert.equal(r[matchIndex(r, 'vm-23', 'anything')].format, 'spring-boot');
  assert.equal(r[matchIndex(r, 'x', 'web-shop')].format, 'nginx-combined');
  assert.ok(ruleMatches({ match: 'a?c' }, null, 'abc') && !ruleMatches({ match: 'a?c' }, null, 'abbc'));
  assert.equal(overrideKey('host.1', 'svc'), 'host.1/svc');
  assert.equal(overrideKey('bad ns', 'svc'), 'svc');
  assert.equal(overrideKey(null, 'a b'), null);
});

test('changes are counted against the saved rules', () => {
  const saved = rules([['a', 'plain'], ['b', 'json'], ['*', 'spring-boot']]);
  assert.equal(changeCount(saved, saved), 0);
  assert.equal(changeCount(saved, putRule(saved, -1, blankRule('c', 'logfmt'))), 1);
  assert.equal(changeCount(saved, removeRule(saved, 0)), 1);
  assert.equal(changeCount(saved, moveRule(saved, 0, 1)), 1);
  const edited = [...saved]; edited[1] = { ...edited[1], format: 'logfmt' };
  assert.equal(changeCount(saved, edited), 1);
});

test('rules move, are removed and added around the catch-all', () => {
  const r = rules([['a', 'plain'], ['b', 'json'], ['*', 'spring-boot']]);
  assert.deepEqual(moveRule(r, 0, 1).map((x) => x.match), ['b', 'a', '*']);
  assert.equal(moveRule(r, 0, -1), null);
  assert.equal(moveRule(r, 1, 1), null);       // nothing moves below the catch-all
  assert.equal(moveRule(r, 2, -1), null);      // and the catch-all does not move
  assert.equal(removeRule(r, 2), null);
  assert.deepEqual(removeRule(r, 1).map((x) => x.match), ['a', '*']);
  assert.deepEqual(putRule(r, -1, blankRule('n', 'syslog')).map((x) => x.match), ['a', 'b', 'n', '*']);
});

test('lines of fields and levels', () => {
  assert.equal(formatLines({ time: 'ts', path: 'req.url' }), 'time = ts\npath = req.url');
  assert.deepEqual(parseLines('time = ts\n\n path=req.url ').map, { time: 'ts', path: 'req.url' });
  assert.equal(parseLines('time = ts\nnonsense').error, 2);
  assert.deepEqual(parseLines('').map, {});
});

test('select options, filter and the bad-reading test', () => {
  assert.deepEqual(optionsFor(['json', 'plain'], 'regex'), ['json', 'plain', 'regex']);
  assert.deepEqual(optionsFor(['json', 'plain'], 'json'), ['json', 'plain']);
  const rows = [{ service: 'a', namespace: 'h1', source: 's3', bad: false }, { service: 'b', namespace: 'h2', source: 'kafka', bad: true }];
  assert.equal(filterServices(rows, { source: 'kafka' }).length, 1);
  assert.equal(filterServices(rows, { bad: true })[0].service, 'b');
  assert.equal(filterServices(rows, { q: 'H1' })[0].service, 'a');
  assert.ok(readsBadly(94.9, null) && !readsBadly(95, null) && !readsBadly(null, null) && readsBadly(100, { format: 'json' }));
  assert.equal(pctText(99.8), '99.8%');
  assert.equal(pctText(100), '100%');
  assert.equal(pctText(null), '');
});
