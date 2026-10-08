// Stage 19 verification ("Impor dari S3" card on the Ingest & import page) in Chromium, against the test server + FAKE S3:
//   .venv/bin/python tools/server_uji_impor.py 8019 <empty-work-dir>   (then)   node tools/uji_tahap19.cjs http://127.0.0.1:8019
// Checked: credential status without values; links rejected with a reason; "Coba dulu" (0 bytes downloaded); "Impor" + confirmation +
// progress -> folder appears; re-import 0 objects; paste/clear temporary credentials; EN errors; audit without secrets; 8 combinations.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const path = require('path');
const fs = require('fs');
const [, , BASE = 'http://127.0.0.1:8019'] = process.argv;
const OUT = process.env.SHOTS_DIR || path.join(require('os').tmpdir(), 's4-shots');
fs.mkdirSync(OUT, { recursive: true });
const hasil = [];
const cek = (n, ok, info = '') => { hasil.push(!!ok); console.log(`${ok ? 'PASS' : 'FAIL'}  ${n}${info ? '  — ' + info : ''}`); };
const PW0 = 'sandi-awal-admin-uji-19', PW1 = 'sandi-baru-admin-uji-19', SECRET = 'rahasiaTiruanUjiYangTidakBolehBocor0001';
const URL = 's3://simpel4-backup/k8s-logs/2026-01-05/', TEMPEL_AK = 'AKIATEMPELBROWSER001', TEMPEL_SK = 'rahasiaTempelBrowserJanganBocor0002';

(async () => {
  const browser = await chromium.launch(process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {});
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const p = await ctx.newPage();
  const errs = [];
  p.on('pageerror', (e) => errs.push(e.message));
  p.on('console', (m) => m.type() === 'error' && !/status of 40[01]/.test(m.text()) && errs.push(m.text()));   // 400 = the rejections under test
  await p.goto(BASE + '/#/admin/ingest');
  await p.fill('#u', 'admin'); await p.fill('#p', PW0); await p.click('button[type=submit]');
  await p.waitForSelector('#pw-old');
  await p.fill('#pw-old', PW0); await p.fill('#pw-new', PW1); await p.fill('#pw-again', PW1); await p.click('button[type=submit]');
  await p.waitForSelector('main .imp #imp-url'); await p.waitForLoadState('networkidle');
  const kartu = () => p.textContent('main .imp');
  const tungguSelesai = () => p.waitForFunction(() => !document.querySelector('main .imp [role=progressbar]') && ![...document.querySelectorAll('main .imp .acts .btn')].every((b) => b.disabled), null, { timeout: 20000 });
  const toast = (re) => p.waitForFunction((s) => [...document.querySelectorAll('.toasts .t')].some((x) => new RegExp(s).test(x.textContent)), re.source, { timeout: 15000 }).then(() => true, () => false);

  let t = await kartu();
  cek('credentials: "tersedia (konfigurasi server)", no values; accepted link format stated', /tersedia/.test(t) && /konfigurasi server/.test(t)
    && /Hanya s3:\/\/simpel4-backup\/k8s-logs\/<YYYY-MM-DD>\//.test(t) && !t.includes(SECRET) && !t.includes('AKIATIRUAN'));

  // links rejected with a reason (before contacting S3)
  for (const [u, re] of [['s3://bucket-lain/k8s-logs/2026-01-05/', /Bucket ini tidak diizinkan/], ['s3://simpel4-backup/k8s-logs/bukan-tanggal/', /harus tanggal/],
                         ['s3://simpel4-backup/lain/2026-01-05/', /Awalan ini tidak diizinkan/]]) {
    await p.fill('#imp-url', u); await p.click('main .imp button:has-text("Coba dulu")');
    await p.waitForSelector('main .imp [role=alert]');
    const a = await p.textContent('main .imp [role=alert]');
    cek(`link "${u}" rejected with a reason`, re.test(a), a);
  }
  // Dry run
  await p.fill('#imp-url', URL); await p.click('main .imp button:has-text("Coba dulu")');
  await p.waitForSelector('main .imp .sum'); await tungguSelesai();
  t = await kartu();
  await p.click('main .imp details.objs summary');
  const rincian = await p.textContent('main .imp details.objs');
  cek('"Coba dulu": 2 objects to fetch · 2 skipped · 0 bytes downloaded; fetch/skip details with reasons',
    /Hasil coba: 2 objek akan diambil .* 2 dilewati · 0 byte diunduh/.test(t) && /\.gz berpasangan dengan \.log/.test(rincian) && /bukan file log/.test(rincian), t.replace(/\s+/g, ' ').slice(0, 200));
  const folder0 = await p.evaluate(() => fetch('/api/meta').then((r) => r.json()).then((m) => m.folders.map((f) => f.folder)));
  // Import: confirmation -> progress -> done
  await p.click('main .imp button.primary:has-text("Impor")');
  await p.waitForSelector('dialog[open]');
  const konf = await p.textContent('dialog[open]');
  await p.click('dialog[open] button.primary');
  const ok = await toast(/Impor selesai: 2 objek diunduh ke folder 2026-01-05/);
  await tungguSelesai(); await p.waitForTimeout(600);
  t = await kartu();
  const folder1 = await p.evaluate(() => fetch('/api/meta').then((r) => r.json()).then((m) => m.folders.map((f) => f.folder)));
  const opsi = await p.$$eval('select option', (o) => o.map((x) => x.value));
  cek('"Impor": confirmation names the link; done, 2 objects downloaded + ingest; folder 2026-01-05 appears in the folder picker',
    konf.includes(URL) && ok && /Selesai: 2 objek diunduh/.test(t) && /Ingest: 2 file berubah/.test(t) && !folder0.includes('2026-01-05') && folder1.includes('2026-01-05') && opsi.includes('2026-01-05'),
    t.replace(/\s+/g, ' ').match(/Selesai[^.]*\.[^.]*\./)?.[0]);
  await p.screenshot({ path: `${OUT}/t19-impor-1440.png`, fullPage: true });
  // re-import: 0 objects
  await p.click('main .imp button.primary:has-text("Impor")'); await p.click('dialog[open] button.primary');
  await toast(/Impor selesai: 0 objek/); await tungguSelesai(); await p.waitForTimeout(400);
  t = await kartu();
  cek('same link again: 0 objects downloaded (identical to the previous download)', /Selesai: 0 objek diunduh/.test(t));
  const riwayat = await p.$$eval('main section.card', (cs) => { const c = cs.find((x) => /Riwayat impor/i.test(x.querySelector('h2')?.textContent || ''));
    return c ? [...c.querySelectorAll('tbody tr')].map((r) => r.innerText.replace(/\s+/g, ' ')) : []; });
  cek('import history: 3 newest rows (done, done, dry run) with link, folder, by admin', riwayat.length >= 3 && /selesai/i.test(riwayat[0]) && /coba/i.test(riwayat[2])
    && riwayat.every((r) => r.includes('s3://simpel4-backup/k8s-logs/2026-01-05/') && /admin/.test(r)), riwayat.slice(0, 3).join(' || ').slice(0, 300));

  // temporary credentials: wrong format rejected, then saved; key unknown to S3 -> clear error; cleared -> back to server config
  await p.click('main .imp button:has-text("Tempel kredensial lain")');
  const tipe = await p.$$eval('main .imp .credf input', (i) => i.map((x) => [x.type, x.getAttribute('autocomplete')]));
  await p.fill('#c-ak', 'bukan kunci'); await p.fill('#c-sk', 'pendek'); await p.click('main .imp .credf button[type=submit]');
  await p.waitForSelector('main .imp .credf [role=alert]');
  const salah = await p.textContent('main .imp .credf [role=alert]');
  await p.fill('#c-ak', TEMPEL_AK); await p.fill('#c-sk', TEMPEL_SK); await p.click('main .imp .credf button[type=submit]');
  await toast(/Kredensial sementara disimpan/); await p.waitForTimeout(400);
  t = await kartu();
  const nilaiKosong = !(await p.$('#c-ak'));
  cek('paste credentials: password-type fields without autocomplete; wrong format rejected; saved -> "ditempel admin, memori server"; values not shown',
    tipe.length === 3 && tipe.every(([ty, ac]) => ty === 'password' && ac === 'off') && /tidak berbentuk kunci akses AWS/.test(salah) && /ditempel admin/.test(t) && nilaiKosong
    && !t.includes(TEMPEL_SK) && !t.includes(TEMPEL_AK), salah);
  await p.click('main .imp button:has-text("Coba dulu")');
  await p.waitForSelector('main .imp [role=alert]'); await tungguSelesai();
  const tolak = await p.textContent('main .imp [role=alert]');
  cek('pasted key unknown to S3: "S3 menolak akses" (nothing written)', /S3 menolak akses/.test(tolak), tolak);
  await p.click('main .imp button:has-text("Hapus kredensial tempel")'); await toast(/Kredensial tempel dihapus/); await p.waitForTimeout(400);
  cek('clear pasted credentials -> back to "konfigurasi server"', /konfigurasi server/.test(await kartu()));

  // audit and all responses: no secrets
  const semua = await p.evaluate(() => Promise.all(['/api/admin/audit?limit=500', '/api/admin/import', '/api/meta', '/api/admin/import/1'].map((u) => fetch(u).then((r) => r.text()))));
  const aksi = JSON.parse(semua[0]).rows.map((r) => r.action);
  cek('audit: import.start, import.credentials.set/clear; no credential values in audit/history/meta',
    ['import.start', 'import.credentials.set', 'import.credentials.clear'].every((a) => aksi.includes(a)) && !semua.some((s) => [SECRET, TEMPEL_SK, TEMPEL_AK, 'AKIATIRUAN'].some((x) => s.includes(x))));

  // errors in English
  await p.evaluate(() => localStorage.setItem('lang', 'en')); await p.reload(); await p.waitForSelector('main .imp #imp-url');
  await p.fill('#imp-url', 's3://bucket-lain/k8s-logs/2026-01-05/'); await p.click('main .imp button:has-text("Dry run")');
  await p.waitForSelector('main .imp [role=alert]');
  const en = await p.textContent('main .imp [role=alert]');
  cek('EN: rejection in English', /This bucket is not allowed/.test(en), en);

  // 2 languages × 2 themes × 2 widths
  for (const lang of ['id', 'en']) for (const theme of ['dark', 'light']) for (const w of [1440, 390]) {
    await p.setViewportSize({ width: w, height: 860 });
    await p.evaluate(([l, th]) => { localStorage.setItem('lang', l); localStorage.setItem('theme', th); }, [lang, theme]);
    await p.goto(BASE + '/#/admin/ingest'); await p.reload(); await p.waitForSelector('main .imp #imp-url'); await p.waitForLoadState('networkidle'); await p.waitForTimeout(300);
    const st = await p.evaluate(() => [document.documentElement.scrollWidth, innerWidth, document.documentElement.lang, document.documentElement.dataset.theme,
      [...document.querySelectorAll('main .imp, main section.card h2, main th')].map((x) => x.textContent.trim()).join(' | ')]);
    const sisa = lang === 'en' ? (st[4].match(/\b(Impor dari|Tautan|Coba dulu|tersedia|Riwayat|Oleh|selesai|Hanya)\b/g) || []) : [];
    cek(`ingest & import ${lang}/${theme}/${w}px: no horizontal scroll, text in the right language`, st[0] <= st[1] && st[2] === lang && st[3] === theme && !sisa.length,
      `width ${st[0]}/${st[1]}${sisa.length ? ', still ID: ' + sisa.slice(0, 4).join(', ') : ''}`);
    await p.screenshot({ path: `${OUT}/t19-${lang}-${theme}-${w}.png`, fullPage: w === 1440 });
  }
  await p.evaluate(() => { localStorage.setItem('lang', 'id'); localStorage.setItem('theme', 'dark'); });
  cek('no page/console errors', errs.length === 0, errs.slice(0, 3).join(' | '));
  await browser.close();
  const gagal = hasil.filter((x) => !x).length;
  console.log(`\n${hasil.length - gagal} passed, ${gagal} failed`);
  process.exit(gagal ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
