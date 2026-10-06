// Verifikasi Tahap 14 (Tren) di Chromium: v2 berdampingan dengan ../dashboard.html lama.
//   node tools/uji_tahap14.cjs http://127.0.0.1:8000 <sandi-admin> [mode]
// mode "rentang": server memakai database simulasi > 30 folder; yang diperiksa hanya pemilih rentang.
// Dashboard lama dibuka sebagai file; Chart.js diganti tiruan yang MENCATAT data tiap chart, lalu dibandingkan dengan
// tampilan "Lihat sebagai tabel" chart v2. Butuh PLAYWRIGHT_MODULE (opsional CHROMIUM_PATH, SHOTS_DIR).
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const path = require('path');
const fs = require('fs');
const [, , BASE = 'http://127.0.0.1:8000', PW, MODE] = process.argv;
const LAMA = 'file://' + path.resolve(__dirname, '..', '..', 'dashboard.html');
const OUT = process.env.SHOTS_DIR || path.join(require('os').tmpdir(), 's4-shots');
fs.mkdirSync(OUT, { recursive: true });
const hasil = [];
const cek = (n, ok, info = '') => { hasil.push(!!ok); console.log(`${ok ? 'LULUS' : 'GAGAL'}  ${n}${info ? '  — ' + info : ''}`); };
const bil = (s) => { const t = String(s ?? '').replace(/[^\d-]/g, ''); return t === '' ? 0 : +t; };
const norm = (s) => String(s).toLowerCase().replace(/\s+/g, ' ').trim();

const CHART_STUB = `(() => { const deep = () => new Proxy({}, { get: (t, k) => (k in t ? t[k] : (t[k] = deep())), set: (t, k, v) => ((t[k] = v), true) });
  window.__charts = {}; window.Chart = class { constructor(el, cfg) { window.__charts[el.id] = { labels: cfg.data.labels,
    datasets: cfg.data.datasets.map((d) => ({ label: d.label, data: d.data })) }; } destroy() {} }; window.Chart.defaults = deep(); })();`;

async function masuk(page) {
  await page.fill('#u', 'admin'); await page.fill('#p', PW); await page.click('button[type=submit]');
  await page.waitForSelector('aside nav');
}
const siap = async (page) => { await page.waitForSelector('main section.card'); await page.waitForLoadState('networkidle'); await page.waitForTimeout(400); };

(async () => {
  const browser = await chromium.launch(process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {});
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();
  const errs = [];
  page.on('pageerror', (e) => errs.push(e.message));
  page.on('console', (m) => m.type() === 'error' && !/status of 401/.test(m.text()) && errs.push(m.text()));
  const reqs = [];
  page.on('request', (r) => r.url().includes('/api/trends') && reqs.push(r.url()));
  await page.goto(BASE + '/#/tren');
  await masuk(page); await siap(page);

  if (MODE === 'rentang') {
    // ------------------------------------------------------------------ pemilih rentang (database simulasi)
    const kolom = () => page.$$eval('section.card table', (t) => t[0].querySelectorAll('thead th').length - 1);
    const n = {};
    for (const r of ['14', '30', '90', 'all']) {
      await page.selectOption('#tr-range', r); await page.waitForTimeout(300); await siap(page);
      n[r] = await kolom();
    }
    const total = n.all;
    cek('pemilih rentang: jumlah kolom berubah (14 / 30 / 90 / semua)', n['14'] === 14 && n['30'] === 30 && n['90'] === Math.min(90, total) && total > 30, JSON.stringify(n));
    cek('pilihan rentang memanggil /api/trends?last=…', ['14', '30', '90', 'all'].every((r) => reqs.some((u) => u.endsWith(`last=${r}`))));
    await page.selectOption('#tr-range', '30'); await siap(page);
    const posisi = await page.$eval('section.card .tt', (el) => [el.scrollLeft, el.scrollWidth - el.clientWidth]);
    cek('tabel mulai di ujung kanan (folder terbaru terlihat)', posisi[1] > 0 && Math.abs(posisi[0] - posisi[1]) <= 2, posisi.join('/'));
    const kunci = await page.$eval('section.card .tt', (el) => { el.scrollLeft = 300; const a = el.getBoundingClientRect().left, th = el.querySelector('tbody th.first').getBoundingClientRect().left;
      return Math.round(th - a); });
    cek('kolom Layanan terkunci saat digulir mendatar', Math.abs(kunci) <= 1, `geser ${kunci}px`);
    await page.reload(); await siap(page);
    cek('rentang diingat setelah muat ulang', (await page.$eval('#tr-range', (e) => e.value)) === '30');
    await page.screenshot({ path: `${OUT}/t14-rentang-30.png`, fullPage: true });
  } else {
    // ------------------------------------------------------------------ chart dan tabel vs lama (11 folder)
    const lctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
    await lctx.route(/^https?:\/\//, (r) => r.abort());
    await lctx.addInitScript(CHART_STUB);
    const lp = await lctx.newPage();
    await lp.goto(LAMA);
    await lp.evaluate(() => { tab = 'tren'; render(); });
    const lama = await lp.evaluate(() => window.__charts);
    const tabelLama = await lp.$$eval('#main .card', (cards) => cards.filter((c) => c.querySelector('table')).map((c) => ({
      title: c.querySelector('h3').textContent.trim(),
      rows: [...c.querySelectorAll('tr')].slice(1).map((tr) => [...tr.cells].map((td) => td.textContent.replace(/\s+/g, ' ').trim())) })));
    await lctx.close();
    await page.selectOption('#tr-range', 'all'); await siap(page);

    const PETA = [['t1', 'Error per hari per layanan'], ['t2', 'Warning per hari per layanan'], ['t3', 'Request HTTP per hari'], ['t4', 'Keamanan per hari'],
                  ['t5', 'Aktivitas bisnis per hari'], ['t6', 'Baris log per hari per layanan']];
    for (const [id, judul] of PETA) {
      const card = page.locator('section.card', { has: page.locator('h2', { hasText: judul }) }).first();
      await card.locator('button', { hasText: 'Lihat sebagai tabel' }).click();
      const t = await card.evaluate((c) => ({ head: [...c.querySelectorAll('thead th')].map((x) => x.textContent.trim()).slice(1),
        rows: [...c.querySelectorAll('tbody tr')].map((tr) => [...tr.cells].map((x) => x.textContent.trim())) }));
      const L = lama[id];
      const beda = [];
      if (t.rows.length !== L.labels.length) beda.push(`kolom folder ${t.rows.length} vs ${L.labels.length}`);
      L.datasets.forEach((d) => {
        const j = t.head.findIndex((h) => norm(h) === norm(d.label));
        if (j < 0) return beda.push(`seri tidak ada: ${d.label}`);
        d.data.forEach((v, i) => { if ((v ?? 0) !== bil(t.rows[i]?.[j + 1])) beda.push(`${d.label} ${L.labels[i]}: ${v} vs ${t.rows[i]?.[j + 1]}`); });
      });
      cek(`chart "${judul}": seri dan angka sama dengan lama (11 folder)`, beda.length === 0, beda.length ? beda.slice(0, 4).join('; ') : `${L.datasets.length} seri × ${L.labels.length} folder`);
      await card.locator('button', { hasText: 'Lihat sebagai chart' }).click();
    }

    const tabelBaru = await page.$$eval('main section.card', (cards) => cards.filter((c) => c.querySelector('table') && c.querySelector('.tt')).map((c) => ({
      title: c.querySelector('h2').textContent.trim(),
      rows: [...c.querySelectorAll('tbody tr')].map((tr) => [...tr.cells].map((td) => td.textContent.replace(/\s+/g, ' ').trim())) })));
    for (const [i, nama] of [[0, 'Error per layanan & perubahan'], [1, 'Kelengkapan data']]) {
      const a = tabelLama[i], b = tabelBaru[i];
      let rusak = 0;
      const beda = [];
      a.rows.forEach((r, ri) => r.forEach((sel, ci) => {
        let x = norm(b.rows[ri]?.[ci] ?? '');
        if (ci > 0 && i === 1 && /\d\s*rusak$/.test(x)) { rusak++; x = x.replace(/\s*rusak$/, ''); }           // tanda baru B05 di sel berangka
        if (ci > 0 && i === 1 && x === 'rusak' && norm(sel) === 'kosong') { rusak++; x = 'kosong'; }            // B05: file kosong karena rusak
        if (ci > 0 && i === 1 && x === 'tidak ada') x = 'tidak ada';
        const y = norm(sel);
        if (ci > 0 ? x.replace(/[.,]/g, '') !== y.replace(/[.,]/g, '') : x !== y) beda.push(`${r[0]} kol ${ci}: lama "${sel}" baru "${b.rows[ri]?.[ci]}"`);
      }));
      cek(`tabel "${nama}": tiap sel sama dengan lama${i === 1 ? ' (kecuali tanda "Rusak" baru, B05)' : ''}`, beda.length === 0 && a.rows.length === b.rows.length,
        beda.length ? beda.slice(0, 4).join('; ') : `${a.rows.length} layanan × ${a.rows[0].length - 1} folder${i === 1 ? `; tanda Rusak: ${rusak}` : ''}`);
    }
    const sl = tabelBaru[1].rows.find((r) => r[0] === 'om-be-simpel-loop');
    cek('Kelengkapan: simpel-loop 30 Sep "Tidak ada"', norm(sl[5]) === 'tidak ada', sl[5]);
    const ok1 = tabelBaru[1].rows.map((r) => r[6]);
    cek('Kelengkapan: 1 Okt berisi "Rusak"/"Kosong"', ok1.some((x) => /Rusak/.test(x)) && ok1.some((x) => /Kosong/.test(x)), ok1.join(' | '));
    const fp = await page.$eval('#folder-select', (e) => [e.disabled, e.title]);
    cek('pemilih folder nonaktif dengan keterangan', fp[0] && /semua folder/i.test(fp[1]), fp[1]);
    const mobil = await (async () => {
      await page.setViewportSize({ width: 390, height: 844 }); await page.waitForTimeout(400);
      return page.evaluate(() => [document.documentElement.scrollWidth, innerWidth, getComputedStyle(document.querySelector('.tt td')).display]);
    })();
    cek('390 px: tabel Tren tetap menggulir mendatar (bukan kartu), halaman tanpa gulir mendatar', mobil[0] <= mobil[1] && mobil[2] === 'table-cell', mobil.join(' '));
    // 2 bahasa × 2 tema × 2 lebar
    for (const lang of ['id', 'en']) for (const theme of ['dark', 'light']) for (const w of [1440, 390]) {
      await page.setViewportSize({ width: w, height: 900 });
      await page.evaluate(([l, th]) => { localStorage.setItem('lang', l); localStorage.setItem('theme', th); }, [lang, theme]);
      await page.reload(); await siap(page);
      const st = await page.evaluate(() => [document.documentElement.scrollWidth, innerWidth, document.documentElement.lang, document.documentElement.dataset.theme,
        document.querySelectorAll('main section.card').length, [...document.querySelectorAll('main section.card h2')].map((h) => h.textContent.trim())]);
      const sisa = lang === 'en' ? st[5].filter((j) => /\b(per hari|layanan|kelengkapan|keamanan)\b/i.test(j)) : [];
      cek(`tren ${lang}/${theme}/${w}px: tanpa gulir mendatar, 8 kartu, teks sesuai bahasa`, st[0] <= st[1] && st[2] === lang && st[3] === theme && st[4] === 8 && !sisa.length,
        `lebar ${st[0]}/${st[1]}, ${st[4]} kartu${sisa.length ? ', masih ID: ' + sisa.join(', ') : ''}`);
      await page.screenshot({ path: `${OUT}/t14-${lang}-${theme}-${w}.png`, fullPage: w === 1440 });
    }
    await page.evaluate(() => { localStorage.setItem('lang', 'id'); localStorage.setItem('theme', 'dark'); });
  }
  cek('tidak ada galat halaman/konsol', errs.length === 0, errs.slice(0, 3).join(' | '));
  await browser.close();
  const gagal = hasil.filter((x) => !x).length;
  console.log(`\n${hasil.length - gagal} lulus, ${gagal} gagal`);
  process.exit(gagal ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
