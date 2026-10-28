// Builds the link preview images of the home page (monishield/interfaces/api/home_meta.py): web/public/og-id.png and
// og-en.png, 1200 × 630. Drawn with the MoniShield logo, colours and font, and sample numbers only (no real data).
// Run after changing the texts:  NODE_PATH=web/node_modules node tools/og_image.cjs
// The address printed on the image is the host of S4_DASHBOARD_URL (environment, else .env); none = no address line.
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const ROOT = path.join(__dirname, '..');
const fromDotenv = (k) => { try { return (fs.readFileSync(path.join(ROOT, '.env'), 'utf8').match(new RegExp(`^${k}=(.*)$`, 'm')) || [])[1]; } catch { return undefined; } };
const DASHBOARD = (process.env.S4_DASHBOARD_URL ?? fromDotenv('S4_DASHBOARD_URL') ?? '').trim().replace(/^["']|["']$/g, '');
const HOST = DASHBOARD ? new URL(DASHBOARD).host : '';
// fonts inline: a page built with setContent may not load local files
const FONT = (w) => 'data:font/woff2;base64,' + fs.readFileSync(path.join(ROOT, `web/node_modules/@fontsource/outfit/files/outfit-latin-${w}-normal.woff2`)).toString('base64');
const TEXT = {
  id: { a: 'Pantau log dan keamanan layanan', b: 'dari satu dashboard', sub: 'Deteksi serangan OWASP CRS, akar masalah error, peta asal request, dan laporan harian.',
        lines: 'Total baris log', err: 'Error', n1: '284.910', n2: '1.284' },
  en: { a: 'Watch your service logs and security', b: 'from one dashboard', sub: 'OWASP CRS attack detection, the cause of errors, a request origin map, and a daily report.',
        lines: 'Total log lines', err: 'Errors', n1: '284,910', n2: '1,284' },
};
const BARS = [10, 8, 18, 35, 60, 72, 66, 58, 70, 88, 76, 50, 30, 20];

const page = (t) => `<!doctype html><html><head><meta charset="utf-8"><style>
  @font-face { font-family: Outfit; font-weight: 400; src: url(${FONT(400)}); }
  @font-face { font-family: Outfit; font-weight: 600; src: url(${FONT(600)}); }
  @font-face { font-family: Outfit; font-weight: 700; src: url(${FONT(700)}); }
  html, body { margin: 0; }
  .og { width: 1200px; height: 630px; box-sizing: border-box; position: relative; overflow: hidden; font-family: Outfit, sans-serif; color: #e8eaed;
        background: radial-gradient(ellipse at 85% 20%, rgba(45,212,191,0.18), transparent 55%), #0f1115; padding: 64px 72px; display: flex; flex-direction: column; gap: 26px; }
  .brand { display: flex; align-items: center; gap: 16px; font-size: 36px; font-weight: 700; }
  h1 { margin: 0; font-size: 66px; line-height: 1.08; font-weight: 700; letter-spacing: -0.01em; max-width: 720px; }
  h1 span { color: #2dd4bf; }
  p { margin: 0; font-size: 26px; line-height: 1.4; color: #c9ced5; max-width: 640px; }
  .url { margin-top: auto; font-size: 22px; color: #9aa3ad; }
  .dash { position: absolute; right: -60px; bottom: -50px; width: 480px; height: 370px; border: 1px solid #343a44; border-radius: 22px; background: #181b21;
          padding: 22px; box-sizing: border-box; display: flex; flex-direction: column; gap: 14px; transform: rotate(-4deg); box-shadow: 0 30px 90px rgba(0,0,0,0.55); }
  .k { display: flex; gap: 14px; } .k div { flex: 1; background: #14171c; border-radius: 12px; padding: 14px; }
  .k small { display: block; font-size: 14px; color: #9aa3ad; } .k b { display: block; font-size: 28px; font-weight: 600; }
  .bars { flex: 1; display: flex; align-items: flex-end; gap: 6px; background: #14171c; border-radius: 12px; padding: 14px; }
  .bars span { flex: 1; background: #2dd4bf; border-radius: 3px; }
</style></head><body><div class="og">
  <div class="brand"><svg width="52" height="52" viewBox="0 0 32 32"><path d="M16 2l12 4.5v8.2c0 7.3-5 13.4-12 15.3C9 28.1 4 22 4 14.7V6.5z" fill="#2dd4bf"/><path d="M10 21V11l6 6 6-6v10" fill="none" stroke="#04201c" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/></svg>MoniShield</div>
  <h1>${t.a} <span>${t.b}</span></h1>
  <p>${t.sub}</p>
  ${HOST ? `<div class="url">${HOST}</div>` : '<div class="url"></div>'}
  <div class="dash"><div class="k"><div><small>${t.lines}</small><b>${t.n1}</b></div><div><small>${t.err}</small><b style="color:#f43f5e">${t.n2}</b></div></div>
    <div class="bars">${BARS.map((h) => `<span style="height:${h}%"></span>`).join('')}</div></div>
</div></body></html>`;

(async () => {
  const browser = await chromium.launch();
  const p = await browser.newPage({ viewport: { width: 1200, height: 630 } });
  for (const [l, t] of Object.entries(TEXT)) {
    await p.setContent(page(t), { waitUntil: 'load' });
    await p.evaluate(() => document.fonts.ready);
    await p.locator('.og').screenshot({ path: path.join(ROOT, `web/public/og-${l}.png`) });
    console.log(`web/public/og-${l}.png`);
  }
  await browser.close();
})();
