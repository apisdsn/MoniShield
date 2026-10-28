<!-- Public home page at / (owner request 2026-10-28; mockup "Halaman utama" on the design canvas). Open to anyone: what
     MoniShield is, the traffic map, and "Sign in". The map data comes from GET /api/public/map (no sign-in): request origins
     rounded to ~50 km areas, small areas left out, no IP addresses (monishield/domain/public_map.py). Live when the Kafka feed
     has traffic in the last minute (real events animate the map), otherwise the newest day. Polled every 5 s while the tab is
     visible. Links into the app load the page anew (data-reload): the home page carries none of the app's data.
     "How it works" shows the current architecture (docs/08-architecture.md) as four stages. -->
<script>
  import { onMount } from 'svelte';
  import { lang, t } from '../i18n.js';
  import { theme } from '../theme.js';
  import { num, dLabel } from '../format.js';
  import { APP_NAME } from '../brand.js';
  import Logo from '../lib/Logo.svelte';
  import MapView from '../lib/MapView.svelte';
  import AppPreview from '../lib/AppPreview.svelte';

  // "Source code" link: S4_SOURCE_URL, written into the page by the server (home_meta.py); none = no link
  const REPO = document.querySelector('meta[name="monishield:source"]')?.content || '';
  // icons of the four architecture stages (static markup, no user data)
  const PRIV_ICON = {
    1: '<rect x="4" y="11" width="16" height="10" rx="2"></rect><path d="M8 11V7a4 4 0 0 1 8 0v4"></path>',
    2: '<path d="M12 21s-7-6.2-7-11a7 7 0 0 1 14 0c0 4.8-7 11-7 11z"></path><circle cx="12" cy="10" r="2.5"></circle>',
    3: '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>',
    4: '<circle cx="12" cy="8" r="4"></circle><path d="M4 21c1.5-4 4.5-6 8-6s6.5 2 8 6"></path>',
  };
  const ARCH_ICON = {
    1: '<path d="M4 7c0-1.7 3.6-3 8-3s8 1.3 8 3-3.6 3-8 3-8-1.3-8-3z"></path><path d="M4 7v5c0 1.7 3.6 3 8 3s8-1.3 8-3V7"></path><path d="M4 12v5c0 1.7 3.6 3 8 3s8-1.3 8-3v-5"></path>',
    2: '<path d="M12 3l8 3v6c0 4.5-3.4 8.2-8 9-4.6-.8-8-4.5-8-9V6z"></path><path d="M9 12l2 2 4-4"></path>',
    3: '<rect x="3" y="4" width="18" height="6" rx="1.5"></rect><rect x="3" y="14" width="18" height="6" rx="1.5"></rect><path d="M7 7h.01M7 17h.01"></path>',
    4: '<rect x="3" y="4" width="18" height="13" rx="2"></rect><path d="M8 21h8M12 17v4"></path>',
  };
  let signedIn = $state(false), map = $state(null), mapRef = $state(), preset = $state(matchMedia('(max-width: 560px)').matches ? 'id' : 'world');   // world first (owner request); a phone is too narrow for the whole world
  // no traffic to show at all (new install, data not arrived yet): sample dots, clearly marked as such (owner request 2026-10-28)
  const SAMPLE = [[-6.0, 107.0, 4200, 'Jakarta'], [-7.0, 107.5, 1380, 'Bandung'], [-7.5, 112.5, 1120, 'Surabaya'], [-7.0, 110.5, 640, 'Semarang'],
    [-8.0, 110.5, 590, 'Yogyakarta'], [3.5, 98.5, 520, 'Medan'], [-5.0, 119.5, 410, 'Makassar'], [-8.5, 115.0, 300, 'Denpasar'],
    [-3.0, 104.5, 260, 'Palembang'], [-1.5, 117.0, 180, 'Balikpapan'], [0.5, 101.5, 150, 'Pekanbaru'], [-0.0, 109.5, 110, 'Pontianak'],
    [1.5, 125.0, 60, 'Manado'], [-2.5, 140.5, 40, 'Jayapura'], [1.5, 104.0, 230, 'Singapore', 'SG'], [3.0, 101.5, 90, 'Kuala Lumpur', 'MY'],
    [35.5, 139.5, 70, 'Tokyo', 'JP'], [37.5, -122.0, 55, 'San Francisco', 'US'], [50.0, 8.5, 45, 'Frankfurt', 'DE']]
    .map(([lat, lon, requests, city, cc = 'ID']) => ({ lat, lon, requests, city, cc, ips: 0, modules: {} }));
  const sample = $derived(map?.enabled && !map.points.length);
  const shown = $derived(sample ? SAMPLE : map?.points || []);
  const totals = $derived(sample ? { requests: SAMPLE.reduce((a, p) => a + p.requests, 0), places: SAMPLE.length, countries: new Set(SAMPLE.map((p) => p.cc)).size } : map?.totals);
  const live = $derived(map?.mode === 'live');
  let menu = $state(false), menuBtn = $state();   // narrow screens: page links in a menu (wide: in the navbar)
  function closeMenu(focus = false) { menu = false; if (focus) menuBtn?.focus(); }
  const enter = $derived(signedIn ? '/overview' : '/login');

  async function poll() {
    try {
      const r = await fetch('/api/public/map', { headers: { Accept: 'application/json' } });
      if (!r.ok) return;
      const m = await r.json();
      map = m.enabled ? { ...m, points: m.points.map((p) => ({ ...p, ips: 0, modules: {} })) } : m;
      if (m.mode === 'live') for (const p of m.pulses || []) mapRef?.pulse({ lat: p.lat, lon: p.lon, n: Math.min(p.n, 20) });
    } catch { /* offline: keep the last map */ }
  }
  // the map library (±1 MB) loads only when the map section comes near the screen, and the 5-second refresh only runs
  // while the map can be seen: the first screen of the page stays light, on phones too
  let mapBox = $state(), near = $state(false), inView = $state(false);
  $effect(() => {
    if (!mapBox || typeof IntersectionObserver === 'undefined') { near = inView = !!mapBox; return; }
    const io = new IntersectionObserver(([e]) => { inView = e.isIntersecting; if (e.isIntersecting) near = true; }, { rootMargin: '400px 0px' });
    io.observe(mapBox);
    return () => io.disconnect();
  });
  onMount(() => {
    fetch('/api/me').then((r) => (signedIn = r.ok)).catch(() => {});
    poll();   // once: whether the map is on, and its numbers
    const id = setInterval(() => { if (inView && document.visibilityState === 'visible') poll(); }, 5000);
    return () => clearInterval(id);
  });
  $effect(() => { document.title = `${APP_NAME} · ${$t('home.badge')}`; });
</script>

<svelte:window onkeydown={(e) => menu && e.key === 'Escape' && closeMenu(true)} />

<div class="home">
  <a class="skip" href="#home-main">{$t('ui.skip')}</a>
  <header class="top">
    <a class="brand" href="/" aria-label={APP_NAME}><Logo size={34} /><span>{APP_NAME}</span></a>
    {#snippet links()}
      {#if map?.enabled}<a href="#home-map" onclick={() => closeMenu()}>{$t('home.nav.map')}</a>{/if}
      <a href="#home-features" onclick={() => closeMenu()}>{$t('home.nav.features')}</a>
      <a href="#home-how" onclick={() => closeMenu()}>{$t('home.nav.how')}</a>
      <a href="#home-privacy" onclick={() => closeMenu()}>{$t('home.nav.privacy')}</a>
      {#if REPO}<a href={REPO} target="_blank" rel="noreferrer">{$t('home.foot.code')}</a>{/if}
    {/snippet}
    <nav class="sections" aria-label={$t('home.nav')}>{@render links()}</nav>
    <div class="seg lang" role="radiogroup" aria-label={$t('ui.language')}>
      <button role="radio" aria-checked={$lang === 'id'} onclick={() => lang.set('id')}>ID</button>
      <button role="radio" aria-checked={$lang === 'en'} onclick={() => lang.set('en')}>EN</button>
    </div>
    <!-- phones: one button that switches the language -->
    <button class="round langbtn" type="button" onclick={() => lang.set($lang === 'id' ? 'en' : 'id')}
      aria-label={`${$t('ui.language')}: ${$lang === 'id' ? 'Indonesia' : 'English'}`}>{$lang.toUpperCase()}</button>
    <button class="round" type="button" onclick={() => theme.set($theme === 'dark' ? 'light' : 'dark')}
      aria-label={$theme === 'dark' ? $t('theme.light') : $t('theme.dark')} title={$theme === 'dark' ? $t('theme.light') : $t('theme.dark')}>
      {#if $theme === 'dark'}
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="4"></circle><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"></path></svg>
      {:else}
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"></path></svg>
      {/if}
    </button>
    <a class="btn primary signin" href={enter} data-reload>{signedIn ? $t('home.open') : $t('home.signin')}</a>
    <button class="menubtn" type="button" bind:this={menuBtn} aria-expanded={menu} aria-controls="home-menu"
      aria-label={menu ? $t('home.nav.close') : $t('home.nav.menu')} onclick={() => (menu = !menu)}>
      {#if menu}
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"></path></svg>
      {:else}
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M4 7h16M4 12h16M4 17h16"></path></svg>
      {/if}
    </button>
    {#if menu}
      <nav class="menu" id="home-menu" aria-label={$t('home.nav')}>{@render links()}</nav>
    {/if}
  </header>
  {#if menu}<button class="scrim" type="button" tabindex="-1" aria-label={$t('home.nav.close')} onclick={() => closeMenu()}></button>{/if}

  <main id="home-main" tabindex="-1">
    <section class="hero" aria-labelledby="home-h1">
      <span class="badge">{$t('home.badge')}</span>
      <h1 id="home-h1">{$t('home.title_a')} <span class="hl">{$t('home.title_b')}</span></h1>
      <p class="lead">{$t('home.lead')}</p>
      <div class="ctas">
        <a class="btn primary big" href={enter} data-reload>
          {signedIn ? $t('home.cta_open') : $t('home.cta')}
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12h14M13 6l6 6-6 6"></path></svg>
        </a>
        <a class="btn big ghost" href="#home-how">{$t('home.how_link')}</a>
      </div>
      <AppPreview />
    </section>

    {#if map?.enabled}
      <section class="block" id="home-map" aria-labelledby="home-map-h">
        <div class="wrap">
          <div class="head">
            <div class="txt">
              <span class="live" class:day={!live} class:sample><span class="dot" aria-hidden="true"></span>{live ? $t('home.live.badge') : sample ? $t('home.sample.badge') : $t('home.day.badge')}</span>
              <h2 id="home-map-h">{$t('home.live.title')}</h2>
              <p class="sub">{live ? $t('home.live.intro') : sample ? $t('home.sample.intro') : $t('home.day.intro', { d: dLabel(map.day, $lang) })}</p>
            </div>
            <div class="seg" role="group" aria-label={$t('map.preset')}>
              <button type="button" aria-pressed={preset === 'world'} onclick={() => (preset = 'world')}>{$t('map.world')}</button>
              <button type="button" aria-pressed={preset === 'id'} onclick={() => (preset = 'id')}>Indonesia</button>
            </div>
          </div>
          <div class="lmap" bind:this={mapBox}>
            {#if near}
              <MapView points={shown} server={map.server} bind:preset bind:this={mapRef} {live} pub label={$t('home.live.map')} />
            {:else}
              <div class="mapwrap ph" aria-hidden="true"></div>
            {/if}
          </div>
          <dl class="kpis">
            <div><dt>{live ? $t('home.k.req_live') : $t('home.k.req_day')}</dt><dd>{num(totals.requests, $lang)}</dd></div>
            <div><dt>{$t('home.k.places')}</dt><dd>{num(totals.places, $lang)}</dd></div>
            <div><dt>{$t('home.k.countries')}</dt><dd>{num(totals.countries, $lang)}</dd></div>
          </dl>
        </div>
      </section>
    {/if}

    <section class="block" id="home-features" aria-labelledby="home-f-h">
      <div class="wrap">
        <h2 id="home-f-h">{$t('home.f.title')}</h2>
        <p class="sub">{$t('home.f.intro')}</p>
        <div class="cards">
          {#each [1, 2, 3, 4] as i}
            <article class="card">
              <span class="ico" aria-hidden="true">
                {#if i === 1}<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="9" rx="1"></rect><rect x="14" y="3" width="7" height="5" rx="1"></rect><rect x="14" y="12" width="7" height="9" rx="1"></rect><rect x="3" y="16" width="7" height="5" rx="1"></rect></svg>
                {:else if i === 2}<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3l8 3v6c0 4.5-3.4 8.2-8 9-4.6-.8-8-4.5-8-9V6z"></path><path d="M9 12l2 2 4-4"></path></svg>
                {:else if i === 3}<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="7"></circle><path d="M21 21l-4.3-4.3"></path></svg>
                {:else}<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"></path><path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"></path></svg>{/if}
              </span>
              <h3>{$t(`home.f.${i}.t`)}</h3>
              <p>{$t(`home.f.${i}.d`)}</p>
            </article>
          {/each}
        </div>
      </div>
    </section>

    <section class="block" id="home-how" aria-labelledby="home-how-h">
      <div class="wrap">
        <h2 id="home-how-h">{$t('home.how.title')}</h2>
        <p class="sub">{$t('home.how.intro')}</p>
        <!-- architecture (docs/08-architecture.md): four stages left to right, stacked with arrows down on phones -->
        <ol class="arch" aria-label={$t('home.arch.label')}>
          {#each [1, 2, 3, 4] as i}
            <li class="stage">
              <div class="sh">
                <span class="ico" aria-hidden="true"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">{@html ARCH_ICON[i]}</svg></span>
                <h3>{$t(`home.arch.${i}.t`)}</h3>
              </div>
              <ul>{#each ['a', 'b', 'c'] as k}<li>{$t(`home.arch.${i}.${k}`)}</li>{/each}</ul>
            </li>
          {/each}
        </ol>
        <div class="under">
          <div class="box">
            <h3>{$t('home.arch.layers')}</h3>
            <div class="layers" aria-hidden="true"><span>interfaces</span><b>→</b><span>application</span><b>→</b><span>domain</span><span class="infra">infrastructure → application · domain</span></div>
            <p>{$t('home.arch.layers.d')}</p>
          </div>
          <div class="box">
            <h3>{$t('home.arch.deploy')}</h3>
            <p>{$t('home.arch.deploy.d')}</p>
          </div>
        </div>
      </div>
    </section>

    <section class="block" id="home-privacy" aria-labelledby="home-priv-h">
      <div class="wrap">
        <h2 id="home-priv-h">{$t('home.priv.title')}</h2>
        <p class="sub">{$t('home.priv.d')}</p>
        <ul class="privs">
          {#each [1, 2, 3, 4] as i}
            <li>
              <span class="ico" aria-hidden="true"><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">{@html PRIV_ICON[i]}</svg></span>
              <div><h3>{$t(`home.priv.${i}.t`)}</h3><p>{$t(`home.priv.${i}.d`)}</p></div>
            </li>
          {/each}
        </ul>
      </div>
    </section>

    <section class="block last" aria-labelledby="home-end-h">
      <div class="wrap">
        <div class="end">
          <h2 id="home-end-h">{signedIn ? APP_NAME : $t('home.end.title')}</h2>
          {#if !signedIn}<p>{$t('home.end.d')}</p>{/if}
          <a class="btn primary big" href={enter} data-reload>
            {signedIn ? $t('home.cta_open') : $t('home.cta')}
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12h14M13 6l6 6-6 6"></path></svg>
          </a>
        </div>
      </div>
    </section>
  </main>

  <footer class="foot">© {new Date().getFullYear()} {APP_NAME}</footer>
</div>

<style>
  .home { min-height: 100vh; background: var(--bg); color: var(--fg); display: flex; flex-direction: column; overflow-x: clip; }
  .skip { position: absolute; left: -9999px; top: 8px; z-index: 30; padding: 10px 14px; border-radius: 10px; background: var(--card); color: var(--fg); }
  .skip:focus { left: 8px; }
  .wrap { max-width: 1120px; margin: 0 auto; width: 100%; }

  .top {
    position: sticky; top: 0; z-index: 20; display: flex; align-items: center; gap: 10px; padding: 12px max(16px, calc((100% - 1120px) / 2));
    border-bottom: 1px solid var(--line); background: color-mix(in srgb, var(--bg) 90%, transparent); backdrop-filter: blur(8px);
  }
  .brand { display: flex; align-items: center; gap: 10px; color: var(--fg); text-decoration: none; font-size: 1.25rem; font-weight: 600; margin-right: auto; min-height: 44px; }
  .sections { display: flex; align-items: center; gap: 2px; }
  .sections a { min-height: 44px; display: inline-flex; align-items: center; padding: 0 12px; color: var(--kpi-label); text-decoration: none; border-radius: 10px; }
  .sections a:hover { color: var(--fg); background: var(--nav-hover); }
  .menubtn { display: none; width: 44px; height: 44px; flex: none; border-radius: 12px; border: 1px solid var(--line-strong); background: var(--card); color: var(--fg); place-items: center; cursor: pointer; }
  .menubtn[aria-expanded='true'] { border-color: var(--accent); color: var(--accent-text); background: color-mix(in srgb, var(--accent) 12%, transparent); }
  .menu { position: absolute; top: calc(100% + 8px); right: max(12px, calc((100% - 1120px) / 2)); width: min(320px, calc(100% - 24px)); z-index: 21;
    display: flex; flex-direction: column; padding: 8px; background: var(--card); border: 1px solid var(--line-strong); border-radius: 16px; box-shadow: 0 20px 40px rgb(0 0 0 / 0.35); }
  .menu a { min-height: 48px; display: flex; align-items: center; justify-content: space-between; padding: 0 14px; border-radius: 10px; color: var(--fg); text-decoration: none; }
  .menu a:hover { background: var(--nav-hover); }
  .scrim { position: fixed; inset: 0; z-index: 19; border: 0; padding: 0; background: rgb(0 0 0 / 0.4); cursor: default; }
  .round.langbtn { display: none; font: inherit; font-size: 0.8125rem; font-weight: 600; }   /* .round sets display: grid */
  .seg { display: flex; background: var(--card); border: 1px solid var(--line-strong); border-radius: 999px; padding: 3px; flex: none; }
  .seg button { min-height: 36px; padding: 0 12px; border: 0; border-radius: 999px; background: transparent; color: var(--kpi-label); font: inherit; font-size: 0.8125rem; cursor: pointer; }
  .seg button[aria-checked='true'], .seg button[aria-pressed='true'] { background: var(--seg-on); color: var(--accent-text); font-weight: 600; }
  .round { width: 44px; height: 44px; flex: none; border-radius: 999px; border: 1px solid var(--line-strong); background: var(--card); color: var(--kpi-label); display: grid; place-items: center; cursor: pointer; }
  .signin { min-height: 44px; border-radius: 999px; padding: 0 20px; display: inline-flex; align-items: center; text-decoration: none; flex: none; }
  .btn.big { min-height: 52px; padding: 0 26px; border-radius: 999px; font-size: 1.0625rem; display: inline-flex; align-items: center; justify-content: center; gap: 10px; text-decoration: none; }
  .btn.ghost { color: var(--fg); }

  .hero { padding: 96px 16px 72px; display: flex; flex-direction: column; align-items: center; text-align: center; gap: 22px; }
  .badge { font-size: 0.8125rem; font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase; color: var(--accent-text); padding: 6px 14px; border-radius: 999px;
    background: color-mix(in srgb, var(--accent) 12%, transparent); border: 1px solid color-mix(in srgb, var(--accent) 40%, transparent); }
  h1 { margin: 0; max-width: 960px; font-size: clamp(2.25rem, 1.2rem + 4.6vw, 4.5rem); line-height: 1.05; font-weight: 700; letter-spacing: -0.02em; color: var(--heading); text-wrap: balance; }
  .hl { color: var(--accent-text); }
  .lead { margin: 0; max-width: 720px; font-size: clamp(1.0625rem, 0.95rem + 0.5vw, 1.3125rem); line-height: 1.55; color: var(--kpi-label); }
  .ctas { display: flex; flex-wrap: wrap; justify-content: center; gap: 12px; margin-top: 6px; }

  .block { padding: 72px 16px; border-top: 1px solid var(--line); }
  .block.last { border-top: 0; padding-top: 0; }
  h2 { margin: 0; font-size: clamp(1.75rem, 1.3rem + 1.6vw, 2.5rem); font-weight: 700; letter-spacing: -0.01em; color: var(--heading); }
  .sub { margin: 10px 0 0; font-size: 1.0625rem; line-height: 1.55; color: var(--kpi-label); max-width: 680px; }
  .head { display: flex; flex-wrap: wrap; align-items: flex-end; justify-content: space-between; gap: 16px 32px; margin-bottom: 20px; }
  .head .txt { flex: 1 1 480px; min-width: 0; }
  .live { display: inline-flex; align-items: center; gap: 8px; margin-bottom: 8px; font-size: 0.8125rem; font-weight: 600; letter-spacing: 0.06em; text-transform: uppercase; color: var(--accent-text); }
  .live .dot { width: 8px; height: 8px; border-radius: 999px; background: var(--accent); box-shadow: 0 0 0 4px color-mix(in srgb, var(--accent) 25%, transparent); animation: beat 1.6s ease-in-out infinite; }
  .live.day { color: var(--kpi-label); } .live.day .dot { background: var(--muted); box-shadow: none; animation: none; }
  .live.sample { color: var(--sev2-fg); } .live.sample .dot { background: var(--warn); }
  @keyframes beat { 50% { box-shadow: 0 0 0 8px color-mix(in srgb, var(--accent) 0%, transparent); } }
  @media (prefers-reduced-motion: reduce) { .live .dot { animation: none; } }
  .lmap :global(.mapwrap) { aspect-ratio: 16 / 8; border-radius: var(--r-card); }
  .ph { background: var(--card2); border: 1px solid var(--line); }   /* same size as the map until it loads */
  .kpis { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; margin: 14px 0 0; }
  .kpis div { background: var(--card); border: 1px solid var(--card-border); border-radius: 14px; padding: 14px 18px; min-width: 0; }
  .kpis dt { font-size: 0.8125rem; color: var(--kpi-label); }
  .kpis dd { margin: 2px 0 0; font-size: 1.75rem; font-weight: 600; font-variant-numeric: tabular-nums; color: var(--fg); }

  .cards { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; margin-top: 28px; }
  .card { background: var(--card); border: 1px solid var(--card-border); border-radius: 18px; padding: 24px; display: flex; flex-direction: column; gap: 10px; min-width: 0; }
  .ico { width: 44px; height: 44px; border-radius: 12px; display: grid; place-items: center; color: var(--accent-text); background: color-mix(in srgb, var(--accent) 12%, transparent); }
  h3 { margin: 0; font-size: 1.25rem; font-weight: 600; color: var(--heading); }
  .card p { margin: 0; font-size: 1rem; line-height: 1.55; color: var(--kpi-label); }
  .arch { list-style: none; margin: 28px 0 0; padding: 0; display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 28px; }
  .stage { position: relative; background: var(--card); border: 1px solid var(--card-border); border-radius: 18px; padding: 20px; display: flex; flex-direction: column; gap: 12px; min-width: 0; }
  .stage + .stage::before {   /* arrow from the previous stage */
    content: ''; position: absolute; left: -24px; top: 50%; width: 20px; height: 2px; background: var(--accent);
  }
  .stage + .stage::after { content: ''; position: absolute; left: -9px; top: calc(50% - 5px); border: 6px solid transparent; border-left-color: var(--accent); border-right: 0; }
  .sh { display: flex; align-items: center; gap: 10px; }
  .sh .ico { width: 38px; height: 38px; border-radius: 10px; flex: none; }
  .sh h3 { font-size: 1.0625rem; }
  .stage ul { margin: 0; padding-left: 18px; display: flex; flex-direction: column; gap: 6px; font-size: 0.9375rem; line-height: 1.45; color: var(--kpi-label); }
  .under { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 16px; margin-top: 16px; }
  .box { border: 1px dashed var(--line-strong); border-radius: 18px; padding: 18px 20px; display: flex; flex-direction: column; gap: 10px; min-width: 0; }
  .box h3 { font-size: 1rem; }
  .box p { margin: 0; font-size: 0.9375rem; line-height: 1.5; color: var(--kpi-label); }
  .layers { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; font-family: var(--mono); font-size: 0.8125rem; }
  .layers span { padding: 4px 10px; border-radius: 999px; background: color-mix(in srgb, var(--accent) 12%, transparent); color: var(--accent-text); }
  .layers b { color: var(--muted); font-weight: 400; }
  .layers .infra { background: transparent; border: 1px solid var(--line-strong); color: var(--kpi-label); }
  .privs { list-style: none; margin: 28px 0 0; padding: 0; display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
  .privs li { background: var(--card); border: 1px solid var(--card-border); border-radius: 18px; padding: 20px 22px; display: flex; gap: 16px; align-items: flex-start; min-width: 0; }
  .privs .ico { flex: none; }
  .privs h3 { font-size: 1.125rem; }
  .privs p { margin: 4px 0 0; font-size: 0.9375rem; line-height: 1.5; color: var(--kpi-label); }
  .end { border-radius: 24px; padding: 48px 32px; text-align: center; display: flex; flex-direction: column; align-items: center; gap: 14px;
    background: var(--card2); border: 1px solid color-mix(in srgb, var(--accent) 40%, transparent); }
  .end h2 { font-size: clamp(1.625rem, 1.3rem + 1vw, 2.125rem); }
  .end p { margin: 0; font-size: 1.0625rem; color: var(--kpi-label); }
  .end .btn { margin-top: 6px; }
  .foot { margin-top: auto; border-top: 1px solid var(--line); padding: 20px 16px; text-align: center; color: var(--muted); font-size: 0.875rem; }

  @media (max-width: 1100px) {
    .sections { display: none; }
    .menubtn { display: grid; }
  }
  @media (max-width: 900px) {
    .cards, .under, .privs { grid-template-columns: minmax(0, 1fr); }
    .arch { grid-template-columns: minmax(0, 1fr); gap: 26px; }
    .stage + .stage::before { left: 50%; top: -22px; width: 2px; height: 18px; }
    .stage + .stage::after { left: calc(50% - 5px); top: -10px; border: 6px solid transparent; border-top-color: var(--accent); border-bottom: 0; }
    .lmap :global(.mapwrap) { aspect-ratio: 4 / 3; }
  }
  @media (max-width: 560px) {
    .top { gap: 6px; padding-top: 10px; padding-bottom: 10px; }
    .brand { font-size: 1.0625rem; gap: 8px; }
    .seg button { padding: 0 9px; }
    .signin { padding: 0 14px; }
    .hero { padding: 56px 16px 48px; }
    .ctas { flex-direction: column; align-self: stretch; }
    .block { padding: 48px 16px; }
    .lmap :global(.mapwrap) { aspect-ratio: 4 / 5; }
    .kpis { gap: 8px; }
    .kpis div { padding: 10px 12px; }
    .kpis dd { font-size: 1.25rem; }
    .lang { display: none; }
    .round.langbtn { display: grid; }
    .privs li { padding: 16px; gap: 14px; }
    .end { padding: 28px 20px; }
    .end .btn { align-self: stretch; }
    .card { padding: 20px; }
  }
  @media (max-width: 380px) {
    .brand span { display: none; }   /* very narrow phones: the logo alone, so the buttons keep their size */
  }
</style>
