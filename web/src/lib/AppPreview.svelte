<!-- Dashboard preview on the public home page (owner request 2026-10-28; mockup "Home page, full" on the design canvas).
     A drawing of four pages (Overview, Security, Command Center, Servers) built from the app's own labels and theme tokens,
     filled with SAMPLE data: the home page is public, so no real service names, hosts or numbers appear here. Wide screens:
     a browser window with the sidebar and header of the app; phones: a phone frame with the phone layout. The picture is
     hidden from screen readers as a whole (one figure label describes it); the four tabs above it are real tabs. -->
<script>
  import { lang, t } from '../i18n.js';
  import { num, dLabel } from '../format.js';
  import Logo from './Logo.svelte';
  import Icon from './Icon.svelte';
  import { theme } from '../theme.js';

  const DAY = '2026-10-27', PREV = '2026-10-26';
  const TABS = ['overview', 'command-center', 'trends', 'security', 'root-causes', 'availability', 'pods', 'business', 'tracing', 'raw-logs', 'servers'];
  // the same icons as the real sidebar (Sidebar.svelte)
  const ICON = { overview: 'overview', 'command-center': 'globe', trends: 'trend', security: 'shield', 'root-causes': 'search',
                 availability: 'pulse', pods: 'box', business: 'briefcase', tracing: 'route', 'raw-logs': 'terminal', servers: 'server' };
  // the part of the Configuration group that fits the picture (ConfigDialogs.svelte CONFIG, Sidebar.svelte)
  const CONFIG = [['nav.cfg.storage', 'bucket'], ['nav.cfg.kafka', 'broker'], ['nav.cfg.notif', 'bell'], ['nav.collectors', 'radio']];
  const SERVICES = [['api-gateway', 391], ['auth-service', 812], ['coredns', 0], ['orders-service', 81], ['payments-service', 0]];
  const CHECK = [['auth-service', 812], ['api-gateway', 391], ['orders-service', 81]];
  const WEEK = [62, 70, 58, 81, 67, 74, 100];
  // errors per hour of the three services (stacked)
  const HOURS = [[2, 1, 0], [1, 0, 0], [0, 0, 0], [1, 0, 0], [2, 1, 0], [6, 2, 1], [18, 8, 3], [40, 14, 6], [62, 22, 8], [70, 26, 12], [66, 30, 10], [58, 24, 14],
    [52, 20, 9], [60, 28, 16], [74, 30, 20], [80, 34, 18], [64, 26, 12], [40, 18, 8], [22, 10, 4], [14, 6, 3], [10, 4, 2], [8, 3, 2], [6, 2, 1], [4, 2, 1]];
  const MAX = Math.max(...HOURS.map((h) => h[0] + h[1] + h[2]));
  const pct = (v, d) => `${num(v, $lang, d)}%`;

  // four pages, all with sample data (documentation IP ranges, example.com)
  const PV = [['overview', 'overview'], ['security', 'shield'], ['command-center', 'globe'], ['servers', 'server']];
  let tab = $state('overview');
  function tabKey(e) {
    const i = PV.findIndex(([id]) => id === tab), n = { ArrowRight: 1, ArrowLeft: -1 }[e.key];
    if (!n) return;
    e.preventDefault();
    tab = PV[(i + n + PV.length) % PV.length][0];
    document.getElementById(`pv-tab-${tab}`)?.focus();
  }
  const CATS = [['sqli', 612], ['path', 455], ['scan', 358], ['xss', 224], ['rce', 89]];
  const ATTACKERS = [['203.0.113.24', 'NL', 'crit', 812], ['198.51.100.7', 'US', 'crit', 540], ['192.0.2.55', 'SG', 'med', 377], ['203.0.113.90', 'DE', 'med', 203]];
  const URLS = [['14:02', '/wp-login.php', 'scan'], ['13:58', "/api/v1/orders?id=1' OR '1'='1", 'sqli'], ['13:41', '/../../etc/passwd', 'path'], ['13:20', '/search?q=<script>', 'xss']];
  const REQ_H = [3, 2, 1, 1, 2, 5, 12, 26, 38, 44, 41, 39, 36, 42, 48, 52, 44, 31, 20, 14, 10, 8, 6, 4];
  const MODS = [['orders-service', 41230], ['auth-service', 33904], ['payments-service', 21117], ['catalog-service', 18442]];
  const country = (cc) => { try { return new Intl.DisplayNames([$lang], { type: 'region' }).of(cc) || cc; } catch { return cc; } };
  // Servers: groups, hosts (name, system, status, CPU %, memory %, disk %) and the two charts (a smooth sample curve)
  const GROUPS = [['Client A', [['api-01', 'Ubuntu 24.04', 6, 'memory_high', 44, 82, 40], ['web-01', 'Ubuntu 24.04', 0, 'ok', 31, 52, 63], ['db-01', 'Debian 12', 0, 'ok', 12, 66, 71]]],
                  ['Client B', [['win-erp', 'Windows Server 2022', 0, 'ok', 9, 61, 55]]]];
  const tone = (v) => (v >= 85 ? 'err' : v >= 70 ? 'warn' : '');
  const wave = (s, base, amp) => Array.from({ length: 49 }, (_, k) => `${(34 + k * 6.1).toFixed(1)},${(130 - (base + amp * Math.sin((k + s) / 3.2)) * 1.15).toFixed(1)}`).join(' ');
  const SPARK = [['cpu', wave(1, 44, 8), '', ['100%', '50%', '0%'], '44%'], ['memory', wave(4, 72, 4), '34,30 330,30', ['9.3 GB', '4.7 GB', '0 B'], '6.6 GB / 8 GB']];
  const XS = ['04:00', '07:30', '11:00', '14:30', '18:00', '21:30', '01:00'];
  const mapImg = $derived($theme === 'light' ? '/preview/map-light.jpg' : '/preview/map-dark.jpg');
  const title = $derived(tab === 'overview' ? $t('title.overview') : $t(`tab.${tab}`));
  const label = $derived($t({ overview: 'home.pv.label', security: 'home.pv.label_sec', 'command-center': 'home.pv.label_cc', servers: 'home.pv.label_sv' }[tab]));
  const serverCount = (n) => $t(n === 1 ? 'sv.group.count_one' : 'sv.group.count', { n });
</script>

{#snippet tri(up, cls = '')}<svg class="tri {cls}" width="9" height="9" viewBox="0 0 10 10" aria-hidden="true"><path d={up ? 'M5 1.5l4 7H1z' : 'M5 8.5l4-7H1z'} fill="currentColor"></path></svg>{/snippet}
{#snippet sev(k)}<em class="pill {k === 'crit' ? 'err' : 'warn'}">{$t(`home.pv.sev.${k}`)}</em>{/snippet}

<figure class="pv" aria-label={label}>
  <div class="tabs" role="tablist" aria-label={$t('home.pv.tabs')}>
    {#each PV as [id, icon]}
      <button type="button" role="tab" id="pv-tab-{id}" aria-selected={tab === id} tabindex={tab === id ? 0 : -1}
        onclick={() => (tab = id)} onkeydown={tabKey}><Icon name={icon} size={16} />{$t(`tab.${id}`)}</button>
    {/each}
  </div>
  <!-- wide screens: browser window -->
  <div class="win" aria-hidden="true">
    <div class="bar"><i></i><i></i><i></i><span class="url">monishield.example.com/{tab}</span></div>
    <div class="app">
      <div class="side">
        <div class="brand"><span><Logo size={24} /><b>MoniShield</b></span><Icon name="side-close" size={16} /></div>
        <span class="grp">{$t('nav.analysis')}<Icon name="chevron" size={12} /></span>
        {#each TABS as tb}<span class="nav" class:on={tb === tab}><Icon name={ICON[tb]} size={16} /><span class="l">{$t(`tab.${tb}`)}</span>{#if tb === 'security'}<em>{$t('nav.badge_ips', { n: 4 })}</em>{/if}</span>{/each}
        <span class="grp">{$t('nav.services')}<Icon name="chevron" size={12} /></span>
        {#each SERVICES as [s, n]}<span class="nav"><Icon name="server" size={16} /><span class="l">{s}</span>{#if n}<em>{num(n, $lang)}</em>{/if}</span>{/each}
        <span class="grp">{$t('nav.config')}<Icon name="chevron" size={12} /></span>
        {#each CONFIG as [key, icon]}<span class="nav"><Icon name={icon} size={16} /><span class="l">{$t(key)}</span></span>{/each}
      </div>
      <div class="main">
        <div class="hd">
          <b>{title}</b>
          <span class="tools">
            {#if tab !== 'servers'}
              <span class="segs"><span class="on">S3</span><span>Kafka</span><span>Collector</span></span>
              <span class="date"><Icon name="prev" size={14} />{dLabel(DAY, $lang)}<Icon name="chevron" size={14} /><Icon name="next" size={14} /></span>
            {/if}
            <span class="hb"><Icon name="search" size={16} /></span>
            <span class="hb"><Icon name="sync" size={16} /></span>
            <span class="hb wide"><Icon name="globe" size={16} /><b>{$lang.toUpperCase()}</b></span>
            <span class="hb"><Icon name={$theme === 'light' ? 'sun' : 'moon'} size={16} /></span>
            <span class="hb wide user"><span class="av">A</span>{$t('home.pv.admin')}<Icon name="chevron" size={13} /></span>
          </span>
        </div>
        {#if tab === 'overview'}
        <div class="band">
          <div><div><small><b>{$t('kpi.lines')}</b> · {$t('vb.scope')}</small><strong class="big">{num(284910, $lang)}</strong><small>{$t('vb.files', { files: 24, svc: 7, empty: 0, corrupt: 0 })}</small></div>
            <span class="wk">{#each WEEK as h, i}<span class:now={i === 6} style="height:{h}%"></span>{/each}</span></div>
          <div><div><small><b>{$t('kpi.http')}</b> · {$t('vb.scope_http')}</small><strong class="big">{num(131204, $lang)}</strong><small>{$t('vb.rates', { r4: pct(4.1, 1), r5: pct(0.12, 2) })}</small></div>
            <span class="wk b">{#each WEEK as h, i}<span class:now={i === 6} style="height:{h}%"></span>{/each}</span></div>
        </div>
        <div class="st"><div><span class="tag"><i class="dot"></i>{$t('ov.st.check')}</span><b>{$t('ov.st.title', { date: dLabel(DAY, $lang) })}</b>
          <span>{$t('ov.st.err', { n: num(1284, $lang), m: 3, list: 'auth-service, api-gateway, orders-service' })}</span><span>{$t('ov.st.attack', { n: 4 })}</span></div>
          <span class="btn">{$t('tab.root-causes')}</span></div>
        <div class="kpis">
          <div><small>{$t('kpi.error')}</small><strong class="err">{num(1284, $lang)} <i>{@render tri(false)} 11%</i></strong><small>{dLabel(PREV, $lang)}</small></div>
          <div><small>{$t('ov.attack_ips')}</small><strong class="err">4</strong><small>{$t('home.pv.new_today', { n: 2 })}</small></div>
          <div><small>{$t('ov.warn_4xx')}</small><strong class="warn">93 <i>{@render tri(false)} 79%</i></strong><small>{dLabel(PREV, $lang)}</small></div>
          <div><small>{$t('kpi.rate5xx')}</small><strong>{pct(0.12, 2)}</strong><small><i class="dot ok"></i>{$t('ov.safe5')}</small></div>
        </div>
        <div class="row">
          <div class="chart"><b>{$t('ov.err_per_hour')}</b>
            <div class="cols">{#each HOURS as [a, b, c]}<span><i style="height:{(a / MAX) * 100}%"></i><i class="c2" style="height:{(b / MAX) * 100}%"></i><i class="c3" style="height:{(c / MAX) * 100}%"></i></span>{/each}</div></div>
          <div class="chk"><b>{$t('ov.check_title')}</b>{#each CHECK as [s, n]}<span>{s}<em class="pill err">{num(n, $lang)} error</em></span>{/each}<small>{$t('ov.check_rest', { n: 4 })}</small></div>
        </div>
        {:else if tab === 'security'}
          <div class="kpis">
            <div><small>{$t('home.pv.sec.atk')}</small><strong class="err">{num(1932, $lang)}</strong><small>{$t('home.pv.sec.countries', { n: 6 })}</small></div>
            <div><small>{$t('home.pv.sec.ips')}</small><strong class="err">4</strong><small>{$t('home.pv.new_today', { n: 2 })}</small></div>
            <div><small>{$t('home.pv.sec.crit')}</small><strong class="err">37</strong><small>{$t('home.pv.sec.crs')}</small></div>
            <div><small>{$t('home.pv.sec.login')}</small><strong class="warn">11</strong><small>{$t('home.pv.sec.tries', { n: 142 })}</small></div>
          </div>
          <div class="row two">
            <div class="chart"><b>{$t('home.pv.sec.cats')}</b>
              {#each CATS as [c, n]}<span class="hb3"><span>{$t(`home.pv.cat.${c}`)}</span><span class="tr"><i style="width:{(n / 612) * 100}%"></i></span><em>{num(n, $lang)}</em></span>{/each}</div>
            <div class="chart"><b>{$t('home.pv.sec.top')}</b>
              {#each ATTACKERS as [ip, cc, sv, n]}<span class="ipr"><code>{ip}</code><span class="mu">{country(cc)}</span>{@render sev(sv)}<em>{num(n, $lang)}</em></span>{/each}</div>
          </div>
          <div class="chart"><b>{$t('home.pv.sec.urls')}</b>
            {#each URLS as [tm, path, c]}<span class="u"><span class="mu tm">{tm}</span><code>{path}</code><span class="mu">{$t(`home.pv.cat.${c}`)}</span></span>{/each}</div>
        {:else if tab === 'command-center'}
          <div class="kpis">
            <div><small>{$t('kpi.http')}</small><strong>{num(131204, $lang)}</strong><small><i class="ok">{@render tri(true)} 6%</i> {$t('home.pv.vs7')}</small></div>
            <div><small>{$t('home.pv.cc.r5')}</small><strong>158</strong><small><i class="ok">{@render tri(false)} 22%</i> {$t('home.pv.vs7')}</small></div>
            <div><small>{$t('home.pv.cc.ips')}</small><strong>{num(2481, $lang)}</strong><small><i class="ok">{@render tri(true)} 3%</i> {$t('home.pv.vs7')}</small></div>
            <div><small>{$t('home.pv.sec.atk')}</small><strong>{num(1932, $lang)}</strong><small><i class="errc">{@render tri(true)} 41%</i> {$t('home.pv.vs7')}</small></div>
          </div>
          <div class="chart map"><b class="sp">{$t('home.pv.cc.map')}<span class="pill ok"><i class="dot ok"></i>{$t('map.live')}</span></b><img src={mapImg} alt="" loading="lazy" decoding="async" /></div>
          <div class="row">
            <div class="chart"><b class="sp">{$t('home.pv.cc.hours')}<small>{$t('home.pv.cc.peak')}</small></b>
              <div class="cols one">{#each REQ_H as h, i}<span><i class:pk={i === 15} style="height:{(h / 52) * 100}%"></i></span>{/each}</div></div>
            <div class="chart"><b>{$t('home.pv.cc.mods')}</b>
              {#each MODS as [m, n]}<span class="mod">{m}<code>{num(n, $lang)}</code></span>{/each}</div>
          </div>
        {:else}
          <div class="sbar"><span class="intro">{$t('sv.intro')}</span>
            <span class="segs sm"><span>{$t('sv.r.1h')}</span><span class="on">{$t('sv.r.24h')}</span><span>{$t('sv.r.7d')}</span><span>{$t('sv.r.30d')}</span></span></div>
          <div class="banner"><span><b>api-01</b> {$t('sv.u.memory', { current: '1.7 GB', band: '0.8–1.0 GB', z: num(4.2, $lang, 1) })} {$t('sv.u.started', { time: '10:05' })}</span>
            <span class="btn ghost">{$t('sv.u.logs')}</span></div>
          <div class="gf"><span class="on">{$t('sv.group.all')}</span><span>Client A</span><span>Client B</span><span>{$t('sv.group.none')}</span></div>
          {#each GROUPS as [g, hosts]}
            <b class="gh">{g} <span class="mu">{serverCount(hosts.length)}</span></b>
            <div class="hosts">
              {#each hosts as [h, os, ct, st, cpu, mem, disk], i}
                <div class="hc" class:sel={g === 'Client A' && i === 0}>
                  <span class="top"><span class="nm"><b>{h}</b><small>{os}{ct ? ` · ${$t('sv.ct.count', { n: ct })}` : ''}</small></span>
                    <em class="pill {st === 'ok' ? 'ok' : 'warn'}"><i class="dot {st === 'ok' ? 'ok' : 'warnc'}"></i>{$t(`sv.st.${st}`)}</em></span>
                  {#each [['sv.bar.cpu', cpu], ['sv.bar.memory', mem], ['sv.bar.disk', disk]] as [k, v]}
                    <span class="b3"><span class="lb">{$t(k)}</span><span class="tr"><i class={tone(v)} style="width:{v}%"></i></span><span class="v">{num(v, $lang)}%</span></span>
                  {/each}
                </div>
              {/each}
            </div>
          {/each}
          <div class="charts">
            {#each SPARK as [k, p, p2, grid, now]}
              <div class="chart"><span class="sp"><b>{$t(`sv.chart.${k}`)}</b><code>{now}</code></span>
                <svg width="100%" height="150" viewBox="0 0 330 150" preserveAspectRatio="none" aria-hidden="true">
                  {#each grid as l, i}<line x1="34" x2="330" y1={15 + i * 57.5} y2={15 + i * 57.5} class="gl"></line><text x="0" y={18 + i * 57.5} class="gt">{l}</text>{/each}
                  <polyline points={p} fill="none" class="ln" stroke-width="2" vector-effect="non-scaling-stroke"></polyline>
                  {#if p2}<polyline points={p2} fill="none" class="ln2" stroke-width="1.5" stroke-dasharray="5 4" vector-effect="non-scaling-stroke"></polyline>{/if}
                  {#each XS as x, i}<text x={30 + i * 46} y="148" class="gt">{x}</text>{/each}
                </svg>
                <small>{$t(`sv.chart.${k}_cap`)}</small></div>
            {/each}
          </div>
        {/if}
      </div>
    </div>
  </div>

  <!-- phones: phone frame with the phone layout -->
  <div class="phone" aria-hidden="true">
    <div class="phd"><span class="mn"><Icon name="menu" size={16} /></span><b>{title}</b><span class="av">A</span></div>
    {#if tab === 'overview'}
    <div class="band col">
      <div><div><small>{$t('kpi.lines')}</small><strong class="big">{num(284910, $lang)}</strong></div><span class="wk">{#each WEEK as h, i}<span class:now={i === 6} style="height:{h}%"></span>{/each}</span></div>
      <div><div><small>{$t('kpi.http')}</small><strong class="big">{num(131204, $lang)}</strong></div><span class="wk b">{#each WEEK as h, i}<span class:now={i === 6} style="height:{h}%"></span>{/each}</span></div>
    </div>
    <div class="st"><div><span class="tag"><i class="dot"></i>{$t('ov.st.check')}</span><b>{$t('ov.st.title', { date: dLabel(DAY, $lang) })}</b></div></div>
    <div class="list">
      <span>{$t('kpi.error')}<b class="err">{num(1284, $lang)}</b></span>
      <span>{$t('ov.attack_ips')}<b class="err">4</b></span>
      <span>{$t('ov.warn_4xx')}<b class="warn">93</b></span>
      <span>{$t('kpi.rate5xx')}<b>{pct(0.12, 2)}</b></span>
    </div>
    {:else if tab === 'security'}
      <div class="list">
        <span>{$t('home.pv.sec.atk')}<b class="err">{num(1932, $lang)}</b></span>
        <span>{$t('home.pv.sec.ips')}<b class="err">4</b></span>
        <span>{$t('home.pv.sec.crit')}<b class="err">37</b></span>
        <span>{$t('home.pv.sec.login')}<b class="warn">11</b></span>
      </div>
      <div class="chart"><b>{$t('home.pv.sec.cats')}</b>
        {#each CATS.slice(0, 3) as [c, n]}<span class="hb3"><span>{$t(`home.pv.cat.${c}`)}</span><span class="tr"><i style="width:{(n / 612) * 100}%"></i></span><em>{num(n, $lang)}</em></span>{/each}</div>
    {:else if tab === 'command-center'}
      <img class="pmap" src={mapImg} alt="" loading="lazy" decoding="async" />
      <div class="list">
        <span>{$t('kpi.http')}<b>{num(131204, $lang)}</b></span>
        <span>{$t('home.pv.cc.ips')}<b>{num(2481, $lang)}</b></span>
        <span>{$t('home.pv.sec.atk')}<b>{num(1932, $lang)}</b></span>
      </div>
    {:else}
      <div class="banner"><span><b>api-01</b> {$t('sv.u.memory', { current: '1.7 GB', band: '0.8–1.0 GB', z: num(4.2, $lang, 1) })}</span></div>
      {#each GROUPS[0][1].slice(0, 2) as [h, os, ct, st, cpu, mem, disk]}
        <div class="hc">
          <span class="top"><span class="nm"><b>{h}</b><small>{os}</small></span><em class="pill {st === 'ok' ? 'ok' : 'warn'}"><i class="dot {st === 'ok' ? 'ok' : 'warnc'}"></i>{$t(`sv.st.${st}`)}</em></span>
          {#each [['sv.bar.cpu', cpu], ['sv.bar.memory', mem], ['sv.bar.disk', disk]] as [k, v]}
            <span class="b3"><span class="lb">{$t(k)}</span><span class="tr"><i class={tone(v)} style="width:{v}%"></i></span><span class="v">{num(v, $lang)}%</span></span>
          {/each}
        </div>
      {/each}
    {/if}
  </div>
  <figcaption>{$t('home.pv.caption')}</figcaption>
</figure>

<style>
  .pv { margin: 40px auto 0; width: 100%; max-width: 1280px; text-align: left; }
  figcaption { margin-top: 12px; text-align: center; font-size: 0.8125rem; color: var(--muted); }
  small { display: block; font-size: 0.8125rem; color: var(--kpi-label); }
  small b { color: var(--fg); font-weight: 600; }
  .mu { color: var(--kpi-label); }
  strong { display: block; font-weight: 700; line-height: 1.15; color: var(--heading); font-variant-numeric: tabular-nums; font-size: 1.875rem; }
  strong.big { font-size: 2.125rem; }
  strong i, small i { font-style: normal; font-size: 0.875rem; font-weight: 500; display: inline-flex; align-items: center; gap: 3px; }
  .err { color: var(--err); } .warn { color: var(--warn); } .ok { color: var(--ok-text); } .errc { color: var(--err); }
  .tri { flex: none; }
  .dot { display: inline-block; width: 8px; height: 8px; border-radius: 999px; background: currentColor; margin-right: 6px; }
  i.dot.ok { background: var(--ok-text); } i.dot.warnc { background: var(--warn); }
  .pill { font-style: normal; font-size: 0.75rem; font-weight: 600; border-radius: 999px; padding: 3px 10px; white-space: nowrap; display: inline-flex; align-items: center; }
  .pill.ok { color: var(--ok-text); background: color-mix(in srgb, var(--ok-text) 12%, transparent); border: 1px solid color-mix(in srgb, var(--ok-text) 40%, transparent); }
  .pill.warn { color: var(--warn); background: color-mix(in srgb, var(--warn) 10%, transparent); border: 1px solid color-mix(in srgb, var(--warn) 45%, transparent); }
  .pill.err { color: var(--err); background: color-mix(in srgb, var(--err) 12%, transparent); border: 1px solid transparent; }
  code { font-family: var(--mono); font-size: 0.8125rem; }

  .win { border: 1px solid var(--line-strong); border-radius: 18px; overflow: hidden; background: var(--bg);
    box-shadow: 0 40px 100px color-mix(in srgb, var(--accent) 12%, transparent), 0 20px 60px rgb(0 0 0 / 0.3); font-size: 0.875rem; }
  .bar { height: 42px; display: flex; align-items: center; gap: 8px; padding: 0 16px; background: var(--card2); border-bottom: 1px solid var(--line); }
  .bar i { width: 11px; height: 11px; border-radius: 999px; background: var(--line-strong); }
  .url { margin-left: 16px; flex: 0 1 520px; height: 26px; border-radius: 8px; background: var(--card); color: var(--kpi-label); font-size: 0.8125rem; display: flex; align-items: center; padding: 0 14px; }
  .app { display: flex; min-height: 960px; }
  .side { width: 230px; flex: none; background: var(--side-bg); border-right: 1px solid var(--line); padding: 14px 10px; display: flex; flex-direction: column; gap: 1px; align-self: stretch; }
  .brand { display: flex; align-items: center; justify-content: space-between; padding: 2px 8px 14px; color: var(--kpi-label); }
  .brand span { display: flex; align-items: center; gap: 8px; color: var(--fg); font-size: 0.9375rem; }
  .grp { display: flex; align-items: center; justify-content: space-between; padding: 12px 10px 4px; font-size: 0.75rem; font-weight: 600; color: var(--kpi-label); }
  .nav { min-height: 34px; display: flex; align-items: center; gap: 10px; padding: 0 10px; border-radius: 10px; border: 1px solid transparent; color: var(--nav-fg); font-size: 0.84rem; }
  .nav .l { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .nav.on { background: var(--seg-on); color: var(--accent-text); font-weight: 600; border-color: color-mix(in srgb, var(--accent) 45%, transparent); }
  .nav em { font-style: normal; font-size: 0.6875rem; font-weight: 600; color: var(--err); background: color-mix(in srgb, var(--err) 14%, transparent); padding: 1px 7px; border-radius: 999px; }
  .main { flex: 1; min-width: 0; padding: 14px 16px; display: flex; flex-direction: column; gap: 14px; }
  .hd { display: flex; align-items: center; justify-content: space-between; gap: 10px; background: var(--card); border: 1px solid var(--card-border); border-radius: 16px; padding: 10px 14px; }
  .hd > b { font-size: 1.25rem; color: var(--heading); white-space: nowrap; }
  .tools { display: flex; gap: 6px; align-items: center; }
  .segs, .date, .hb { height: 38px; box-sizing: border-box; border: 1px solid var(--line-strong); border-radius: 12px; display: inline-flex; align-items: center; font-size: 0.8125rem; font-weight: 500; color: var(--fg); }
  .segs { padding: 3px; gap: 2px; font-weight: 600; }
  .segs span { padding: 0 10px; height: 100%; display: inline-flex; align-items: center; border-radius: 9px; color: var(--kpi-label); }
  .segs span.on { background: var(--seg-on); color: var(--accent-text); }
  .segs.sm span { padding: 0 12px; }
  .date { gap: 8px; padding: 0 10px; } .date :global(svg) { color: var(--kpi-label); }
  .hb { width: 38px; justify-content: center; gap: 6px; } .hb.wide { width: auto; padding: 0 10px; } .hb b { font-size: 0.75rem; }
  .hb.user { padding: 0 8px 0 4px; font-size: 0.8125rem; }
  .av { width: 28px; height: 28px; border-radius: 999px; background: var(--accent); color: #04201c; font-size: 0.75rem; font-weight: 700; display: grid; place-items: center; flex: none; }
  .band { display: grid; grid-template-columns: 1fr 1fr; background: var(--card); border: 1px solid var(--card-border); border-radius: 16px; }
  .band > div { padding: 14px 18px; display: flex; align-items: flex-end; justify-content: space-between; gap: 10px; min-height: 108px; box-sizing: border-box; }
  .band > div > div { display: flex; flex-direction: column; gap: 4px; }
  .band > div + div { border-left: 1px solid var(--line); }
  .wk { display: flex; align-items: flex-end; gap: 4px; height: 36px; flex: none; }
  .wk span { width: 10px; background: var(--line-strong); opacity: 0.5; border-radius: 1px; }
  .wk span.now { background: var(--c1); opacity: 1; } .wk.b span.now { background: var(--c2); }
  .st { background: var(--card); border: 1px solid color-mix(in srgb, var(--warn) 50%, transparent); border-radius: 16px; padding: 14px 18px; display: flex; align-items: center; gap: 12px; }
  .st > div { flex: 1; display: flex; flex-direction: column; gap: 5px; font-size: 0.875rem; }
  .st > div > b { font-size: 1rem; color: var(--heading); }
  .tag { align-self: flex-start; display: inline-flex; align-items: center; font-size: 0.75rem; font-weight: 600; color: var(--warn); background: color-mix(in srgb, var(--warn) 10%, transparent); border: 1px solid color-mix(in srgb, var(--warn) 45%, transparent); padding: 3px 10px; border-radius: 999px; }
  .tag .dot { background: var(--warn); }
  .btn { min-height: 44px; display: inline-flex; align-items: center; font-size: 0.875rem; font-weight: 600; background: var(--accent); color: #04201c; border-radius: var(--r-ctl); padding: 0 16px; white-space: nowrap; box-sizing: border-box; }
  .btn.ghost { background: var(--card); color: var(--fg); border: 1px solid var(--line-strong); min-height: 40px; font-size: 0.8125rem; padding: 0 14px; }
  .kpis { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }
  .kpis > div { background: var(--card); border: 1px solid var(--card-border); border-radius: 16px; padding: 14px 16px; display: flex; flex-direction: column; gap: 6px; min-width: 0; }
  .kpis small { display: flex; align-items: center; gap: 4px; min-height: 18px; font-size: 0.8125rem; }
  .kpis > div > small:first-child { font-size: 0.875rem; }
  .row { display: grid; grid-template-columns: 2fr 1fr; gap: 12px; }
  .row.two { grid-template-columns: 1fr 1fr; }
  .chart, .chk { background: var(--card); border: 1px solid var(--card-border); border-radius: 16px; padding: 14px 16px; display: flex; flex-direction: column; gap: 10px; min-width: 0; }
  .chart > b, .chk > b { font-size: 0.9375rem; color: var(--heading); }
  .sp { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
  .cols { height: 200px; display: flex; align-items: flex-end; gap: 5px; border-bottom: 1px solid var(--line); }
  .cols span { flex: 1; height: 100%; display: flex; flex-direction: column-reverse; gap: 1px; }
  .cols i { background: var(--c1); border-radius: 1px; } .cols i.c2 { background: var(--c2); } .cols i.c3 { background: var(--c6); }
  .cols.one { height: 150px; } .cols.one i { background: var(--c1); border-radius: 2px; } .cols.one i.pk { background: var(--c2); }
  .chk > span { display: flex; justify-content: space-between; align-items: center; gap: 8px; padding-bottom: 8px; border-bottom: 1px solid var(--line); font-size: 0.875rem; }
  .hb3 { display: grid; grid-template-columns: 170px 1fr 48px; align-items: center; gap: 10px; font-size: 0.8125rem; }
  .hb3 em { font-style: normal; text-align: right; font-family: var(--mono); }
  .tr { display: block; height: 8px; border-radius: 999px; background: var(--line); overflow: hidden; }
  .tr i { display: block; height: 100%; border-radius: 999px; background: var(--err); }
  .tr i.warn { background: var(--warn); } .tr i.err { background: var(--err); }
  .ipr { display: grid; grid-template-columns: 1.2fr 1fr 80px 50px; align-items: center; gap: 6px; font-size: 0.8125rem; padding-bottom: 8px; border-bottom: 1px solid var(--line); }
  .ipr em { font-style: normal; text-align: right; font-family: var(--mono); } .ipr .pill { justify-self: start; }
  .u { display: flex; gap: 12px; font-size: 0.8125rem; padding-bottom: 8px; border-bottom: 1px solid var(--line); }
  .u .tm { width: 60px; flex: none; } .u code { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .map img { display: block; width: 100%; height: 270px; object-fit: cover; background: var(--card2); border-radius: 10px; border: 1px solid var(--line); }
  .mod { display: flex; justify-content: space-between; font-size: 0.8125rem; gap: 8px; }

  .sbar { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
  .intro { font-size: 0.875rem; color: var(--kpi-label); }
  .banner { border-radius: 16px; padding: 10px 16px; background: color-mix(in srgb, var(--warn) 8%, transparent); border: 1px solid color-mix(in srgb, var(--warn) 40%, transparent); display: flex; justify-content: space-between; align-items: center; gap: 12px; font-size: 0.875rem; }
  .gf { display: flex; gap: 6px; flex-wrap: wrap; }
  .gf span { min-height: 44px; display: inline-flex; align-items: center; padding: 0 14px; border-radius: var(--r-ctl); font-size: 0.8125rem; border: 1px solid var(--line-strong); background: var(--card); box-sizing: border-box; }
  .gf span.on { border: 1.5px solid var(--accent); background: var(--seg-on); color: var(--accent-text); font-weight: 600; }
  .gh { font-size: 0.9375rem; color: var(--heading); } .gh .mu { font-weight: 400; font-size: 0.8125rem; }
  .hosts { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }
  .hc { background: var(--card); border: 1px solid var(--card-border); border-radius: 16px; padding: 12px 14px; display: flex; flex-direction: column; gap: 8px; min-width: 0; }
  .hc.sel { border: 1.5px solid var(--accent); background: var(--seg-on); }
  .hc .top { display: flex; justify-content: space-between; align-items: flex-start; gap: 8px; min-height: 40px; }
  .hc .nm { display: flex; flex-direction: column; min-width: 0; } .hc .nm b { font-size: 0.875rem; } .hc .nm small { font-size: 0.75rem; }
  .hc .pill { font-size: 0.6875rem; padding: 2px 8px; }
  .b3 { display: grid; grid-template-columns: 60px 1fr 40px; gap: 8px; align-items: center; font-size: 0.75rem; }
  .b3 .lb { color: var(--kpi-label); } .b3 .v { text-align: right; font-family: var(--mono); }
  .b3 .tr { height: 6px; } .b3 .tr i { background: var(--c1); }
  .charts { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
  .gl { stroke: var(--line); } .gt { font-size: 9px; fill: var(--kpi-label); } .ln { stroke: var(--c1); } .ln2 { stroke: var(--kpi-label); }

  .phone { display: none; width: 300px; margin: 0 auto; border: 8px solid var(--line); border-radius: 36px; overflow: hidden; background: var(--bg); padding: 10px;
    flex-direction: column; gap: 8px; box-shadow: 0 30px 80px color-mix(in srgb, var(--accent) 14%, transparent); font-size: 0.8125rem; box-sizing: border-box; }
  .phd { display: flex; align-items: center; gap: 8px; background: var(--card); border: 1px solid var(--card-border); border-radius: 12px; padding: 8px 10px; }
  .phd > b { flex: 1; font-size: 0.9375rem; color: var(--heading); }
  .mn { width: 32px; height: 32px; border: 1px solid var(--line-strong); border-radius: 9px; display: grid; place-items: center; }
  .phone .av { width: 28px; height: 28px; }
  .band.col { grid-template-columns: 1fr; }
  .band.col > div { min-height: 0; align-items: center; }
  .band.col > div + div { border-left: 0; border-top: 1px solid var(--line); }
  .band.col strong { font-size: 1.5rem; }
  .list { background: var(--card); border: 1px solid var(--card-border); border-radius: 12px; display: flex; flex-direction: column; }
  .list span { display: flex; justify-content: space-between; align-items: center; padding: 9px 12px; font-size: 0.8125rem; color: var(--kpi-label); }
  .list span + span { border-top: 1px solid var(--line); }
  .list b { font-size: 1rem; color: var(--fg); font-variant-numeric: tabular-nums; } .list b.err { color: var(--err); } .list b.warn { color: var(--warn); }
  .phone .hb3 { grid-template-columns: 110px 1fr 36px; }
  .phone .banner { padding: 8px 12px; font-size: 0.75rem; }
  .pmap { display: block; width: 100%; aspect-ratio: 16 / 11; object-fit: cover; border-radius: 12px; border: 1px solid var(--line); }

  .tabs { display: flex; gap: 2px; width: max-content; max-width: 100%; margin: 0 auto 18px; padding: 4px; border: 1px solid var(--line-strong); border-radius: 14px; background: var(--card); }
  .tabs button { font: inherit; font-size: 1rem; font-weight: 600; display: inline-flex; align-items: center; gap: 8px; min-height: 48px; padding: 0 18px;
    border: 0; border-radius: 10px; background: transparent; color: var(--fg); cursor: pointer; white-space: nowrap; }
  .tabs button:hover { color: var(--accent-text); }
  .tabs button[aria-selected='true'] { background: var(--seg-on); color: var(--accent-text); }
  .tabs button:focus-visible { outline: 2px solid var(--focus); outline-offset: 1px; }

  @media (max-width: 1100px) { .side { display: none; } .hosts { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
  @media (max-width: 760px) {
    .win { display: none; }
    .phone { display: flex; }
    .pv { margin-top: 32px; }
  }
  @media (max-width: 560px) {
    .tabs { display: grid; grid-template-columns: 1fr 1fr; width: 100%; box-sizing: border-box; }
    .tabs button { justify-content: center; min-height: 44px; padding: 0 8px; font-size: 0.9375rem; }
  }
</style>
