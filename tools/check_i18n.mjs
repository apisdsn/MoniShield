#!/usr/bin/env node
// The keys of the id.json and en.json dictionaries must match, and the {name} parameters of each text must match in both languages;
// also: labels are in Title Case and sentences in sentence case, with a period (tools/i18n_case.mjs; docs/08-architecture.md, UI text);
// also: every key used in code ($t('…') / translate(_, '…')) exists in the dictionary.
//   node tools/check_i18n.mjs        (from the v2/ folder)   -> "keys match: N", exit code 1 on any difference
import { readFileSync, readdirSync, statSync, writeFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { labelProblems, periodProblems } from './i18n_case.mjs';

const web = join(dirname(fileURLToPath(import.meta.url)), '..', 'web', 'src');
const id = JSON.parse(readFileSync(join(web, 'i18n', 'id.json'), 'utf8'));
const en = JSON.parse(readFileSync(join(web, 'i18n', 'en.json'), 'utf8'));
const problems = [];
const ki = Object.keys(id), ke = Object.keys(en);
for (const k of ki) if (!(k in en)) problems.push(`only in id.json: ${k}`);
for (const k of ke) if (!(k in id)) problems.push(`only in en.json: ${k}`);
const par = (s) => [...String(s).matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort().join(',');
for (const k of ki) if (k in en && par(id[k]) !== par(en[k])) problems.push(`parameters differ: ${k} (${par(id[k])} / ${par(en[k])})`);
for (const k of ki) if (!String(id[k]).trim() || !String(en[k] ?? 'x').trim()) problems.push(`empty text: ${k}`);

// capitalisation: `node tools/check_i18n.mjs --fix` rewrites the findings (labels to Title Case, missing periods), then check the diff
const caps = [...labelProblems(en, id), ...periodProblems(en, id)];
if (process.argv.includes('--fix') && caps.length) {
  for (const x of caps) (x.lang === 'en' ? en : id)[x.key] = x.want;
  writeFileSync(join(web, 'i18n', 'en.json'), JSON.stringify(en, null, 1) + '\n'); writeFileSync(join(web, 'i18n', 'id.json'), JSON.stringify(id, null, 1) + '\n');
  console.log(`rewrote ${caps.length} texts`); caps.length = 0;
}
for (const x of caps) problems.push(`capitalisation (${x.lang}) ${x.key}: "${x.value}" should be "${x.want}"`);

// keys used by code: a full literal, or a dynamic prefix `tab.${…}` (at least one key with that prefix must exist)
const files = [];
const walk = (d) => readdirSync(d).forEach((f) => { const p = join(d, f); statSync(p).isDirectory() ? walk(p) : /\.(svelte|js)$/.test(f) && files.push(p); });
walk(web);
let uses = 0;
for (const f of files) {
  const src = readFileSync(f, 'utf8');
  for (const m of src.matchAll(/\$t\(\s*'([\w.-]+)'/g)) { uses++; if (!(m[1] in id)) problems.push(`not in the dictionary: ${m[1]} (${f.slice(web.length + 1)})`); }
  for (const m of src.matchAll(/\$t\(\s*`([\w.-]+)\$\{/g)) { uses++; if (!ki.some((k) => k.startsWith(m[1]))) problems.push(`prefix not in the dictionary: ${m[1]}… (${f.slice(web.length + 1)})`); }
}

if (problems.length) {
  console.error(problems.join('\n'));
  console.error(`differences: ${problems.length}`);
  process.exit(1);
}
console.log(`keys match: ${ki.length} (used in code: ${uses} places)`);
