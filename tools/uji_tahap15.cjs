// Verifikasi Tahap 15 (Keamanan) di Chromium: v2 berdampingan dengan ../dashboard.html lama.
//   node tools/uji_tahap15.cjs http://127.0.0.1:8000 <sandi-admin>
// Dibandingkan: 8 KPI, kalimat "Temuan utama", daftar kartu, dan isi 5 tabel (kolom inti), untuk 06 Okt, 29 Sep
// (ada SQLi/XSS berisi <script>), dan 28 Sep (tanpa nginx). Juga: URL serangan tampil sebagai teks, tanpa eksekusi.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const path = require('path');
const fs = require('fs');
const [, , BASE = 'http://127.0.0.1:8000', PW] = process.argv;
const LAMA = 'file://' + path.resolve(__dirname, '..', '..', 'dashboard.html');
const OUT = process.env.SHOTS_DIR || path.join(require('os').tmpdir(), 's4-shots');
fs.mkdirSync(OUT, { recursive: true });
const hasil = [];
const cek = (n, ok, info = '') => { hasil.push(!!ok); console.log(`${ok ? 'LULUS' : 'GAGAL'}  ${n}${info ? '  — ' + info : ''}`); };
const rapat = (s) => String(s ?? '').toLowerCase().replace(/(\d)[.,](\d{3})\b/g, '$1$2').replace(/\s+/g, '');   // tanpa spasi, tanpa pemisah ribuan
const norm = (s) => String(s).toLowerCase().replace(/\s+/g, ' ').trim();
const CHART_STUB = `(() => { const deep = () => new Proxy({}, { get: (t, k) => (k in t ? t[k] : (t[k] = deep())), set: (t, k, v) => ((t[k] = v), true) });
  window.Chart = class { constructor() {} destroy() {} }; window.Chart.defaults = deep(); })();`;

// tabel lama/baru -> baris berisi teks sel (kolom inti dipilih pemanggil)
const tabel = (p, sel, judul) => p.$$eval(sel, (cards, judul) => {
  const c = cards.find((x) => x.querySelector('table') && (x.querySelector('h3, h2')?.childNodes[0]?.textContent || '').trim().toLowerCase().startsWith(judul));   // kartu chart berjudul mirip dilewati
  if (!c) return null;
  return [...c.querySelectorAll('tr')].filter((tr) => tr.querySelector('td') && !tr.querySelector('td[colspan]')).map((tr) => [...tr.cells].map((td) => td.innerText));
}, judul);

(async () => {
  const browser = await chromium.launch(process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {});
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();
  const errs = [], dialogs = [];
  page.on('pageerror', (e) => errs.push(e.message));
  page.on('console', (m) => m.type() === 'error' && !/status of 401/.test(m.text()) && errs.push(m.text()));
  page.on('dialog', (d) => { dialogs.push(d.message()); d.dismiss(); });          // alert() dari URL serangan = tereksekusi
  await page.goto(BASE + '/#/keamanan?folder=2026-10-06');
  await page.fill('#u', 'admin'); await page.fill('#p', PW); await page.click('button[type=submit]');
  const siap = async () => { await page.waitForSelector('main .kpi'); await page.waitForLoadState('networkidle'); await page.waitForTimeout(500); };
  await siap();

  const lctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  await lctx.route(/^https?:\/\//, (r) => r.abort());
  await lctx.addInitScript(CHART_STUB);
  const lp = await lctx.newPage();
  lp.on('dialog', (d) => d.dismiss());
  await lp.goto(LAMA);

  for (const f of ['2026-10-06', '2026-09-29', '2026-09-28']) {
    await page.goto(`${BASE}/#/keamanan?folder=${f}`); await siap();
    await lp.evaluate((d) => { day = d; tab = 'keamanan'; render(); }, f);
    // KPI
    const kl = await lp.$$eval('.kpi', (e) => e.map((x) => [x.querySelector('.l').textContent.trim(), x.querySelector('.v').textContent.trim()]));
    const kb = await page.$$eval('main .kpi', (e) => e.map((x) => [x.querySelector('.l').textContent.trim(), x.querySelector('.v').textContent.trim()]));
    cek(`${f}: 8 KPI sama dengan lama`, kl.length === 8 && kb.length === 8 && kl.every(([l, v], i) => norm(kb[i][0]) === norm(l) && rapat(kb[i][1]) === rapat(v)),
      kb.map(([l, v]) => `${v}`).join(' · '));
    // temuan
    const tl = await lp.$$eval('.alert li', (e) => e.map((x) => x.textContent));
    const tb = await page.$$eval('main .alert li', (e) => e.map((x) => x.textContent));
    const bedaT = tl.map((x, i) => [x, tb[i]]).filter(([a, b]) => rapat(a) !== rapat(b));
    cek(`${f}: "Temuan utama" ${tl.length} butir, kalimat sama dengan lama`, tl.length === tb.length && bedaT.length === 0,
      bedaT.length ? bedaT.slice(0, 2).map(([a, b]) => `lama "${a.slice(0, 90)}" | baru "${(b || '').slice(0, 90)}"`).join(' ;; ') : tb.map((x) => x.slice(0, 40)).join(' | '));
    // kartu
    const jl = (await lp.$$eval('#main .card h3', (e) => e.map((x) => x.childNodes[0].textContent.trim()))).map(norm);
    const jb = (await page.$$eval('main .grid section.card > header h2', (e) => e.map((x) => x.childNodes[0].textContent.trim()))).map(norm);
    const kurang = jl.filter((x) => !jb.includes(x)), lebih = jb.filter((x) => !jl.includes(x));
    cek(`${f}: kartu chart dan tabel sama dengan lama`, !kurang.length && !lebih.length, `${jb.length} kartu` + (kurang.length ? ' | kurang: ' + kurang.join(', ') : '') + (lebih.length ? ' | lebih: ' + lebih.join(', ') : ''));
    // isi tabel: kolom inti, dibandingkan sebagai himpunan (urutan antar baris bernilai sama boleh beda)
    const TAB = [['endpoint dengan indikasi serangan', [0, 1, 2, 4, 5, 6], [0, 1, 2, 4, 5, 6]], ['ip sumber serangan', [1, 2, 3, 4], [1, 2, 3, 4]],
                 ['analisis akun', [0, 1, 2, 3, 6], [0, 1, 2, 3, 6]], ['login gagal / brute force', [1, 2, 3, 4], [1, 2, 3, 4]], ['ip dengan respons 4xx terbanyak', [1, 2], [1, 2]]];
    for (const [judul, kL, kB] of TAB) {
      const a = await tabel(lp, '#main .card', judul), b = await tabel(page, 'main section.card', judul);
      if (a === null && b === null) continue;
      const kunci = (rows, k) => rows.map((r) => k.map((i) => rapat(r[i]).replace(/2xx–verifikasi|2xx–verify/, '!2xx')).join('|')).sort();
      const A = kunci(a || [], kL), B = kunci(b || [], kB);
      const hilang = A.filter((x) => !B.includes(x));
      cek(`${f}: tabel "${judul}" sama (${A.length} baris)`, A.length === B.length && hilang.length === 0, hilang.length ? 'beda: ' + hilang.slice(0, 2).join(' ;; ').slice(0, 300) : '');
    }
    if (f === '2026-09-28') {
      cek('28 Sep (tanpa nginx): catatan "deteksi serangan per URL tidak tersedia"; bagian login tetap',
        /deteksi serangan per URL tidak tersedia/.test(await page.textContent('main')) && !!(await tabel(page, 'main section.card', 'login gagal / brute force')));
    }
    if (f === '2026-09-29') {
      const t = await page.textContent('main');
      const dom = await page.evaluate(() => [document.querySelectorAll('main script, main img[src="x"]').length, [...document.querySelectorAll('main code')].some((c) => c.textContent.includes('<script>alert("XSS");</script>'))]);
      cek('URL berisi <script> / onerror tampil sebagai teks, tidak dieksekusi', t.includes('<script>alert("XSS");</script>') && dom[0] === 0 && dom[1] && dialogs.length === 0,
        `elemen tersisip ${dom[0]}, dialog ${dialogs.length}`);
      await page.screenshot({ path: `${OUT}/t15-0929.png`, fullPage: true });
    }
  }
  await lctx.close();

  // 2 bahasa × 2 tema × 2 lebar
  for (const lang of ['id', 'en']) for (const theme of ['dark', 'light']) for (const w of [1440, 390]) {
    await page.setViewportSize({ width: w, height: 900 });
    await page.evaluate(([l, th]) => { localStorage.setItem('lang', l); localStorage.setItem('theme', th); }, [lang, theme]);
    await page.goto(`${BASE}/#/keamanan?folder=2026-10-06`); await page.reload(); await siap();
    const st = await page.evaluate(() => [document.documentElement.scrollWidth, innerWidth, document.documentElement.lang, document.documentElement.dataset.theme,
      document.querySelectorAll('main section.card').length, [...document.querySelectorAll('main section.card h2, main .alert li')].map((h) => h.textContent.trim()),
      getComputedStyle(document.querySelector('main .kpis')).gridTemplateColumns.split(' ').length]);
    const sisa = lang === 'en' ? st[5].filter((j) => /\b(serangan|dengan|akun|kemungkinan|berasal|pemilik)\b/i.test(j)) : [];
    cek(`keamanan ${lang}/${theme}/${w}px: tanpa gulir mendatar, KPI ${w > 900 ? '4' : '2'} kolom, teks sesuai bahasa`,
      st[0] <= st[1] && st[2] === lang && st[3] === theme && st[4] >= 11 && st[6] === (w > 900 ? 4 : 2) && !sisa.length,
      `lebar ${st[0]}/${st[1]}, ${st[4]} kartu, KPI ${st[6]} kolom${sisa.length ? ', masih ID: ' + sisa.slice(0, 2).join(' | ') : ''}`);
    await page.screenshot({ path: `${OUT}/t15-${lang}-${theme}-${w}.png`, fullPage: w === 1440 });
  }
  await page.evaluate(() => { localStorage.setItem('lang', 'id'); localStorage.setItem('theme', 'dark'); });
  cek('tidak ada galat halaman/konsol', errs.length === 0, errs.slice(0, 3).join(' | '));
  await browser.close();
  const gagal = hasil.filter((x) => !x).length;
  console.log(`\n${hasil.length - gagal} lulus, ${gagal} gagal`);
  process.exit(gagal ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
