#!/usr/bin/env node
// Contrast ratio of the color tokens (WCAG 2.1) for both themes, read directly from web/src/theme.css (DRD §5.6, §9.1).
// Text ≥ 4.5 : 1; graphical elements and control borders ≥ 3 : 1. Exit code 1 when any pair is below its threshold.
//   node tools/check_contrast.mjs        (from the v2/ folder)
import { readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const css = readFileSync(join(dirname(fileURLToPath(import.meta.url)), '..', 'web', 'src', 'theme.css'), 'utf8');
const block = (sel) => {
  const i = css.indexOf(sel + ' {');
  const body = css.slice(i, css.indexOf('\n}', i));
  return Object.fromEntries([...body.matchAll(/--([\w-]+):\s*(#[0-9a-fA-F]{6})\b/g)].map((m) => [m[1], m[2]]));
};
const dark = block(':root');
const themes = { dark: dark, light: { ...dark, ...block(":root[data-theme='light']") } };

const lum = (hex) => {
  const c = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255).map((v) => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4));
  return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
};
const ratio = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05); };

const TEXT = 4.5, GRAPHIC = 3;
// [foreground, background, threshold, description]
const PAIRS = [
  ['fg', 'card', TEXT, 'main text on card'], ['fg', 'bg', TEXT, 'main text on background'],
  ['muted', 'card', TEXT, 'secondary text on card'], ['muted', 'bg', TEXT, 'secondary text on background'], ['muted', 'card2', TEXT, 'secondary text on attention item'],
  ['kpi-label', 'card', TEXT, 'KPI label'], ['nav-fg', 'side-bg', TEXT, 'navigation'], ['th-fg', 'card', TEXT, 'table header'],
  ['accent-text', 'card', TEXT, 'accent as text'], ['accent-text', 'bg', TEXT, 'accent as text on background'], ['ok-text', 'card', TEXT, 'success as text'],
  ['err', 'card', TEXT, 'error as text'], ['warn', 'card', TEXT, 'warning as text'], ['code-fg', 'pre-bg', TEXT, 'code block'],
  ['sev3-fg', 'card', TEXT, 'critical tag'], ['sev2-fg', 'card', TEXT, 'medium tag'], ['sev1-fg', 'card', TEXT, 'low tag'], ['sevok-fg', 'card', TEXT, 'tag ok'],
  ['badge-fg', 'side-bg', TEXT, 'navigation badge'],
  ['line-strong', 'card', GRAPHIC, 'control border on card'], ['line-strong', 'bg', GRAPHIC, 'control border on background'],
  ['accent', 'card', GRAPHIC, 'graphic accent'], ['ok', 'card', GRAPHIC, 'graphic success'],
  ...Array.from({ length: 10 }, (_, i) => [`c${i + 1}`, 'card', GRAPHIC, `chart series ${i + 1}`]),
];

let failed = 0;
for (const [name, t] of Object.entries(themes)) {
  console.log(`\n## theme ${name}`);
  for (const [a, b, min, note] of PAIRS) {
    if (!t[a] || !t[b]) { console.log(`  ?    ${a} / ${b}: token is not #rrggbb, skipped`); continue; }
    const r = ratio(t[a], t[b]), ok = r >= min;
    if (!ok) failed++;
    console.log(`  ${ok ? 'ok  ' : 'FAIL '} ${r.toFixed(2).padStart(5)} ≥ ${min}  ${a} ${t[a]} / ${b} ${t[b]}  (${note})`);
  }
}
console.log(`\n${failed ? `FAIL: ${failed} pairs below the threshold` : 'all pairs meet the threshold'}`);
process.exit(failed ? 1 : 0);
