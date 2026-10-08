// Map flow animation (owner request 2026-10-07; web/src/lib/mapFlow.js) in Chromium (software WebGL):
// particles move toward the server, ripple on arrival, pause/play remembered, live mode + monishield:map-pulse event (Kafka
// preparation), stops when not visible, cost per frame, prefers-reduced-motion.
//   node tools/uji_animasi_peta.cjs http://127.0.0.1:8000 <admin-password>   (password already changed; folder with map data)
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const fs = require('fs');
const [, , B = 'http://127.0.0.1:8000', PW] = process.argv;
const OUT = process.env.SHOTS_DIR || require('os').tmpdir(); const r = [];
const cek = (n, ok, i = '') => { r.push(!!ok); console.log(`${ok ? 'PASS' : 'FAIL'}  ${n}${i ? '  — ' + i : ''}`); };
const heads = (p) => p.evaluate(() => { const m = document.querySelector('.map').__map; return m.queryRenderedFeatures({ layers: ['flow-head'] }).length; });
const ripples = (p) => p.evaluate(() => document.querySelector('.map').__map.queryRenderedFeatures({ layers: ['flow-ripple'] }).length);
(async () => {
  const b = await chromium.launch({ ...(process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {}), args: ['--use-gl=swiftshader', '--enable-unsafe-swiftshader'] });
  const ctx = await b.newContext({ viewport: { width: 1440, height: 1000 } });
  const p = await ctx.newPage();
  const errs = []; p.on('pageerror', (e) => errs.push(e.message)); p.on('console', (m) => m.type() === 'error' && !/40[0139]/.test(m.text()) && errs.push(m.text()));
  await p.goto(B + '/#/peta');
  await p.fill('#u', 'admin'); await p.fill('#p', PW); await p.click('button[type=submit]');
  await p.waitForFunction(() => document.querySelector('.map')?.__flow, null, { timeout: 30000 });
  await p.waitForTimeout(2500);
  const info = await p.evaluate(() => { const m = document.querySelector('.map').__map, f = document.querySelector('.map').__flow;
    return { arcs: f.arcs.length, grad: !!m.getPaintProperty('arcs', 'line-gradient'), layers: ['flow-tail', 'flow-head', 'flow-ripple'].every((id) => m.getLayer(id)) }; });
  cek('flow layers + direction-gradient arcs', info.layers && info.grad, `${info.arcs} arcs`);
  const h1 = await heads(p);
  cek('particles moving on the map', h1 > 0, `${h1} particles`);
  // particle position changes over time and heads toward the server
  const moves = await p.evaluate(async () => {
    const f = document.querySelector('.map').__flow;
    const one = f.parts.find((x) => { const s = (performance.now() - x.t0) / x.dur; return s >= 0 && s < 0.4 && x.dur > 1500; });
    if (!one) return null;
    const d = (s) => { const u = 1 - s, a = one.a; return Math.hypot(u * u * a.x0 + 2 * u * s * a.cx + s * s * a.x1 - a.x1, u * u * a.y0 + 2 * u * s * a.cy + s * s * a.y1 - a.y1); };
    const s1 = (performance.now() - one.t0) / one.dur; await new Promise((ok) => setTimeout(ok, 500));
    const s2 = (performance.now() - one.t0) / one.dur;
    return { s1, s2, closer: d(Math.min(1, s2)) < d(s1) };
  });
  cek('particle advances toward the destination IP (server)', moves && moves.s2 > moves.s1 && moves.closer, JSON.stringify(moves));
  await p.waitForTimeout(1500);
  let rp = 0; for (let k = 0; k < 15 && !rp; k++) { rp = await ripples(p); if (!rp) await p.waitForTimeout(200); }
  cek('ripple at the server point when a particle arrives', rp > 0);
  await p.screenshot({ path: OUT + '/anim-dark.png' });
  // pause
  const btn = 'button[aria-label^="Jeda animasi"]';
  cek('pause button present (aria-pressed=true)', (await p.getAttribute(btn, 'aria-pressed')) === 'true');
  await p.click(btn); await p.waitForTimeout(400);
  cek('paused: no particles', (await heads(p)) === 0 && (await p.evaluate(() => localStorage.getItem('map_anim'))) === '0');
  await p.reload(); await p.waitForFunction(() => document.querySelector('.map')?.__flow, null, { timeout: 30000 }); await p.waitForTimeout(1500);
  cek('pause remembered after reload', (await heads(p)) === 0 && (await p.getAttribute('button[aria-label^="Putar animasi"]', 'aria-pressed')) === 'false');
  await p.click('button[aria-label^="Putar animasi"]'); await p.waitForTimeout(1500);
  cek('playing again: particles return', (await heads(p)) > 0);
  // live mode + pulse (Kafka preparation)
  await p.evaluate(() => document.querySelector('.map').__flow.setLive(true));
  await p.waitForTimeout(3600);
  cek('live mode: ambient particles stop', (await heads(p)) === 0);
  await p.evaluate(() => window.dispatchEvent(new CustomEvent('monishield:map-pulse', { detail: { lat: -7.25, lon: 112.75, n: 3 } })));
  await p.waitForTimeout(350);
  const hp = await heads(p);
  cek('monishield:map-pulse event -> particles from that location', hp > 0, `${hp} particles`);
  const london = await p.evaluate(() => document.querySelector('.map').__flow.pulse({ lat: 51.5, lon: -0.12, n: 1 }));
  cek('pulse from a new location (temporary arc)', london === true);
  await p.waitForTimeout(3600);
  cek('after arrival: empty again (no motion without events)', (await heads(p)) === 0);
  await p.evaluate(() => document.querySelector('.map').__flow.setLive(false));
  // light theme
  await p.evaluate(() => localStorage.setItem('theme', 'light')); await p.reload();
  await p.waitForFunction(() => document.querySelector('.map')?.__flow, null, { timeout: 30000 }); await p.waitForTimeout(2500);
  cek('light theme: particles still shown', (await heads(p)) > 0);
  await p.screenshot({ path: OUT + '/anim-light.png' });
  // not visible (scrolled away) -> stops drawing
  const stopped = await p.evaluate(async () => {
    const f = document.querySelector('.map').__flow; f.visible = false; await new Promise((ok) => setTimeout(ok, 300)); const a = f.raf; f.visible = true; f._kick(); return a === 0;
  });
  cek('stops while the map is not visible', stopped);
  // cost: average time per animation frame
  const cost = await p.evaluate(async () => {
    const f = document.querySelector('.map').__flow, orig = f._frame.bind(f); let n = 0, t = 0;
    f._frame = (now) => { const s = performance.now(); orig(now); t += performance.now() - s; n++; };
    await new Promise((ok) => setTimeout(ok, 2000)); f._frame = orig; return { n, avg: t / Math.max(1, n), parts: f.parts.length };
  });
  cek('small JS cost per frame (< 4 ms)', cost.avg < 4, `${cost.avg.toFixed(2)} ms, ${cost.n} frames/2 s, ${cost.parts} particles`);
  cek('no JS errors', errs.length === 0, errs.slice(0, 3).join(' | '));
  // reduced motion (system) with no saved choice -> paused by default
  const ctx2 = await b.newContext({ viewport: { width: 1200, height: 900 }, reducedMotion: 'reduce', storageState: await ctx.storageState() });
  const q = await ctx2.newPage();
  await q.evaluate(() => 0).catch(() => {});
  await q.goto(B + '/#/peta'); await q.evaluate(() => localStorage.removeItem('map_anim')); await q.reload();
  await q.waitForFunction(() => document.querySelector('.map')?.__flow, null, { timeout: 30000 }); await q.waitForTimeout(1500);
  cek('prefers-reduced-motion: paused by default, gradient arcs kept', (await heads(q)) === 0 && (await q.getAttribute('button[aria-label^="Putar animasi"]', 'aria-pressed')) === 'false');
  await b.close();
  console.log(`${r.filter(Boolean).length}/${r.length} passed`);
  process.exit(r.every(Boolean) ? 0 : 1);
})().catch((e) => { console.error(e); process.exit(2); });
