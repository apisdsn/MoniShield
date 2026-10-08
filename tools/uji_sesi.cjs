// Stage 12 checks: session warning, session expiring mid-use, server down then back up. Stops and restarts
// the server itself (S4_SESSION_IDLE_MINUTES=5). Run after tools/uji_browser.cjs.
//   node tools/uji_sesi.cjs http://127.0.0.1:8000 <admin-password> <v2-folder>
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const { execSync, spawn } = require('child_process');
const path = require('path');
const [, , BASE, PW, V2] = process.argv;
const hasil = [];
const cek = (n, ok, info = '') => { hasil.push(ok); console.log(`${ok ? 'PASS' : 'FAIL'}  ${n}${info ? '  — ' + info : ''}`); };
const tunggu = (ms) => new Promise((r) => setTimeout(r, ms));
const startServer = () => spawn(path.join(V2, '.venv/bin/python'), ['-m', 'monishield', 'serve'], { cwd: V2, detached: true, stdio: 'ignore',
  env: { ...process.env, S4_SESSION_IDLE_MINUTES: '5', S4_INGEST_ON_START: 'false' } }).unref();
const up = async () => { for (let i = 0; i < 60; i++) { try { if ((await fetch(BASE + '/api/health')).ok) return true; } catch {} await tunggu(500); } return false; };

(async () => {
  const browser = await chromium.launch(process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {});
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 860 } });
  const page = await ctx.newPage();
  await page.goto(BASE + '/#/keamanan?folder=2026-09-29');
  await page.fill('#u', 'admin'); await page.fill('#p', PW); await page.click('button[type=submit]');
  await page.waitForSelector('aside nav');
  // 1. session warning (5-minute idle limit -> immediately within the last 5 minutes)
  await page.waitForSelector('.band.info', { timeout: 20000 });
  const teks = await page.textContent('.band.info');
  cek('band "Sesi berakhir dalam N menit" + "Tetap masuk"', /Sesi berakhir dalam \d menit/.test(teks) && teks.includes('Tetap masuk'), teks.trim());
  await page.screenshot({ path: path.join(process.env.SHOTS_DIR || path.join(require('os').tmpdir(), 's4-shots'), '08-peringatan-sesi.png') });
  // 2. session expires mid-use -> sign-in with an explanation, back to the same address
  await page.evaluate(() => fetch('/api/auth/logout', { method: 'POST', headers: { 'X-Requested-With': 'uji' } }));
  await page.click('button[aria-label="Muat ulang"]');
  await page.waitForSelector('#u');
  cek('session expired → sign-in screen "Sesi Anda berakhir"', (await page.textContent('main')).includes('Sesi Anda berakhir'));
  await page.fill('#u', 'admin'); await page.fill('#p', PW); await page.click('button[type=submit]');
  await page.waitForSelector('aside nav');
  cek('after signing in again: same address (tab + folder)', page.url().endsWith('#/keamanan?folder=2026-09-29'), page.url());
  // 3. server down -> red band; back up -> recovers by itself
  execSync(`kill $(pgrep -f "python -m monishield serve$")`);
  await tunggu(1500);
  await page.click('button[aria-label="Muat ulang"]');
  await page.waitForSelector('.band.err', { timeout: 10000 });
  cek('server down → band "Tidak tersambung" (automatic retry)', (await page.textContent('.band.err')).includes('Tidak tersambung'), (await page.textContent('.band.err')).trim());
  await page.screenshot({ path: path.join(process.env.SHOTS_DIR || path.join(require('os').tmpdir(), 's4-shots'), '09-tidak-tersambung.png') });
  startServer();
  cek('server back up', await up());
  const t0 = Date.now();
  await page.waitForSelector('.band.err', { state: 'detached', timeout: 20000 });
  cek('band disappears by itself after the server is up', true, `${Math.round((Date.now() - t0) / 1000)} s`);
  await page.waitForSelector('.kpis .kpi', { timeout: 10000 });
  cek('page reloads automatically after recovery', true);
  await browser.close();
  console.log(`\n${hasil.filter(Boolean).length} passed, ${hasil.filter((x) => !x).length} failed`);
  process.exit(hasil.every(Boolean) ? 0 : 1);
})().catch((e) => { console.error(e); process.exit(2); });
