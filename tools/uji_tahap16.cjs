// Stage 16 verification (Root Causes, Availability) in Chromium: v2 side by side with the old ../dashboard.html.
//   node tools/uji_tahap16.cjs http://127.0.0.1:8000 <admin-password>
// EXPECTED differences (TRD §4.4 item 1): nginx → pod connection errors are no longer cut at 200 (KPI and summary
// sentence use the full count; the table shows the first 200 + "show next"); 401 clients table 30 of N.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const path = require('path');
const fs = require('fs');
const [, , BASE = 'http://127.0.0.1:8000', PW] = process.argv;
const LAMA = 'file://' + path.resolve(__dirname, '..', '..', 'dashboard.html');
const OUT = process.env.SHOTS_DIR || path.join(require('os').tmpdir(), 's4-shots');
fs.mkdirSync(OUT, { recursive: true });
const hasil = [];
const cek = (n, ok, info = '') => { hasil.push(!!ok); console.log(`${ok ? 'PASS' : 'FAIL'}  ${n}${info ? '  — ' + info : ''}`); };
const rapat = (s) => String(s ?? '').toLowerCase().replace(/(\d)[.,](\d{3})\b/g, '$1$2').replace(/\s+/g, '');
const norm = (s) => String(s).toLowerCase().replace(/\s+/g, ' ').trim();
const bil = (s) => +String(s ?? '').replace(/[^\d-]/g, '') || 0;
const CHART_STUB = `(() => { const deep = () => new Proxy({}, { get: (t, k) => (k in t ? t[k] : (t[k] = deep())), set: (t, k, v) => ((t[k] = v), true) });
  window.__charts = {}; window.Chart = class { constructor(el, cfg) { window.__charts[el.id] = { labels: cfg.data.labels,
    datasets: cfg.data.datasets.map((d) => ({ label: d.label, data: d.data })) }; } destroy() {} }; window.Chart.defaults = deep(); })();`;
const tabel = (p, sel, judul) => p.$$eval(sel, (cards, judul) => {
  const c = cards.find((x) => x.querySelector('table') && (x.querySelector('h3, h2')?.childNodes[0]?.textContent || '').trim().toLowerCase().startsWith(judul));   // chart cards with similar titles are skipped
  if (!c) return null;
  return [...c.querySelectorAll('tr')].filter((tr) => tr.querySelector('td') && !tr.querySelector('td[colspan]')).map((tr) => [...tr.cells].map((td) => td.innerText));
}, judul);

(async () => {
  const browser = await chromium.launch(process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {});
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();
  const errs = [];
  page.on('pageerror', (e) => errs.push(e.message));
  page.on('console', (m) => m.type() === 'error' && !/status of 401/.test(m.text()) && errs.push(m.text()));
  await page.goto(BASE + '/#/akar-masalah?folder=2026-09-29');
  await page.fill('#u', 'admin'); await page.fill('#p', PW); await page.click('button[type=submit]');
  const siap = async () => { await page.waitForSelector('main section.card, main .note'); await page.waitForLoadState('networkidle'); await page.waitForTimeout(500); };
  await siap();
  const lctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  await lctx.route(/^https?:\/\//, (r) => r.abort());
  await lctx.addInitScript(CHART_STUB);
  const lp = await lctx.newPage();
  await lp.goto(LAMA);
  const lama = async (f, tab) => { await lp.evaluate(([d, t]) => { window.__charts = {}; day = d; tab = t; render(); }, [f, tab]); return lp.evaluate(() => window.__charts); };
  const chartTabel = async (judul) => {
    const card = page.locator('section.card', { has: page.locator('h2', { hasText: judul }) }).first();
    await card.locator('button', { hasText: 'Lihat sebagai tabel' }).click();
    const t = await card.evaluate((c) => ({ head: [...c.querySelectorAll('thead th')].map((x) => x.textContent.trim()).slice(1),
      rows: [...c.querySelectorAll('tbody tr')].map((tr) => [...tr.cells].map((x) => x.textContent.trim())) }));
    await card.locator('button', { hasText: 'Lihat sebagai chart' }).click();
    return t;
  };
  const samaSeri = (L, t) => {
    const beda = [];
    if (!L) return ['old chart missing'];
    L.datasets.forEach((d, k) => {
      const j = L.datasets.length === 1 ? 0 : t.head.findIndex((h) => norm(h) === norm(d.label ?? ''));
      if (j < 0) return beda.push(`series ${d.label}`);
      d.data.forEach((v, i) => { if ((v ?? 0) !== bil(t.rows[i]?.[j + 1])) beda.push(`${d.label ?? ''}[${i}] ${v} vs ${t.rows[i]?.[j + 1]}`); });
    });
    if (t.rows.length !== L.labels.length) beda.push(`points ${t.rows.length} vs ${L.labels.length}`);
    return beda;
  };

  // ------------------------------------------------------------------ Root Causes
  for (const f of ['2026-09-29', '2026-10-06', '2026-09-30', '2026-09-27']) {
    await page.goto(`${BASE}/#/akar-masalah?folder=${f}`); await siap();
    const C = await lama(f, 'akar-masalah');
    const sl = await lp.$$eval('.alert li', (e) => e.map((x) => x.textContent));
    const sb = await page.$$eval('main .alert li', (e) => e.map((x) => x.textContent));
    // item 5: connection error count is now full (old was cut at 200)
    const diharapkan = (a, b) => /error koneksi nginx → pod/.test(a) && rapat(a).replace(/^\d+/, '') === rapat(b).replace(/^\d+/, '');
    const beda = sl.map((x, i) => [x, sb[i]]).filter(([a, b]) => rapat(a) !== rapat(b) && !diharapkan(a, b || ''));
    const butir5 = sl.map((x, i) => [x, sb[i]]).filter(([a, b]) => rapat(a) !== rapat(b) && diharapkan(a, b || ''));
    cek(`root causes ${f}: summary ${sl.length} items same as old`, sl.length === sb.length && !beda.length,
      beda.length ? beda.slice(0, 2).map(([a, b]) => `old "${a.slice(0, 80)}" | new "${(b || '').slice(0, 80)}"`).join(' ;; ')
                  : (butir5.length ? `expected difference (item 1): ${butir5.map(([a, b]) => `${a.match(/^\s*([\d.,]+)/)?.[1]} → ${b.match(/^\s*([\d.,]+)/)?.[1]}`).join(', ')}` : ''));
    if (!sl.length) cek(`root causes ${f}: "tidak ada pola" note`, /Tidak ada pola akar masalah/.test(await page.textContent('main')));
    const jl = (await lp.$$eval('#main .card h3', (e) => e.map((x) => x.childNodes[0].textContent.trim()))).map(norm);
    const jb = (await page.$$eval('main .grid section.card > header h2', (e) => e.map((x) => x.childNodes[0].textContent.trim()))).map(norm);
    cek(`root causes ${f}: cards same as old`, jl.length === jb.length && jl.every((x) => jb.includes(x)), `${jb.length} cards`);
    if (C.r2) cek(`root causes ${f}: JWT age chart identical`, !samaSeri(C.r2, await chartTabel('Umur token JWT')).length);
    if (C.r3) cek(`root causes ${f}: PDF per template chart identical`, !samaSeri(C.r3, await chartTabel('Pembuatan PDF report')).length);
    if (C.r4) {
      const b = samaSeri(C.r4, await chartTabel('Error koneksi nginx → pod per jenis'));
      cek(`root causes ${f}: connection errors by type chart identical${f === '2026-09-30' ? ' (except the uncut count)' : ''}`, f === '2026-09-30' ? true : !b.length, b.slice(0, 2).join('; '));
    }
    for (const [judul, kol] of [['status pembuatan pdf', [0, 1, 2]], ['dns timeout per domain', [0, 1, 2]]]) {
      const a = await tabel(lp, '#main .card', judul), b = await tabel(page, 'main section.card', judul);
      if (!a && !b) continue;
      const K = (rows) => (rows || []).map((r) => kol.map((i) => rapat(r[i])).join('|')).sort();
      const A = K(a), B = K(b);
      cek(`root causes ${f}: table "${judul}" identical (${A.length} rows)`, A.length === B.length && A.every((x) => B.includes(x)), A.filter((x) => !B.includes(x)).slice(0, 2).join(' ;; '));
    }
    const a401 = await tabel(lp, '#main .card', 'klien dengan 401 berulang'), b401 = await tabel(page, 'main section.card', 'klien dengan 401 berulang');
    if (a401) {
      const K = (rows) => rows.map((r) => [r[0].split('\n')[0], r[1], r[2], r[3]].map(rapat).join('|'));
      const foot = await page.locator('section.dt', { has: page.locator('h2', { hasText: 'Klien dengan 401 berulang' }) }).locator('.foot .muted').textContent().catch(() => '');
      // count order identical; rows above the cutoff value equal as sets; equal-valued rows at the 30 cutoff may be chosen differently (rule E2)
      const A = K(a401), B = K(b401).slice(0, a401.length), nA = A.map((x) => +x.split('|')[2]), nB = B.map((x) => +x.split('|')[2]);
      const batas = Math.min(...nA), atas = (L) => L.filter((x) => +x.split('|')[2] > batas).sort();
      cek(`root causes ${f}: 401 table = ${a401.length} old rows (same counts in order; ties may differ in order) + "Menampilkan 30 dari N"`,
        a401.length > 0 && JSON.stringify(nA) === JSON.stringify(nB) && JSON.stringify(atas(A)) === JSON.stringify(atas(B)) && /Menampilkan 30 dari/.test(foot), foot);
    }
    if (f === '2026-09-29') {
      const rt = await page.textContent('main');
      cek('29 Sep: new "Refresh token kedaluwarsa: 237" below the JWT chart', /Refresh token kedaluwarsa: 237/.test(rt));
      await page.screenshot({ path: `${OUT}/t16-akar-0929.png`, fullPage: true });
    }
  }

  // ------------------------------------------------------------------ Availability
  for (const f of ['2026-09-30', '2026-10-06', '2026-09-28']) {
    await page.goto(`${BASE}/#/ketersediaan?folder=${f}`); await siap();
    const C = await lama(f, 'ketersediaan');
    if (f === '2026-09-28') {
      cek('availability 28 Sep: note "memakai log ingress nginx…"', /Analisis ketersediaan memakai log ingress nginx/.test(await page.textContent('main')));
      continue;
    }
    const kl = await lp.$$eval('.kpi', (e) => e.map((x) => [x.querySelector('.l').textContent.trim(), x.querySelector('.v').textContent.trim()]));
    const kb = Object.fromEntries(await page.$$eval('main .kpi', (e) => e.map((x) => [x.querySelector('.l').textContent.trim().toLowerCase(), x.querySelector('.v').textContent.trim()])));
    const bedaK = kl.filter(([l, v]) => rapat(kb[l.toLowerCase()]) !== rapat(v));
    const harap = bedaK.filter(([l]) => /error koneksi ke pod/i.test(l));
    cek(`availability ${f}: 7 KPIs same as old, except pod connection errors (item 1)`, kl.length === 7 && bedaK.length === harap.length,
      kl.map(([l, v]) => `${v}${/error koneksi/i.test(l) ? `→${kb[l.toLowerCase()]}` : ''}`).join(' · ') + (bedaK.length > harap.length ? ' | DIFF ' + JSON.stringify(bedaK) : ''));
    if (f === '2026-09-30') cek('30 Sep: pod connection error KPI 1,200 (old 200), retry 825, 10 incidents',
      bil(kb['error koneksi ke pod']) === 1200 && bil(kb['retry ke pod lain']) === 825 && bil(kb['insiden 5xx']) === 10);
    const jl = (await lp.$$eval('#main .card h3', (e) => e.map((x) => x.childNodes[0].textContent.trim()))).map(norm);
    const jb = (await page.$$eval('main .grid section.card > header h2', (e) => e.map((x) => x.childNodes[0].textContent.trim()))).map(norm);
    cek(`availability ${f}: cards same as old`, jl.length === jb.length && jl.every((x) => jb.includes(x)), `${jb.length} cards`);
    cek(`availability ${f}: 5xx per hour chart identical`, !samaSeri(C.a1, await chartTabel('Respons 5xx per jam')).length);
    cek(`availability ${f}: 5xx per upstream chart identical`, !samaSeri(C.a2, await chartTabel('Respons 5xx per upstream')).length);
    if (C.a3) cek(`availability ${f}: Uptime-Kuma chart identical`, !samaSeri(C.a3, await chartTabel('Health check Uptime-Kuma')).length);
    for (const [judul, kol] of [['ketersediaan per upstream', [0, 1, 2, 3]], ['daftar insiden 5xx', [0, 1, 2, 3, 4]], ['target health check', [0, 1]]]) {
      const a = await tabel(lp, '#main .card', judul), b = await tabel(page, 'main section.card', judul);
      if (!a && !b) continue;
      const K = (rows) => (rows || []).map((r) => kol.map((i) => rapat(r[i]).replace(/mnt$|min$/, '')).join('|')).sort();
      const A = K(a), B = K(b);
      cek(`availability ${f}: table "${judul}" identical (${A.length} rows)`, A.length === B.length && A.every((x) => B.includes(x)), A.filter((x) => !B.includes(x)).slice(0, 2).join(' ;; ').slice(0, 300));
    }
    const ue = await tabel(page, 'main section.card', 'error koneksi nginx → pod');
    const foot = await page.locator('section.dt', { has: page.locator('h2', { hasText: 'Error koneksi nginx → pod' }) }).locator('.foot .muted').textContent().catch(() => '');
    cek(`availability ${f}: connection error table first 200 + more`, ue.length === Math.min(200, bil(kb['error koneksi ke pod'])) && (bil(kb['error koneksi ke pod']) <= 200 || /Menampilkan 200 dari/.test(foot)), `${ue.length} rows; ${foot}`);
    if (f === '2026-09-30') await page.screenshot({ path: `${OUT}/t16-ketersediaan-0930.png`, fullPage: true });
  }
  await lctx.close();

  // ------------------------------------------------------------------ 2 languages × 2 themes × 2 widths
  for (const lang of ['id', 'en']) for (const theme of ['dark', 'light']) for (const w of [1440, 390]) {
    await page.setViewportSize({ width: w, height: 900 });
    await page.evaluate(([l, th]) => { localStorage.setItem('lang', l); localStorage.setItem('theme', th); }, [lang, theme]);
    for (const [u, nama, min] of [['/#/akar-masalah?folder=2026-09-29', 'akar', 7], ['/#/ketersediaan?folder=2026-09-30', 'ketersediaan', 7]]) {
      await page.goto(BASE + u); await page.reload(); await siap();
      const st = await page.evaluate(() => [document.documentElement.scrollWidth, innerWidth, document.documentElement.lang, document.documentElement.dataset.theme,
        document.querySelectorAll('main section.card').length, [...document.querySelectorAll('main section.card h2, main .alert li')].map((h) => h.textContent.trim())]);
      const sisa = lang === 'en' ? st[5].filter((j) => /\b(dengan|berulang|kedaluwarsa|per jam|ketersediaan|insiden|gagal|dipakai)\b/i.test(j)) : [];
      cek(`${nama} ${lang}/${theme}/${w}px: no horizontal scroll, all cards, text in the right language`, st[0] <= st[1] && st[2] === lang && st[3] === theme && st[4] >= min && !sisa.length,
        `width ${st[0]}/${st[1]}, ${st[4]} cards${sisa.length ? ', still ID: ' + sisa.slice(0, 2).join(' | ') : ''}`);
      await page.screenshot({ path: `${OUT}/t16-${nama}-${lang}-${theme}-${w}.png`, fullPage: w === 1440 });
    }
  }
  await page.evaluate(() => { localStorage.setItem('lang', 'id'); localStorage.setItem('theme', 'dark'); });
  cek('no page/console errors', errs.length === 0, errs.slice(0, 3).join(' | '));
  await browser.close();
  const gagal = hasil.filter((x) => !x).length;
  console.log(`\n${hasil.length - gagal} passed, ${gagal} failed`);
  process.exit(gagal ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
