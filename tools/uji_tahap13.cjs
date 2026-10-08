// Stage 13 verification (Overview + service pages) in Chromium: v2 side by side with the old ../dashboard.html.
//   node tools/uji_tahap13.cjs http://127.0.0.1:8000 <admin-password>      (admin has already changed the initial password)
// Needs PLAYWRIGHT_MODULE (and optionally CHROMIUM_PATH, SHOTS_DIR). The old dashboard is opened as a file; Chart.js from the
// CDN is blocked and replaced with an empty stub, since what is compared is numbers, tables and card lists, not chart images.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const path = require('path');
const fs = require('fs');
const [, , BASE = 'http://127.0.0.1:8000', PW] = process.argv;
const LAMA = 'file://' + path.resolve(__dirname, '..', '..', 'dashboard.html');
const OUT = process.env.SHOTS_DIR || path.join(require('os').tmpdir(), 's4-shots');
fs.mkdirSync(OUT, { recursive: true });
const hasil = [];
const cek = (n, ok, info = '') => { hasil.push(!!ok); console.log(`${ok ? 'PASS' : 'FAIL'}  ${n}${info ? '  — ' + info : ''}`); };
// numbers from display text. Percent: old writes decimals with a dot ("3.6%", toFixed), v2 follows the language ("3,6%").
// Integers: thousands dots/commas dropped ('191.898' -> '191898').
const angka = (s) => {
  const t = String(s).replace(/[^\d,.%-]/g, '');
  return t.endsWith('%') ? String(parseFloat(t.replace(',', '.'))) + '%' : t.replace(/[.,]/g, '');
};
const normPct = (s) => String(s).replace(/(\d),(\d)/g, '$1.$2');   // "37,3%" and "37.3%" treated as equal in titles
const norm = (s) => normPct(String(s).toLowerCase().replace(/\s+/g, ' ').trim());
// EXPECTED differences (TRD §4.4 item 4): simpel-loop level KPI uses the effective level (old ERROR -> WARN)
const DIHARAPKAN = { 'om-be-simpel-loop': (l) => l === 'error' || l === 'warn' };
const PETA_LAMA = /^(peta|alur ip)/;   // map + flow cards on the service page: Stage 20

// Chart.js stub for the old dashboard (empty constructor, nested defaults)
const CHART_STUB = `(() => { const deep = () => new Proxy({}, { get: (t, k) => (k in t ? t[k] : (t[k] = deep())), set: (t, k, v) => ((t[k] = v), true) });
  window.Chart = class { constructor() {} destroy() {} }; window.Chart.defaults = deep(); })();`;

async function lama(browser, day, tab) {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  await ctx.route(/^https?:\/\//, (r) => r.abort());
  await ctx.addInitScript(CHART_STUB);
  const p = await ctx.newPage();
  await p.goto(LAMA);
  await p.evaluate(([d, t]) => { day = d; tab = t; render(); }, [day, tab]);   // old script's global variables
  return { ctx, p };
}
const kpiLama = (p) => p.$$eval('.kpi', (els) => els.map((e) => [e.querySelector('.l').textContent.trim(), e.querySelector('.v').textContent.trim(), e.querySelector('.dl')?.textContent.trim() || '']));
const kpiBaru = (p) => p.$$eval('main .kpi', (els) => els.map((e) => [e.querySelector('.l').textContent.trim(), e.querySelector('.v').textContent.trim(),
  [...e.querySelectorAll('.badge, .dl')].map((x) => x.textContent.trim()).join(' ')]));
const judulLama = (p) => p.$$eval('#main .card h3', (els) => els.map((e) => e.childNodes[0].textContent.trim()).filter(Boolean));
const judulBaru = (p) => p.$$eval('main .grid section.card > header h2', (els) => els.map((e) => e.childNodes[0].textContent.trim()).filter(Boolean));

(async () => {
  const browser = await chromium.launch(process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {});
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();
  const errs = [];
  page.on('pageerror', (e) => errs.push(e.message));
  page.on('console', (m) => m.type() === 'error' && !/status of 401/.test(m.text()) && errs.push(m.text()));
  await page.goto(BASE + '/#/overview?folder=2026-10-06');
  await page.fill('#u', 'admin'); await page.fill('#p', PW); await page.click('button[type=submit]');
  const siap = async () => { await page.waitForSelector('main .kpi'); await page.waitForLoadState('networkidle'); await page.waitForTimeout(400); };
  await siap();

  // ------------------------------------------------------------------ Overview 2026-10-06 vs old
  const L = await lama(browser, '2026-10-06', 'overview');
  const kl = await kpiLama(L.p), kb = await kpiBaru(page);
  const peta = Object.fromEntries(kb.map(([l, v, d]) => [norm(l), [v, d]]));
  const beda = kl.filter(([l, v]) => angka(peta[norm(l)]?.[0] ?? 'x') !== angka(v));
  cek('Overview 06 Oct: all old KPIs present in v2 with the same numbers', beda.length === 0, beda.length ? JSON.stringify(beda) : kl.map(([l, v]) => `${l} ${v}`).join(' · '));
  const deltaLama = Object.fromEntries(kl.map(([l, , d]) => [norm(l), (d.match(/[▲▼] \d+%/) || [''])[0]]));
  const deltaBaru = Object.fromEntries(kb.map(([l, , d]) => [norm(l), (d.match(/[▲▼] \d+%/) || [''])[0]]));
  const deltaBeda = Object.keys(deltaLama).filter((l) => deltaLama[l] !== (deltaBaru[l] ?? ''));
  cek('Overview: ▲/▼ change vs 5 Oct same as old (including absent ones)', deltaBeda.length === 0,
    Object.entries(deltaLama).filter(([, d]) => d).map((x) => x.join(' ')).join(' · ') + (deltaBeda.length ? ' | DIFF ' + deltaBeda.map((l) => `${l}: ${deltaLama[l]} vs ${deltaBaru[l]}`).join(', ') : ''));
  for (const [l, v] of [['Total baris log', '191898'], ['Error', '2810'], ['Warning / 4xx app', '856'], ['HTTP request', '124822'], ['Rate 4xx', '3.6%'], ['Rate 5xx', '0.04%'], ['Layanan', '7'], ['File log', '18']])
    if (angka(peta[norm(l)]?.[0]) !== v) cek(`Overview: ${l} = ${v}`, false, peta[norm(l)]?.[0]);
  // top 25 messages across services
  const msgLama = await L.p.$$eval('.card', (cards) => { const c = cards.find((x) => /Top pesan error lintas layanan/i.test(x.querySelector('h3')?.textContent || ''));
    return [...c.querySelectorAll('tr')].slice(1).map((tr) => [tr.cells[0].textContent.replace(/^\[[^\]]+\]\s*/, '').trim(), tr.cells[1].textContent.trim()]); });
  const msgBaru = await page.$$eval('section.dt', (secs) => { const s = secs.find((x) => /Top pesan error lintas layanan/i.test(x.querySelector('h2').textContent));
    return [...s.querySelectorAll('tbody tr')].map((tr) => [tr.cells[1].textContent.trim() + ' | ' + tr.cells[2].querySelector('summary').textContent.trim(), tr.cells[3].textContent.trim()]); });
  const msgBeda = msgLama.filter(([k, n], i) => !msgBaru[i] || angka(msgBaru[i][1]) !== angka(n));
  cek('Overview: top 25 messages, same per-row counts in the same order', msgLama.length === 25 && msgBaru.length === 25 && msgBeda.length === 0, `${msgLama.length} vs ${msgBaru.length}`);
  const isiBeda = msgLama.filter(([k]) => !msgBaru.some(([b]) => b === k));
  cek('Overview: top 25 message texts identical', isiBeda.length === 0, isiBeda.slice(0, 2).join(' | '));
  const jl = (await judulLama(L.p)).map(norm), jb = (await judulBaru(page)).map(norm);
  const kurang = jl.filter((x) => !jb.includes(x));
  cek('Overview: all old cards present (including the nginx HTTP Traffic section)', kurang.length === 0, kurang.length ? 'missing: ' + kurang.join(', ') : `${jl.length} cards`);
  await L.ctx.close();

  // ------------------------------------------------------------------ service pages vs old
  const LAYANAN = [['2026-10-06', 'nginx-ingress-controller'], ['2026-09-29', 'om-be-simpel-loop'], ['2026-10-06', 'om-be-appsmanager'], ['2026-10-06', 'coredns'], ['2026-10-06', 'om-fe-inhouse']];
  for (const [f, s] of LAYANAN) {
    await page.goto(`${BASE}/#/layanan/${s}?folder=${f}`); await siap();
    const O = await lama(browser, f, s);
    const kl2 = await kpiLama(O.p), kb2 = Object.fromEntries((await kpiBaru(page)).map(([l, v]) => [norm(l), v]));
    const beda2 = kl2.filter(([l, v]) => angka(kb2[norm(l)] ?? 'x') !== angka(v) && !DIHARAPKAN[s]?.(norm(l)));
    cek(`${s} ${f}: KPIs same as old`, beda2.length === 0, beda2.length ? JSON.stringify(beda2) : kl2.map(([l, v]) => `${l} ${v}`).join(' · '));
    const a = (await judulLama(O.p)).map(norm).filter((x) => !PETA_LAMA.test(x)), b = (await judulBaru(page)).map(norm);
    const k1 = a.filter((x) => !b.includes(x)), k2 = b.filter((x) => !a.includes(x));
    cek(`${s} ${f}: cards same as old (without map, Stage 20)`, k1.length === 0 && k2.length === 0, `${b.length} cards` + (k1.length ? ' | missing: ' + k1.join(', ') : '') + (k2.length ? ' | extra: ' + k2.join(', ') : ''));
    if (s === 'coredns') cek('coredns titled "domain gagal resolve"', b.some((x) => x.includes('domain gagal resolve')));
    await O.ctx.close();
  }

  // ------------------------------------------------------------------ expected differences (TRD §4.4)
  const tabelChart = async (judul) => {
    const card = page.locator('section.card', { has: page.locator('h2', { hasText: judul }) }).first();
    await card.locator('button', { hasText: /Lihat sebagai tabel|View as table/ }).click();
    return card.locator('tbody tr').evaluateAll((trs) => trs.map((tr) => [...tr.cells].map((c) => c.textContent.trim())));
  };
  await page.goto(`${BASE}/#/layanan/nginx-ingress-controller?folder=2026-10-06`); await siap();
  const jam = await tabelChart('Aktivitas per jam');
  const sumErr = jam.reduce((a, r) => a + +angka(r[2]), 0);
  cek('nginx: hourly Error line includes error log lines (item 2): Σ = Error KPI 125', sumErr === 125, `Σ ${sumErr}`);
  await page.goto(`${BASE}/#/layanan/om-be-simpel-loop?folder=2026-09-29`); await siap();
  const lv = Object.fromEntries((await tabelChart('Distribusi level')).map((r) => [r[0], angka(r[1])]));
  cek('simpel-loop 29 Sep: level donut WARN 9,614, no ERROR (item 4)', lv.WARN === '9614' && !('ERROR' in lv), JSON.stringify(lv));

  // ------------------------------------------------------------------ nearly empty folder, message filter
  await page.goto(`${BASE}/#/overview?folder=2026-10-01`); await siap();
  cek('folder 1 Oct: band "hanya berisi 4 baris; file rusak"', /hanya berisi 4 baris log; 4 file rusak/.test(await page.textContent('.band.warn')), await page.textContent('.band.warn'));
  await page.goto(`${BASE}/#/overview?folder=2026-09-27`); await siap();
  const tanpaNg = await page.evaluate(() => [[...document.querySelectorAll('main .kpi .l')].map((e) => e.textContent.trim()), !!document.querySelector('main .traffic')]);
  cek('Overview 27 Sep (no nginx): HTTP KPIs and HTTP Traffic section not shown', !tanpaNg[0].some((l) => /HTTP|Rate/.test(l)) && !tanpaNg[1], tanpaNg[0].join(', '));
  await page.goto(`${BASE}/#/layanan/om-be-referensi?folder=2026-10-01`); await page.waitForSelector('main .note'); await page.waitForTimeout(300);
  cek('folder 1 Oct: empty service page explains why', /Tidak ada log untuk layanan ini/.test(await page.textContent('main')));
  await page.goto(`${BASE}/#/layanan/om-be-appsmanager?folder=2026-10-06`); await siap();
  const pesan = page.locator('section.dt', { has: page.locator('h2', { hasText: 'Pesan error / warning' }) });
  await pesan.locator('input[type=search]').fill('JWT'); await page.waitForTimeout(900); await page.waitForLoadState('networkidle');
  const baris = await pesan.locator('tbody tr').allTextContents();
  const umum = await pesan.locator('[aria-live]').textContent();
  cek('message filter "JWT": only matching rows + "N baris cocok"', baris.length > 0 && baris.every((x) => /jwt/i.test(x)) && /\d+ baris cocok/.test(umum), `${baris.length} rows; ${umum}`);

  // ------------------------------------------------------------------ 2 languages × 2 themes × 2 widths
  for (const lang of ['id', 'en']) for (const theme of ['dark', 'light']) for (const w of [1440, 390]) {
    await page.setViewportSize({ width: w, height: 900 });
    await page.evaluate(([l, th]) => { localStorage.setItem('lang', l); localStorage.setItem('theme', th); }, [lang, theme]);
    for (const [u, nama] of [['/#/overview?folder=2026-10-06', 'overview'], ['/#/layanan/nginx-ingress-controller?folder=2026-10-06', 'nginx']]) {
      await page.goto(BASE + u); await page.reload(); await siap();
      const st = await page.evaluate(() => [document.documentElement.scrollWidth, innerWidth, document.documentElement.lang, document.documentElement.dataset.theme,
        document.querySelectorAll('main section.card').length]);
      const judul = await judulBaru(page);
      const sisaId = lang === 'en' ? judul.filter((j) => /\b(per jam|layanan|pesan|gagal|dengan|lambat|ringkasan)\b/i.test(j)) : [];
      cek(`${nama} ${lang}/${theme}/${w}px: no horizontal scroll, all cards, text in the right language`,
        st[0] <= st[1] && st[2] === lang && st[3] === theme && st[4] >= (nama === 'overview' ? 20 : 15) && sisaId.length === 0,
        `width ${st[0]}/${st[1]}, ${st[4]} cards${sisaId.length ? ', still ID: ' + sisaId.join(', ') : ''}`);
      await page.screenshot({ path: `${OUT}/t13-${nama}-${lang}-${theme}-${w}.png`, fullPage: w === 390 ? false : true });
    }
  }
  cek('no page/console errors', errs.length === 0, errs.slice(0, 3).join(' | '));
  await browser.close();
  const gagal = hasil.filter((x) => !x).length;
  console.log(`\n${hasil.length - gagal} passed, ${gagal} failed`);
  process.exit(gagal ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
