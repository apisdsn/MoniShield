// Stage 18 verification (admin pages: Manage users, Ingest & import, audit log) in Chromium, two windows (admin + user).
//   node tools/uji_tahap18.cjs http://127.0.0.1:8000 <admin-password>      (admin has already changed the initial password; user 'rina' does not exist yet)
// Scenario = Stage 18 plan verification table: add user -> forced password change -> dashboard without admin menu; role
// promotion/demotion applies on the next request; password reset / deactivate ends the session; last admin protected; regular user
// on an admin page -> "tidak punya akses" + 403; "Ingest sekarang" while the dashboard stays open; audit without passwords/tokens.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const path = require('path');
const fs = require('fs');
const [, , BASE = 'http://127.0.0.1:8000', PW] = process.argv;
const OUT = process.env.SHOTS_DIR || path.join(require('os').tmpdir(), 's4-shots');
fs.mkdirSync(OUT, { recursive: true });
const hasil = [];
const cek = (n, ok, info = '') => { hasil.push(!!ok); console.log(`${ok ? 'PASS' : 'FAIL'}  ${n}${info ? '  — ' + info : ''}`); };
const U = 'rina', PW_U0 = 'sandi-awal-rina-2026', PW_U1 = 'sandi-rina-baru-2026', PW_U3 = 'sandi-rina-ketiga-2026';

(async () => {
  const browser = await chromium.launch(process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {});
  const errs = [];
  const buka = async () => {
    const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
    const p = await ctx.newPage();
    p.on('pageerror', (e) => errs.push(e.message));
    p.on('console', (m) => m.type() === 'error' && !/status of 40[139]/.test(m.text()) && errs.push(m.text()));
    return p;
  };
  const masuk = async (p, user, pw) => { await p.waitForSelector('#u'); await p.fill('#u', user); await p.fill('#p', pw); await p.click('button[type=submit]'); };
  const teks = (p) => p.textContent('body');
  const toast = (p, re) => p.waitForFunction((s) => [...document.querySelectorAll('.toasts .t')].some((x) => new RegExp(s).test(x.textContent)), re.source, { timeout: 15000 }).then(() => true, () => false);
  const menuAdmin = async (p) => { await p.click('button.who'); const a = await p.$$eval('#user-menu [role=menuitem]', (e) => e.map((x) => x.textContent.trim())); await p.keyboard.press('Escape'); return a.includes('Kelola user'); };
  const baris = (p, user) => p.$$eval('main section.card tbody tr', (rows, u) => { const r = rows.find((x) => x.cells[0]?.textContent.trim().startsWith(u + ' ') || x.cells[0]?.textContent.trim() === u);
    return r ? [...r.cells].map((c) => c.innerText.trim()) : null; }, user);
  const aksi = async (p, user, butir) => {
    await p.click(`button[aria-label="Aksi untuk ${user}"]`);
    const it = p.locator('[role=menu] [role=menuitem]', { hasText: butir }).first();
    const dis = await it.getAttribute('aria-disabled');
    if (dis === 'true') { const t = await it.textContent(); await p.keyboard.press('Escape'); return t; }
    await it.click(); return null;
  };
  const dialog = (p) => p.locator('dialog[open]');
  const pindah = async (p, nama) => { await p.click(`aside nav a:has-text("${nama}")`); await p.waitForLoadState('networkidle'); await p.waitForTimeout(400); };

  // ------------------------------------------------------------------ admin
  const pa = await buka();
  await pa.goto(BASE + '/#/admin/user');
  await masuk(pa, 'admin', PW);
  await pa.waitForSelector('main tbody tr');
  const id0 = await pa.evaluate(() => fetch('/api/me').then((r) => r.json()));
  // add user: rules shown before typing, per-field errors, then success
  await pa.click('button:has-text("Tambah user")');
  await pa.waitForSelector('dialog[open] #u-name');
  const fokus = await pa.evaluate(() => document.activeElement.id);
  await pa.fill('#u-name', 'Ri'); await pa.fill('#u-pw', 'pendek'); await dialog(pa).locator('button[type=submit]').click();
  const g1 = await pa.evaluate(() => [document.querySelector('#u-name-e')?.textContent, document.querySelector('#u-pw-e')?.textContent, document.querySelector('#u-name').getAttribute('aria-describedby')]);
  cek('add user: dialog opens with focus on the first field; per-field errors (aria-describedby) before submit', fokus === 'u-name' && /3–32/.test(g1[0] || '') && /12/.test(g1[1] || '') && /u-name-e/.test(g1[2] || ''), JSON.stringify(g1));
  await pa.fill('#u-name', U); await pa.fill('#u-disp', 'Rina'); await pa.fill('#u-pw', PW_U0);
  await dialog(pa).locator('button[type=submit]').click();
  const okTambah = await toast(pa, /User rina ditambahkan/);
  await pa.waitForFunction(() => !document.querySelector('dialog[open]'));
  const r1 = await baris(pa, U);
  cek('add user "rina" (user role): notification, new row "User · Aktif · Wajib ganti sandi"', okTambah && r1 && r1[2] === 'User' && /Aktif/i.test(r1[3]) && /Wajib ganti sandi/.test(r1[3]), JSON.stringify(r1));
  // Esc closes the dialog, focus back on the trigger
  await pa.click('button:has-text("Tambah user")'); await pa.waitForSelector('dialog[open]'); await pa.keyboard.press('Escape');
  await pa.waitForFunction(() => !document.querySelector('dialog[open]'));
  cek('Esc closes the dialog; focus back on "+ Tambah user"', /Tambah user/.test(await pa.evaluate(() => document.activeElement.textContent)));

  // ------------------------------------------------------------------ user: forced password change, then dashboard without admin menu
  const pr = await buka();
  await pr.goto(BASE + '/#/overview');
  await masuk(pr, U, PW_U0);
  await pr.waitForSelector('#pw-old');
  const wajib = /Anda harus mengganti sandi/.test(await teks(pr)) && !(await pr.$('aside nav'));
  await pr.fill('#pw-old', PW_U0); await pr.fill('#pw-new', PW_U1); await pr.fill('#pw-again', PW_U1); await pr.click('button[type=submit]');
  await pr.waitForSelector('main .kpi'); await pr.waitForLoadState('networkidle');
  cek('new user signs in: forced password change (no sidebar), then sees the dashboard', wajib && (await pr.$$('main .kpi')).length >= 6);
  cek('regular user: user menu without "Kelola user" / "Ingest & impor"', !(await menuAdmin(pr)));

  // ------------------------------------------------------------------ role promotion/demotion: applies on the next request
  const ubahPeran = async (role) => {
    await aksi(pa, U, 'Ubah'); await pa.waitForSelector('dialog[open] input[value=user]');
    await pa.check(`dialog[open] input[value=${role}]`); await dialog(pa).locator('button[type=submit]').click();
    await toast(pa, /User rina disimpan/); await pa.waitForFunction(() => !document.querySelector('dialog[open]'));
  };
  await ubahPeran('admin');
  await pindah(pr, 'Tren');
  const naik = await menuAdmin(pr);
  await ubahPeran('user');
  await pindah(pr, 'Overview');
  const turun = await menuAdmin(pr);
  cek('admin promotes rina -> admin menu appears; demotes -> gone (on the next tab change)', naik && !turun, `promoted ${naik}, demoted ${turun}`);
  await pr.goto(BASE + '/#/admin/user'); await pr.waitForSelector('main'); await pr.waitForTimeout(600);
  const s403 = await pr.evaluate(() => fetch('/api/admin/users').then((r) => r.status));
  cek('regular user opens an admin page address: "Tidak punya akses"; GET /api/admin/users -> 403', /Tidak punya akses/.test(await pr.textContent('main')) && s403 === 403, `status ${s403}`);
  await pr.goto(BASE + '/#/overview'); await pr.waitForSelector('main .kpi');

  // ------------------------------------------------------------------ last admin protected
  const sebabNon = await aksi(pa, 'admin', 'Nonaktifkan'), sebabHapus = await aksi(pa, 'admin', 'Hapus');
  await aksi(pa, 'admin', 'Ubah'); await pa.waitForSelector('dialog[open] fieldset');
  const kunci = await pa.evaluate(() => [document.querySelector('dialog[open] fieldset').disabled, document.querySelector('dialog[open]').textContent]);
  await pa.keyboard.press('Escape'); await pa.waitForFunction(() => !document.querySelector('dialog[open]'));
  const api409 = await pa.evaluate((id) => fetch(`/api/admin/users/${id}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'uji' }, body: JSON.stringify({ role: 'user' }) })
    .then(async (r) => [r.status, (await r.json()).error?.message]), (await pa.evaluate(() => fetch('/api/admin/users').then((r) => r.json()))).users.find((u) => u.username === 'admin').user_id);
  cek('only admin: Deactivate/Delete not offered (with reason), role locked; API PATCH -> 409 with message',
    /akun sendiri/.test(sebabNon || '') && /akun sendiri/.test(sebabHapus || '') && kunci[0] && /Admin aktif terakhir/.test(kunci[1]) && api409[0] === 409 && /last admin/.test(api409[1] || ''),
    `${sebabNon} | ${sebabHapus} | ${JSON.stringify(api409)}`);
  // stale on-screen list (2 admins), then the other admin is demoted elsewhere: save rejected by the server with a message in the dialog
  await ubahPeran('admin');
  const rid = (await pa.evaluate(() => fetch('/api/admin/users').then((r) => r.json()))).users.find((u) => u.username === U).user_id;
  await aksi(pa, 'admin', 'Ubah'); await pa.waitForSelector('dialog[open] input[value=user]:not([disabled])');
  await pa.evaluate((id) => fetch(`/api/admin/users/${id}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'uji' }, body: JSON.stringify({ role: 'user' }) }), rid);
  await pa.check('dialog[open] input[value=user]'); await dialog(pa).locator('button[type=submit]').click();
  await pa.waitForSelector('dialog[open] [role=alert]');
  const tolak = await pa.textContent('dialog[open] [role=alert]');
  await pa.keyboard.press('Escape'); await pa.waitForFunction(() => !document.querySelector('dialog[open]'));
  const me1 = await pa.evaluate(() => fetch('/api/me').then((r) => r.json()));
  cek('demoting the last admin (stale list): rejected with a message in the dialog; stays admin', /Admin aktif terakhir tidak bisa/.test(tolak) && me1.role === 'admin', tolak);

  // ------------------------------------------------------------------ password reset: user session ends at once; temporary password shown once
  await aksi(pa, U, 'Reset sandi'); await pa.waitForSelector('dialog[open]');
  const konf = await pa.textContent('dialog[open]');
  await dialog(pa).locator('button.primary', { hasText: 'Reset sandi' }).click();
  await pa.waitForSelector('dialog[open] code.pw');
  const temp = (await pa.textContent('dialog[open] code.pw')).trim();
  const sekali = /tidak akan ditampilkan lagi/.test(await pa.textContent('dialog[open]')) && !!(await pa.$('dialog[open] button:has-text("Salin")'));
  await pa.screenshot({ path: `${OUT}/t18-reset.png` });
  await dialog(pa).locator('button', { hasText: 'Selesai' }).click(); await pa.waitForFunction(() => !document.querySelector('dialog[open]'));
  const hilang = !(await teks(pa)).includes(temp);
  await pindah(pr, 'Tren');
  await pr.waitForSelector('#u', { timeout: 10000 }).catch(() => {});
  const habis = /Sesi Anda berakhir/.test(await teks(pr));
  await masuk(pr, U, temp); await pr.waitForSelector('#pw-old');
  await pr.fill('#pw-old', temp); await pr.fill('#pw-new', PW_U3); await pr.fill('#pw-again', PW_U3); await pr.click('button[type=submit]');
  await pr.waitForSelector('main section.card');
  const kembali = /#\/tren/.test(pr.url());                     // back to the address from before the session ended
  cek('password reset: confirmation names rina; temporary password shown once (+ Copy), gone after closing; rina session ends at once; sign-in with temporary password -> forced change -> original address',
    /rina/.test(konf) && temp.length >= 12 && sekali && hilang && habis && kembali, pr.url());

  // ------------------------------------------------------------------ deactivate: session ends, cannot sign in; reactivate
  await aksi(pa, U, 'Nonaktifkan'); await pa.waitForSelector('dialog[open]');
  const konfN = await pa.textContent('dialog[open]');
  await dialog(pa).locator('button.danger').click(); await toast(pa, /rina dinonaktifkan/);
  const r2 = await baris(pa, U);
  await pindah(pr, 'Keamanan');
  await pr.waitForSelector('#u', { timeout: 10000 }).catch(() => {});
  const habis2 = /Sesi Anda berakhir/.test(await teks(pr));
  await masuk(pr, U, PW_U3); await pr.waitForSelector('.err, [role=alert]');
  const ditolak = /Nama user atau sandi salah/.test(await teks(pr));
  cek('deactivate rina (confirmation names her): status "Nonaktif"; her session ends at once; sign-in rejected with a generic message',
    /rina/.test(konfN) && /Nonaktif/.test(r2?.[3] || '') && habis2 && ditolak, JSON.stringify(r2));
  await aksi(pa, U, 'Aktifkan'); await toast(pa, /rina diaktifkan/);
  cek('reactivate -> "Aktif"', /^Aktif/.test((await baris(pa, U))?.[3] || ''));
  await pa.screenshot({ path: `${OUT}/t18-users-1440.png`, fullPage: true });

  // ------------------------------------------------------------------ Ingest sekarang
  await pa.goto(BASE + '/#/admin/ingest'); await pa.waitForSelector('main .ing'); await pa.waitForLoadState('networkidle');
  const sebelum = await pa.textContent('main .lastline');
  // an ingest without changes can finish in < 0.5 s, between two status reads: proof of completion = new run_id in the status
  const runAwal = await pa.evaluate(() => fetch('/api/admin/ingest/status').then((r) => r.json()).then((s) => s.last?.run_id ?? null));
  const pantau = pa.evaluate(async (awal) => {
    const seen = [], data = [];
    for (let i = 0; i < 600; i++) {
      const s = await fetch('/api/admin/ingest/status').then((r) => r.json());
      seen.push(s.running);
      data.push((await fetch('/api/folders/2026-10-06/overview')).status);
      if (!s.running && s.last && s.last.run_id !== awal) return { seen, data, s };
      await new Promise((r) => setTimeout(r, 25));
    }
    return { seen, data, s: null };
  }, runAwal);
  await pa.click('button:has-text("Ingest sekarang")');
  const tombolNon = await pa.evaluate(() => [...document.querySelectorAll('main .ing button')].some((b) => b.disabled));
  const m = await pantau;
  const selesai = await toast(pa, /Ingest selesai: 0 file berubah/);
  await pa.waitForTimeout(500);
  const sesudah = await pa.textContent('main .lastline');
  cek('"Ingest sekarang": status running -> done, "0 file berubah"; dashboard stays open while running (all 200)',
    (m.seen.includes(true) || tombolNon) && m.s && !m.s.running && m.s.last_run.files_changed === 0 && selesai && /0 file berubah/.test(sesudah) && m.data.every((x) => x === 200),
    `run ${runAwal ?? '–'} -> ${m.s?.last?.run_id}, running seen ${m.seen.filter(Boolean).length}×, data ${[...new Set(m.data)]}, button disabled ${tombolNon}; "${sesudah.replace(/\s+/g, ' ').trim()}"`);

  // ------------------------------------------------------------------ delete rina, then the audit log
  await pa.goto(BASE + '/#/admin/user'); await pa.waitForSelector('main tbody tr');
  await aksi(pa, U, 'Hapus'); await pa.waitForSelector('dialog[open]');
  const konfH = await pa.textContent('dialog[open]');
  await dialog(pa).locator('button.danger').click(); await toast(pa, /rina dihapus/);
  cek('delete rina: confirmation names her; row gone', /rina/.test(konfH) && !(await baris(pa, U)));
  await pa.goto(BASE + '/#/admin/ingest'); await pa.waitForSelector('main tbody tr'); await pa.waitForLoadState('networkidle');
  // the audit table specifically (the page also has the folder-management table)
  const audit = await pa.$$eval('main section.card', (cards) => {
    const c = cards.find((x) => /Catatan audit|Audit log/.test(x.querySelector('h2,h3')?.textContent || ''));
    return c ? [...c.querySelectorAll('tbody tr')].map((r) => [...r.cells].map((x) => x.innerText.trim())) : [];
  });
  const semua = (await pa.evaluate(() => fetch('/api/admin/audit?limit=500').then((r) => r.json()))).rows;   // page: first 50 + more
  const ada = (act, re = null) => semua.some((r) => r.action === act && (!re || re.test(r.detail || '')) && r.at && r.username && r.ip);
  const perlu = [['user.create', /rina \(user\)/], ['user.update', /role user -> admin/], ['user.update', /role admin -> user/], ['user.reset_password', /rina/],
    ['user.update', /rina: deactivated/], ['user.update', /rina: activated/], ['user.delete', /rina/], ['ingest.start', /folder=all/], ['login.ok'], ['login.fail'], ['user.change_password']];
  const kurang = perlu.filter(([a, re]) => !ada(a, re)).map(([a, re]) => `${a} ${re || ''}`);
  const lengkap = audit.slice(0, 12).every((r) => /\d{4} \d\d\.\d\d WIB/.test(r[0]) && r[4] !== '');
  const json = JSON.stringify(await pa.evaluate(() => fetch('/api/admin/audit?limit=500').then((r) => r.json())));
  const bocor = [PW, PW_U0, PW_U1, PW_U3, temp].filter((s) => json.includes(s) || audit.some((r) => r.join(' ').includes(s)));
  cek(`audit log: ${perlu.length} actions recorded with time (WIB), actor, IP; no passwords or tokens`,
    !kurang.length && lengkap && !bocor.length && !/eyJ[A-Za-z0-9_-]{10,}/.test(json), (kurang.length ? 'missing: ' + kurang.join(', ') : `${audit.length} rows`) + (bocor.length ? ' | LEAKED' : ''));
  await pa.screenshot({ path: `${OUT}/t18-ingest-1440.png`, fullPage: true });

  // ------------------------------------------------------------------ 2 languages × 2 themes × 2 widths
  for (const lang of ['id', 'en']) for (const theme of ['dark', 'light']) for (const w of [1440, 390]) {
    await pa.setViewportSize({ width: w, height: 860 });
    await pa.evaluate(([l, th]) => { localStorage.setItem('lang', l); localStorage.setItem('theme', th); }, [lang, theme]);
    for (const [u, nama] of [['/#/admin/user', 'user'], ['/#/admin/ingest', 'ingest']]) {
      await pa.goto(BASE + u); await pa.reload(); await pa.waitForSelector('main section.card'); await pa.waitForLoadState('networkidle'); await pa.waitForTimeout(300);
      const st = await pa.evaluate(() => [document.documentElement.scrollWidth, innerWidth, document.documentElement.lang, document.documentElement.dataset.theme,
        [...document.querySelectorAll('main h2, main th, main button, main .note, main .lastline, main .bar')].map((h) => h.textContent.trim()).join(' | '),
        (() => { const b = document.querySelector('main .add'); return b ? getComputedStyle(b).position : null; })()]);
      const sisa = lang === 'en' ? (st[4].match(/\b(Tambah|Nama|Peran|Aktif|Terakhir|Sekarang|berhasil|berubah|Catatan|Tindakan|Rincian|Impor dari|dibangun)\b/g) || []) : [];
      cek(`admin/${nama} ${lang}/${theme}/${w}px: no horizontal scroll, text in the right language${nama === 'user' && w === 390 ? ', "+ Tambah user" pinned at the bottom' : ''}`,
        st[0] <= st[1] && st[2] === lang && st[3] === theme && !sisa.length && (nama !== 'user' || w !== 390 || st[5] === 'fixed'),
        `width ${st[0]}/${st[1]}${sisa.length ? ', still ID: ' + sisa.slice(0, 4).join(', ') : ''}`);
      await pa.screenshot({ path: `${OUT}/t18-${nama}-${lang}-${theme}-${w}.png`, fullPage: w === 1440 });
    }
  }
  // dialog on phones: full screen
  await pa.goto(BASE + '/#/admin/user'); await pa.waitForSelector('main tbody tr');
  await pa.click('main .add'); await pa.waitForSelector('dialog[open]');
  const dl = await pa.evaluate(() => { const r = document.querySelector('dialog[open]').getBoundingClientRect(); return [Math.round(r.width), Math.round(r.height), innerWidth, innerHeight]; });
  await pa.screenshot({ path: `${OUT}/t18-dialog-390.png` });
  cek('dialog at 390 px: full screen', dl[0] === dl[2] && dl[1] === dl[3], dl.join('×'));
  await pa.keyboard.press('Escape');
  await pa.evaluate(() => { localStorage.setItem('lang', 'id'); localStorage.setItem('theme', 'dark'); });
  cek('no page/console errors', errs.length === 0, errs.slice(0, 3).join(' | '));
  await browser.close();
  const gagal = hasil.filter((x) => !x).length;
  console.log(`\n${hasil.length - gagal} passed, ${gagal} failed`);
  process.exit(gagal ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
