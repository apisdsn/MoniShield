// Browser smoke test (CI job "Browser smoke test"): signs in to the server of tools/smoke_server.py, changes the forced
// first password, then opens every page for all data sources (S3, Kafka, collector) and both languages. A page fails when the
// browser throws a script error, the server answers 5xx, the page shows its error card, or it does not finish loading.
//
//   node tools/smoke_browser.cjs [base URL, default http://127.0.0.1:8777] [folder for failure screenshots]
const { chromium } = require('playwright');

const BASE = process.argv[2] || 'http://127.0.0.1:8777';
const SHOTS = process.argv[3] || '';
const PW0 = 'smoke-test-first-password', PW1 = 'Smoke-Test-Second-Password-2026!';
const PAGES = ['overview', 'command-center', 'trends', 'security', 'root-causes', 'availability', 'pods', 'business', 'tracing', 'raw-logs',
  'services/event-api', 'servers', 'collectors', 'admin/users', 'admin/ingest', 'admin/configuration', 'admin/notifications'];
const RUNS = [{ lang: 'id', source: '' }, { lang: 'id', source: 'kafka' }, { lang: 'id', source: 'collector' }, { lang: 'en', source: '' }];

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
    const mapAnswer = hp.waitForResponse((r) => r.url().endsWith('/api/v1/public/map'));
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

  // sign-in page and home page: the same language menu and theme button as the dashboard header (44 x 44, line icons, no emoji),
  // the menu stays on the screen on a phone, Esc closes it and the focus returns to its button
  for (const [path, width] of [['/login', 1280], ['/login', 320], ['/', 390]]) {
    const lp = await (await browser.newContext({ viewport: { width, height: 800 } })).newPage();
    await lp.goto(BASE + path);
    await lp.waitForSelector('.lbtn');
    const m = await lp.evaluate(() => {
      const l = document.querySelector('.lbtn').getBoundingClientRect(), t = document.querySelector('.icon-btn[aria-pressed]').getBoundingClientRect();
      const text = document.querySelector('.lbtn').parentElement.parentElement.innerText + document.querySelector('.icon-btn[aria-pressed]').innerText;
      return { l: [l.width, l.height], t: [t.width, t.height], seg: !!document.querySelector('.seg[role=radiogroup]'), emoji: /\p{Extended_Pictographic}/u.test(text), over: document.documentElement.scrollWidth - innerWidth };
    });
    if (m.t[0] !== 44 || m.t[1] !== 44 || m.l[1] !== 44 || m.seg || m.emoji || m.over > 0) throw new Error(`${path} at ${width}px: controls ${JSON.stringify(m)}`);
    await lp.locator('.lbtn').click();
    const r = await lp.locator('#lang-menu').boundingBox();
    if (r.x < 0 || r.x + r.width > width) throw new Error(`${path} at ${width}px: the language menu leaves the screen (${r.x}, ${r.width})`);
    await lp.keyboard.press('Escape');
    if (await lp.locator('#lang-menu').count() || !(await lp.locator('.lbtn').evaluate((b) => document.activeElement === b))) throw new Error(`${path}: Esc did not close the language menu and return the focus`);
    const was = await lp.evaluate(() => document.documentElement.dataset.theme);
    await lp.locator('.icon-btn[aria-pressed]').click();
    if ((await lp.evaluate(() => document.documentElement.dataset.theme)) === was) throw new Error(`${path}: the theme button did not switch the theme`);
    await lp.context().close();
  }
  console.log('ok   sign-in and home page: language menu and theme button like the dashboard header');

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

  // header language menu: opens, Esc closes and returns focus to the button, choosing a row switches the language and closes the menu
  await page.goto(BASE + '/overview');
  await page.waitForSelector('main#main[aria-busy="false"]');
  const langBtn = page.locator('button[aria-controls="lang-menu"]');
  await langBtn.click();
  if ((await langBtn.getAttribute('aria-expanded')) !== 'true') throw new Error('language menu did not open');
  await page.keyboard.press('Escape');
  if (await page.locator('#lang-menu').count()) throw new Error('Esc did not close the language menu');
  if (!(await langBtn.evaluate((b) => document.activeElement === b))) throw new Error('focus did not return to the language button');
  const want = (await page.evaluate(() => document.documentElement.lang)) === 'en' ? 'id' : 'en';
  await langBtn.click();
  await page.locator(`#lang-menu [role=menuitemradio]:has(.code:text-is("${want.toUpperCase()}"))`).click();
  if (await page.evaluate(() => document.documentElement.lang) !== want) throw new Error('the language menu did not switch the language');
  if (await page.locator('#lang-menu').count()) throw new Error('the language menu stayed open after a choice');
  console.log('ok   header language menu (open, Esc, choose)');

  // header controls are one family (same height, border colour and radius), and a dialog closed with the mouse gives the focus back
  // to its button without a ring (with the keyboard it keeps one)
  const family = await page.evaluate(() => ['.where .seg', '.fp', 'button[aria-keyshortcuts]', '.lbtn', 'header.top button[aria-pressed]', '.who'].map((s) => {
    const e = document.querySelector(s), c = e && getComputedStyle(e), r = e && e.getBoundingClientRect();
    return e && `${s}: ${Math.round(r.height)}px ${c.borderTopWidth} ${c.borderTopColor} ${c.borderTopLeftRadius}`;
  }));
  const kinds = new Set(family.filter(Boolean).map((x) => x.replace(/^[^:]*: /, '')));
  if (kinds.size !== 1) throw new Error(`header controls differ: ${family.join(' | ')}`);
  const searchBtn = page.locator('button[aria-keyshortcuts]');
  await searchBtn.click();
  await page.keyboard.type('ab');
  await page.locator('dialog[open] button.x').click();
  const ring = () => searchBtn.evaluate((b) => ({ on: document.activeElement === b, ring: getComputedStyle(b).outlineStyle !== 'none' }));
  let st = await ring();
  if (!st.on || st.ring) throw new Error(`search button after closing the dialog with the mouse: focused ${st.on}, ring ${st.ring}`);
  await searchBtn.press('Enter');
  await page.keyboard.press('Escape'); await page.keyboard.press('Escape');   // the first Esc only clears the field
  st = await ring();
  if (!st.on || !st.ring) throw new Error(`search button after closing the dialog with Esc: focused ${st.on}, ring ${st.ring}`);
  console.log('ok   header controls look alike; focus ring only after the keyboard');

  // dark theme button (an icon button with aria-pressed): toggles data-theme, shows a moon or a sun, and both themes render the Overview
  // without script errors
  const sw = page.locator('header.top button[aria-pressed]');
  const box = await sw.boundingBox();
  if (Math.round(box.width) !== 44 || Math.round(box.height) !== 44) throw new Error(`theme button is ${box.width} x ${box.height}, not 44 x 44`);
  const errsBefore = problems.length;
  for (let i = 0; i < 2; i++) {
    const was = await page.evaluate(() => document.documentElement.dataset.theme);
    await sw.click();
    const now = await page.evaluate(() => document.documentElement.dataset.theme);
    if (now === was || (await sw.getAttribute('aria-pressed')) !== String(now === 'dark')) throw new Error(`theme button: ${was} -> ${now}`);
    await page.waitForTimeout(400);
    await page.locator('main#main[aria-busy="false"]').waitFor();
  }
  if (problems.length !== errsBefore) throw new Error(`errors while switching themes: ${problems.slice(errsBefore).join('; ')}`);
  console.log('ok   dark theme button (both themes render the Overview)');

  // wide and narrow screens: at 3840 x 2160 the Overview fills the width (scaled up, no empty right side, no sideways scroll);
  // at 390 px nothing scrolls sideways
  for (const [w, h] of [[3840, 2160], [390, 844]]) {
    await page.setViewportSize({ width: w, height: h });
    await page.goto(BASE + '/overview');
    await page.waitForSelector('main#main[aria-busy="false"]');
    await page.waitForTimeout(600);
    const m = await page.evaluate(() => ({ right: document.querySelector('main').getBoundingClientRect().right, over: document.documentElement.scrollWidth - document.documentElement.clientWidth, wide: [...document.querySelectorAll('body *')].filter((e) => e.getBoundingClientRect().right > innerWidth + 2).slice(0, 3).map((e) => `${e.tagName}.${e.className}`).join(', '), w: innerWidth, zoom: document.documentElement.style.zoom }));
    if (m.over > 0) throw new Error(`horizontal scroll of ${m.over}px at ${w}px (${m.wide})`);
    if (w >= 3000 && (m.w - m.right > 40 || m.zoom !== '1.6')) throw new Error(`Overview main ends ${m.w - m.right}px before the right edge (zoom "${m.zoom}") at ${w}px`);
    console.log(`ok   Overview at ${w}px (right gap ${Math.round(m.w - m.right)}px, zoom ${m.zoom || '1'}, no sideways scroll)`);
  }
  // narrow phone: the date picker shows the whole date (its text is not cut) and no sideways scroll
  for (const w of [320, 360]) {
    await page.setViewportSize({ width: w, height: 800 });
    await page.goto(BASE + '/overview');
    await page.waitForSelector('main#main[aria-busy="false"]');
    const d = await page.evaluate(() => {
      const s = document.querySelector('#folder-select'), cs = getComputedStyle(s), g = document.createElement('canvas').getContext('2d');
      g.font = cs.font;
      return { text: g.measureText(s.options[s.selectedIndex].text).width, room: s.getBoundingClientRect().width - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight), over: document.documentElement.scrollWidth - innerWidth };
    });
    if (d.text > d.room || d.over > 0) throw new Error(`date picker at ${w}px: text ${Math.round(d.text)}px, room ${Math.round(d.room)}px, overflow ${d.over}px`);
    console.log(`ok   date picker shows the whole date at ${w}px`);
  }
  await page.setViewportSize({ width: 1280, height: 900 });

  // Collectors page: the add dialog opens and closes with Esc, creating a collector shows the token and the install command,
  // the new collector is listed and its panel opens (no sideways scroll on a phone either)
  await page.goto(BASE + '/collectors');
  await page.waitForSelector('main#main[aria-busy="false"]');
  await page.click('button.add');
  await page.waitForSelector('dialog[open] #cl-name');
  await page.keyboard.press('Escape');
  if (await page.locator('dialog[open]').count()) throw new Error('Esc did not close the add collector dialog');
  await page.click('button.add');
  await page.fill('#cl-name', 'smoke-web-01');
  await page.click('dialog .addf');
  await page.fill('#add-p0', '/var/log/app/*.log'); await page.fill('#add-s0', 'app');
  await page.click('dialog button[type=submit]');
  await page.waitForSelector('dialog code.tok');
  const token = await page.locator('dialog code.tok').first().innerText();
  const cmd = await page.locator('dialog pre').allInnerTexts();
  if (!/^mse_\d+_/.test(token) || !cmd.join('\n').includes(`--token ${token}`) || !cmd.join('\n').includes('/collector/install.sh')) throw new Error(`token / command not shown: ${token} ${cmd}`);
  await page.click('dialog .acts button.primary');
  await page.waitForSelector('tr:has-text("smoke-web-01")');
  if (!(await page.locator('#cl-panel').count())) throw new Error('the new collector was not selected');
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(BASE + '/collectors');
  await page.waitForSelector('tr:has-text("smoke-web-01")');
  const over = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  if (over > 0) throw new Error(`Collectors page scrolls sideways by ${over}px at 390px`);
  await page.setViewportSize({ width: 1280, height: 900 });
  console.log('ok   Collectors: add dialog (Esc), token and command, list, no sideways scroll at 390px');

  // Collector groups and the Servers page (the sample servers of tools/seed_metrics.py: three groups and one collector without a group).
  // Every /api answer these pages read must be encrypted (X-MS-Enc, application/octet-stream); only the public key exchange and /api/health are plain JSON.
  const plain = [];
  const watch = (r) => {
    const u = new URL(r.url());
    if (u.pathname.startsWith('/api/') && !/^\/api\/(v1\/crypto\/handshake|health)$/.test(u.pathname) && (r.headers()['content-type'] || '').startsWith('application/json')) plain.push(`${r.request().method()} ${u.pathname}`);
  };
  page.on('response', watch);
  await page.evaluate(() => { localStorage.setItem('lang', 'en'); localStorage.removeItem('cl-closed'); });
  await page.goto(BASE + '/collectors');
  await page.waitForSelector('h2.gh');
  const heads = await page.locator('h2.gh .gn').allInnerTexts();
  if (heads.join('|') !== 'Client A|Client B|Internal|No Group') throw new Error(`collector sections: ${heads.join('|')}`);
  const hb = page.locator('h2.gh button').first();
  if ((await hb.getAttribute('aria-expanded')) !== 'true' || (await hb.evaluate((b) => b.getBoundingClientRect().height)) < 56) throw new Error('section header: not open or under 56 px');
  await hb.click();
  if ((await hb.getAttribute('aria-expanded')) !== 'false' || (await page.locator('tr:has-text("db-01")').count()) !== 0) throw new Error('a section did not fold');
  await page.reload();
  await page.waitForSelector('h2.gh');
  if ((await page.locator('h2.gh button').first().getAttribute('aria-expanded')) !== 'false') throw new Error('the folded section was not remembered');
  await page.fill('.find input', 'web-01');          // a search opens every matching section
  if ((await page.locator('h2.gh button').first().getAttribute('aria-expanded')) !== 'true' || (await page.locator('tbody tr').count()) < 1) throw new Error('a search did not open the matching section');
  await page.fill('.find input', 'no-such-collector');
  if (!(await page.locator('.nomatch').count())) throw new Error('no "nothing matches" line');
  await page.fill('.find input', '');
  await page.click('.flt button:has-text("Offline")');
  if ((await page.locator('.flt button[aria-pressed=true]').count()) !== 1 || (await page.locator('h2.gh .gn').allInnerTexts()).join('|') !== 'No Group') throw new Error('status filter Offline');
  await page.click('.flt button:has-text("All")');
  await page.click('button.all');
  if ((await page.locator('h2.gh button[aria-expanded=true]').count()) !== 0) throw new Error('Collapse All');
  await page.click('button.all');
  if ((await page.locator('h2.gh button[aria-expanded=false]').count()) !== 0) throw new Error('Expand All');
  await page.click('tr:has-text("web-02") .rowbtn');         // the panel: change the group, the metric options and the upgrade note
  await page.click('#cl-panel button:has-text("Change Group")');
  await page.waitForSelector('dialog[open] #cl-gr-in');
  await page.fill('#cl-gr-in', 'client b');
  if (!(await page.locator('dialog .note:has-text("Joins the existing group Client B")').count())) throw new Error('group note');
  await page.click('dialog button[type=submit]');
  await page.waitForSelector('tr:has-text("web-02")');
  await page.waitForFunction(() => [...document.querySelectorAll('h2.gh')].some((h) => h.textContent.includes('Client B') && h.textContent.includes('3 collectors')));
  await page.waitForSelector('#cl-panel');                  // still selected: the panel stays open after the group changed
  await page.click('#cl-panel button:has-text("Change Inputs")');
  await page.waitForSelector('dialog[open] fieldset.met');
  await page.click('dialog fieldset.met label:has-text("Server Metrics") input');
  await page.click('dialog button[type=submit]');
  await page.waitForSelector('dialog:has-text("Run the upgrade command on the server to apply this")');
  if (!(await page.locator('dialog pre:has-text("install.sh --upgrade")').count())) throw new Error('upgrade command not shown after a metrics change');
  await page.keyboard.press('Escape');
  console.log('ok   Collectors: sections per group, fold (remembered), search, status filter, change group, metric options and the upgrade command');

  await page.goto(BASE + '/servers');
  await page.waitForSelector('.hc');
  await page.waitForSelector('.charts canvas');
  if ((await page.locator('.hc').count()) < 6 || (await page.locator('section.banner li').count()) < 1) throw new Error('Servers: cards or banner missing');
  if ((await page.locator('.seg[role=radiogroup]').count()) !== 0) throw new Error('the source switch is shown on the Servers page');
  const groupBtns = await page.locator('.gfilter .gb').allInnerTexts();
  if (groupBtns[0] !== 'All Groups' || groupBtns.length < 4) throw new Error(`group filter: ${groupBtns.join('|')}`);
  await page.click('.gfilter .gb:text-is("Client B")');
  if ((await page.locator('.hc').count()) !== 3 || (await page.locator('.gfilter .gb[aria-pressed=true]').count()) !== 1) throw new Error('Servers: group filter Client B');
  await page.click('.gfilter .gb:text-is("All Groups")');
  await page.click('.hc:has-text("VM-23-71-ubuntu")');
  await page.waitForSelector('.ct tbody tr');
  if ((await page.locator('.ct tbody tr').count()) !== 4 || !(await page.locator('.ct tr.off').count())) throw new Error('Servers: containers table');
  await page.click('.rng button:text-is("7 d")');
  await page.waitForSelector('.charts canvas');
  for (const w of [390, 1280]) {
    await page.setViewportSize({ width: w, height: 900 });
    // charts resize after the window does: wait up to 2 s for the layout to settle, then name what sticks out
    let o = 0, wide = [];
    for (let i = 0; i < 10; i++) {
      await page.waitForTimeout(200);
      [o, wide] = await page.evaluate(() => {
        const cw = document.documentElement.clientWidth;
        const out = [...document.querySelectorAll('main *')].filter((el) => el.getBoundingClientRect().right > cw + 1 && !el.closest('.scroll'))
          .slice(0, 3).map((el) => `${el.tagName.toLowerCase()}.${String(el.className?.baseVal ?? el.className).split(' ')[0]} +${Math.round(el.getBoundingClientRect().right - cw)}px`);
        return [document.documentElement.scrollWidth - cw, out];
      });
      if (o <= 0) break;
    }
    if (o > 0) throw new Error(`Servers page scrolls sideways by ${o}px at ${w}px (${wide.join(', ') || 'no element found'})`);
  }
  // a quiet page asks for nothing: the next refresh is 30 s away (a loop once asked for the host without end)
  let asked = 0;
  const count = (r) => { if (r.url().includes('/servers')) asked++; };
  page.on('request', count);
  await page.waitForTimeout(4000);
  page.off('request', count);
  if (asked > 2) throw new Error(`Servers page sent ${asked} requests in 4 s while nothing changed`);
  console.log('ok   Servers: cards, banner, group filter, charts, containers, ranges, no sideways scroll, no request loop');
  page.off('response', watch);
  if (plain.length) throw new Error(`these /api answers were plain JSON, not encrypted: ${[...new Set(plain)].join(', ')}`);
  console.log('ok   Collectors and Servers read only encrypted /api answers');

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
