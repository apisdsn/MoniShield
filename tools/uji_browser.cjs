// Pemeriksaan Tahap 12 (rencana) di Chromium lewat Playwright: masuk, ganti sandi wajib, kerangka, folder di alamat,
// tabel, bahasa/tema, keyboard, user vs admin, layar 390/360 px. Butuh server berjalan dengan database akun BARU
// (admin belum ganti sandi). Playwright tidak termasuk dependensi proyek: PLAYWRIGHT_MODULE=/jalur/ke/playwright.
//   node tools/uji_browser.cjs http://127.0.0.1:8000 <sandi-awal-admin> <sandi-baru-admin>
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const fs = require('fs');
const path = require('path');

const [, , BASE = 'http://127.0.0.1:8000', PW0, PW1] = process.argv;
const OUT = process.env.SHOTS_DIR || path.join(require('os').tmpdir(), 's4-shots');
fs.mkdirSync(OUT, { recursive: true });
const hasil = [];
const cek = (nama, ok, info = '') => { hasil.push({ nama, ok: !!ok, info }); console.log(`${ok ? 'LULUS' : 'GAGAL'}  ${nama}${info ? '  — ' + info : ''}`); };

async function ctxWith(browser, opts = {}) {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, ...opts });
  const page = await ctx.newPage();
  page._errors = [];
  page.on('console', (m) => m.type() === 'error' && page._errors.push(m.text()));
  page.on('pageerror', (e) => page._errors.push('pageerror: ' + e.message));
  page._reqs = [];
  page.on('request', (r) => page._reqs.push(r.url()));
  page._bad = [];
  page.on('response', (r) => r.status() >= 400 && page._bad.push(`${r.status()} ${r.request().method()} ${r.url().replace(/^https?:\/\/[^/]+/, '')}`));
  return { ctx, page };
}

async function login(page, user, pw) {
  await page.fill('#u', user);
  await page.fill('#p', pw);
  await page.click('button[type=submit]');
}

(async () => {
  const browser = await chromium.launch(process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {});
  // ------------------------------------------------------------------ 1. layar Masuk, tanpa data sebelum masuk
  const { ctx, page } = await ctxWith(browser);
  await page.goto(BASE + '/#/keamanan');
  await page.waitForSelector('#u');
  cek('layar Masuk tampil tanpa sidebar', (await page.locator('aside').count()) === 0);
  const dataReq = page._reqs.filter((u) => /\/api\/(meta|folders|trends)/.test(u));
  cek('tidak ada data dashboard dimuat sebelum masuk', dataReq.length === 0, dataReq.join(', '));
  await page.screenshot({ path: `${OUT}/01-masuk-1440.png` });
  await login(page, 'admin', 'salah-sandi-xx');
  await page.waitForSelector('[role=alert]');
  cek('sandi salah: pesan satu kalimat + fokus kembali ke sandi', (await page.textContent('[role=alert]')).includes('Nama user atau sandi salah') &&
      (await page.evaluate(() => document.activeElement.id)) === 'p');
  // ------------------------------------------------------------------ 2. ganti sandi wajib
  await login(page, 'admin', PW0);
  await page.waitForSelector('#pw-old');
  cek('ganti sandi wajib tampil sendirian', (await page.locator('aside').count()) === 0 && (await page.textContent('body')).includes('harus mengganti sandi'));
  await page.fill('#pw-old', PW0); await page.fill('#pw-new', 'pendek'); await page.fill('#pw-again', 'pendek');
  await page.click('button[type=submit]');
  cek('galat per kolom di bawah kolom', await page.locator('#pw-new-e').isVisible());
  await page.fill('#pw-new', PW1); await page.fill('#pw-again', PW1);
  await page.click('button[type=submit]');
  await page.waitForSelector('aside nav');
  // ------------------------------------------------------------------ 3. kerangka setelah masuk
  await page.waitForFunction(() => document.querySelector('aside')?.textContent.includes('Om-Be-Simpel-Loop'));
  cek('kembali ke alamat yang diminta (#/keamanan)', page.url().includes('#/keamanan'), page.url());
  const grp = await page.$$eval('aside .grp', (e) => e.map((x) => x.textContent.trim()));
  cek('sidebar dua grup', grp.length === 2, grp.join(' | '));
  const badge = await page.textContent('aside a[href*="keamanan"]');
  cek('lencana Keamanan "14 IP"', /14 IP/.test(badge), badge.trim());
  const opts = await page.$$eval('#folder-select option', (o) => o.map((x) => x.textContent));
  cek('pemilih folder berisi 11 folder', opts.length === 11, opts[0]);
  const sub = await page.textContent('.sub');
  cek('subjudul memuat rentang waktu log', /berisi log .+WIB/.test(sub) && /\d+ layanan/.test(sub), sub);
  cek('folder ada di alamat', /folder=2026-10-06/.test(page.url()), page.url());
  await page.click('aside a[href*="#/overview"]');
  await page.waitForSelector('.kpis .kpi');
  await page.waitForSelector('canvas');
  await page.waitForTimeout(600);
  await page.screenshot({ path: `${OUT}/02-overview-gelap-1440.png`, fullPage: true });
  cek('tab Overview di alamat', page.url().includes('#/overview?folder='), page.url());
  // ganti folder lewat select dan pintasan
  await page.selectOption('#folder-select', '2026-09-29');
  await page.waitForFunction(() => document.querySelector('.sub')?.textContent.includes('29 Sep'));
  cek('ganti folder memperbarui alamat', page.url().includes('folder=2026-09-29'), page.url());
  await page.locator('body').press('[');
  await page.waitForFunction(() => location.hash.includes('2026-09-28'));
  cek('pintasan [ = folder sebelumnya', page.url().includes('2026-09-28'));
  await page.goBack();
  await page.waitForFunction(() => location.hash.includes('2026-09-29'));
  cek('tombol kembali browser mengembalikan folder', page.url().includes('2026-09-29'));
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(300);
  // tabel server: filter, urut, lanjutan
  const pesan = page.locator('section.dt', { hasText: 'Top pesan error' });
  const awal = await pesan.locator('tbody tr').count();
  const status = await pesan.locator('.foot .muted').textContent().catch(() => '');
  cek('tabel pesan: jumlah awal = batas lama (25) + "Menampilkan N dari M"', awal === 25 && /Menampilkan 25 dari/.test(status), `${awal} baris; ${status}`);
  await pesan.locator('.foot button').click();
  await page.waitForFunction(() => [...document.querySelectorAll('section.dt')].find((s) => s.textContent.includes('Top pesan error')).querySelectorAll('tbody tr').length > 25);
  cek('"Tampilkan berikutnya" memuat lanjutan', (await pesan.locator('tbody tr').count()) > 25, String(await pesan.locator('tbody tr').count()));
  await pesan.locator('input[type=search]').fill('timeout');
  await page.waitForTimeout(900);
  const sesudah = await pesan.locator('tbody tr').allTextContents();
  cek('filter mencari seluruh data di server', sesudah.length > 0 && sesudah.every((t) => /timeout|Tidak ada baris/i.test(t)), `${sesudah.length} baris`);
  await pesan.locator('th button').first().click();
  await page.waitForTimeout(600);
  cek('header urut memakai aria-sort', (await pesan.locator('th[aria-sort=descending]').count()) === 1);
  // ------------------------------------------------------------------ 4. bahasa, tema, ingat setelah muat ulang
  await page.click('[role=radio]:has-text("EN")');
  await page.click('[role=radio][aria-label="Light theme"]');
  await page.reload();
  await page.waitForSelector('aside nav');
  await page.waitForSelector('.kpis .kpi');
  const htmlAttr = await page.evaluate(() => [document.documentElement.lang, document.documentElement.dataset.theme]);
  cek('bahasa dan tema diingat setelah muat ulang', htmlAttr[0] === 'en' && htmlAttr[1] === 'light', htmlAttr.join(','));
  cek('teks antarmuka berbahasa Inggris', (await page.textContent('aside')).includes('Root Causes') && (await page.textContent('.sub')).includes('Log folder'));
  await page.waitForTimeout(600);
  await page.screenshot({ path: `${OUT}/03-overview-terang-en-1440.png`, fullPage: true });
  await page.click('[role=radio]:has-text("ID")');
  await page.click('[role=radio][aria-label="Tema gelap"]');
  // ------------------------------------------------------------------ 5. keyboard
  await page.goto('about:blank');
  await page.goto(BASE + '/#/overview?folder=2026-10-06');
  await page.waitForSelector('.kpis .kpi');
  await page.keyboard.press('Tab');
  const f1 = await page.evaluate(() => document.activeElement.textContent.trim());
  await page.keyboard.press('Tab');
  const f2 = await page.evaluate(() => document.activeElement.closest('nav') ? 'nav' : document.activeElement.tagName);
  const outline = await page.evaluate(() => getComputedStyle(document.activeElement).outlineStyle + ' ' + getComputedStyle(document.activeElement).outlineWidth);
  for (let i = 0; i < 25; i++) { await page.keyboard.press('Tab'); if (await page.evaluate(() => !!document.activeElement.closest('header'))) break; }
  const f3 = await page.evaluate(() => (document.activeElement.closest('header') ? 'header' : document.activeElement.tagName));
  cek('Tab: "Lewati ke isi" → navigasi → header; fokus terlihat', f1 === 'Lewati ke isi' && f2 === 'nav' && f3 === 'header' && !outline.startsWith('none'), `${f1} → ${f2} → ${f3}; outline ${outline}`);
  // ------------------------------------------------------------------ 6. user biasa
  const r = await page.evaluate(async () => {
    const x = await fetch('/api/admin/users', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'uji' },
      body: JSON.stringify({ username: 'uji', display_name: 'Uji', role: 'user', password: 'sandi-awal-uji-123' }) });
    return x.status;
  });
  cek('admin membuat user "uji"', r === 201 || r === 409, String(r));
  const u = await ctxWith(browser);
  await u.page.goto(BASE + '/#/overview');
  await u.page.waitForSelector('#u');
  await login(u.page, 'uji', 'sandi-awal-uji-123');
  await u.page.waitForSelector('#pw-old');
  await u.page.fill('#pw-old', 'sandi-awal-uji-123'); await u.page.fill('#pw-new', 'sandi-baru-uji-456'); await u.page.fill('#pw-again', 'sandi-baru-uji-456');
  await u.page.click('button[type=submit]');
  await u.page.waitForSelector('aside nav');
  await u.page.waitForFunction(() => document.querySelector('aside')?.textContent.includes('Om-Be-Simpel-Loop'));
  const navUser = await u.page.textContent('aside nav'), navAdmin = await page.textContent('aside nav');
  cek('sidebar user sama dengan admin', navUser === navAdmin);
  await u.page.click('button[aria-haspopup=menu] >> visible=true');
  const menu = await u.page.textContent('#user-menu');
  cek('menu user tanpa "Kelola user" dan "Ingest & impor"', !menu.includes('Kelola user') && !menu.includes('Ingest') && menu.includes('Ganti sandi') && menu.includes('Keluar'), menu.replace(/\s+/g, ' '));
  await u.page.keyboard.press('Escape');
  await page.click('button[aria-haspopup=menu] >> visible=true');
  const menuA = await page.textContent('#user-menu');
  cek('menu admin memuat "Kelola user" dan "Ingest & impor"', menuA.includes('Kelola user') && menuA.includes('Ingest & impor'));
  await page.keyboard.press('ArrowDown');
  const fokusMenu = await page.evaluate(() => document.activeElement.getAttribute('role'));
  await page.keyboard.press('Escape');
  const balik = await page.evaluate(() => document.activeElement.getAttribute('aria-haspopup'));
  cek('menu: panah berpindah, Esc menutup dan mengembalikan fokus', fokusMenu?.startsWith('menuitem') && balik === 'menu', `${fokusMenu} / ${balik}`);
  await u.page.goto(BASE + '/#/admin/user');
  await u.page.waitForSelector('text=Tidak punya akses');
  cek('alamat layar admin oleh user → "Tidak punya akses" (sidebar tetap)', (await u.page.locator('aside nav').count()) === 1);
  await u.page.screenshot({ path: `${OUT}/04-user-tanpa-akses-1440.png` });
  // 401 /api/me sebelum masuk, 401 login salah, 403 sebelum ganti sandi wajib = jawaban yang diharapkan (dicatat browser sebagai galat sumber daya)
  const diharapkan = (x) => /^401 GET \/api\/me$|^401 POST \/api\/auth\/login$/.test(x);
  const bad = [...page._bad, ...u.page._bad];
  cek('respons ≥ 400 hanya yang diharapkan', bad.every(diharapkan), [...new Set(bad)].join(' | '));
  const konsol = [...page._errors, ...u.page._errors].filter((x) => !/Failed to load resource: the server responded with a status of 401/.test(x));
  cek('tidak ada galat konsol lain (admin, user)', konsol.length === 0, konsol.slice(0, 3).join(' | '));
  const luar = [...page._reqs, ...u.page._reqs].filter((x) => !x.startsWith(BASE) && !x.startsWith('data:') && !x.startsWith('blob:'));
  cek('tidak ada permintaan ke domain lain', luar.length === 0, luar.slice(0, 3).join(', '));
  // ------------------------------------------------------------------ 7. layar sempit
  for (const w of [390, 360]) {
    const m = await ctxWith(browser, { viewport: { width: w, height: 800 }, isMobile: true, hasTouch: true, deviceScaleFactor: 2,
      storageState: await ctx.storageState() });
    await m.page.goto(BASE + '/#/overview?folder=2026-10-06');
    await m.page.waitForSelector('.kpis .kpi');
    await m.page.waitForTimeout(700);
    const lebar = await m.page.evaluate(() => [document.documentElement.scrollWidth, innerWidth]);
    cek(`${w}px: tidak ada gulir mendatar halaman`, lebar[0] <= lebar[1], `${lebar[0]} ≤ ${lebar[1]}`);
    const kol = await m.page.$eval('.kpis', (e) => getComputedStyle(e).gridTemplateColumns.split(' ').length);
    cek(`${w}px: KPI 2 kolom`, kol === 2, String(kol));
    cek(`${w}px: sidebar tersembunyi, tombol ☰ ada`, !(await m.page.locator('aside a').first().isVisible()) && (await m.page.locator('button.burger').isVisible()));
    const kartu = await m.page.$eval('section.dt.card .cards td:not(.k)', (e) => getComputedStyle(e).display).catch(() => 'tidak ada');
    cek(`${w}px: tabel > 4 kolom jadi kartu baris`, kartu === 'grid', kartu);
    await m.page.screenshot({ path: `${OUT}/05-overview-${w}.png`, fullPage: true });
    const kecil = await m.page.$$eval('header button, header select, .card button.btn', (els) => els.filter((e) => e.offsetParent).map((e) => {
      const r = e.getBoundingClientRect(); return [e.getAttribute('aria-label') || e.textContent.trim().slice(0, 20), Math.round(r.width), Math.round(r.height)];
    }).filter(([, wd, h]) => wd < 44 || h < 44));
    cek(`${w}px: target sentuh header ≥ 44 px`, kecil.filter(([n]) => !/Lihat sebagai/.test(n)).length === 0, JSON.stringify(kecil.slice(0, 4)));
    await m.page.click('button.burger');
    await m.page.waitForTimeout(300);
    const laci = await m.page.evaluate(() => [!!document.querySelector('aside.open'), document.activeElement.closest('aside') !== null, document.querySelector('.wrap').inert]);
    cek(`${w}px: laci terbuka, fokus di dalam, isi lain inert`, laci.every(Boolean), laci.join(','));
    await m.page.screenshot({ path: `${OUT}/06-laci-${w}.png` });
    const navT = await m.page.$$eval('aside a', (els) => els.map((e) => Math.round(e.getBoundingClientRect().height)));
    cek(`${w}px: butir navigasi ≥ 44 px`, Math.min(...navT) >= 44, String(Math.min(...navT)));
    await m.page.keyboard.press('Escape');
    await m.page.waitForTimeout(200);
    cek(`${w}px: Esc menutup laci, fokus kembali ke ☰`, await m.page.evaluate(() => !document.querySelector('aside.open') && document.activeElement.classList.contains('burger')));
    await m.page.click('button[aria-label="Menu lainnya"]');
    const isi = await m.page.textContent('#user-menu');
    cek(`${w}px: menu ⋯ berisi bahasa, tema, muat ulang, menu user`, ['English', 'Tema terang', 'Muat ulang', 'Ganti sandi', 'Keluar'].every((k) => isi.includes(k)));
    await m.page.screenshot({ path: `${OUT}/07-menu-${w}.png` });
    await m.ctx.close();
  }
  // ------------------------------------------------------------------ 8. keluar
  await u.page.click('button[aria-haspopup=menu] >> visible=true');
  await u.page.click('#user-menu >> text=Keluar');
  await u.page.waitForSelector('#u');
  cek('keluar → layar Masuk', true);
  await u.ctx.close();
    await browser.close();
  const gagal = hasil.filter((h) => !h.ok).length;
  console.log(`\n${hasil.length - gagal} lulus, ${gagal} gagal`);
  process.exit(gagal ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
