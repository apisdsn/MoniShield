// Capitalisation rules of the UI text (tools/i18n_case.mjs, docs/08-architecture.md "UI text").
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { titleCase, isLabel, needsPeriod, labelProblems } from '../tools/i18n_case.mjs';

test('English labels: Title Case, small words stay lower case unless first', () => {
  assert.equal(titleCase('Add collector', 'en'), 'Add Collector');
  assert.equal(titleCase('open in raw logs', 'en'), 'Open in Raw Logs');
  assert.equal(titleCase('last seen', 'en'), 'Last Seen');
  assert.equal(titleCase('the end of the line', 'en'), 'The End of the Line');
  assert.equal(titleCase('Back to sign in', 'en'), 'Back to Sign In');
  assert.equal(titleCase('Errors per service from the log', 'en'), 'Errors per Service from the Log');
  assert.equal(titleCase('last sign-in', 'en'), 'Last Sign-In');
  assert.equal(titleCase('change vs previous day', 'en'), 'Change vs Previous Day');
  assert.equal(titleCase('back up now', 'en'), 'Back Up Now');
  assert.equal(titleCase('Send test email to', 'en'), 'Send Test Email to');
});

test('product names, acronyms, placeholders, numbers and units keep their form', () => {
  assert.equal(titleCase('MoniShield s3 and kafka settings', 'en'), 'MoniShield S3 and Kafka Settings');
  assert.equal(titleCase('cpu, ram and smtp', 'en'), 'CPU, RAM and SMTP');
  assert.equal(titleCase('Details of {name}', 'en'), 'Details of {name}');
  assert.equal(titleCase('5xx responses per hour ({tz})', 'en'), '5xx Responses per Hour ({tz})');
  assert.equal(titleCase('last 24 h', 'en'), 'Last 24 h');
  assert.equal(titleCase('Search by requestId', 'en'), 'Search by requestId');
  assert.equal(titleCase('nginx ingress log', 'en'), 'nginx Ingress Log');
  assert.equal(titleCase('uptime-kuma checks', 'en'), 'Uptime-Kuma Checks');
});

test('Indonesian labels use their own small words', () => {
  assert.equal(titleCase('Tambah collector', 'id'), 'Tambah Collector');
  assert.equal(titleCase('Buka di log mentah', 'id'), 'Buka di Log Mentah');
  assert.equal(titleCase('Kirim yang belum terkirim', 'id'), 'Kirim yang Belum Terkirim');
  assert.equal(titleCase('Request per jam dengan error atau warning untuk dari ke', 'id'), 'Request per Jam dengan Error atau Warning untuk dari ke');
});

test('which keys are labels and which are sentences', () => {
  assert.equal(isLabel('cl.add', 'Add Collector'), true);
  assert.equal(isLabel('cl.intro', 'Servers and clusters that send logs'), false);        // named as a sentence
  assert.equal(isLabel('x.title', 'Saved to the file.'), false);                          // ends with a period
  assert.equal(isLabel('x.title', 'Ingest running'), true);
  assert.equal(isLabel('cl.pill.late', '{n} late'), true);                                // a badge, although it starts with a number
  assert.equal(isLabel('x.count', '{n} late'), false);                                    // a fragment that starts with a placeholder
  assert.equal(isLabel('ingest.none', 'No ingest since server start'), false);            // status lines are listed as sentences
  assert.equal(titleCase('{n} late', 'en'), '{n} Late');
  assert.equal(isLabel('x.cpu_cap', 'Share of all cores'), false);                        // a name ending in _cap
  assert.equal(isLabel('x.t', 'one two three four five six seven eight'), false);         // long
  assert.equal(isLabel('raw.ph.text', 'Words to find'), false);
});

test('sentences in descriptions end with a period; placeholders do not', () => {
  assert.equal(needsPeriod('cl.in.hint', 'The collector uses the change after it fetches its configuration'), true);
  assert.equal(needsPeriod('cl.in.hint', 'The collector uses the change.'), false);
  assert.equal(needsPeriod('raw.ph.text', 'Words to find, e.g. verify-otp'), false);
  assert.equal(needsPeriod('cl.in.hint', 'Two words'), false);
});

test('the dictionaries follow the rule', async () => {
  const { readFileSync } = await import('node:fs');
  const en = JSON.parse(readFileSync(new URL('../web/src/i18n/en.json', import.meta.url))), id = JSON.parse(readFileSync(new URL('../web/src/i18n/id.json', import.meta.url)));
  assert.deepEqual(labelProblems(en, id).slice(0, 5), []);
});
