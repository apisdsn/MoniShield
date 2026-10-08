#!/usr/bin/env node
// Contrast ratio of the color tokens (WCAG 2.1) for both themes, read directly from web/src/theme.css (DRD §5.6, §9.1).
// Text ≥ 4.5 : 1; graphical elements and control borders ≥ 3 : 1. Exit code 1 when any pair is below its threshold.
//   node tools/cek_kontras.mjs        (from the v2/ folder)
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
const tema = { dark: gelap, light: { ...gelap, ...blok(":root[data-theme='light']") } };

const lum = (hex) => {
  const c = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255).map((v) => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4));
  return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
};
const rasio = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05); };

const TEKS = 4.5, GRAFIK = 3;
// [foreground, background, threshold, description]
const PASANG = [
  ['fg', 'card', TEKS, 'main text on card'], ['fg', 'bg', TEKS, 'main text on background'],
  ['muted', 'card', TEKS, 'secondary text on card'], ['muted', 'bg', TEKS, 'secondary text on background'], ['muted', 'card2', TEKS, 'secondary text on attention item'],
  ['kpi-label', 'card', TEKS, 'KPI label'], ['nav-fg', 'side-bg', TEKS, 'navigation'], ['th-fg', 'card', TEKS, 'table header'],
  ['accent-text', 'card', TEKS, 'accent as text'], ['accent-text', 'bg', TEKS, 'accent as text on background'], ['ok-text', 'card', TEKS, 'success as text'],
  ['err', 'card', TEKS, 'error as text'], ['warn', 'card', TEKS, 'warning as text'], ['code-fg', 'pre-bg', TEKS, 'code block'],
  ['sev3-fg', 'card', TEKS, 'critical tag'], ['sev2-fg', 'card', TEKS, 'medium tag'], ['sev1-fg', 'card', TEKS, 'low tag'], ['sevok-fg', 'card', TEKS, 'tag ok'],
  ['badge-fg', 'side-bg', TEKS, 'navigation badge'],
  ['line-strong', 'card', GRAFIK, 'control border on card'], ['line-strong', 'bg', GRAFIK, 'control border on background'],
  ['accent', 'card', GRAFIK, 'graphic accent'], ['ok', 'card', GRAFIK, 'graphic success'],
  ...Array.from({ length: 10 }, (_, i) => [`c${i + 1}`, 'card', GRAFIK, `chart series ${i + 1}`]),
];

let gagal = 0;
for (const [nama, t] of Object.entries(tema)) {
  console.log(`\n## theme ${nama}`);
  for (const [a, b, min, ket] of PASANG) {
    if (!t[a] || !t[b]) { console.log(`  ?    ${a} / ${b}: token is not #rrggbb, skipped`); continue; }
    const r = rasio(t[a], t[b]), ok = r >= min;
    if (!ok) gagal++;
    console.log(`  ${ok ? 'ok  ' : 'FAIL '} ${r.toFixed(2).padStart(5)} ≥ ${min}  ${a} ${t[a]} / ${b} ${t[b]}  (${ket})`);
  }
}
console.log(`\n${gagal ? `FAIL: ${gagal} pairs below the threshold` : 'all pairs meet the threshold'}`);
process.exit(gagal ? 1 : 0);
