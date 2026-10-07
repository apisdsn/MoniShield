// Verifikasi Tahap 17 (Pod, Bisnis, Pelacakan Request) di Chromium: v2 berdampingan dengan ../dashboard.html lama.
//   node tools/uji_tahap17.cjs http://127.0.0.1:8000 <sandi-admin>
// Selisih yang DIHARAPKAN: label "Pod dengan retry" (B10), status file "Rusak" (B05); KPI Bisnis yang lognya tidak ada
// tampil "–" + keterangan, bukan 0 (U16); Pelacakan memakai SEMUA jejak (TRD §4.4 butir 1: lama dipotong 300) dan
// "lambat ≥ 5 dtk" semua status selain gagal (butir 9); folder tanpa kecocokan (matched = 0) tampil catatan (ASUMSI).
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const path = require('path');
const fs = require('fs');
const [, , BASE = 'http://127.0.0.1:8000', PW] = process.argv;
const LAMA = 'file://' + path.resolve(__dirname, '..', '..', 'dashboard.html');
const OUT = process.env.SHOTS_DIR || path.join(require('os').tmpdir(), 's4-shots');
fs.mkdirSync(OUT, { recursive: true });
const hasil = [];
const cek = (n, ok, info = '') => { hasil.push(!!ok); console.log(`${ok ? 'LULUS' : 'GAGAL'}  ${n}${info ? '  — ' + info : ''}`); };
const rapat = (s) => String(s ?? '').toLowerCase().replace(/(\d)[.,](\d{3})\b/g, '$1$2').replace(/\s+/g, '');
const norm = (s) => String(s).toLowerCase().replace(/\s+/g, ' ').trim();
const bil = (s) => +String(s ?? '').replace(/[^\d-]/g, '') || 0;
const CHART_STUB = `(() => { const deep = () => new Proxy({}, { get: (t, k) => (k in t ? t[k] : (t[k] = deep())), set: (t, k, v) => ((t[k] = v), true) });
  window.__charts = {}; window.Chart = class { constructor(el, cfg) { window.__charts[el.id] = { labels: cfg.data.labels,
    datasets: cfg.data.datasets.map((d) => ({ label: d.label, data: d.data })) }; } destroy() {} }; window.Chart.defaults = deep(); })();`;
const tabel = (p, sel, judul) => p.$$eval(sel, (cards, judul) => {
  const c = cards.find((x) => x.querySelector('table') && (x.querySelector('h3, h2')?.childNodes[0]?.textContent || '').trim().toLowerCase().startsWith(judul));   // kartu chart berjudul mirip dilewati
  if (!c) return null;
  return [...c.querySelectorAll('tr')].filter((tr) => tr.querySelector('td') && !tr.querySelector('td[colspan]')).map((tr) => [...tr.cells].map((td) => td.innerText));
}, judul);

const dec = (s) => rapat(s).replace(/(\d),(\d)/g, '$1.$2');          // desimal ID "0,12" = lama "0.12"
const ipOf = (s) => (String(s).match(/\d{1,3}(?:\.\d{1,3}){3}|[0-9a-f:]{6,}/i) || [''])[0];

(async () => {
  const browser = await chromium.launch(process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {});
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();
  const errs = [], dialogs = [];
  page.on('pageerror', (e) => errs.push(e.message));
  page.on('console', (m) => m.type() === 'error' && !/status of 401/.test(m.text()) && errs.push(m.text()));
  page.on('dialog', (d) => { dialogs.push(d.message()); d.dismiss(); });
  await page.goto(BASE + '/#/pod?folder=2026-10-06');
  await page.fill('#u', 'admin'); await page.fill('#p', PW); await page.click('button[type=submit]');
  const siap = async () => { await page.waitForSelector('main section.card, main .note'); await page.waitForLoadState('networkidle'); await page.waitForTimeout(500); };
  await siap();
  const api = (p) => page.evaluate((p) => fetch(p).then((r) => r.json()), p);
  const lctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  await lctx.route(/^https?:\/\//, (r) => r.abort());
  await lctx.addInitScript(CHART_STUB);
  const lp = await lctx.newPage();
  lp.on('dialog', (d) => d.dismiss());
  await lp.goto(LAMA);
  const lama = async (f, tab) => { await lp.evaluate(([d, t]) => { window.__charts = {}; day = d; tab = t; render(); }, [f, tab]); return lp.evaluate(() => window.__charts); };
  const chartTabel = async (judul) => {
    const card = page.locator('section.card', { has: page.locator('h2', { hasText: judul }) }).first();
    await card.locator('button', { hasText: 'Lihat sebagai tabel' }).click();
    const t = await card.evaluate((c) => ({ head: [...c.querySelectorAll('thead th')].map((x) => x.textContent.trim()).slice(1),
      rows: [...c.querySelectorAll('tbody tr')].map((tr) => [...tr.cells].map((x) => x.textContent.trim())) }));
    await card.locator('button', { hasText: 'Lihat sebagai chart' }).click();
    return t;
  };
  const samaSeri = (L, t) => {
    const beda = [];
    if (!L) return ['chart lama tidak ada'];
    L.datasets.forEach((d, k) => {
      const j = L.datasets.length === 1 ? 0 : t.head.findIndex((h) => norm(h) === norm(d.label ?? ''));
      if (j < 0) return beda.push(`seri ${d.label}`);
      d.data.forEach((v, i) => { if ((v ?? 0) !== bil(t.rows[i]?.[j + 1])) beda.push(`${d.label ?? ''}[${i}] ${v} vs ${t.rows[i]?.[j + 1]}`); });
    });
    if (t.rows.length !== L.labels.length) beda.push(`titik ${t.rows.length} vs ${L.labels.length}`);
    return beda;
  };
  const kpiLama = () => lp.$$eval('.kpi', (e) => e.map((x) => [x.querySelector('.l').textContent.trim(), x.querySelector('.v').textContent.trim(), x.querySelector('.dl')?.textContent.trim() || '']));
  // KPI baru: [label, angka, perubahan] — perubahan = lencana + teks terlihat (tanpa teks pembaca layar)
  const kpiBaru = () => page.$$eval('main .kpi', (e) => e.map((x) => [x.querySelector('.l').textContent.trim(), x.querySelector('.v').textContent.trim(),
    [x.querySelector('.badge')?.textContent || '', ...[...x.querySelectorAll('.dl')].map((d) => (d.querySelector('[aria-hidden]') || d).textContent)].join(' ').trim(),
    [...x.querySelectorAll('.dl')].map((d) => d.textContent).join(' ')]));
  const kartu = async () => [(await lp.$$eval('#main .card h3', (e) => e.map((x) => x.childNodes[0].textContent.trim()))).map(norm),
    (await page.$$eval('main .grid section.card > header h2', (e) => e.map((x) => x.childNodes[0].textContent.trim()))).map(norm)];
  const samaTabel = async (judul, kL, kB = kL, fx = (s) => s) => {
    const a = await tabel(lp, '#main .card', judul), b = await tabel(page, 'main section.card', judul);
    if (!a && !b) return null;
    const K = (rows, k) => (rows || []).map((r) => k.map((i) => fx(dec(r[i]), i)).join('|')).sort();
    const A = K(a, kL), B = K(b, kB);
    return { n: A.length, m: B.length, hilang: A.filter((x) => !B.includes(x)) };
  };

  // ------------------------------------------------------------------ Pod
  for (const f of ['2026-10-06', '2026-09-29', '2026-09-28']) {
    await page.goto(`${BASE}/#/pod?folder=${f}`); await siap();
    const C = await lama(f, 'pod');
    const kl = await kpiLama(), kb = await kpiBaru();
    const lbl = (l) => norm(l).replace('pod dengan retry 502', 'pod dengan retry');      // B10
    cek(`pod ${f}: 5 KPI sama dengan lama (label "Pod dengan retry")`, kl.length === 5 && kb.length === 5 && kl.every(([l, v], i) => lbl(l) === norm(kb[i][0]) && rapat(v) === rapat(kb[i][1])),
      kb.map(([l, v]) => `${l} ${v}`).join(' · '));
    const [jl, jb] = await kartu();
    cek(`pod ${f}: kartu sama dengan lama`, jl.length === jb.length && jl.every((x) => jb.includes(x)), `${jb.length} kartu` + (jl.filter((x) => !jb.includes(x)).length ? ' | kurang: ' + jl.filter((x) => !jb.includes(x)).join(', ') : ''));
    cek(`pod ${f}: chart error per pod sama`, !samaSeri(C.o1, await chartTabel('Error per pod')).length);
    if (C.o2) cek(`pod ${f}: chart sebaran request per pod sama`, !samaSeri(C.o2, await chartTabel('Sebaran request per pod')).length);
    // kesehatan per pod: status lama "Tanpa Log" boleh menjadi "Rusak"/"Gagal dibaca" (B05)
    const sum = await api(`/api/folders/${f}`);
    const rusak = sum.files.filter((x) => x.status === 'corrupt').length;
    // status: file rusak/gagal dibaca di lama "Ada Log"/"Tanpa Log" menurut jumlah barisnya, di v2 "Rusak"/"Gagal dibaca" (B05)
    const h = await samaTabel('kesehatan per pod', [0, 1, 2, 3, 4]);
    const sL = Object.fromEntries((await tabel(lp, '#main .card', 'kesehatan per pod')).map((r) => [dec(r[0]), dec(r[5])]));
    const tb = await tabel(page, 'main section.card', 'kesehatan per pod');
    const nRusak = tb.filter((r) => /rusak/i.test(r[5])).length;
    const bedaSt = tb.filter((r) => !/^(rusak|gagaldibaca)$/.test(dec(r[5])) && sL[dec(r[0])] !== dec(r[5]));
    cek(`pod ${f}: tabel kesehatan per pod sama (${h.n} baris), status "Rusak" = ${rusak} file rusak, status lain sama`,
      h.n === h.m && !h.hilang.length && nRusak === rusak && !bedaSt.length, [...h.hilang, ...bedaSt.map((r) => r.join('|'))].slice(0, 2).join(' ;; '));
    const bp = await samaTabel('sebaran traffic per pod backend', [0, 1, 2, 3, 4, 5]);
    if (bp) cek(`pod ${f}: tabel sebaran traffic per pod backend sama (${bp.n} baris)`, bp.n === bp.m && !bp.hilang.length, bp.hilang.slice(0, 2).join(' ;; '));
    const rs = await samaTabel('restart / start aplikasi', [1, 2, 3]);
    cek(`pod ${f}: tabel restart sama (${rs.n} baris)`, rs.n === rs.m && !rs.hilang.length, rs.hilang.slice(0, 2).join(' ;; '));
    if (f === '2026-10-06') await page.screenshot({ path: `${OUT}/t17-pod-1006.png`, fullPage: true });
  }

  // ------------------------------------------------------------------ Bisnis
  for (const f of ['2026-09-29', '2026-10-06', '2026-09-30', '2026-09-28']) {
    await page.goto(`${BASE}/#/bisnis?folder=${f}`); await siap();
    const C = await lama(f, 'bisnis');
    const B = await api(`/api/folders/${f}/business`);
    const kl = await kpiLama(), kb = await kpiBaru();
    const sumber = { 'om-be-simpel-loop': [0, 1, 2, 3, 4, 5, 6], 'om-be-report': [7, 8], 'om-be-appsmanager': [9, 10] };
    const hilangLog = Object.entries(sumber).filter(([s]) => !B.sources.includes(s)).flatMap(([, ix]) => ix);
    const bedaK = kl.map(([l, v, d], i) => [l, v, d, kb[i]]).filter(([l, v, d, b], i) => !b || norm(l) !== norm(b[0])
      || (hilangLog.includes(i) ? !(b[1] === '–' && /tidak ada di folder ini/.test(b[3])) : rapat(v) !== rapat(b[1]) || rapat(d) !== rapat(b[2])));
    cek(`bisnis ${f}: 11 KPI + perubahan sama dengan lama${hilangLog.length ? `; ${hilangLog.length} KPI tanpa log "–" + keterangan` : ''}`, kl.length === 11 && kb.length === 11 && !bedaK.length,
      bedaK.length ? JSON.stringify(bedaK.slice(0, 2)) : kb.map(([, v, d]) => v + (d ? ` (${d})` : '')).join(' · '));
    if (f === '2026-09-29') {
      const v = Object.fromEntries(kb.map(([l, x]) => [norm(l), bil(x)]));
      cek('bisnis 29 Sep: 12 / 108 / 35 / 12 / 314 / 18 / 55 / PDF 813 / 32 / login 389',
        v['laporan dibuat'] === 12 && v['registrasi laporan'] === 108 && v['otp diminta'] === 35 && v['otp terverifikasi'] === 12 && v['file diunggah'] === 314
        && v['upload ditolak'] === 18 && v['email terkirim'] === 55 && v['pdf report dibuat'] === 813 && v['pdf report gagal'] === 32 && v['login sukses'] === 389);
    }
    const [jl, jb] = await kartu();
    cek(`bisnis ${f}: kartu sama dengan lama`, jl.length === jb.length && jl.every((x) => jb.includes(x)), `${jb.length} kartu` + (jl.filter((x) => !jb.includes(x)).length ? ' | kurang: ' + jl.filter((x) => !jb.includes(x)).join(', ') : ''));
    for (const [id, judul] of [['b1', 'Ringkasan aktivitas'], ['b2', 'Email notifikasi'], ['b3', 'Top aktivitas proses'], ['b4', 'Login sukses per jam'], ['b5', 'PDF report per template']]) {
      if (!C[id]) continue;
      const beda = samaSeri(C[id], await chartTabel(judul));
      cek(`bisnis ${f}: chart "${judul}" sama`, !beda.length, beda.slice(0, 3).join(' ; '));
    }
    // aktivitas: 20 teratas; baris berjumlah sama di batas ke-20 boleh berbeda pilihan (aturan E2), jumlahnya harus sama
    const aL = await tabel(lp, '#main .card', 'aktivitas proses laporan'), aB = await tabel(page, 'main section.card', 'aktivitas proses laporan');
    if (aL || aB) {
      const nL = aL.map((r) => bil(r[1])), nB = aB.map((r) => bil(r[1])), batas = Math.min(...nL);
      const KB = new Set(aB.map((r) => rapat(r[0]) + '|' + bil(r[1])));
      const hilang = aL.filter((r) => bil(r[1]) > batas && !KB.has(rapat(r[0]) + '|' + bil(r[1])));
      cek(`bisnis ${f}: tabel "aktivitas proses laporan" sama (${aL.length} baris; urutan bebas hanya di antara jumlah ${batas})`,
        aL.length === aB.length && nL.join() === nB.join() && !hilang.length, hilang.slice(0, 2).map((r) => r.join('|')).join(' ;; '));
    }
    const r = await samaTabel('pdf report per template', [0, 1, 2]);
    if (r) cek(`bisnis ${f}: tabel "pdf report per template" sama (${r.n} baris)`, r.n === r.m && !r.hilang.length, r.hilang.slice(0, 2).join(' ;; '));
    if (f === '2026-09-30') await page.screenshot({ path: `${OUT}/t17-bisnis-0930.png`, fullPage: true });
  }

  // ------------------------------------------------------------------ Pelacakan
  for (const f of ['2026-09-29', '2026-10-06', '2026-09-30', '2026-09-27']) {
    await page.goto(`${BASE}/#/pelacakan?folder=${f}`); await siap();
    const C = await lama(f, 'pelacakan');
    const T = await api(`/api/folders/${f}/tracing`);
    if (!T.available || !T.corr.matched) {
      const nol = await lp.$$eval('.kpi .v', (e) => e.map((x) => x.textContent.trim()));
      cek(`pelacakan ${f}: catatan "butuh log simpel-loop dan ingress nginx…" (ASUMSI matched = 0; lama: ${nol.length ? 'KPI ' + nol.join('/') : 'catatan'})`,
        /Pelacakan butuh log om-be-simpel-loop dan ingress nginx/.test(await page.textContent('main')) && !(await page.$('main .kpi')));
      continue;
    }
    const kl = await kpiLama(), kb = await kpiBaru();
    const sama3 = kl.slice(0, 3).every(([l, v], i) => norm(l) === norm(kb[i][0]) && dec(v) === dec(kb[i][1]));
    cek(`pelacakan ${f}: KPI 1–3 sama dengan lama`, kl.length === 6 && kb.length === 6 && sama3 && kl.every(([l], i) => norm(l) === norm(kb[i][0])), kb.slice(0, 3).map(([, v]) => v).join(' / '));
    cek(`pelacakan ${f}: KPI 4–6 = seluruh jejak (butir 1, 9): gagal ${kb[3][1]} (lama ${kl[3][1]}), IP ${kb[4][1]} (lama ${kl[4][1]}), lambat ${kb[5][1]} (lama ${kl[5][1]})`,
      bil(kb[3][1]) === T.kpi.failed_requests && bil(kb[4][1]) === T.kpi.failed_ips && bil(kb[5][1]) === T.kpi.slow_requests && bil(kb[3][1]) >= bil(kl[3][1]));
    if (f === '2026-09-29') cek('pelacakan 29 Sep: 60.665 / 22.638 / 37,3 %', bil(kb[0][1]) === 60665 && bil(kb[1][1]) === 22638 && kb[2][1] === '37,3%');
    const nl = await lp.$eval('#main .card.muted', (x) => x.textContent), nb = await page.$eval('main .note', (x) => x.textContent);
    cek(`pelacakan ${f}: catatan dengan persen tidak cocok sama dengan lama`, dec(nl) === dec(nb), nb.slice(-140));
    const [jl, jb] = await kartu();
    cek(`pelacakan ${f}: kartu sama dengan lama`, jl.length === jb.length && jl.every((x) => jb.includes(x)), `${jb.length} kartu`);
    // tabel jejak: 300 pertama + lanjutan; setelah dimuat semua, tiap baris lama ada di v2
    const card = page.locator('section.card', { has: page.locator('h2', { hasText: 'Jejak request gagal' }) }).first();
    const n0 = await card.locator('tbody tr').count();
    const foot = await card.locator('.foot .muted').textContent().catch(() => '');
    cek(`pelacakan ${f}: tabel jejak ${Math.min(300, T.tables.trace.total)} pertama${T.tables.trace.total > 300 ? ' + "tampilkan berikutnya"' : ''}`,
      n0 === Math.min(300, T.tables.trace.total) && (T.tables.trace.total <= 300 || /Menampilkan 300 dari/.test(foot)), `${n0} baris; ${foot}`);
    for (let i = 0; i < 10 && (await card.locator('button', { hasText: 'berikutnya' }).count()); i++) {
      await card.locator('button', { hasText: 'berikutnya' }).click(); await page.waitForLoadState('networkidle'); await page.waitForTimeout(300);
    }
    const a = await tabel(lp, '#main .card', 'jejak request gagal'), b = await tabel(page, 'main section.card', 'jejak request gagal');
    const K = (r) => [ipOf(r[0]), dec(r[1]), dec(r[2]), dec(r[3]).replace(/host(tidak|not)(tercatat|recorded)/, 'hostx'), dec(r[4]), dec(r[5])].join('|');
    const B = new Set(b.map(K)), hilang = a.map(K).filter((x) => !B.has(x));
    cek(`pelacakan ${f}: ${a.length} baris jejak lama semuanya ada di v2 (${b.length} baris setelah dimuat semua)`, b.length === T.tables.trace.total && !hilang.length, hilang.slice(0, 2).join(' ;; ').slice(0, 400));
    for (const [id, judul] of [['p1', 'Top 10 IP'], ['p2', 'Request gagal per jenis']]) {
      const beda = samaSeri(C[id], await chartTabel(judul));
      console.log(`  info  pelacakan ${f}: chart "${judul}" ${beda.length ? 'berbeda dari lama (lama dari 300 jejak, butir 1): ' + beda.slice(0, 2).join(' ; ') : 'sama dengan lama'}`);
    }
    if (f === '2026-09-29') await page.screenshot({ path: `${OUT}/t17-pelacakan-0929.png`, fullPage: false });
  }
  cek('URL jejak tampil sebagai teks, tidak ada dialog/eksekusi', dialogs.length === 0 && (await page.$$('main script')).length === 0);
  await lctx.close();

  // ------------------------------------------------------------------ 2 bahasa × 2 tema × 2 lebar
  for (const lang of ['id', 'en']) for (const theme of ['dark', 'light']) for (const w of [1440, 390]) {
    await page.setViewportSize({ width: w, height: 900 });
    await page.evaluate(([l, th]) => { localStorage.setItem('lang', l); localStorage.setItem('theme', th); }, [lang, theme]);
    for (const [u, nama, min] of [['/#/pod?folder=2026-10-06', 'pod', 5], ['/#/bisnis?folder=2026-09-29', 'bisnis', 7], ['/#/pelacakan?folder=2026-09-29', 'pelacakan', 3]]) {
      await page.goto(BASE + u); await page.reload(); await siap();
      const st = await page.evaluate(() => [document.documentElement.scrollWidth, innerWidth, document.documentElement.lang, document.documentElement.dataset.theme,
        document.querySelectorAll('main section.card').length, [...document.querySelectorAll('main section.card h2, main .kpi .l, main .note')].map((h) => h.textContent.trim()),
        getComputedStyle(document.querySelector('main .kpis')).gridTemplateColumns.split(' ').length]);
      const sisa = lang === 'en' ? st[5].filter((j) => /\b(dengan|tanpa|dibuat|gagal|sukses|per jam|aktivitas|lambat|cocok|sebaran|kesehatan|lama)\b/i.test(j)) : [];
      cek(`${nama} ${lang}/${theme}/${w}px: tanpa gulir mendatar, kartu lengkap${w <= 900 ? ', KPI 2 kolom' : ''}, teks sesuai bahasa`,
        st[0] <= st[1] && st[2] === lang && st[3] === theme && st[4] >= min && (w > 900 || st[6] === 2) && !sisa.length,
        `lebar ${st[0]}/${st[1]}, ${st[4]} kartu, KPI ${st[6]} kolom${sisa.length ? ', masih ID: ' + sisa.slice(0, 2).join(' | ') : ''}`);
      await page.screenshot({ path: `${OUT}/t17-${nama}-${lang}-${theme}-${w}.png`, fullPage: w === 1440 });
    }
  }
  await page.evaluate(() => { localStorage.setItem('lang', 'id'); localStorage.setItem('theme', 'dark'); });
  cek('tidak ada galat halaman/konsol', errs.length === 0, errs.slice(0, 3).join(' | '));
  await browser.close();
  const gagal = hasil.filter((x) => !x).length;
  console.log(`\n${hasil.length - gagal} lulus, ${gagal} gagal`);
  process.exit(gagal ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
