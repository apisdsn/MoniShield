// Verifikasi Tahap 19 (kartu "Impor dari S3" di layar Ingest & impor) di Chromium, terhadap server uji + S3 TIRUAN:
//   .venv/bin/python tools/server_uji_impor.py 8019 <dir-kerja-kosong>   (lalu)   node tools/uji_tahap19.cjs http://127.0.0.1:8019
// Diperiksa: status kredensial tanpa nilai; tautan ditolak dengan sebab; "Coba dulu" (0 byte diunduh); "Impor" + konfirmasi +
// kemajuan -> folder muncul; impor ulang 0 objek; tempel/hapus kredensial sementara; galat EN; audit tanpa rahasia; 8 kombinasi.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const path = require('path');
const fs = require('fs');
const [, , BASE = 'http://127.0.0.1:8019'] = process.argv;
const OUT = process.env.SHOTS_DIR || path.join(require('os').tmpdir(), 's4-shots');
fs.mkdirSync(OUT, { recursive: true });
const hasil = [];
const cek = (n, ok, info = '') => { hasil.push(!!ok); console.log(`${ok ? 'LULUS' : 'GAGAL'}  ${n}${info ? '  — ' + info : ''}`); };
const PW0 = 'sandi-awal-admin-uji-19', PW1 = 'sandi-baru-admin-uji-19', SECRET = 'rahasiaTiruanUjiYangTidakBolehBocor0001';
const URL = 's3://simpel4-backup/k8s-logs/2026-01-05/', TEMPEL_AK = 'AKIATEMPELBROWSER001', TEMPEL_SK = 'rahasiaTempelBrowserJanganBocor0002';

(async () => {
  const browser = await chromium.launch(process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {});
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const p = await ctx.newPage();
  const errs = [];
  p.on('pageerror', (e) => errs.push(e.message));
  p.on('console', (m) => m.type() === 'error' && !/status of 40[01]/.test(m.text()) && errs.push(m.text()));   // 400 = penolakan yang diuji
  await p.goto(BASE + '/#/admin/ingest');
  await p.fill('#u', 'admin'); await p.fill('#p', PW0); await p.click('button[type=submit]');
  await p.waitForSelector('#pw-old');
  await p.fill('#pw-old', PW0); await p.fill('#pw-new', PW1); await p.fill('#pw-again', PW1); await p.click('button[type=submit]');
  await p.waitForSelector('main .imp #imp-url'); await p.waitForLoadState('networkidle');
  const kartu = () => p.textContent('main .imp');
  const tungguSelesai = () => p.waitForFunction(() => !document.querySelector('main .imp [role=progressbar]') && ![...document.querySelectorAll('main .imp .acts .btn')].every((b) => b.disabled), null, { timeout: 20000 });
  const toast = (re) => p.waitForFunction((s) => [...document.querySelectorAll('.toasts .t')].some((x) => new RegExp(s).test(x.textContent)), re.source, { timeout: 15000 }).then(() => true, () => false);

  let t = await kartu();
  cek('kredensial: "tersedia (konfigurasi server)", tanpa nilai; bentuk tautan yang diterima ditulis', /tersedia/.test(t) && /konfigurasi server/.test(t)
    && /Hanya s3:\/\/simpel4-backup\/k8s-logs\/<YYYY-MM-DD>\//.test(t) && !t.includes(SECRET) && !t.includes('AKIATIRUAN'));

  // tautan ditolak dengan sebab (sebelum menghubungi S3)
  for (const [u, re] of [['s3://bucket-lain/k8s-logs/2026-01-05/', /Bucket ini tidak diizinkan/], ['s3://simpel4-backup/k8s-logs/bukan-tanggal/', /harus tanggal/],
                         ['s3://simpel4-backup/lain/2026-01-05/', /Awalan ini tidak diizinkan/]]) {
    await p.fill('#imp-url', u); await p.click('main .imp button:has-text("Coba dulu")');
    await p.waitForSelector('main .imp [role=alert]');
    const a = await p.textContent('main .imp [role=alert]');
    cek(`tautan "${u}" ditolak dengan sebab`, re.test(a), a);
  }
  // Coba dulu
  await p.fill('#imp-url', URL); await p.click('main .imp button:has-text("Coba dulu")');
  await p.waitForSelector('main .imp .sum'); await tungguSelesai();
  t = await kartu();
  await p.click('main .imp details.objs summary');
  const rincian = await p.textContent('main .imp details.objs');
  cek('"Coba dulu": 2 objek akan diambil · 2 dilewati · 0 byte diunduh; rincian ambil/lewati dengan alasan',
    /Hasil coba: 2 objek akan diambil .* 2 dilewati · 0 byte diunduh/.test(t) && /\.gz berpasangan dengan \.log/.test(rincian) && /bukan file log/.test(rincian), t.replace(/\s+/g, ' ').slice(0, 200));
  const folder0 = await p.evaluate(() => fetch('/api/meta').then((r) => r.json()).then((m) => m.folders.map((f) => f.folder)));
  // Impor: konfirmasi -> kemajuan -> selesai
  await p.click('main .imp button.primary:has-text("Impor")');
  await p.waitForSelector('dialog[open]');
  const konf = await p.textContent('dialog[open]');
  await p.click('dialog[open] button.primary');
  const ok = await toast(/Impor selesai: 2 objek diunduh ke folder 2026-01-05/);
  await tungguSelesai(); await p.waitForTimeout(600);
  t = await kartu();
  const folder1 = await p.evaluate(() => fetch('/api/meta').then((r) => r.json()).then((m) => m.folders.map((f) => f.folder)));
  const opsi = await p.$$eval('select option', (o) => o.map((x) => x.value));
  cek('"Impor": konfirmasi menyebut tautan; selesai 2 objek diunduh + ingest; folder 2026-01-05 muncul di pemilih folder',
    konf.includes(URL) && ok && /Selesai: 2 objek diunduh/.test(t) && /Ingest: 2 file berubah/.test(t) && !folder0.includes('2026-01-05') && folder1.includes('2026-01-05') && opsi.includes('2026-01-05'),
    t.replace(/\s+/g, ' ').match(/Selesai[^.]*\.[^.]*\./)?.[0]);
  await p.screenshot({ path: `${OUT}/t19-impor-1440.png`, fullPage: true });
  // impor ulang: 0 objek
  await p.click('main .imp button.primary:has-text("Impor")'); await p.click('dialog[open] button.primary');
  await toast(/Impor selesai: 0 objek/); await tungguSelesai(); await p.waitForTimeout(400);
  t = await kartu();
  cek('tautan sama lagi: 0 objek diunduh (sama dengan unduhan sebelumnya)', /Selesai: 0 objek diunduh/.test(t));
  const riwayat = await p.$$eval('main section.card', (cs) => { const c = cs.find((x) => /Riwayat impor/i.test(x.querySelector('h2')?.textContent || ''));
    return c ? [...c.querySelectorAll('tbody tr')].map((r) => r.innerText.replace(/\s+/g, ' ')) : []; });
  cek('riwayat impor: 3 baris terbaru (selesai, selesai, coba) dengan tautan, folder, oleh admin', riwayat.length >= 3 && /selesai/i.test(riwayat[0]) && /coba/i.test(riwayat[2])
    && riwayat.every((r) => r.includes('s3://simpel4-backup/k8s-logs/2026-01-05/') && /admin/.test(r)), riwayat.slice(0, 3).join(' || ').slice(0, 300));

  // kredensial sementara: bentuk salah ditolak, lalu disimpan; kunci tak dikenal S3 -> galat jelas; dihapus -> kembali ke server
  await p.click('main .imp button:has-text("Tempel kredensial lain")');
  const tipe = await p.$$eval('main .imp .credf input', (i) => i.map((x) => [x.type, x.getAttribute('autocomplete')]));
  await p.fill('#c-ak', 'bukan kunci'); await p.fill('#c-sk', 'pendek'); await p.click('main .imp .credf button[type=submit]');
  await p.waitForSelector('main .imp .credf [role=alert]');
  const salah = await p.textContent('main .imp .credf [role=alert]');
  await p.fill('#c-ak', TEMPEL_AK); await p.fill('#c-sk', TEMPEL_SK); await p.click('main .imp .credf button[type=submit]');
  await toast(/Kredensial sementara disimpan/); await p.waitForTimeout(400);
  t = await kartu();
  const nilaiKosong = !(await p.$('#c-ak'));
  cek('tempel kredensial: kolom bertipe sandi tanpa autocomplete; bentuk salah ditolak; disimpan -> "ditempel admin, memori server"; nilai tidak tampil',
    tipe.length === 3 && tipe.every(([ty, ac]) => ty === 'password' && ac === 'off') && /tidak berbentuk kunci akses AWS/.test(salah) && /ditempel admin/.test(t) && nilaiKosong
    && !t.includes(TEMPEL_SK) && !t.includes(TEMPEL_AK), salah);
  await p.click('main .imp button:has-text("Coba dulu")');
  await p.waitForSelector('main .imp [role=alert]'); await tungguSelesai();
  const tolak = await p.textContent('main .imp [role=alert]');
  cek('kunci tempel tak dikenal S3: "S3 menolak akses" (tanpa menulis apa pun)', /S3 menolak akses/.test(tolak), tolak);
  await p.click('main .imp button:has-text("Hapus kredensial tempel")'); await toast(/Kredensial tempel dihapus/); await p.waitForTimeout(400);
  cek('hapus kredensial tempel -> kembali "konfigurasi server"', /konfigurasi server/.test(await kartu()));

  // audit dan seluruh respons: tanpa rahasia
  const semua = await p.evaluate(() => Promise.all(['/api/admin/audit?limit=500', '/api/admin/import', '/api/meta', '/api/admin/import/1'].map((u) => fetch(u).then((r) => r.text()))));
  const aksi = JSON.parse(semua[0]).rows.map((r) => r.action);
  cek('audit: import.start, import.credentials.set/clear; tidak ada nilai kredensial di audit/riwayat/meta',
    ['import.start', 'import.credentials.set', 'import.credentials.clear'].every((a) => aksi.includes(a)) && !semua.some((s) => [SECRET, TEMPEL_SK, TEMPEL_AK, 'AKIATIRUAN'].some((x) => s.includes(x))));

  // galat dalam bahasa Inggris (kamus per kode)
  await p.evaluate(() => localStorage.setItem('lang', 'en')); await p.reload(); await p.waitForSelector('main .imp #imp-url');
  await p.fill('#imp-url', 's3://bucket-lain/k8s-logs/2026-01-05/'); await p.click('main .imp button:has-text("Dry run")');
  await p.waitForSelector('main .imp [role=alert]');
  const en = await p.textContent('main .imp [role=alert]');
  cek('EN: penolakan dalam bahasa Inggris', /This bucket is not allowed/.test(en), en);

  // 2 bahasa × 2 tema × 2 lebar
  for (const lang of ['id', 'en']) for (const theme of ['dark', 'light']) for (const w of [1440, 390]) {
    await p.setViewportSize({ width: w, height: 860 });
    await p.evaluate(([l, th]) => { localStorage.setItem('lang', l); localStorage.setItem('theme', th); }, [lang, theme]);
    await p.goto(BASE + '/#/admin/ingest'); await p.reload(); await p.waitForSelector('main .imp #imp-url'); await p.waitForLoadState('networkidle'); await p.waitForTimeout(300);
    const st = await p.evaluate(() => [document.documentElement.scrollWidth, innerWidth, document.documentElement.lang, document.documentElement.dataset.theme,
      [...document.querySelectorAll('main .imp, main section.card h2, main th')].map((x) => x.textContent.trim()).join(' | ')]);
    const sisa = lang === 'en' ? (st[4].match(/\b(Impor dari|Tautan|Coba dulu|tersedia|Riwayat|Oleh|selesai|Hanya)\b/g) || []) : [];
    cek(`ingest & impor ${lang}/${theme}/${w}px: tanpa gulir mendatar, teks sesuai bahasa`, st[0] <= st[1] && st[2] === lang && st[3] === theme && !sisa.length,
      `lebar ${st[0]}/${st[1]}${sisa.length ? ', masih ID: ' + sisa.slice(0, 4).join(', ') : ''}`);
    await p.screenshot({ path: `${OUT}/t19-${lang}-${theme}-${w}.png`, fullPage: w === 1440 });
  }
  await p.evaluate(() => { localStorage.setItem('lang', 'id'); localStorage.setItem('theme', 'dark'); });
  cek('tidak ada galat halaman/konsol', errs.length === 0, errs.slice(0, 3).join(' | '));
  await browser.close();
  const gagal = hasil.filter((x) => !x).length;
  console.log(`\n${hasil.length - gagal} lulus, ${gagal} gagal`);
  process.exit(gagal ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
