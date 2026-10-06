#!/usr/bin/env node
// Kunci kamus id.json dan en.json harus sama, dan parameter {nama} di tiap teks harus sama di kedua bahasa;
// juga: setiap kunci yang dipakai di kode ($t('…') / translate(_, '…')) ada di kamus.
//   node tools/cek_i18n.mjs        (dari folder v2/)   -> "kunci sama: N", kode keluar 1 bila ada selisih
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const web = join(dirname(fileURLToPath(import.meta.url)), '..', 'web', 'src');
const id = JSON.parse(readFileSync(join(web, 'i18n', 'id.json'), 'utf8'));
const en = JSON.parse(readFileSync(join(web, 'i18n', 'en.json'), 'utf8'));
const masalah = [];
const ki = Object.keys(id), ke = Object.keys(en);
for (const k of ki) if (!(k in en)) masalah.push(`hanya di id.json: ${k}`);
for (const k of ke) if (!(k in id)) masalah.push(`hanya di en.json: ${k}`);
const par = (s) => [...String(s).matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort().join(',');
for (const k of ki) if (k in en && par(id[k]) !== par(en[k])) masalah.push(`parameter berbeda: ${k} (${par(id[k])} / ${par(en[k])})`);
for (const k of ki) if (!String(id[k]).trim() || !String(en[k] ?? 'x').trim()) masalah.push(`teks kosong: ${k}`);

// kunci yang dipakai kode: literal penuh, atau awalan dinamis `tab.${…}` (minimal satu kunci berawalan itu harus ada)
const files = [];
const walk = (d) => readdirSync(d).forEach((f) => { const p = join(d, f); statSync(p).isDirectory() ? walk(p) : /\.(svelte|js)$/.test(f) && files.push(p); });
walk(web);
let dipakai = 0;
for (const f of files) {
  const src = readFileSync(f, 'utf8');
  for (const m of src.matchAll(/\$t\(\s*'([\w.-]+)'/g)) { dipakai++; if (!(m[1] in id)) masalah.push(`tidak ada di kamus: ${m[1]} (${f.slice(web.length + 1)})`); }
  for (const m of src.matchAll(/\$t\(\s*`([\w.-]+)\$\{/g)) { dipakai++; if (!ki.some((k) => k.startsWith(m[1]))) masalah.push(`awalan tidak ada di kamus: ${m[1]}… (${f.slice(web.length + 1)})`); }
}

if (masalah.length) {
  console.error(masalah.join('\n'));
  console.error(`berbeda: ${masalah.length}`);
  process.exit(1);
}
console.log(`kunci sama: ${ki.length} (dipakai di kode: ${dipakai} tempat)`);
