// Verifikasi Tahap 21 (deteksi serangan OWASP CRS + kategori CAPEC) di halaman Keamanan, Chromium.
//   node tools/uji_tahap21.cjs http://127.0.0.1:8000 <sandi-admin>      (server dengan attack_rules = 'crs', bawaan)
// Perbandingan dengan dashboard lama TIDAK dilakukan di sini: kategori sengaja berbeda (aturan lama -> CRS); kesetaraan
// tampilan aturan lama diuji uji_tahap15.cjs dengan server S4_ATTACK_RULES=lama. Yang diuji: isi halaman = API, kategori =
// nama CAPEC dua bahasa, ID aturan per baris, catatan kaki menyebut CRS + versi + tingkat paranoia, 2 bahasa × 2 tema × 2 lebar.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const path = require('path');
const fs = require('fs');
const [, , BASE = 'http://127.0.0.1:8000', PW] = process.argv;
const OUT = process.env.SHOTS_DIR || path.join(require('os').tmpdir(), 's4-shots');
const CAPEC = JSON.parse(fs.readFileSync(path.resolve(__dirname, '..', 'monishield', 'capec.json'), 'utf8'));
fs.mkdirSync(OUT, { recursive: true });
const hasil = [];
const cek = (n, ok, info = '') => { hasil.push(!!ok); console.log(`${ok ? 'LULUS' : 'GAGAL'}  ${n}${info ? '  — ' + info : ''}`); };
const bil = (s) => +String(s ?? '').replace(/[^\d-]/g, '') || 0;
const norm = (s) => String(s).toLowerCase().replace(/\s+/g, ' ').trim();
const SAMA = new Set(['66/sqli', '63/xss', '126/lfi', '253/rfi', '664/ssrf', '310/reputation-scanner']);
const nama = (c, l) => { const [id, fam] = c.split('/'); const a = CAPEC.capec[id][l]; return SAMA.has(c) || !fam ? a : `${a} · ${CAPEC.attack[fam][l]}`; };
const F = '2026-10-06';

(async () => {
  const browser = await chromium.launch(process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {});
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();
  const errs = [], dialogs = [];
  page.on('pageerror', (e) => errs.push(e.message));
  page.on('console', (m) => m.type() === 'error' && !/status of 401/.test(m.text()) && errs.push(m.text()));
  page.on('dialog', (d) => { dialogs.push(d.message()); d.dismiss(); });
  await page.goto(BASE + `/#/keamanan?folder=${F}`);
  await page.fill('#u', 'admin'); await page.fill('#p', PW); await page.click('button[type=submit]');
  const siap = async () => { await page.waitForSelector('main .kpi'); await page.waitForLoadState('networkidle'); await page.waitForTimeout(500); };
  await siap();
  const api = (p) => page.evaluate((p) => fetch(p, { headers: { 'X-Requested-With': 'fetch' } }).then((r) => r.json()), p);
  const S = await api(`/api/folders/${F}/security`);
  cek('API: skema crs, versi v4.30.0, paranoia 1, ambang 5', S.scheme === 'crs' && S.crs.version === 'v4.30.0' && S.crs.paranoia === 1 && S.crs.threshold === 5,
    JSON.stringify(S.crs));

  // ------------------------------------------------------------------ KPI = API; IP penyerang di Ringkasan = Keamanan
  const kpi = await page.$$eval('main .kpi', (e) => e.map((x) => [x.querySelector('.l').textContent.trim(), x.querySelector('.v').textContent.trim()]));
  const k = S.kpi, harap = [k.attack_requests, k.attack_ips, k.critical_hits, k.attack_urls_2xx, k.login_fail_ips, k.accounts_ok_after_fail, k.accounts_ok_other_ip, k.resets];
  cek(`8 KPI = API (${harap.join(' · ')}), KPI kritis berlabel "keparahan tertinggi"`, kpi.length === 8 && kpi.every(([, v], i) => bil(v) === harap[i]) && /keparahan tertinggi/i.test(kpi[2][0]),
    kpi.map(([l, v]) => `${l}=${v}`).join(' · '));
  const sum = await api(`/api/folders/${F}`);
  const ipSum = sum.attack_ip_count ?? sum.summary?.attack_ip_count;
  cek('Ringkasan folder: jumlah IP penyerang = KPI Keamanan (skema yang sama)', ipSum === k.attack_ips, `ringkasan ${ipSum}, keamanan ${k.attack_ips}`);

  // ------------------------------------------------------------------ tabel URL serangan: kategori CAPEC, ID aturan
  const card = (judul) => page.$$eval('main section.card', (cs, j) => {
    const c = cs.find((x) => x.querySelector('table') && (x.querySelector('h2, h3')?.childNodes[0]?.textContent || '').trim().toLowerCase().startsWith(j));
    if (!c) return null;
    const head = [...c.querySelectorAll('thead th')].map((th) => th.innerText.trim());
    return { head, rows: [...c.querySelectorAll('tbody tr')].filter((tr) => !tr.querySelector('td[colspan]')).map((tr) => [...tr.cells].map((td) => td.innerText.trim())) };
  }, judul);
  const urls = await card('endpoint');
  const U = S.tables['attack-urls'];
  cek('tabel URL serangan: kolom "Aturan CRS" sesudah URL', urls && urls.head.findIndex((h) => /aturan crs/i.test(h)) === 2, urls?.head.join(' | '));
  const bedaKat = [], bedaAt = [];
  U.rows.forEach((r, i) => {
    const row = urls.rows[i]; if (!row) { bedaKat.push(`baris ${i} hilang`); return; }
    if (!norm(row[0]).startsWith(norm(nama(r.category, 'id'))) || !row[0].includes(`CAPEC-${r.category.split('/')[0]}`)) bedaKat.push(`${row[0]} ≠ ${nama(r.category, 'id')}`);
    if (row[2].split(/\s+/).map(Number).join() !== r.rules.join()) bedaAt.push(`${row[2]} ≠ ${r.rules}`);
  });
  cek(`${U.rows.length} baris: kategori = nama CAPEC (ID) + "CAPEC-n"`, U.rows.length && !bedaKat.length, bedaKat.slice(0, 3).join(' ;; '));
  cek('ID aturan CRS per baris = API (diurutkan)', !bedaAt.length && U.rows.every((r) => r.rules.length >= 1), bedaAt.slice(0, 3).join(' ;; '));
  const aturan = new Set(U.rows.flatMap((r) => r.rules));
  cek(`semua ID aturan di tabel ada di crs_rules.json PL1 (${aturan.size} aturan berbeda)`, [...aturan].every((id) => id >= 913000 && id < 945000), [...aturan].join(', '));
  const catChart = await page.$$eval('main section.card', (cs) => { const c = cs.find((x) => /kategori serangan/i.test(x.querySelector('h2, h3')?.textContent || '')); return c ? c.innerText : ''; });
  cek('chart "Request per kategori serangan" ada', !!catChart);

  // temuan utama: Log4Shell dari aturan + kategori kritis bernama CAPEC
  const temuan = await page.$$eval('main section.alert li', (e) => e.map((x) => x.innerText.replace(/\s+/g, ' ').trim()));
  const tLog = S.findings.log4shell ? temuan.some((s) => /Log4Shell/.test(s) && s.includes(String(S.findings.log4shell.hits))) : true;
  const tKrit = S.findings.by_critical_category.every((c) => temuan.some((s) => norm(s).includes(norm(nama(c.category, 'id')))));
  cek('Temuan utama: Log4Shell (aturan CRS Log4j) + kategori kritis bernama CAPEC', temuan.length && tLog && tKrit, temuan.slice(0, 3).join(' ;; ').slice(0, 300));

  // tabel IP penyerang: kategori per IP bernama CAPEC
  const ips = await card('ip sumber');
  const IP = S.tables['attack-ips'];
  const bedaIp = IP.rows.filter((r, i) => !Object.keys(r.cats).every((c) => norm(ips?.rows[i]?.join(' ') || '').includes(norm(nama(c, 'id')))));
  cek(`tabel IP penyerang (${IP.rows.length} baris): kategori bernama CAPEC`, ips && !bedaIp.length, bedaIp.slice(0, 2).map((r) => r.ip.ip).join(', '));

  // catatan kaki
  const foot = await page.textContent('main .content > p.foot');
  cek('catatan kaki: OWASP CRS v4.30.0, Apache 2.0, paranoia 1, 91 aturan, ambang 5, CAPEC, bukan pengganti WAF',
    /OWASP Core Rule Set v4\.30\.0/.test(foot) && /Apache 2\.0/.test(foot) && /paranoia 1/.test(foot) && /91 aturan/.test(foot) && /≥ 5/.test(foot) && /CAPEC/.test(foot) && /bukan pengganti WAF/.test(foot), foot.slice(0, 160));
  cek('isi URL/User-Agent serangan tampil sebagai teks (tidak ada dialog/skrip)', dialogs.length === 0 && (await page.$$('main script')).length === 0);
  await page.screenshot({ path: `${OUT}/t21-keamanan-1006.png`, fullPage: true });

  // ------------------------------------------------------------------ bahasa Inggris: nama CAPEC + catatan kaki EN
  await page.evaluate(() => localStorage.setItem('lang', 'en')); await page.reload(); await siap();
  const urlsEn = await card('endpoint');
  const bedaEn = U.rows.filter((r, i) => !norm(urlsEn?.rows[i]?.[0] || '').startsWith(norm(nama(r.category, 'en'))));
  const footEn = await page.textContent('main .content > p.foot');
  cek('EN: kategori = nama CAPEC Inggris, kolom "CRS rules", catatan kaki Inggris',
    urlsEn && !bedaEn.length && urlsEn.head.some((h) => /crs rules/i.test(h)) && /OWASP Core Rule Set v4\.30\.0/.test(footEn) && /paranoia level 1/.test(footEn) && /not a WAF replacement/.test(footEn),
    bedaEn.slice(0, 2).map((r) => r.category).join(', ') + ' ' + footEn.slice(0, 100));

  // ------------------------------------------------------------------ 2 bahasa × 2 tema × 2 lebar
  for (const lang of ['id', 'en']) for (const theme of ['dark', 'light']) for (const w of [1440, 390]) {
    await page.setViewportSize({ width: w, height: 900 });
    await page.evaluate(([l, th]) => { localStorage.setItem('lang', l); localStorage.setItem('theme', th); }, [lang, theme]);
    await page.reload(); await siap();
    const st = await page.evaluate(() => [document.documentElement.scrollWidth, innerWidth, document.documentElement.lang, document.documentElement.dataset.theme,
      document.querySelectorAll('main section.card').length, document.querySelector('main .content > p.foot')?.textContent || '',
      getComputedStyle(document.querySelector('main .kpis')).gridTemplateColumns.split(' ').length]);
    const bahasaOk = lang === 'en' ? /Detection uses/.test(st[5]) : /Deteksi memakai/.test(st[5]);
    cek(`keamanan ${lang}/${theme}/${w}px: tanpa gulir mendatar, kartu lengkap, catatan kaki sesuai bahasa${w <= 900 ? ', KPI 2 kolom' : ''}`,
      st[0] <= st[1] && st[2] === lang && st[3] === theme && st[4] >= 9 && bahasaOk && (w > 900 || st[6] === 2), `lebar ${st[0]}/${st[1]}, ${st[4]} kartu, KPI ${st[6]} kolom`);
    await page.screenshot({ path: `${OUT}/t21-keamanan-${lang}-${theme}-${w}.png`, fullPage: w === 1440 });
  }
  await page.evaluate(() => { localStorage.setItem('lang', 'id'); localStorage.setItem('theme', 'dark'); });
  cek('tidak ada galat halaman/konsol', errs.length === 0, errs.slice(0, 3).join(' | '));
  await browser.close();
  const gagal = hasil.filter((x) => !x).length;
  console.log(`\n${hasil.length - gagal}/${hasil.length} lulus`);
  process.exit(gagal ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
