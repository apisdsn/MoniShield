<!-- Dashboard preview on the public home page (owner request 2026-10-28; mockup "Halaman utama" on the design canvas).
     A drawing of the Overview built from the app's own labels and theme tokens, filled with SAMPLE data: the home page is
     public, so no real service names or numbers appear here. Wide screens: a browser window with the sidebar; phones: a
     phone frame with the phone layout. Hidden from screen readers as a whole (one image label describes it). -->
<script>
  import { lang, t } from '../i18n.js';
  import { num, dLabel } from '../format.js';
  import Logo from './Logo.svelte';
  import Icon from './Icon.svelte';
  import { theme } from '../theme.js';

  const DAY = '2026-10-27', PREV = '2026-10-26';
  const TABS = ['overview', 'command-center', 'trends', 'security', 'root-causes', 'availability', 'pods', 'business', 'tracing'];
  // the same icons as the real sidebar (Sidebar.svelte)
  const ICON = { overview: 'overview', 'command-center': 'globe', trends: 'trend', security: 'shield', 'root-causes': 'search',
                 availability: 'pulse', pods: 'box', business: 'briefcase', tracing: 'route' };
  // the Configuration group of the real sidebar (ConfigDialogs.svelte CONFIG), copied so the home page does not load the dialogs
  const CONFIG = [['storage', 'bucket'], ['kafka', 'broker'], ['maxmind', 'globe'], ['smtp', 'mail'], ['notif', 'bell'], ['blocklist', 'ban'],
                  ['retention', 'archive'], ['public', 'globe'], ['server', 'key']];
  const SERVICES = [['api-gateway', 391], ['auth-service', 812], ['coredns', 0], ['notification-worker', 0], ['orders-service', 81], ['payments-service', 0]];
  const CHECK = [['auth-service', 812], ['api-gateway', 391], ['orders-service', 81]];
  const WEEK = [62, 70, 58, 81, 67, 74, 100];
  // errors per hour of the three services (stacked)
  const HOURS = [[2, 1, 0], [1, 0, 0], [0, 0, 0], [1, 0, 0], [2, 1, 0], [6, 2, 1], [18, 8, 3], [40, 14, 6], [62, 22, 8], [70, 26, 12], [66, 30, 10], [58, 24, 14],
    [52, 20, 9], [60, 28, 16], [74, 30, 20], [80, 34, 18], [64, 26, 12], [40, 18, 8], [22, 10, 4], [14, 6, 3], [10, 4, 2], [8, 3, 2], [6, 2, 1], [4, 2, 1]];
  const MAX = Math.max(...HOURS.map((h) => h[0] + h[1] + h[2]));
  const pct = (v, d) => `${num(v, $lang, d)}%`;

  // tabs: three pages of the dashboard, all with sample data (documentation IP ranges, example.com)
  const PV = [['overview', 'overview'], ['security', 'shield'], ['command-center', 'globe']];
  let tab = $state('overview');
  function tabKey(e) {
    const i = PV.findIndex(([id]) => id === tab), n = { ArrowRight: 1, ArrowLeft: -1 }[e.key];
    if (!n) return;
    e.preventDefault();
    tab = PV[(i + n + PV.length) % PV.length][0];
    document.getElementById(`pv-tab-${tab}`)?.focus();
  }
  const CATS = [['SQL injection', 32, 'err'], ['Path traversal', 21, 'err'], ['Cross-site scripting', 14, 'warn'], ['scanner', 12, 'warn'], ['Remote code execution', 9, 'warn']];
  const ATTACKERS = [['203.0.113.24', 'SG', 31, 'SQL injection'], ['198.51.100.7', 'US', 19, 'Path traversal'], ['192.0.2.45', 'NL', 14, 'scanner'], ['203.0.113.90', 'ID', 11, 'XSS']];
  const URLS = [['GET', "/api/v1/users?id=1' OR '1'='1", 'crit'], ['GET', '/static/../../etc/passwd', 'crit'], ['POST', '/search?q=<script>alert(1)<\/script>', 'med'], ['GET', '/.env', 'med']];
  const REQ_H = [3, 2, 1, 1, 2, 5, 12, 26, 38, 44, 41, 39, 36, 42, 48, 52, 44, 31, 20, 14, 10, 8, 6, 4];
  const MODS = [['auth-service', 41], ['api-gateway', 33], ['orders-service', 16], ['payments-service', 10]];
  const cat = (c) => (c === 'scanner' ? $t('home.pv.sec.scanner') : c);
  const mapImg = $derived($theme === 'light' ? '/preview/map-light.jpg' : '/preview/map-dark.jpg');
  const title = $derived(tab === 'overview' ? $t('title.overview') : $t(`tab.${tab}`));
</script>

<figure class="pv" aria-label={$t(tab === 'overview' ? 'home.pv.label' : tab === 'security' ? 'home.pv.label_sec' : 'home.pv.label_cc')}>
  <div class="tabs" role="tablist" aria-label={$t('home.pv.tabs')}>
    {#each PV as [id, icon]}
      <button type="button" role="tab" id="pv-tab-{id}" aria-selected={tab === id} tabindex={tab === id ? 0 : -1}
        onclick={() => (tab = id)} onkeydown={tabKey}><Icon name={icon} size={15} />{$t(`tab.${id}`)}</button>
    {/each}
  </div>
  <!-- wide screens: browser window -->
  <div class="win" aria-hidden="true">
    <div class="bar"><i></i><i></i><i></i><span class="url">{location.host}/{tab}</span></div>
    <div class="app">
      <div class="side">
        <div class="brand"><Logo size={22} /><b>MoniShield</b></div>
        <span class="grp">{$t('nav.analysis')}</span>
        {#each TABS as tb}<span class="nav" class:on={tb === tab}><Icon name={ICON[tb]} size={13} />{$t(`tab.${tb}`)}</span>{/each}
        <span class="grp">{$t('nav.services')}</span>
        {#each SERVICES as [s, n]}<span class="svc"><span class="sn"><Icon name="server" size={12} />{s}</span>{#if n}<em>{num(n, $lang)}</em>{/if}</span>{/each}
        <span class="grp">{$t('nav.config')}</span>
        {#each CONFIG as [id, icon]}<span class="nav"><Icon name={icon} size={13} />{$t(`nav.cfg.${id}`)}</span>{/each}
      </div>
      <div class="main">
        <div class="hd"><b>{title}</b><span class="pill"><b class="ac">S3</b> · Kafka</span><span class="pill date">◀ {dLabel(DAY, $lang)} ▾ ▶</span><span class="av">AD</span></div>
        {#if tab === 'overview'}
        <div class="band">
          <div><div><small>{$t('kpi.lines')}</small><strong>{num(284910, $lang)}</strong><small class="mu">{$t('vb.files', { files: 24, svc: 7, empty: 0, corrupt: 0 })}</small></div>
            <span class="wk">{#each WEEK as h, i}<span class:now={i === 6} style="height:{h}%"></span>{/each}</span></div>
          <div><div><small>{$t('kpi.http')}</small><strong>{num(131204, $lang)}</strong><small class="mu">{$t('vb.rates', { r4: pct(4.1, 1), r5: pct(0.12, 2) })}</small></div>
            <span class="wk b">{#each WEEK as h, i}<span class:now={i === 6} style="height:{h}%"></span>{/each}</span></div>
        </div>
        <div class="st"><div><span class="tag">● {$t('ov.st.check')}</span><b>{$t('ov.st.title', { date: dLabel(DAY, $lang) })}</b>
          <p>{$t('ov.st.err', { n: num(1284, $lang), m: 3, list: 'auth-service, api-gateway, orders-service' })}</p><p>{$t('ov.st.attack', { n: 4 })}</p></div>
          <span class="btn">{$t('tab.root-causes')}</span></div>
        <div class="kpis">
          <div><small>{$t('kpi.error')}</small><strong class="err">{num(1284, $lang)} <i>▼ 11%</i></strong><small class="mu">{dLabel(PREV, $lang)}</small></div>
          <div><small>{$t('ov.attack_ips')}</small><strong class="err">4</strong></div>
          <div><small>{$t('ov.warn_4xx')}</small><strong class="warn">93 <i>▼ 79%</i></strong><small class="mu">{dLabel(PREV, $lang)}</small></div>
          <div><small>{$t('kpi.rate5xx')}</small><strong>{pct(0.12, 2)}</strong><small class="mu">● {$t('ov.safe5')}</small></div>
        </div>
        <div class="row">
          <div class="chart"><b>{$t('ov.err_per_hour')}</b>
            <div class="cols">{#each HOURS as [a, b, c]}<span><i style="height:{(a / MAX) * 100}%"></i><i class="c2" style="height:{(b / MAX) * 100}%"></i><i class="c3" style="height:{(c / MAX) * 100}%"></i></span>{/each}</div></div>
          <div class="chk"><b>{$t('ov.check_title')}</b>{#each CHECK as [s, n]}<span>{s}<em>{num(n, $lang)} error</em></span>{/each}<small class="mu">{$t('ov.check_rest', { n: 4 })}</small></div>
        </div>
        {:else if tab === 'security'}
          <div class="kpis">
            <div><small>{$t('home.pv.sec.atk')}</small><strong class="err">88 <i>▲ 34%</i></strong><small class="mu">{$t('home.pv.vs7')}</small></div>
            <div><small>{$t('home.pv.sec.ips')}</small><strong>14</strong><small class="mu">{$t('home.pv.sec.countries', { n: 6 })}</small></div>
            <div><small>{$t('home.pv.sec.crit')}</small><strong class="err">5</strong><small class="mu">{$t('home.pv.sec.crs')}</small></div>
            <div><small>{$t('home.pv.sec.login')}</small><strong class="warn">4</strong><small class="mu">{$t('home.pv.sec.tries', { n: 27 })}</small></div>
          </div>
          <div class="row sec">
            <div class="chart"><b>{$t('home.pv.sec.cats')}</b>
              {#each CATS as [c, n, k]}<span class="hb"><span>{cat(c)}</span><span class="tr"><i class={k} style="width:{(n / 32) * 100}%"></i></span><em>{n}</em></span>{/each}</div>
            <div class="chk ips"><b class="sp">{$t('home.pv.sec.top')}<span class="mini"><Icon name="ban" size={11} />{$t('bl.open')}</span></b>
              {#each ATTACKERS as [ip, cc, n, r]}<span><code>{ip}</code><small class="mu">{cc}</small><em class="n">{n}</em><small>{cat(r)}</small></span>{/each}</div>
          </div>
          <div class="chart urls"><b>{$t('home.pv.sec.urls')}</b>
            {#each URLS as [m, path, sv]}<span class="u"><small class="mu">{m}</small><code><b>api.example.com</b>{path}</code><em class={sv}>{$t(`home.pv.sev.${sv}`)}</em></span>{/each}</div>
        {:else}
          <div class="kpis">
            <div><small>{$t('kpi.http')}</small><strong>{num(131204, $lang)} <i class="mu2">▲ 6%</i></strong><small class="mu">{$t('home.pv.vs7')}</small></div>
            <div><small>{$t('home.pv.cc.r5')}</small><strong>158 <i class="ok">▼ 12%</i></strong><small class="mu">{$t('home.pv.cc.rate', { p: pct(0.12, 2) })}</small></div>
            <div><small>{$t('home.pv.cc.ips')}</small><strong>{num(2841, $lang)}</strong><small class="mu">{$t('home.pv.cc.places', { n: 107 })}</small></div>
            <div><small>{$t('map.kpi.countries')}</small><strong>11</strong><small class="mu">{$t('home.pv.cc.share', { p: '94%' })}</small></div>
          </div>
          <div class="row cc">
            <div class="chart"><b class="sp">{$t('home.pv.cc.map')}<span class="lv">● {$t('map.live')}</span></b><img src={mapImg} alt="" loading="lazy" decoding="async" /></div>
            <div class="stack">
              <div class="chart"><b>{$t('home.pv.cc.hours')}</b>
                <div class="cols one">{#each REQ_H as h, i}<span><i class:pk={i === 15} style="height:{(h / 52) * 100}%"></i></span>{/each}</div>
                <small class="mu">{$t('home.pv.cc.peak')}</small></div>
              <div class="chk grow"><b>{$t('home.pv.cc.mods')}</b>
                {#each MODS as [m, p]}<span class="mb">{m}<span class="tr"><i style="width:{(p / 41) * 100}%"></i></span><small class="mu">{p}%</small></span>{/each}</div>
            </div>
          </div>
        {/if}
      </div>
    </div>
  </div>

  <!-- phones: phone frame with the phone layout -->
  <div class="phone" aria-hidden="true">
    <div class="hd"><span class="mn">☰</span><b>{title}</b><span class="av">AD</span></div>
    {#if tab === 'overview'}
    <div class="band col">
      <div><div><small>{$t('kpi.lines')}</small><strong>{num(284910, $lang)}</strong></div><span class="wk">{#each WEEK as h, i}<span class:now={i === 6} style="height:{h}%"></span>{/each}</span></div>
      <div><div><small>{$t('kpi.http')}</small><strong>{num(131204, $lang)}</strong></div><span class="wk b">{#each WEEK as h, i}<span class:now={i === 6} style="height:{h}%"></span>{/each}</span></div>
    </div>
    <div class="st"><div><span class="tag">● {$t('ov.st.check')}</span><b>{$t('ov.st.title', { date: dLabel(DAY, $lang) })}</b></div></div>
    <div class="list">
      <span>{$t('kpi.error')}<b class="err">{num(1284, $lang)}</b></span>
      <span>{$t('ov.attack_ips')}<b class="err">4</b></span>
      <span>{$t('ov.warn_4xx')}<b class="warn">93</b></span>
      <span>{$t('kpi.rate5xx')}<b>{pct(0.12, 2)}</b></span>
    </div>
    {:else if tab === 'security'}
      <div class="list">
        <span>{$t('home.pv.sec.atk')}<b class="err">88</b></span>
        <span>{$t('home.pv.sec.ips')}<b>14</b></span>
        <span>{$t('home.pv.sec.crit')}<b class="err">5</b></span>
        <span>{$t('home.pv.sec.login')}<b class="warn">4</b></span>
      </div>
      <div class="chart"><b>{$t('home.pv.sec.cats')}</b>
        {#each CATS.slice(0, 3) as [c, n, k]}<span class="hb"><span>{cat(c)}</span><span class="tr"><i class={k} style="width:{(n / 32) * 100}%"></i></span><em>{n}</em></span>{/each}</div>
    {:else}
      <img class="pmap" src={mapImg} alt="" loading="lazy" decoding="async" />
      <div class="list">
        <span>{$t('kpi.http')}<b>{num(131204, $lang)}</b></span>
        <span>{$t('home.pv.cc.ips')}<b>{num(2841, $lang)}</b></span>
        <span>{$t('map.kpi.countries')}<b>11</b></span>
      </div>
    {/if}
  </div>
  <figcaption>{$t('home.pv.caption')}</figcaption>
</figure>

<style>
  .pv { margin: 56px auto 0; width: 100%; max-width: 1180px; text-align: left; }
  figcaption { margin-top: 12px; text-align: center; font-size: 0.8125rem; color: var(--muted); }
  small { display: block; font-size: 0.6875rem; color: var(--kpi-label); }
  small.mu, .mu { color: var(--muted); font-size: 0.625rem; }
  strong { display: block; font-weight: 600; line-height: 1.15; color: var(--fg); font-variant-numeric: tabular-nums; }
  strong i { font-style: normal; font-size: 0.6875rem; }
  .err { color: var(--err); } .warn { color: var(--warn); } .ac { color: var(--accent-text); }

  .win { border: 1px solid var(--line-strong); border-radius: 16px; overflow: hidden; background: var(--bg);
    box-shadow: 0 40px 100px color-mix(in srgb, var(--accent) 12%, transparent), 0 20px 60px rgb(0 0 0 / 0.35); font-size: 12px; }
  .bar { height: 32px; display: flex; align-items: center; gap: 7px; padding: 0 14px; background: var(--card2); border-bottom: 1px solid var(--line); }
  .bar i { width: 10px; height: 10px; border-radius: 999px; background: var(--line-strong); }
  .url { margin-left: 12px; flex: 0 1 420px; height: 20px; border-radius: 6px; background: var(--bg); color: var(--muted); font-size: 10.5px; display: flex; align-items: center; padding: 0 10px; }
  .app { display: flex; }
  .side { width: 180px; flex: none; background: var(--side-bg); border-right: 1px solid var(--line); padding: 12px 10px; display: flex; flex-direction: column; gap: 1px; }
  .brand { display: flex; align-items: center; gap: 8px; padding: 0 6px 10px; font-size: 14px; }
  .grp { font-size: 9.5px; font-weight: 600; letter-spacing: 0.06em; text-transform: uppercase; color: var(--muted); padding: 8px 8px 4px; }
  .nav { height: 25px; display: flex; align-items: center; gap: 8px; padding: 0 8px; border-radius: 7px; font-size: 11px; color: var(--nav-fg); }
  .nav.on { background: var(--seg-on); color: var(--accent-text); font-weight: 600; }
  .sn { display: inline-flex; align-items: center; gap: 7px; min-width: 0; }
  .svc { height: 23px; display: flex; align-items: center; justify-content: space-between; padding: 0 8px; font-size: 10.5px; color: var(--nav-fg); }
  .svc em, .chk em { font-style: normal; font-size: 9.5px; color: var(--err); background: color-mix(in srgb, var(--err) 14%, transparent); padding: 1px 7px; border-radius: 999px; }
  .main { flex: 1; min-width: 0; padding: 12px; display: flex; flex-direction: column; gap: 10px; }
  .hd { display: flex; align-items: center; gap: 8px; background: var(--card); border: 1px solid var(--card-border); border-radius: 12px; padding: 9px 12px; }
  .hd > b { flex: 1; font-size: 16px; color: var(--heading); }
  .pill { font-size: 10.5px; border: 1px solid var(--line-strong); border-radius: 999px; padding: 4px 10px; white-space: nowrap; }
  .av { width: 24px; height: 24px; border-radius: 999px; background: var(--accent); color: #04201c; font-size: 9.5px; font-weight: 700; display: grid; place-items: center; flex: none; }
  .band { display: grid; grid-template-columns: 1fr 1fr; background: var(--card); border: 1px solid var(--card-border); border-radius: 12px; }
  .band > div { padding: 10px 14px; display: flex; align-items: center; justify-content: space-between; gap: 10px; }
  .band > div + div { border-left: 1px solid var(--line); }
  .band strong { font-size: 28px; }
  .wk { display: flex; align-items: flex-end; gap: 3px; height: 30px; flex: none; }
  .wk span { width: 7px; background: var(--line-strong); opacity: 0.5; border-radius: 1px; }
  .wk span.now { background: var(--c1); opacity: 1; } .wk.b span.now { background: var(--c2); }
  .st { background: var(--card); border: 1px solid color-mix(in srgb, var(--warn) 50%, transparent); border-radius: 12px; padding: 10px 14px; display: flex; align-items: center; gap: 12px; }
  .st > div { flex: 1; display: flex; flex-direction: column; gap: 4px; }
  .st b { font-size: 13px; color: var(--heading); }
  .st p { margin: 0; font-size: 11px; color: var(--kpi-label); }
  .tag { align-self: flex-start; font-size: 10px; font-weight: 600; color: var(--warn); background: color-mix(in srgb, var(--warn) 14%, transparent); padding: 2px 9px; border-radius: 999px; }
  .btn { font-size: 11px; font-weight: 600; background: var(--accent); color: #04201c; border-radius: 999px; padding: 8px 14px; white-space: nowrap; }
  .kpis { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; }
  .kpis > div { background: var(--card); border: 1px solid var(--card-border); border-radius: 12px; padding: 10px 12px; display: flex; flex-direction: column; gap: 3px; min-width: 0; }
  .kpis strong { font-size: 24px; }
  .row { flex: 1; display: grid; grid-template-columns: 2fr 1fr; gap: 10px; }
  .chart, .chk { background: var(--card); border: 1px solid var(--card-border); border-radius: 12px; padding: 10px 12px; display: flex; flex-direction: column; gap: 6px; min-width: 0; }
  .chart b, .chk b { font-size: 11.5px; color: var(--heading); }
  .cols { height: 120px; flex: 1; display: flex; align-items: flex-end; gap: 4px; border-bottom: 1px solid var(--line); }
  .cols span { flex: 1; height: 100%; display: flex; flex-direction: column-reverse; gap: 1px; }
  .cols i { background: var(--c1); border-radius: 1px; } .cols i.c2 { background: var(--c2); } .cols i.c3 { background: var(--c6); }
  .chk > span { display: flex; justify-content: space-between; align-items: center; gap: 8px; padding: 6px 0; border-bottom: 1px solid var(--line); font-size: 11px; }

  .phone { display: none; width: 280px; margin: 0 auto; border: 8px solid var(--line); border-radius: 36px; overflow: hidden; background: var(--bg); padding: 10px;
    flex-direction: column; gap: 8px; box-shadow: 0 30px 80px color-mix(in srgb, var(--accent) 14%, transparent); font-size: 12px; }
  .phone .hd > b { font-size: 13px; }
  .mn { width: 24px; height: 24px; border: 1px solid var(--line-strong); border-radius: 7px; display: grid; place-items: center; font-size: 11px; }
  .band.col { grid-template-columns: 1fr; }
  .band.col > div + div { border-left: 0; border-top: 1px solid var(--line); }
  .band.col strong { font-size: 21px; }
  .list { background: var(--card); border: 1px solid var(--card-border); border-radius: 12px; display: flex; flex-direction: column; }
  .list span { display: flex; justify-content: space-between; align-items: center; padding: 8px 12px; font-size: 11px; color: var(--kpi-label); }
  .list span + span { border-top: 1px solid var(--line); }
  .list b { font-size: 15px; color: var(--fg); } .list b.err { color: var(--err); } .list b.warn { color: var(--warn); }

  .tabs { display: flex; gap: 4px; width: max-content; max-width: 100%; margin: 0 auto 18px; padding: 4px; border: 1px solid var(--line-strong);
    border-radius: 999px; background: var(--card2); overflow-x: auto; scrollbar-width: none; }
  .tabs button { font: inherit; font-size: 0.875rem; font-weight: 600; display: inline-flex; align-items: center; gap: 7px; min-height: 40px; padding: 0 16px;
    border: 0; border-radius: 999px; background: transparent; color: var(--nav-fg); cursor: pointer; white-space: nowrap; }
  .tabs button:hover { color: var(--fg); }
  .tabs button[aria-selected='true'] { background: var(--seg-on); color: var(--accent-text); }
  .tabs button:focus-visible { outline: 2px solid var(--focus); outline-offset: 1px; }
  strong i.ok { color: var(--ok-text); } strong i.mu2 { color: var(--muted); }
  .sp { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
  .mini { white-space: nowrap; font-size: 9.5px; font-weight: 500; border: 1px solid var(--line-strong); border-radius: 999px; padding: 2px 8px; display: inline-flex; gap: 5px; align-items: center; color: var(--nav-fg); }
  .hb { display: grid; grid-template-columns: 128px 1fr 22px; align-items: center; gap: 8px; font-size: 10.5px; color: var(--kpi-label); padding: 2px 0; }
  .hb em, .chk em.n { font-style: normal; text-align: right; font-variant-numeric: tabular-nums; color: var(--fg); }
  .tr { display: block; height: 7px; border-radius: 4px; background: var(--line); }
  .tr i { display: block; height: 100%; border-radius: 4px; background: var(--c6); } .tr i.err { background: var(--err); } .tr i.warn { background: var(--warn); }
  .row.sec { flex: none; grid-template-columns: 1.2fr 1fr; }
  code { font-family: var(--mono, ui-monospace, monospace); font-size: 10px; }
  .chk.ips span { display: grid; grid-template-columns: 1fr 24px 26px 1fr; gap: 6px; }
  .chk.ips em.n { background: none; padding: 0; color: var(--fg); font-size: 11px; }
  .urls { flex: 1; }
  .u { display: flex; align-items: center; gap: 8px; padding: 5px 0; border-top: 1px solid var(--line); font-size: 10.5px; }
  .u code { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; } .u code b { font-weight: 600; color: var(--fg); }
  .u em { font-style: normal; font-size: 9px; font-weight: 600; padding: 1px 8px; border-radius: 999px; border: 1px solid currentColor; }
  .u em.crit { color: var(--err); } .u em.med { color: var(--warn); }
  .row.cc { grid-template-columns: 1.65fr 1fr; }
  /* contain: the whole map stays in view; the card's background is the map's sea colour */
  .cc img { display: block; width: 100%; flex: 1; min-height: 0; object-fit: contain; background: var(--card2); border-radius: 10px; border: 1px solid var(--line); }
  .lv { font-size: 9.5px; font-weight: 700; letter-spacing: 0.06em; color: var(--accent-text); }
  .stack { display: flex; flex-direction: column; gap: 10px; min-width: 0; } .grow { flex: 1; }
  .cols.one { flex: none; height: 110px; } .cols.one i { background: var(--c1); } .cols.one i.pk { background: var(--c2); }
  .chk span.mb { display: grid; grid-template-columns: 1fr 80px 30px; gap: 8px; }
  .pmap { display: block; width: 100%; aspect-ratio: 16 / 11; object-fit: cover; border-radius: 12px; border: 1px solid var(--line); }
  .phone .hb { grid-template-columns: 110px 1fr 20px; }

  @media (max-width: 1100px) { .side { display: none; } }
  @media (max-width: 560px) { .tabs button { padding: 0 12px; font-size: 0.8125rem; } .tabs button :global(svg) { display: none; } }
  @media (max-width: 760px) {
    .win { display: none; }
    .phone { display: flex; }
    .pv { margin-top: 40px; }
  }
</style>
