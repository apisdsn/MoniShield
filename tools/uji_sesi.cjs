// Pemeriksaan Tahap 12: peringatan sesi, sesi habis di tengah pemakaian, server mati lalu hidup lagi. Mematikan dan
// menyalakan ulang server sendiri (S4_SESSION_IDLE_MINUTES=5). Jalankan setelah tools/uji_browser.cjs.
//   node tools/uji_sesi.cjs http://127.0.0.1:8000 <sandi-admin> <folder-v2>
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const { execSync, spawn } = require('child_process');
const path = require('path');
const [, , BASE, PW, V2] = process.argv;
const hasil = [];
const cek = (n, ok, info = '') => { hasil.push(ok); console.log(`${ok ? 'LULUS' : 'GAGAL'}  ${n}${info ? '  — ' + info : ''}`); };
const tunggu = (ms) => new Promise((r) => setTimeout(r, ms));
const startServer = () => spawn(path.join(V2, '.venv/bin/python'), ['-m', 'simpel4', 'serve'], { cwd: V2, detached: true, stdio: 'ignore',
  env: { ...process.env, S4_SESSION_IDLE_MINUTES: '5', S4_INGEST_ON_START: 'false' } }).unref();
const up = async () => { for (let i = 0; i < 60; i++) { try { if ((await fetch(BASE + '/api/health')).ok) return true; } catch {} await tunggu(500); } return false; };

(async () => {
  const browser = await chromium.launch(process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {});
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 860 } });
  const page = await ctx.newPage();
  await page.goto(BASE + '/#/keamanan?folder=2026-09-29');
  await page.fill('#u', 'admin'); await page.fill('#p', PW); await page.click('button[type=submit]');
  await page.waitForSelector('aside nav');
  // 1. peringatan sesi (batas menganggur 5 menit -> langsung dalam 5 menit terakhir)
  await page.waitForSelector('.band.info', { timeout: 20000 });
  const teks = await page.textContent('.band.info');
  cek('pita "Sesi berakhir dalam N menit" + "Tetap masuk"', /Sesi berakhir dalam \d menit/.test(teks) && teks.includes('Tetap masuk'), teks.trim());
  await page.screenshot({ path: path.join(process.env.SHOTS_DIR || path.join(require('os').tmpdir(), 's4-shots'), '08-peringatan-sesi.png') });
  // 2. sesi habis di tengah pemakaian -> Masuk dengan keterangan, kembali ke alamat yang sama
  await page.evaluate(() => fetch('/api/auth/logout', { method: 'POST', headers: { 'X-Requested-With': 'uji' } }));
  await page.click('button[aria-label="Muat ulang"]');
  await page.waitForSelector('#u');
  cek('sesi habis → layar Masuk "Sesi Anda berakhir"', (await page.textContent('main')).includes('Sesi Anda berakhir'));
  await page.fill('#u', 'admin'); await page.fill('#p', PW); await page.click('button[type=submit]');
  await page.waitForSelector('aside nav');
  cek('setelah masuk lagi: alamat sama (tab + folder)', page.url().endsWith('#/keamanan?folder=2026-09-29'), page.url());
  // 3. server mati -> pita merah; hidup lagi -> pulih sendiri
  execSync(`kill $(pgrep -f "python -m simpel4 serve$")`);
  await tunggu(1500);
  await page.click('button[aria-label="Muat ulang"]');
  await page.waitForSelector('.band.err', { timeout: 10000 });
  cek('server mati → pita "Tidak tersambung" (coba otomatis)', (await page.textContent('.band.err')).includes('Tidak tersambung'), (await page.textContent('.band.err')).trim());
  await page.screenshot({ path: path.join(process.env.SHOTS_DIR || path.join(require('os').tmpdir(), 's4-shots'), '09-tidak-tersambung.png') });
  startServer();
  cek('server hidup lagi', await up());
  const t0 = Date.now();
  await page.waitForSelector('.band.err', { state: 'detached', timeout: 20000 });
  cek('pita hilang sendiri setelah server hidup', true, `${Math.round((Date.now() - t0) / 1000)} dtk`);
  await page.waitForSelector('.kpis .kpi', { timeout: 10000 });
  cek('halaman dimuat ulang otomatis setelah pulih', true);
  await browser.close();
  console.log(`\n${hasil.filter(Boolean).length} lulus, ${hasil.filter((x) => !x).length} gagal`);
  process.exit(hasil.every(Boolean) ? 0 : 1);
})().catch((e) => { console.error(e); process.exit(2); });
