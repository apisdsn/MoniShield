// Verifikasi Langkah 7 (docker compose) di Chromium: dashboard di container + pgAdmin + DbGate.
//   ADMIN_PW=… [PGADMIN_EMAIL=… PGADMIN_PW=…] [DBGATE_LOGIN=… DBGATE_PW=…] node tools/uji_docker.cjs [http://127.0.0.1:8000]
// Admin baru (PostgreSQL kosong) masuk dengan S4_ADMIN_PASSWORD lalu wajib ganti sandi; sandi baru dicetak TIDAK pernah.
// Sandi dari variabel lingkungan, bukan argumen, agar tidak tampil di daftar proses. Tangkapan layar ke SHOTS_DIR.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const path = require('path');
const fs = require('fs');
const [, , BASE = 'http://127.0.0.1:8000'] = process.argv;
const E = process.env;
const OUT = E.SHOTS_DIR || path.join(require('os').tmpdir(), 's4-shots');
fs.mkdirSync(OUT, { recursive: true });
const hasil = [];
const cek = (n, ok, info = '') => { hasil.push(!!ok); console.log(`${ok ? 'LULUS' : 'GAGAL'}  ${n}${info ? '  — ' + info : ''}`); };

(async () => {
  const browser = await chromium.launch(E.CHROMIUM_PATH ? { executablePath: E.CHROMIUM_PATH } : {});
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const p = await ctx.newPage();
  const errs = [];
  p.on('pageerror', (e) => errs.push(e.message));
  p.on('console', (m) => m.type() === 'error' && !/status of 40[139]/.test(m.text()) && errs.push(m.text()));

  // ------------------------------------------------------------------ dashboard (ONLY_TOOLS=1: lewati, hanya pgAdmin/DbGate)
  if (!E.ONLY_TOOLS) {
  await p.goto(BASE + '/');
  await p.waitForSelector('#u');
  await p.fill('#u', E.ADMIN_USER || 'admin'); await p.fill('#p', E.ADMIN_PW); await p.click('button[type=submit]');
  const sandi = E.ADMIN_PW2 || E.ADMIN_PW + '-baru';
  const wajib = await p.waitForSelector('#pw-old', { timeout: 8000 }).then(() => true, () => false);
  if (wajib) {
    await p.fill('#pw-old', E.ADMIN_PW); await p.fill('#pw-new', sandi); await p.fill('#pw-again', sandi);
    await p.click('button[type=submit]');
  }
  cek('masuk (admin baru di PostgreSQL wajib ganti sandi dulu)', wajib);
  const muat = async (hash, sel, nama) => {
    await p.goto(BASE + '/' + hash); await p.waitForLoadState('networkidle'); await p.waitForTimeout(1200);
    const ok = await p.waitForSelector(sel, { timeout: 15000 }).then(() => true, () => false);
    await p.screenshot({ path: path.join(OUT, `docker-${nama}.png`) });
    return ok;
  };
  cek('ringkasan: KPI tampil', await muat('#/overview', 'main .kpi', 'ringkasan'));
  const folders = await p.evaluate(() => fetch('/api/meta').then((r) => r.json()).then((m) => (m.folders || []).length));
  cek('semua folder ter-ingest terbaca dari volume', folders >= 1, `${folders} folder`);
  cek('halaman layanan nginx', await muat('#/layanan/nginx-ingress-controller', 'main table', 'layanan'));
  cek('Command Center: peta MapLibre', await muat('#/peta', 'main canvas.maplibregl-canvas', 'command-center'));
  cek('tanpa galat JavaScript', errs.length === 0, errs.slice(0, 3).join(' | '));
  }

  // ------------------------------------------------------------------ pgAdmin (opsional)
  if (E.PGADMIN_EMAIL) {
    const g = await ctx.newPage();
    await g.goto(E.PGADMIN_URL || 'http://127.0.0.1:5050/');
    await g.waitForSelector('input[name=email]', { timeout: 60000 });
    await g.fill('input[name=email]', E.PGADMIN_EMAIL); await g.fill('input[name=password]', E.PGADMIN_PW); await g.keyboard.press('Enter');
    const ok = await g.waitForSelector('text=MoniShield', { timeout: 60000 }).then(() => true, () => false);
    await g.waitForTimeout(1500); await g.screenshot({ path: path.join(OUT, 'docker-pgadmin.png') });
    cek('pgAdmin: masuk, server MoniShield terdaftar otomatis', ok);
  }

  // ------------------------------------------------------------------ DbGate (opsional)
  if (E.DBGATE_LOGIN) {
    const d = await ctx.newPage();
    await d.goto(E.DBGATE_URL || 'http://127.0.0.1:5051/');
    await d.waitForSelector('input[type=password]', { timeout: 60000 });
    await d.fill('input[name=login], input[type=text]', E.DBGATE_LOGIN); await d.fill('input[type=password]', E.DBGATE_PW); await d.keyboard.press('Enter');
    const ok = await d.waitForSelector('text=data log (DuckDB', { timeout: 60000 }).then(() => true, () => false);
    cek('DbGate: masuk, koneksi DuckDB (salinan) dan PostgreSQL terdaftar', ok);
    await d.click('text=data log (DuckDB');                                 // buka salinan DuckDB -> daftar tabel log
    const tabel = await d.waitForSelector('text=nginx_access', { timeout: 60000 }).then(() => true, () => false);
    await d.waitForTimeout(1500); await d.screenshot({ path: path.join(OUT, 'docker-dbgate.png') });
    cek('DbGate: tabel log DuckDB terbaca (nginx_access)', tabel);
  }

  await browser.close();
  console.log(`\n${hasil.filter(Boolean).length}/${hasil.length} lulus; tangkapan layar: ${OUT}`);
  process.exit(hasil.every(Boolean) ? 0 : 1);
})().catch((e) => { console.error(e); process.exit(1); });
