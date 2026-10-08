// Stage 20 verification (IP map + collapsed map on service pages) in Chromium (software WebGL), side by side with the old
// ../dashboard.html for KPIs and the flow table.   node tools/uji_tahap20.cjs http://127.0.0.1:8000 <admin-password>
// EXPECTED differences: locations/countries/"dari luar Indonesia" differ from old because IP location is now MaxMind GeoLite2
// (old used DB-IP; Stage 7 plan item i); source IPs, modules, pods and total requests must match.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const path = require('path');
const fs = require('fs');
const [, , BASE = 'http://127.0.0.1:8000', PW] = process.argv;
const LAMA = 'file://' + path.resolve(__dirname, '..', '..', 'dashboard.html');
const OUT = process.env.SHOTS_DIR || path.join(require('os').tmpdir(), 's4-shots');
fs.mkdirSync(OUT, { recursive: true });
const hasil = [];
const cek = (n, ok, info = '') => { hasil.push(!!ok); console.log(`${ok ? 'PASS' : 'FAIL'}  ${n}${info ? '  — ' + info : ''}`); };
const bil = (s) => +String(s ?? '').replace(/[^\d-]/g, '') || 0;
const norm = (s) => String(s).toLowerCase().replace(/\s+/g, ' ').trim();
const ipOf = (s) => (String(s).match(/\d{1,3}(?:\.\d{1,3}){3}|[0-9a-f:]{6,}/i) || [''])[0];
const CHART_STUB = `(() => { const deep = () => new Proxy({}, { get: (t, k) => (k in t ? t[k] : (t[k] = deep())), set: (t, k, v) => ((t[k] = v), true) });
  window.Chart = class { constructor() {} destroy() {} }; window.Chart.defaults = deep(); })();`;

const M = (p) => p.evaluate(() => { const m = document.querySelector('.mapwrap .map').__map; const c = m.getCenter(); return { lng: c.lng, lat: c.lat, zoom: m.getZoom() }; });
const siapPeta = (p) => p.waitForFunction(() => { const m = document.querySelector('.mapwrap .map')?.__map; return m && m.isStyleLoaded() && m.loaded() && !m.isMoving(); }, null, { timeout: 30000 })
  .then(() => p.waitForTimeout(400));
const fitur = (p, layers) => p.evaluate((ls) => { const m = document.querySelector('.mapwrap .map').__map;
  return Object.fromEntries(ls.map((l) => [l, m.queryRenderedFeatures({ layers: [l] }).length])); }, layers);
const sama = (a, b) => Math.abs(a.lng - b.lng) < 1e-6 && Math.abs(a.lat - b.lat) < 1e-6 && Math.abs(a.zoom - b.zoom) < 1e-6;

(async () => {
  const browser = await chromium.launch({ ...(process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {}), args: ['--enable-unsafe-swiftshader'] });
  // flow animation paused in every context: the particle source updates every frame so map.loaded() is never true
  // (the animation is tested separately: tools/uji_animasi_peta.cjs)
  const newCtx = browser.newContext.bind(browser);
  browser.newContext = async (o) => { const c = await newCtx(o); await c.addInitScript(() => { try { localStorage.setItem('map_anim', '0'); } catch {} }); return c; };
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const p = await ctx.newPage();
  const errs = [], luar = [];
  p.on('pageerror', (e) => errs.push(e.message));
  p.on('console', (m) => m.type() === 'error' && !/status of 40[134]/.test(m.text()) && errs.push(m.text()));
  p.on('request', (r) => { const u = r.url(); if (!u.startsWith(BASE) && !u.startsWith('blob:' + BASE) && !u.startsWith('data:')) luar.push(u); });
  await p.goto(BASE + '/#/peta?folder=2026-10-06');
  await p.fill('#u', 'admin'); await p.fill('#p', PW); await p.click('button[type=submit]');
  await p.waitForSelector('main .kpi'); await siapPeta(p);
  const api = (u) => p.evaluate((u) => fetch(u).then((r) => r.json()), u);

  // ------------------------------------------------------------------ KPIs + sentence + server point + labels, side by side with old
  const kb = await p.$$eval('main .mapstats div', (e) => e.map((x) => [x.querySelector('dt').textContent.trim(), x.querySelector('dd').textContent.trim()]));   // Stage 22: map numbers in the Command Center summary
  const lctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  await lctx.route(/^https?:\/\//, (r) => r.abort()); await lctx.addInitScript(CHART_STUB);
  const lp = await lctx.newPage(); await lp.goto(LAMA);
  await lp.evaluate(() => { day = '2026-10-06'; tab = 'peta'; render(); });
  const kl = await lp.$$eval('.kpi', (e) => e.map((x) => [x.querySelector('.l').textContent.trim(), x.querySelector('.v').textContent.trim()]));
  const kalimat = await p.textContent('main .legend');
  const kalLama = await lp.textContent('.maplg');
  const harap = [516, 166, 9, 9, 15, 124822];
  cek('06 Oct: 6 KPIs = 516 IPs · 166 locations · 9 countries · 9 modules · 15 pods · 124,822 requests; labels same as old',
    kb.length === 6 && kb.every(([, v], i) => bil(v) === harap[i]) && kl.every(([l], i) => norm(l) === norm(kb[i][0])), kb.map(([, v]) => v).join(' · '));
  cek('06 Oct: source IPs, modules, pods, total requests SAME as old; locations/countries differ due to MaxMind vs DB-IP (expected)',
    [0, 3, 4, 5].every((i) => bil(kl[i][1]) === bil(kb[i][1])), `old ${kl.map(([, v]) => v).join(' · ')}`);
  cek('sentence "N request dari luar Indonesia · 0 request dari IP internal / tanpa lokasi"', /1\.293 request dari luar Indonesia · 0 request dari IP internal/.test(kalimat),
    `${kalimat.replace(/\s+/g, ' ').slice(-110)} | old: ${kalLama.replace(/\s+/g, ' ').slice(-100)}`);
  const srv = await p.evaluate(() => { const m = document.querySelector('.mapwrap .map').__map; const f = m.queryRenderedFeatures({ layers: ['server'] }); return f.map((x) => x.geometry.coordinates); });
  const f0 = await fitur(p, ['lbl-top', 'lbl-srv', 'points', 'clusters', 'arcs', 'land', 'lbl-country']);
  await p.evaluate(() => document.querySelector('.mapwrap .map').__map.jumpTo({ center: [106.6, -6.4], zoom: 8 })); await siapPeta(p);
  const atas = await p.evaluate(() => [...new Set(document.querySelector('.mapwrap .map').__map.queryRenderedFeatures({ layers: ['lbl-top'] }).map((f) => f.properties.name))]);
  await p.evaluate(() => document.querySelector('.mapwrap .map').__map.fitBounds([[94, -12], [142, 8]], { padding: 12, duration: 0 })); await siapPeta(p);
  // ASSUMPTION: the 6 largest labels follow collision rules; an overlapping one (Serang, ±15 px from Jakarta + server label) appears when zoomed in
  cek('server point in Jakarta (labelled); ≥ 5 largest location labels in the Indonesia view without overlap, 6th label (Serang) appears when zoomed in; land, arcs, points, country labels',
    srv.length === 1 && Math.abs(srv[0][1] + 6.175) < 0.01 && Math.abs(srv[0][0] - 106.83) < 0.01 && f0['lbl-srv'] === 1 && f0['lbl-top'] >= 5 && atas.includes('Serang')
    && f0.land > 0 && f0.arcs > 0 && f0.points + f0.clusters > 0 && f0['lbl-country'] > 0, `${JSON.stringify(f0)}; zoom 8 around Jakarta: ${atas.join(', ')}`);
  // flow table: the first 100 v2 rows are all in the old table (IP, module, requests)
  const tl = await lp.$$eval('#main .card', (cs) => { const c = cs.find((x) => /Alur IP Asal/i.test(x.querySelector('h3')?.textContent || '') && x.querySelector('table'));
    return c ? [...c.querySelectorAll('tr')].filter((r) => r.querySelector('td')).map((r) => [...r.cells].map((td) => td.innerText)) : []; });
  const tb = await p.$$eval('main section.card', (cs) => { const c = cs.find((x) => /Alur IP asal/i.test(x.querySelector('h2')?.textContent || '') && x.querySelector('table'));
    return c ? [...c.querySelectorAll('tbody tr')].map((r) => [...r.cells].map((td) => td.innerText)) : []; });
  const K = (r) => `${ipOf(r[0])}|${norm(r[2])}|${bil(r[4])}`;
  const L = new Set(tl.map(K)), hilang = tb.map(K).filter((x) => !L.has(x));
  const foot = await p.textContent('main section.card:has(table) .foot').catch(() => '');
  cek(`flow table: first ${tb.length} v2 rows all present in the old table (${tl.length} rows); "Menampilkan 100 dari N"`, tb.length === 100 && !hilang.length && /Menampilkan 100 dari/.test(foot),
    hilang.slice(0, 2).join(' ;; ') || foot.replace(/\s+/g, ' ').trim());
  await lctx.close();
  await p.screenshot({ path: `${OUT}/t20-peta-1440.png`, fullPage: true });

  // ------------------------------------------------------------------ change module: KPIs, points, table change; position and zoom kept
  await p.evaluate(() => document.querySelector('.mapwrap .map').__map.jumpTo({ center: [110, -6], zoom: 5 }));
  await siapPeta(p);
  const m0 = await M(p);
  await p.selectOption('#map-mod', 'om-be-simpel-loop');
  await p.waitForFunction(() => /modul=om-be-simpel-loop/.test(location.hash));
  await p.waitForLoadState('networkidle'); await siapPeta(p);
  const m1 = await M(p);
  const d1 = await api('/api/folders/2026-10-06/map?module=om-be-simpel-loop');
  const kb1 = await p.$$eval('main .mapstats dd', (e) => e.map((x) => x.textContent.trim()));
  const modTabel = await p.$$eval('main section.card:has(table) tbody tr', (rs) => [...new Set(rs.map((r) => r.cells[2]?.innerText.trim()))]);
  const nTitik = await p.evaluate(() => { const m = document.querySelector('.mapwrap .map').__map; return m.querySourceFeatures('loc').filter((f) => !f.properties.cluster).length; });
  cek('select module om-be-simpel-loop: KPIs, table (that module only) and point data change; map position and zoom kept',
    bil(kb1[5]) === d1.kpi.requests && d1.kpi.requests < 124822 && modTabel.length === 1 && modTabel[0] === 'om-be-simpel-loop' && sama(m0, m1),
    `requests ${kb1[5]}, table module ${modTabel}, camera ${JSON.stringify(m0)} -> ${JSON.stringify(m1)}, points read ${nTitik}`);
  await p.selectOption('#map-mod', ''); await p.waitForLoadState('networkidle'); await siapPeta(p);

  // ------------------------------------------------------------------ mouse wheel: page scrolls + hint; Ctrl + wheel zooms
  const box = await p.$eval('.mapwrap', (e) => { e.scrollIntoView({ block: 'center' }); const r = e.getBoundingClientRect(); return { x: r.x + r.width / 2, y: r.y + r.height / 2 }; });
  await p.waitForTimeout(300);
  const yA = await p.evaluate(() => scrollY), zA = (await M(p)).zoom;
  await p.evaluate(() => { window.__coop = null; document.querySelector('.mapwrap .map').__map.once('cooperativegestureprevented', (e) => (window.__coop = e.gestureType)); });
  await p.mouse.move(box.x, box.y); await p.mouse.wheel(0, 300); await p.waitForTimeout(500);
  const pet = await p.evaluate(() => [window.__coop === 'wheel_zoom', document.querySelector('.maplibregl-cooperative-gesture-screen')?.textContent]);
  const yB = await p.evaluate(() => scrollY), zB = (await M(p)).zoom;
  // the page has scrolled 300 px: the map's center point may be covered by the sticky page header, so the wheel
  // lands on the header, not the map. Bring the map back into view and make sure the target point is the map canvas.
  const box2 = await p.$eval('.mapwrap', (e) => { e.scrollIntoView({ block: 'center' }); const r = e.getBoundingClientRect(); return { x: r.x + r.width / 2, y: r.y + r.height / 2 }; });
  await p.waitForTimeout(300);
  const diPeta = await p.evaluate(({ x, y }) => document.elementFromPoint(x, y)?.closest('.mapwrap .map') != null, box2);
  await p.mouse.move(box2.x, box2.y); await p.keyboard.down('Control'); await p.mouse.wheel(0, -400); await p.keyboard.up('Control'); await p.waitForTimeout(900);
  const zC = (await M(p)).zoom;
  cek('mouse wheel over the map: page scrolls, map stays, hint "Tahan Ctrl…"; Ctrl + wheel zooms', yB > yA && Math.abs(zB - zA) < 1e-6 && pet[0] && /Tahan Ctrl/.test(pet[1]) && diPeta && zC > zB + 0.2,
    `scroll ${yA}->${yB}, zoom ${zA.toFixed(2)} -> ${zB.toFixed(2)} -> Ctrl ${zC.toFixed(2)}${diPeta ? "" : " (target point is not the map canvas)"}`);

  // ------------------------------------------------------------------ zoom smoothness: frame-to-frame time during the zoom animation (info)
  const fps = await p.evaluate(async () => { const m = document.querySelector('.mapwrap .map').__map; const t = [];
    let on = true; const f = (x) => { t.push(x); if (on) requestAnimationFrame(f); }; requestAnimationFrame(f);
    await new Promise((r) => { m.once('moveend', r); m.zoomTo(m.getZoom() + 2, { duration: 1200 }); });
    await new Promise((r) => { m.once('moveend', r); m.zoomTo(m.getZoom() - 2, { duration: 1200 }); });
    on = false; const d = t.slice(1).map((x, i) => x - t[i]).sort((a, b) => a - b);
    return { n: d.length, median: d[d.length >> 1], p95: d[Math.floor(d.length * 0.95)] }; });
  console.log(`  info  zoom animation (2 × 1.2 s): ${fps.n} frames, median ${fps.median.toFixed(1)} ms, p95 ${fps.p95.toFixed(1)} ms (software WebGL, no GPU)`);

  // ------------------------------------------------------------------ keyboard
  await p.click('main .fm .seg button:has-text("Indonesia")');
  await p.evaluate(() => document.querySelector('.mapwrap .map').__map.fitBounds([[94, -12], [142, 8]], { padding: 12, duration: 0 })); await siapPeta(p);
  const kAwal = await M(p);
  await p.focus('.mapwrap canvas');
  await p.keyboard.press('ArrowRight'); await p.waitForTimeout(600);
  const kKanan = await M(p);
  await p.keyboard.press('Equal'); await p.waitForTimeout(700);   // '=' / '+' zooms in (MapLibre keyboard handler)
  const kPlus = await M(p);
  await p.keyboard.press('Digit0'); await p.waitForTimeout(800);
  const kNol = await M(p);
  cek('keyboard: arrows pan, + zooms in, 0 returns to the preset', kKanan.lng > kAwal.lng + 0.5 && kPlus.zoom > kKanan.zoom + 0.5 && Math.abs(kNol.zoom - kAwal.zoom) < 0.05 && Math.abs(kNol.lng - kAwal.lng) < 0.5,
    `${kAwal.lng.toFixed(1)}→${kKanan.lng.toFixed(1)}; zoom ${kKanan.zoom.toFixed(2)}→${kPlus.zoom.toFixed(2)}→${kNol.zoom.toFixed(2)}`);

  // ------------------------------------------------------------------ click a point -> tooltip -> "Lihat di tabel"; Esc closes
  await p.evaluate(() => document.querySelector('.mapwrap .map').__map.jumpTo({ center: [110.4, -7.0], zoom: 9 })); await siapPeta(p);
  const titik = await p.evaluate(() => { const m = document.querySelector('.mapwrap .map').__map; const f = m.queryRenderedFeatures({ layers: ['points'] })
    .sort((a, b) => b.properties.requests - a.properties.requests)[0]; if (!f) return null; const q = m.project(f.geometry.coordinates); const r = m.getCanvas().getBoundingClientRect();
    return { x: r.x + q.x, y: r.y + q.y, name: f.properties.name }; });
  let tipOk = false, filt = '', baris = [];
  if (titik) {
    await p.mouse.click(titik.x, titik.y); await p.waitForSelector('.mapwrap .tip', { timeout: 5000 }).catch(() => {});
    const tipText = await p.textContent('.mapwrap .tip').catch(() => '');
    tipOk = /IP asal · .* request/.test(tipText) && /→/.test(tipText);
    await p.focus('.mapwrap canvas'); await p.keyboard.press('Escape'); await p.waitForTimeout(200);
    const tutup = !(await p.$('.mapwrap .tip'));
    await p.mouse.click(titik.x, titik.y); await p.waitForSelector('.mapwrap .tip button');
    await p.click('.mapwrap .tip button:has-text("Lihat di tabel")');
    await p.waitForTimeout(800); await p.waitForLoadState('networkidle');
    filt = await p.inputValue('main section.card:has(table) input[data-filter]');
    baris = await p.$$eval('main section.card:has(table) tbody tr', (rs) => rs.map((r) => r.cells[1]?.innerText || ''));
    cek(`click point "${titik.name}": tooltip (location · IP · requests → module); Esc closes; "Lihat di tabel" fills the flow table filter`,
      tipOk && tutup && filt === titik.name && baris.length > 0 && baris.every((b) => b.includes(titik.name)), `filter "${filt}", ${baris.length} rows`);
  } else cek('click point -> tooltip -> Lihat di tabel', false, 'no points in Central Java at zoom 9');

  // ------------------------------------------------------------------ World -> Java: clusters split, labels in stages
  await p.click('main .fm .seg button:has-text("Dunia")'); await p.waitForTimeout(800); await siapPeta(p);
  const fw = await fitur(p, ['clusters', 'points', 'lbl-country', 'lbl-prov', 'lbl-kab']);
  const zw = (await M(p)).zoom;
  const tahap = [];
  for (const z of [4.5, 6, 8.2]) {
    await p.evaluate((z) => document.querySelector('.mapwrap .map').__map.jumpTo({ center: [110.5, -7.2], zoom: z }), z); await siapPeta(p);
    tahap.push([z, await fitur(p, ['clusters', 'points', 'lbl-country', 'lbl-prov', 'lbl-kab'])]);
  }
  const [, z45] = tahap[0], [, z8] = tahap[2];
  cek('World -> Java: clusters in the world view split into points at zoom 8; labels country -> province (zoom ≥ 4) -> regency (zoom ≥ 7)',
    fw.clusters > 0 && fw['lbl-prov'] === 0 && fw['lbl-kab'] === 0 && fw['lbl-country'] > 0 && z45['lbl-prov'] > 0 && z45['lbl-kab'] === 0 && z8.clusters === 0 && z8.points > 0 && z8['lbl-kab'] > 0,
    `world z${zw.toFixed(1)} ${JSON.stringify(fw)} | ${tahap.map(([z, f]) => `z${z} ${JSON.stringify(f)}`).join(' | ')}`);
  // labels do not overlap: drawn text boxes do not cover each other (the map engine handles collisions)
  const tumpuk = await p.evaluate(() => { const m = document.querySelector('.mapwrap .map').__map;
    const ids = ['lbl-kab', 'lbl-prov', 'lbl-country', 'lbl-country-small', 'lbl-loc', 'lbl-top'];
    const fs = m.queryRenderedFeatures({ layers: ids });
    return { n: fs.length, layers: [...new Set(fs.map((f) => f.layer.id))] }; });
  cek('regency/province/location labels shown together at zoom 8 (collisions handled by the map engine)', tumpuk.n > 3, JSON.stringify(tumpuk));
  await p.screenshot({ path: `${OUT}/t20-jawa-z8.png` });

  // ------------------------------------------------------------------ theme + language: colors and country names change, position kept, attribution visible
  await p.evaluate(() => document.querySelector('.mapwrap .map').__map.jumpTo({ center: [118, -2], zoom: 4 })); await siapPeta(p);
  const t0 = await M(p);
  await p.click('button[aria-label="Tema terang"]');
  await p.waitForTimeout(600);
  const warna = await p.evaluate(() => { const m = document.querySelector('.mapwrap .map').__map; return [m.getPaintProperty('sea', 'background-color'),
    getComputedStyle(document.documentElement).getPropertyValue('--card2').trim(), document.documentElement.dataset.theme]; });
  await p.click('button:has-text("EN")'); await p.waitForTimeout(600);
  const tf = await p.evaluate(() => document.querySelector('.mapwrap .map').__map.getLayoutProperty('lbl-country', 'text-field'));
  const t1 = await M(p);
  const attr = await p.$eval('.mapwrap .attr', (a) => { const r = a.getBoundingClientRect(), w = a.closest('.mapwrap').getBoundingClientRect();
    return [a.textContent.trim(), r.width > 0 && r.right <= w.right + 1 && r.bottom <= w.bottom + 1, [...a.querySelectorAll('a')].map((x) => [x.href, x.rel, x.target])]; });
  cek('change theme (light) and language (EN): sea color = theme token, EN country names, position/zoom kept; MaxMind · GeoNames · Natural Earth attribution visible',
    warna[2] === 'light' && warna[0] === warna[1] && JSON.stringify(tf) === JSON.stringify(['get', 'en']) && sama(t0, t1) && /MaxMind · GeoNames · Natural Earth/.test(attr[0]) && attr[1]
    && attr[2].every(([, rel, tg]) => rel === 'noreferrer' && tg === '_blank'), `${warna[0]} | ${JSON.stringify(tf)} | ${attr[0]}`);
  await p.click('button:has-text("ID")'); await p.click('button[aria-label="Dark theme"], button[aria-label="Tema gelap"]').catch(() => {});

  // ------------------------------------------------------------------ no internet: map, labels, points still shown
  const octx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const luar2 = [];
  await octx.route((u) => !u.href.startsWith(BASE), (r) => { luar2.push(r.request().url()); r.abort(); });
  const op = await octx.newPage();
  await op.goto(BASE + '/#/peta?folder=2026-10-06'); await op.fill('#u', 'admin'); await op.fill('#p', PW); await op.click('button[type=submit]');
  await op.waitForSelector('main .kpi'); await siapPeta(op);
  const fo = await fitur(op, ['land', 'points', 'clusters', 'lbl-country', 'lbl-top', 'server']);
  cek('internet cut (only the dashboard server reachable): map, labels and points still shown', fo.land > 0 && fo['lbl-country'] > 0 && fo['lbl-top'] > 0 && fo.server === 1 && fo.points + fo.clusters > 0 && !luar2.filter((u) => !u.startsWith('blob:')).length,
    JSON.stringify(fo) + (luar2.length ? ' | blocked: ' + luar2.slice(0, 2).join(', ') : ''));
  await octx.close();

  // ------------------------------------------------------------------ 28 Sep (no nginx)
  await p.goto(`${BASE}/#/peta?folder=2026-09-28`); await p.waitForSelector('main .note'); await p.waitForTimeout(300);
  cek('28 Sep: note "Peta butuh log ingress nginx…"', /Peta butuh log ingress nginx/.test(await p.textContent('main')));

  // ------------------------------------------------------------------ service page: map collapsed, opened -> only that module's flows
  await p.goto(`${BASE}/#/layanan/om-be-simpel-loop?folder=2026-10-06`); await p.waitForSelector('main details.sm', { timeout: 15000 });
  const tertutup = !(await p.$('main .mapwrap')) && !(await p.$eval('main details.sm', (d) => d.open));
  await p.click('main details.sm summary'); await siapPeta(p);
  const modS = await p.$$eval('main section.card:has(table) tbody tr', (rs) => { const t = rs[0]?.closest('section.card'); return /Alur IP asal/i.test(t?.querySelector('h2')?.textContent || '') ? [...new Set(rs.map((r) => r.cells[2]?.innerText.trim()))] : null; })
    .catch(() => null);
  const modS2 = await p.$$eval('main section.card', (cs) => { const c = cs.find((x) => /Alur IP asal/i.test(x.querySelector('h2')?.textContent || '') && x.querySelector('table'));
    return c ? [...new Set([...c.querySelectorAll('tbody tr')].map((r) => r.cells[2]?.innerText.trim()))] : []; });
  cek('service page om-be-simpel-loop: map collapsed; opened -> map drawn, flow table only that module', tertutup && !!(await p.$('main .mapwrap canvas')) && modS2.length === 1 && modS2[0] === 'om-be-simpel-loop',
    JSON.stringify(modS2 || modS));
  await p.screenshot({ path: `${OUT}/t20-layanan-peta.png`, fullPage: true });

  // ------------------------------------------------------------------ 390 px with touch: 4:3, 44 px controls, one finger does not pan, two fingers pan
  const mctx = await browser.newContext({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true, deviceScaleFactor: 2 });
  const mp = await mctx.newPage();
  mp.on('pageerror', (e) => errs.push(e.message));
  await mp.goto(BASE + '/#/peta?folder=2026-10-06'); await mp.fill('#u', 'admin'); await mp.fill('#p', PW); await mp.click('button[type=submit]');
  await mp.waitForSelector('main .kpi'); await siapPeta(mp);
  const ukur = await mp.$eval('.mapwrap', (e) => { const r = e.getBoundingClientRect(); e.scrollIntoView({ block: 'center' });
    return [r.width, r.height, getComputedStyle(e.querySelector('.mb')).width, getComputedStyle(e.querySelector('.maplibregl-canvas-container')).touchAction, document.documentElement.scrollWidth]; });
  await mp.waitForTimeout(300);
  const cdp = await mctx.newCDPSession(mp);
  const r = await mp.$eval('.mapwrap', (e) => { const b = e.getBoundingClientRect(); return { x: b.x + b.width / 2, y: b.y + b.height / 2 }; });
  const geser = async (a, b) => {
    await cdp.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: a.map(([x, y], i) => ({ x, y, id: i })) });
    for (let s = 1; s <= 12; s++) await cdp.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: a.map(([x, y], i) => ({ x: x + (b[i][0] - x) * s / 12, y: y + (b[i][1] - y) * s / 12, id: i })) });
    await cdp.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] }); await mp.waitForTimeout(700);
  };
  const s0 = await M(mp);
  await geser([[r.x, r.y]], [[r.x + 90, r.y]]);
  const s1 = await M(mp);
  await geser([[r.x - 30, r.y], [r.x + 30, r.y]], [[r.x + 60, r.y], [r.x + 120, r.y]]);
  const s2 = await M(mp);
  cek('390 px touch: Command Center map as tall as the screen (100dvh − 220 px, min. 360 px; Stage 22), 44 px buttons, 44 px buttons, one finger does not pan the map, two fingers pan; no horizontal scroll',
    Math.abs(ukur[1] - Math.max(844 - 220, 360)) < 2 && ukur[2] === '44px' && /pan-x pan-y/.test(ukur[3]) && sama(s0, s1) && Math.abs(s2.lng - s1.lng) > 0.3 && ukur[4] <= 390,
    `${Math.round(ukur[0])}×${Math.round(ukur[1])}, buttons ${ukur[2]}, touch-action ${ukur[3]}, lng ${s0.lng.toFixed(2)}/${s1.lng.toFixed(2)}/${s2.lng.toFixed(2)}`);
  await mp.screenshot({ path: `${OUT}/t20-peta-390.png`, fullPage: true });
  await mctx.close();

  // ------------------------------------------------------------------ 2 languages × 2 themes × 2 widths
  for (const lang of ['id', 'en']) for (const theme of ['dark', 'light']) for (const w of [1440, 390]) {
    await p.setViewportSize({ width: w, height: 900 });
    await p.evaluate(([l, th]) => { localStorage.setItem('lang', l); localStorage.setItem('theme', th); }, [lang, theme]);
    await p.goto(`${BASE}/#/peta?folder=2026-10-06`); await p.reload(); await p.waitForSelector('main .kpi'); await siapPeta(p);
    const st = await p.evaluate(() => [document.documentElement.scrollWidth, innerWidth, document.documentElement.lang, document.documentElement.dataset.theme,
      [...document.querySelectorAll('main h2, main .kpi .l, main .mapstats dt, main .legend, main th, main .note')].map((x) => x.textContent.trim()).join(' | ')]);
    const sisa = lang === 'en' ? (st[4].match(/\b(Peta|Lokasi|Negara|Modul|asal|tujuan|dari luar|Jaringan|perkiraan)\b/g) || []) : [];
    cek(`map ${lang}/${theme}/${w}px: no horizontal scroll, text in the right language`, st[0] <= st[1] && st[2] === lang && st[3] === theme && !sisa.length,
      `width ${st[0]}/${st[1]}${sisa.length ? ', still ID: ' + sisa.slice(0, 4).join(', ') : ''}`);
    await p.screenshot({ path: `${OUT}/t20-${lang}-${theme}-${w}.png`, fullPage: w === 1440 });
  }
  await p.evaluate(() => { localStorage.setItem('lang', 'id'); localStorage.setItem('theme', 'dark'); });
  cek('all requests to the same origin (0 to other domains)', luar.length === 0, luar.slice(0, 3).join(' | '));
  cek('no page/console errors', errs.length === 0, errs.slice(0, 3).join(' | '));
  await browser.close();
  const gagal = hasil.filter((x) => !x).length;
  console.log(`\n${hasil.length - gagal} passed, ${gagal} failed`);
  process.exit(gagal ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
