#!/usr/bin/env node
// The keys of the id.json and en.json dictionaries must match, and the {name} parameters of each text must match in both languages;
// also: every key used in code ($t('…') / translate(_, '…')) exists in the dictionary.
//   node tools/cek_i18n.mjs        (from the v2/ folder)   -> "keys match: N", exit code 1 on any difference
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const web = join(dirname(fileURLToPath(import.meta.url)), '..', 'web', 'src');
const id = JSON.parse(readFileSync(join(web, 'i18n', 'id.json'), 'utf8'));
const en = JSON.parse(readFileSync(join(web, 'i18n', 'en.json'), 'utf8'));
const masalah = [];
const ki = Object.keys(id), ke = Object.keys(en);
for (const k of ki) if (!(k in en)) masalah.push(`only in id.json: ${k}`);
for (const k of ke) if (!(k in id)) masalah.push(`only in en.json: ${k}`);
const par = (s) => [...String(s).matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort().join(',');
for (const k of ki) if (k in en && par(id[k]) !== par(en[k])) masalah.push(`parameters differ: ${k} (${par(id[k])} / ${par(en[k])})`);
for (const k of ki) if (!String(id[k]).trim() || !String(en[k] ?? 'x').trim()) masalah.push(`empty text: ${k}`);

// keys used by code: a full literal, or a dynamic prefix `tab.${…}` (at least one key with that prefix must exist)
const files = [];
const walk = (d) => readdirSync(d).forEach((f) => { const p = join(d, f); statSync(p).isDirectory() ? walk(p) : /\.(svelte|js)$/.test(f) && files.push(p); });
walk(web);
let dipakai = 0;
for (const f of files) {
  const src = readFileSync(f, 'utf8');
  for (const m of src.matchAll(/\$t\(\s*'([\w.-]+)'/g)) { dipakai++; if (!(m[1] in id)) masalah.push(`not in the dictionary: ${m[1]} (${f.slice(web.length + 1)})`); }
  for (const m of src.matchAll(/\$t\(\s*`([\w.-]+)\$\{/g)) { dipakai++; if (!ki.some((k) => k.startsWith(m[1]))) masalah.push(`prefix not in the dictionary: ${m[1]}… (${f.slice(web.length + 1)})`); }
}

if (masalah.length) {
  console.error(masalah.join('\n'));
  console.error(`differences: ${masalah.length}`);
  process.exit(1);
}
console.log(`keys match: ${ki.length} (used in code: ${dipakai} places)`);
