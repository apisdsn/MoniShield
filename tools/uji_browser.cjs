// Stage 12 checks (plan) in Chromium via Playwright: sign-in, forced password change, shell, folder in the address,
// tables, language/theme, keyboard, user vs admin, 390/360 px screens. Needs a running server with a NEW account database
// (admin has not changed the password yet). Playwright is not a project dependency: PLAYWRIGHT_MODULE=/path/to/playwright.
//   node tools/uji_browser.cjs http://127.0.0.1:8000 <admin-initial-password> <admin-new-password>
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const fs = require('fs');
const path = require('path');

const [, , BASE = 'http://127.0.0.1:8000', PW0, PW1] = process.argv;
const OUT = process.env.SHOTS_DIR || path.join(require('os').tmpdir(), 's4-shots');
fs.mkdirSync(OUT, { recursive: true });
const hasil = [];
const cek = (nama, ok, info = '') => { hasil.push({ nama, ok: !!ok, info }); console.log(`${ok ? 'PASS' : 'FAIL'}  ${nama}${info ? '  — ' + info : ''}`); };

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
  // ------------------------------------------------------------------ 1. sign-in screen, no data before sign-in
  const { ctx, page } = await ctxWith(browser);
  await page.goto(BASE + '/#/keamanan');
  await page.waitForSelector('#u');
  cek('sign-in screen shown without sidebar', (await page.locator('aside').count()) === 0);
  const dataReq = page._reqs.filter((u) => /\/api\/(meta|folders|trends)/.test(u));
  cek('no dashboard data loaded before sign-in', dataReq.length === 0, dataReq.join(', '));
  await page.screenshot({ path: `${OUT}/01-masuk-1440.png` });
  await login(page, 'admin', 'salah-sandi-xx');
  await page.waitForSelector('[role=alert]');
  cek('wrong password: one-sentence message + focus back on password', (await page.textContent('[role=alert]')).includes('Nama user atau kata sandi salah') &&
      (await page.evaluate(() => document.activeElement.id)) === 'p');
  // ------------------------------------------------------------------ 2. forced password change
  await login(page, 'admin', PW0);
  await page.waitForSelector('#pw-old');
  cek('forced password change shown on its own', (await page.locator('aside').count()) === 0 && (await page.textContent('body')).includes('harus mengganti kata sandi'));
  await page.fill('#pw-old', PW0); await page.fill('#pw-new', 'pendek'); await page.fill('#pw-again', 'pendek');
  await page.click('button[type=submit]');
  cek('per-field error below the field', await page.locator('#pw-new-e').isVisible());
  await page.fill('#pw-new', PW1); await page.fill('#pw-again', PW1);
  await page.click('button[type=submit]');
  await page.waitForSelector('aside nav');
  // ------------------------------------------------------------------ 3. shell after sign-in
  await page.waitForFunction(() => document.querySelector('aside')?.textContent.includes('om-be-simpel-loop'));
  cek('back to the requested address (#/keamanan)', page.url().includes('#/keamanan'), page.url());
  const grp = await page.$$eval('aside .grp', (e) => e.map((x) => x.textContent.trim()));
  cek('sidebar has two groups', grp.length === 2, grp.join(' | '));
  const badge = await page.textContent('aside a[href*="keamanan"]');
  cek('Security badge "14 IP"', /14 IP/.test(badge), badge.trim());
  const opts = await page.$$eval('#folder-select option', (o) => o.map((x) => x.textContent));
  cek('folder picker has 11 folders', opts.length === 11, opts[0]);
  const sub = await page.textContent('.sub'), st = await page.textContent('header .status');
  cek('subtitle shows the log time range; status line shows the service count', /berisi log .+WIB/.test(sub) && /\d+\s+layanan/.test(st), `${sub} | ${st}`);
  cek('folder is in the address', /folder=2026-10-06/.test(page.url()), page.url());
  // system (service) names shown lowercase, including the service page title (owner decision 2026-10-06)
  const namaLayanan = await page.$$eval('aside a[href*="layanan/"] .lbl', (e) => e.map((x) => x.innerText.trim()));
  await page.click('aside a[href*="layanan/om-be-appsmanager"]');
  await page.waitForFunction(() => location.hash.includes('layanan/om-be-appsmanager'));
  const judulLayanan = await page.$eval('header h1 span', (e) => e.innerText.trim());
  cek('service names lowercase in sidebar and title', namaLayanan.length === 7 && namaLayanan.every((x) => x === x.toLowerCase()) && judulLayanan === 'om-be-appsmanager',
      `${namaLayanan.join(', ')} | title: ${judulLayanan}`);
  await page.click('aside a[href*="#/overview"]');
  await page.waitForSelector('.kpis .kpi');
  await page.waitForSelector('canvas');
  await page.waitForTimeout(600);
  await page.screenshot({ path: `${OUT}/02-overview-gelap-1440.png`, fullPage: true });
  cek('Overview tab in the address', page.url().includes('#/overview?folder='), page.url());
  // change folder via the select and the shortcut
  await page.selectOption('#folder-select', '2026-09-29');
  await page.waitForFunction(() => document.querySelector('.sub')?.textContent.includes('29 Sep'));
  cek('changing folder updates the address', page.url().includes('folder=2026-09-29'), page.url());
  await page.locator('body').press('[');
  await page.waitForFunction(() => location.hash.includes('2026-09-28'));
  cek('shortcut [ = previous folder', page.url().includes('2026-09-28'));
  await page.goBack();
  await page.waitForFunction(() => location.hash.includes('2026-09-29'));
  cek('browser back button restores the folder', page.url().includes('2026-09-29'));
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(300);
  // server-side table: filter, sort, load more
  const pesan = page.locator('section.dt', { hasText: 'Top pesan error' });
  const awal = await pesan.locator('tbody tr').count();
  const status = await pesan.locator('.foot .muted').textContent().catch(() => '');
  cek('messages table: initial count = old limit (25) + "Menampilkan N dari M"', awal === 25 && /Menampilkan 25 dari/.test(status), `${awal} rows; ${status}`);
  await pesan.locator('.foot button').click();
  await page.waitForFunction(() => [...document.querySelectorAll('section.dt')].find((s) => s.textContent.includes('Top pesan error')).querySelectorAll('tbody tr').length > 25);
  cek('"Tampilkan berikutnya" loads more', (await pesan.locator('tbody tr').count()) > 25, String(await pesan.locator('tbody tr').count()));
  await pesan.locator('input[type=search]').fill('timeout');
  await page.waitForTimeout(900);
  const sesudah = await pesan.locator('tbody tr').allTextContents();
  cek('filter searches all data on the server', sesudah.length > 0 && sesudah.every((t) => /timeout|Tidak ada baris/i.test(t)), `${sesudah.length} rows`);
  await pesan.locator('th button').first().click();
  await page.waitForTimeout(600);
  cek('sort header uses aria-sort', (await pesan.locator('th[aria-sort=descending]').count()) === 1);
  // ------------------------------------------------------------------ 4. language, theme, remembered after reload
  await page.click('[role=radio]:has-text("EN")');
  await page.click('[role=radio][aria-label="Light theme"]');
  await page.reload();
  await page.waitForSelector('aside nav');
  await page.waitForSelector('.kpis .kpi');
  const htmlAttr = await page.evaluate(() => [document.documentElement.lang, document.documentElement.dataset.theme]);
  cek('language and theme remembered after reload', htmlAttr[0] === 'en' && htmlAttr[1] === 'light', htmlAttr.join(','));
  cek('interface text in English', (await page.textContent('aside')).includes('Root Causes') && (await page.textContent('.sub')).includes('Log folder'));
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
  cek('Tab: "Lewati ke isi" → navigation → header; focus visible', f1 === 'Lewati ke isi' && f2 === 'nav' && f3 === 'header' && !outline.startsWith('none'), `${f1} → ${f2} → ${f3}; outline ${outline}`);
  // ------------------------------------------------------------------ 6. regular user
  const r = await page.evaluate(async () => {
    const x = await fetch('/api/admin/users', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'uji' },
      body: JSON.stringify({ username: 'uji', display_name: 'Uji', role: 'user', password: 'sandi-awal-uji-123' }) });
    return x.status;
  });
  cek('admin creates user "uji"', r === 201 || r === 409, String(r));
  const u = await ctxWith(browser);
  await u.page.goto(BASE + '/#/overview');
  await u.page.waitForSelector('#u');
  await login(u.page, 'uji', 'sandi-awal-uji-123');
  await u.page.waitForSelector('#pw-old');
  await u.page.fill('#pw-old', 'sandi-awal-uji-123'); await u.page.fill('#pw-new', 'sandi-baru-uji-456'); await u.page.fill('#pw-again', 'sandi-baru-uji-456');
  await u.page.click('button[type=submit]');
  await u.page.waitForSelector('aside nav');
  await u.page.waitForFunction(() => document.querySelector('aside')?.textContent.includes('om-be-simpel-loop'));
  const navUser = await u.page.textContent('aside nav'), navAdmin = await page.textContent('aside nav');
  cek('user sidebar same as admin', navUser === navAdmin);
  await u.page.click('button[aria-haspopup=menu] >> visible=true');
  const menu = await u.page.textContent('#user-menu');
  cek('user menu without "Kelola user" and "Ingest & impor"', !menu.includes('Kelola user') && !menu.includes('Ingest') && menu.includes('Ganti kata sandi') && menu.includes('Keluar'), menu.replace(/\s+/g, ' '));
  await u.page.keyboard.press('Escape');
  await page.click('button[aria-haspopup=menu] >> visible=true');
  const menuA = await page.textContent('#user-menu');
  cek('admin menu has "Kelola user" and "Ingest & impor"', menuA.includes('Kelola user') && menuA.includes('Ingest & impor'));
  await page.keyboard.press('ArrowDown');
  const fokusMenu = await page.evaluate(() => document.activeElement.getAttribute('role'));
  await page.keyboard.press('Escape');
  const balik = await page.evaluate(() => document.activeElement.getAttribute('aria-haspopup'));
  cek('menu: arrows move, Esc closes and restores focus', fokusMenu?.startsWith('menuitem') && balik === 'menu', `${fokusMenu} / ${balik}`);
  await u.page.goto(BASE + '/#/admin/user');
  await u.page.waitForSelector('text=Tidak punya akses');
  cek('admin page address opened by a user → "Tidak punya akses" (sidebar kept)', (await u.page.locator('aside nav').count()) === 1);
  await u.page.screenshot({ path: `${OUT}/04-user-tanpa-akses-1440.png` });
  // 401 /api/me before sign-in, 401 wrong login, 403 before the forced password change = expected responses (logged by the browser as resource errors)
  const diharapkan = (x) => /^401 GET \/api\/me$|^401 POST \/api\/auth\/login$/.test(x);
  const bad = [...page._bad, ...u.page._bad];
  cek('only expected responses ≥ 400', bad.every(diharapkan), [...new Set(bad)].join(' | '));
  const konsol = [...page._errors, ...u.page._errors].filter((x) => !/Failed to load resource: the server responded with a status of 401/.test(x));
  cek('no other console errors (admin, user)', konsol.length === 0, konsol.slice(0, 3).join(' | '));
  const luar = [...page._reqs, ...u.page._reqs].filter((x) => !x.startsWith(BASE) && !x.startsWith('data:') && !x.startsWith('blob:'));
  cek('no requests to other domains', luar.length === 0, luar.slice(0, 3).join(', '));
  // ------------------------------------------------------------------ 7. narrow screens
  for (const w of [390, 360]) {
    const m = await ctxWith(browser, { viewport: { width: w, height: 800 }, isMobile: true, hasTouch: true, deviceScaleFactor: 2,
      storageState: await ctx.storageState() });
    await m.page.goto(BASE + '/#/overview?folder=2026-10-06');
    await m.page.waitForSelector('.kpis .kpi');
    await m.page.waitForTimeout(700);
    const lebar = await m.page.evaluate(() => [document.documentElement.scrollWidth, innerWidth]);
    cek(`${w}px: no horizontal page scroll`, lebar[0] <= lebar[1], `${lebar[0]} ≤ ${lebar[1]}`);
    const kol = await m.page.$eval('.kpis', (e) => getComputedStyle(e).gridTemplateColumns.split(' ').length);
    cek(`${w}px: KPIs in 2 columns`, kol === 2, String(kol));
    cek(`${w}px: sidebar hidden, ☰ button present`, !(await m.page.locator('aside a').first().isVisible()) && (await m.page.locator('button.burger').isVisible()));
    const kartu = await m.page.$eval('section.dt.card .cards td:not(.k)', (e) => getComputedStyle(e).display).catch(() => 'none');
    cek(`${w}px: tables with > 4 columns become row cards`, kartu === 'grid', kartu);
    await m.page.screenshot({ path: `${OUT}/05-overview-${w}.png`, fullPage: true });
    const kecil = await m.page.$$eval('header button, header select, .card button.btn', (els) => els.filter((e) => e.offsetParent).map((e) => {
      const r = e.getBoundingClientRect(); return [e.getAttribute('aria-label') || e.textContent.trim().slice(0, 20), Math.round(r.width), Math.round(r.height)];
    }).filter(([, wd, h]) => wd < 44 || h < 44));
    cek(`${w}px: header touch targets ≥ 44 px`, kecil.filter(([n]) => !/Lihat sebagai/.test(n)).length === 0, JSON.stringify(kecil.slice(0, 4)));
    await m.page.click('button.burger');
    await m.page.waitForTimeout(300);
    const laci = await m.page.evaluate(() => [!!document.querySelector('aside.open'), document.activeElement.closest('aside') !== null, document.querySelector('.wrap').inert]);
    cek(`${w}px: drawer open, focus inside, rest inert`, laci.every(Boolean), laci.join(','));
    await m.page.screenshot({ path: `${OUT}/06-laci-${w}.png` });
    const navT = await m.page.$$eval('aside a', (els) => els.map((e) => Math.round(e.getBoundingClientRect().height)));
    cek(`${w}px: navigation items ≥ 44 px`, Math.min(...navT) >= 44, String(Math.min(...navT)));
    await m.page.keyboard.press('Escape');
    await m.page.waitForTimeout(200);
    cek(`${w}px: Esc closes the drawer, focus back on ☰`, await m.page.evaluate(() => !document.querySelector('aside.open') && document.activeElement.classList.contains('burger')));
    await m.page.click('button[aria-label="Menu lainnya"]');
    const isi = await m.page.textContent('#user-menu');
    cek(`${w}px: ⋯ menu has language, theme, reload, user menu`, ['English', 'Tema terang', 'Muat ulang', 'Ganti kata sandi', 'Keluar'].every((k) => isi.includes(k)));
    await m.page.screenshot({ path: `${OUT}/07-menu-${w}.png` });
    await m.ctx.close();
  }
  // ------------------------------------------------------------------ 8. sign out
  await u.page.click('button[aria-haspopup=menu] >> visible=true');
  await u.page.click('#user-menu >> text=Keluar');
  await u.page.waitForSelector('#u');
  cek('sign out → sign-in screen', true);
  await u.ctx.close();
    await browser.close();
  const gagal = hasil.filter((h) => !h.ok).length;
  console.log(`\n${hasil.length - gagal} passed, ${gagal} failed`);
  process.exit(gagal ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
