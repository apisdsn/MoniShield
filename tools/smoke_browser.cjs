// Browser smoke test (CI job "Browser smoke test"): signs in to the server of tools/smoke_server.py, changes the forced
// first password, then opens every page for both data sources (S3, Kafka) and both languages. A page fails when the
// browser throws a script error, the server answers 5xx, the page shows its error card, or it does not finish loading.
//
//   node tools/smoke_browser.cjs [base URL, default http://127.0.0.1:8777] [folder for failure screenshots]
const { chromium } = require('playwright');

const BASE = process.argv[2] || 'http://127.0.0.1:8777';
const SHOTS = process.argv[3] || '';
const PW0 = 'smoke-test-first-password', PW1 = 'Smoke-Test-Second-Password-2026!';
const PAGES = ['overview', 'command-center', 'trends', 'security', 'root-causes', 'availability', 'pods', 'business', 'tracing', 'raw-logs',
  'services/event-api', 'admin/users', 'admin/ingest', 'admin/configuration', 'admin/notifications'];
const RUNS = [{ lang: 'id', source: '' }, { lang: 'id', source: 'kafka' }, { lang: 'en', source: '' }];

(async () => {
  // software WebGL (bundled SwiftShader): the maps draw in a headless browser too, so a broken map shows up here
  const browser = await chromium.launch({ args: ['--use-gl=angle', '--use-angle=swiftshader', '--ignore-gpu-blocklist'] });
  const page = await (await browser.newContext({ viewport: { width: 1280, height: 900 } })).newPage();
  let problems = [];
  page.on('pageerror', (e) => problems.push(`script error: ${e.message}`));
  page.on('response', (r) => { if (r.status() >= 500) problems.push(`${r.status()} ${r.request().method()} ${r.url().replace(BASE, '')}`); });

  // public home page (no sign-in), on a wide screen and on a phone: renders, reads the public map, no sideways scroll
  for (const width of [1280, 360]) {
    const hp = await (await browser.newContext({ viewport: { width, height: 800 }, isMobile: width < 800, hasTouch: width < 800 })).newPage();
    const errs = [];
    hp.on('pageerror', (e) => errs.push(e.message));
    // console errors too (a map worker that fails to load is only logged). "Failed to load resource" lines are left out: server
    // errors are caught as 5xx answers above, the 401 is the page asking whether you are signed in, and CI has no map files (404)
    hp.on('console', (m) => { if (m.type() === 'error' && !/^Failed to load resource/.test(m.text())) errs.push(m.text().slice(0, 200)); });
    const mapAnswer = hp.waitForResponse((r) => r.url().endsWith('/api/public/map'));
    await hp.goto(BASE + '/');
    await hp.waitForSelector('#home-h1');
    const st = (await mapAnswer).status();
    await hp.waitForTimeout(800);
    const wide = await hp.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    // the map loads only near the screen (and not before): scroll to it, then it really draws (MapLibre loaded, WebGL canvas)
    let drawn = true;
    if (await hp.locator('#home-map').count()) {
      const early = await hp.locator('#home-map canvas').count();
      await hp.locator('#home-map').scrollIntoViewIfNeeded();
      drawn = await hp.locator('#home-map canvas').first().waitFor({ timeout: 15000 }).then(() => true, () => false);
      if (early && width >= 800) errs.push('the map loaded before it came near the screen');
    }
    // the dashboard preview tabs switch the page shown (Security, Command Center, back to Overview)
    for (const id of ['security', 'command-center', 'overview']) {
      await hp.locator(`#pv-tab-${id}`).click();
      if ((await hp.locator(`#pv-tab-${id}`).getAttribute('aria-selected')) !== 'true') errs.push(`preview tab ${id} not selected`);
    }
    if (errs.length || st !== 200 || wide > 0 || !drawn) throw new Error(`home page at ${width}px: errors ${errs.join('; ')} map ${st} overflow ${wide}px drawn ${drawn}`);
    await hp.context().close();
    console.log(`ok   home page at ${width}px`);
  }

  // robots.txt: the home page may be indexed, the dashboard and the API not
  const robots = await (await browser.newContext()).request.get(BASE + '/robots.txt');
  if (robots.status() !== 200 || !/Disallow: \/api\//.test(await robots.text())) throw new Error(`robots.txt: ${robots.status()}`);
  console.log('ok   robots.txt');

  // link preview tags of the home page, per language (?lang=, else Accept-Language), and their images
  const req = (await browser.newContext()).request;
  for (const [q, hdr, want] of [['/', 'id-ID', 'id'], ['/?lang=en', 'id-ID', 'en'], ['/', 'en-US,en;q=0.9', 'en']]) {
    const body = await (await req.get(BASE + q, { headers: { 'Accept-Language': hdr } })).text();
    if (!body.includes(`og-${want}.png`) || !body.includes(`<html lang="${want}"`)) throw new Error(`link preview of ${q} (${hdr}) is not "${want}"`);
  }
  for (const l of ['id', 'en']) {
    const img = await req.get(BASE + `/og-${l}.png`);
    if (img.status() !== 200 || img.headers()['content-type'] !== 'image/png') throw new Error(`og-${l}.png: ${img.status()}`);
  }
  console.log('ok   link preview tags (id, en) and images');

  // signed out: the sign-in page has its own address and returns to the page that was asked for
  await page.goto(BASE + '/security');
  await page.waitForSelector('#u');
  const atLogin = new URL(page.url());
  if (atLogin.pathname + atLogin.search !== '/login?next=%2Fsecurity') throw new Error(`sign-in address is ${atLogin.pathname + atLogin.search}`);
  await page.fill('#u', 'admin'); await page.fill('#p', PW0); await page.click('button[type=submit]');
  await page.waitForSelector('#pw-old');
  await page.fill('#pw-old', PW0); await page.fill('#pw-new', PW1); await page.fill('#pw-again', PW1); await page.click('button[type=submit]');
  await page.waitForSelector('#folder-select');
  if (new URL(page.url()).pathname !== '/security') throw new Error(`after sign-in the address is ${page.url()}`);
  console.log('ok   sign-in at /login?next=… returns to the page asked for');

  // the open list of a select (folder picker): a solid background and readable text in both themes (Chrome/Edge on
  // Windows draw it with the option colours; a transparent background fell back to white under light text)
  for (const th of ['dark', 'light']) {
    const bad = await page.evaluate((th) => {
      document.documentElement.dataset.theme = th;
      const rgb = (s) => (s.match(/[\d.]+/g) || []).map(Number);
      const lum = ([r, g, b]) => { const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; }; return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b); };
      const out = [];
      for (const o of document.querySelectorAll('select option:not(:disabled)')) {
        const cs = getComputedStyle(o), bg = rgb(cs.backgroundColor), fg = rgb(cs.color);
        if (bg.length === 4 && bg[3] < 1) { out.push(`${o.textContent}: transparent background`); break; }
        const [a, b] = [lum(fg), lum(bg)].sort((x, y) => y - x);
        if ((a + 0.05) / (b + 0.05) < 4.5) { out.push(`${o.textContent}: contrast ${((a + 0.05) / (b + 0.05)).toFixed(1)}`); break; }
      }
      return out;
    }, th);
    if (bad.length) throw new Error(`select list in the ${th} theme: ${bad.join('; ')}`);
  }
  await page.evaluate(() => { document.documentElement.dataset.theme = localStorage.getItem('theme') === 'light' ? 'light' : 'dark'; });
  console.log('ok   select lists readable in the dark and light themes');

  let failed = 0, checked = 0;
  for (const run of RUNS) {
    await page.evaluate((l) => localStorage.setItem('lang', l), run.lang);
    for (const p of PAGES) {
      const url = `/${p}${run.source ? `?source=${run.source}` : ''}`;
      problems = [];
      try {
        await page.goto(BASE + url);
        await page.waitForSelector('main#main[aria-busy="false"]', { timeout: 20000 });
        await page.waitForTimeout(800);   // late requests of the page (cards, charts)
        if (await page.locator('main [role=alert].box').count()) problems.push(`error card: ${(await page.locator('main [role=alert].box').first().innerText()).replace(/\s+/g, ' ')}`);
        const picked = await page.evaluate(() => document.querySelector('[role=radio][data-v][aria-checked=true]')?.dataset.v ?? null);
        if (picked !== null && picked !== (run.source || 's3')) problems.push(`source switch shows the wrong source: ${picked}`);
        // folder-wide volume band: on folder pages, never on a service page (its own numbers would contradict it)
        const band = await page.locator('section.vb').count();
        if (p.startsWith('services/') && band) problems.push('volume band shown on a service page');
      } catch (e) { problems.push(`did not load: ${e.message.split('\n')[0]}`); }
      checked++;
      const tag = `${run.lang} ${url}`;
      if (problems.length) {
        failed++;
        console.log(`FAIL ${tag}\n  ${problems.join('\n  ')}`);
        if (SHOTS) await page.screenshot({ path: `${SHOTS}/${run.lang}-${(run.source || 's3')}-${p.replace(/\//g, '_')}.png`, fullPage: true }).catch(() => {});
      } else console.log(`ok   ${tag}`);
    }
  }
  await browser.close();
  console.log(`${checked - failed}/${checked} pages ok`);
  process.exit(failed ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(1); });
