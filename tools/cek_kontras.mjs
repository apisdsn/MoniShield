#!/usr/bin/env node
// Rasio kontras token warna (WCAG 2.1) untuk kedua tema, langsung dari web/src/theme.css (DRD §5.6, §9.1).
// Teks ≥ 4,5 : 1; elemen grafik dan batas kontrol ≥ 3 : 1. Kode keluar 1 bila ada pasangan di bawah ambang.
//   node tools/cek_kontras.mjs        (dari folder v2/)
import { readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const css = readFileSync(join(dirname(fileURLToPath(import.meta.url)), '..', 'web', 'src', 'theme.css'), 'utf8');
const blok = (sel) => {
  const i = css.indexOf(sel + ' {');
  const isi = css.slice(i, css.indexOf('\n}', i));
  return Object.fromEntries([...isi.matchAll(/--([\w-]+):\s*(#[0-9a-fA-F]{6})\b/g)].map((m) => [m[1], m[2]]));
};
const gelap = blok(':root');
const tema = { gelap, terang: { ...gelap, ...blok(":root[data-theme='light']") } };

const lum = (hex) => {
  const c = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255).map((v) => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4));
  return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
};
const rasio = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05); };

const TEKS = 4.5, GRAFIK = 3;
// [depan, latar, ambang, keterangan]
const PASANG = [
  ['fg', 'card', TEKS, 'teks utama di kartu'], ['fg', 'bg', TEKS, 'teks utama di latar'],
  ['muted', 'card', TEKS, 'teks sekunder di kartu'], ['muted', 'bg', TEKS, 'teks sekunder di latar'], ['muted', 'card2', TEKS, 'teks sekunder di butir perhatian'],
  ['kpi-label', 'card', TEKS, 'label KPI'], ['nav-fg', 'side-bg', TEKS, 'navigasi'], ['th-fg', 'card', TEKS, 'kepala tabel'],
  ['accent-text', 'card', TEKS, 'aksen sebagai teks'], ['accent-text', 'bg', TEKS, 'aksen sebagai teks di latar'], ['ok-text', 'card', TEKS, 'sukses sebagai teks'],
  ['err', 'card', TEKS, 'error sebagai teks'], ['warn', 'card', TEKS, 'warning sebagai teks'], ['code-fg', 'pre-bg', TEKS, 'blok kode'],
  ['sev3-fg', 'card', TEKS, 'tag kritis'], ['sev2-fg', 'card', TEKS, 'tag sedang'], ['sev1-fg', 'card', TEKS, 'tag rendah'], ['sevok-fg', 'card', TEKS, 'tag ok'],
  ['badge-fg', 'side-bg', TEKS, 'lencana navigasi'],
  ['line-strong', 'card', GRAFIK, 'batas kontrol di kartu'], ['line-strong', 'bg', GRAFIK, 'batas kontrol di latar'],
  ['accent', 'card', GRAFIK, 'aksen grafik'], ['ok', 'card', GRAFIK, 'sukses grafik'],
  ...Array.from({ length: 10 }, (_, i) => [`c${i + 1}`, 'card', GRAFIK, `seri chart ${i + 1}`]),
];

let gagal = 0;
for (const [nama, t] of Object.entries(tema)) {
  console.log(`\n## tema ${nama}`);
  for (const [a, b, min, ket] of PASANG) {
    if (!t[a] || !t[b]) { console.log(`  ?    ${a} / ${b}: token tidak berupa #rrggbb, dilewati`); continue; }
    const r = rasio(t[a], t[b]), ok = r >= min;
    if (!ok) gagal++;
    console.log(`  ${ok ? 'ok  ' : 'GAGAL'} ${r.toFixed(2).padStart(5)} ≥ ${min}  ${a} ${t[a]} / ${b} ${t[b]}  (${ket})`);
  }
}
console.log(`\n${gagal ? `GAGAL: ${gagal} pasangan di bawah ambang` : 'semua pasangan memenuhi ambang'}`);
process.exit(gagal ? 1 : 0);
