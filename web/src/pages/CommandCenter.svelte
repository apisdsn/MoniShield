<!-- Command Center (Stage 22, DRD §12, TRD §12): absorbs the IP Map tab (ASSUMPTION DRD §12) at the same address (#/peta, ?modul=).
     One request: GET /api/folders/{folder}/command[?module=…] = main KPIs (+ previous folder) + "what needs attention"
     + hourly + map data (IP Map response). Layout: 6 operational KPIs with ▲/▼ change vs the previous folder ·
     module picker + map numbers · map as wide and tall as the screen (main content, owner request) · attention card ·
     2 hourly charts (requests; 5xx & attacks — different scales, so two charts, not two axes) · flow table.
     Source = log folders (Kafka deferred, Stage 23); refreshed on ingest or "Muat ulang". Changing the module only filters the
     map; map position and zoom are kept. Stage 24 item 9: "Unduh ringkasan (PDF)" = browser print of one landscape A4 page
     (KPIs, map, attention items) in the light theme; no PDF library on the server. -->
<script>
  import { tick } from 'svelte';
  import { get } from 'svelte/store';
  import { lang, t } from '../i18n.js';
  import { api } from '../api.js';
  import { theme } from '../theme.js';
  import { num, delta, dLabel, sysName } from '../format.js';
  import { APP_NAME } from '../brand.js';
  import { load as loadPref, save as savePref } from '../store.js';
  import { route, go, build } from '../state.js';
  import Kpi from '../lib/Kpi.svelte';
  import Alert from '../lib/Alert.svelte';
  import ChartCard from '../lib/ChartCard.svelte';
  import FlowMap from '../lib/FlowMap.svelte';
  import Note from '../lib/Note.svelte';
  import Skeleton from '../lib/Skeleton.svelte';
  import ErrorState from '../lib/ErrorState.svelte';
  import Icon from '../lib/Icon.svelte';

  let { folder, server = null, reloadKey = 0, onready = null } = $props();
  let data = $state.raw(null), busy = $state(false), error = $state(null), printing = $state(false), printedAt = $state(''), snap = $state('');
  let seq = 0;
  const module = $derived($route.module || null);
  async function load() {
    const my = ++seq;
    busy = true; error = null; onready?.(false);
    try {
      const q = module ? `?module=${encodeURIComponent(module)}` : '';
      const j = await api.get(`/api/folders/${encodeURIComponent(folder)}/command${q}`);
      if (my === seq) data = j;
    } catch (e) {
      if (my === seq) {
        if (e.status === 404 && module) go({ module: null }, { replace: true });   // module not in this folder -> all modules
        else error = e;
      }
    } finally {
      if (my === seq) { busy = false; onready?.(true); }
    }
  }
  $effect(() => { void [folder, module, reloadKey]; if (folder) load(); });

  // change vs the previous folder; ingress-based KPIs are compared only when yesterday's ingress log is comparable (Overview rule)
  const NGX = new Set(['requests', 'n5xx', 'upstream_errors', 'attack_ips']);
  // comparison (owner request 2026-10-07): average of comparable folders (default) or the previous folder; per browser
  let cmp = $state(loadPref('cc_cmp', 'avg') === 'prev' ? 'prev' : 'avg');
  const setCmp = (v) => { cmp = v; savePref('cc_cmp', v); };
  const d = (key, good = false) => {
    const v = data?.kpi[key], b = data?.baseline;
    if (v === null || v === undefined) return null;
    const avgN = b ? (NGX.has(key) ? b.n_nginx : b.n_all) : 0;
    if (cmp === 'avg' && b && b.kpi[key] !== null && b.kpi[key] !== undefined)
      return delta(v, b.kpi[key], null, $lang, { good, label: $t('cc.cmp.avg_label', { n: avgN, v: num(b.kpi[key], $lang) }) });
    const p = data?.prev;
    if (!p || p.kpi[key] === null) return null;
    return delta(v, p.kpi[key], p.folder, $lang, { good, comparable: p.comparable[NGX.has(key) ? 'nginx' : 'all'] });
  };
  const avgMissing = $derived(cmp === 'avg' && data?.baseline && data.baseline.n_all < 3);

  // attention items: key + numbers from the server, sentences from the dictionary, links to their source page
  const items = $derived((data?.attention || []).map((a) => {
    const p = { n: num(a.n, $lang), ips: num(a.ips ?? 0, $lang), resets: num(a.resets ?? 0, $lang), kind: a.kind ?? '', upstream: a.upstream ?? '',
                top: num(a.top ?? 0, $lang), total: num(a.total ?? 0, $lang), templates: num(a.templates ?? 0, $lang), prev: num(a.prev ?? 0, $lang),
                date: a.prev_folder ? dLabel(a.prev_folder, $lang) : '', service: sysName(a.service ?? '') };
    if (a.basis === 'avg') p.days = num(a.days ?? 0, $lang);
    const text = a.key === 'n5xx' && !a.upstream ? $t('cc.a.n5xx.text_plain') : a.key === 'login' && !a.resets ? $t('cc.a.login.text_none')
      : a.basis === 'avg' ? $t(`cc.a.${a.key}.text_avg`, p) : $t(`cc.a.${a.key}.text`, p);
    const svc = a.tab === 'layanan';
    return { title: $t(`cc.a.${a.key}.title`, p), text, tone: a.tone, link: $t('cc.open', { page: svc ? p.service : $t(`tab.${a.tab}`) }),
             href: build({ tab: a.tab, service: svc ? a.service : null, folder, module: null }) };
  }));
  const hours = $derived(data?.by_hour?.hours || []);

  async function printSummary() {
    const prev = get(theme);
    printing = true;
    printedAt = new Intl.DateTimeFormat($lang === 'en' ? 'en-GB' : 'id-ID', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Asia/Jakarta' }).format(new Date());
    if (prev !== 'light') theme.set('light');   // paper: light theme; map & charts redraw with light tokens
    await tick();
    await new Promise((r) => setTimeout(r, 1200));   // give the map time to finish redrawing
    // the map is printed as an image: a screen-sized WebGL canvas does not adapt to the paper width
    try { snap = document.querySelector('main .mapwrap.tall canvas')?.toDataURL('image/png') || ''; } catch { snap = ''; }
    await tick();
    // restore the view after the print dialog closes (afterprint; Firefox does not block in print()); 2-minute fallback
    let done = false;
    const restore = () => { if (done) return; done = true; snap = ''; if (prev !== 'light') theme.set(prev); printing = false; };
    window.addEventListener('afterprint', restore, { once: true });
    setTimeout(restore, 120000);
    window.print();
  }
</script>

{#if error && !data}
  <ErrorState {error} onretry={load} />
{:else if !data}
  <Skeleton kpis={6} charts={1} />
{:else}
  {@const k = data.kpi}
  {@const m = data.map}
  <div class="content" class:dim={busy} class:printing>
    <div class="print-only phead">
      <b>{APP_NAME} — {$t('cc.print.title')}</b>
      <span>{$t('cc.print.sub', { date: dLabel(folder, $lang), at: printedAt })}</span>
    </div>
    <div class="ccbar no-print">
      <button class="btn" onclick={printSummary} disabled={printing}><Icon name="file" size={16} /> {$t('cc.print.button')}</button>
      <span class="muted small">{$t('cc.print.hint')}</span>
      <span class="cmp">
        <span class="muted small" id="cmp-l">{$t('cc.cmp.label')}</span>
        <span class="seg" role="radiogroup" aria-labelledby="cmp-l">
          <button role="radio" aria-checked={cmp === 'avg'} onclick={() => setCmp('avg')}>{$t('cc.cmp.avg', { n: data?.baseline?.window ?? 7 })}</button>
          <button role="radio" aria-checked={cmp === 'prev'} onclick={() => setCmp('prev')}>{$t('cc.cmp.prev')}</button>
        </span>
      </span>
    </div>
    {#if avgMissing}<p class="muted small cmpnote no-print">{$t('cc.cmp.not_enough', { n: data.baseline.n_all })}</p>{/if}
    <div class="kpis cc">
      <Kpi icon="pulse" label={$t('cc.kpi.requests')} value={k.requests} missing={$t('cc.no_nginx')} delta={d('requests', true)} />
      <Kpi icon="alert" label={$t('cc.kpi.n5xx')} value={k.n5xx} tone={k.n5xx ? 'err' : null} missing={$t('cc.no_nginx')} delta={d('n5xx')} />
      <Kpi icon="alert" label={$t('cc.kpi.errors')} value={k.errors} tone={k.errors ? 'err' : null} delta={d('errors')} />
      <Kpi icon="server" label={$t('cc.kpi.upstream')} value={k.upstream_errors} tone={k.upstream_errors ? 'err' : null} delta={d('upstream_errors')} />
      <Kpi icon="shield" label={$t('cc.kpi.attack_ips')} value={k.attack_ips} tone={k.attack_ips ? 'warn' : null} delta={d('attack_ips')} />
      <Kpi icon="key" label={$t('cc.kpi.login_ips')} value={k.login_fail_ips} tone={k.login_fail_ips ? 'warn' : null} delta={d('login_fail_ips')} />
    </div>

    {#snippet attention()}
      {#if snap}<figure class="snap"><img src={snap} alt={$t('map.title')} /><figcaption>{$t('map.title')} · {$t('map.lg.sentence', { abroad: num(m.abroad_requests, $lang), unloc: num(m.unlocated_requests, $lang) })} · {$t('map.attr_pre')} MaxMind · GeoNames · Natural Earth</figcaption></figure>{/if}
      {#if items.length}
        <Alert title={$t('cc.attention')} {items} />
      {:else}
        <section class="card calm" aria-label={$t('cc.attention')}><h2>{$t('cc.attention')}</h2><p class="muted">{$t('cc.none')}</p></section>
      {/if}
      {#if hours.length}
        <div class="grid hourly no-print">
          <ChartCard title={$t('cc.hour.requests')} type="bar" timeAxis labels={hours} chip={$t('chip.hourly')}
            datasets={[{ label: $t('cc.kpi.requests'), data: data.by_hour.requests, color: '--accent' }]} options={{ plugins: { legend: { display: false } } }} />
          <ChartCard title={$t('cc.hour.problems')} type="line" timeAxis labels={hours} chip={$t('chip.hourly')}
            datasets={[{ label: $t('cc.kpi.n5xx'), data: data.by_hour.n5xx, color: '--err' }, { label: $t('cc.hour.attacks'), data: data.by_hour.attacks, color: '--warn' }]} />
        </div>
      {/if}
    {/snippet}

    {#if m.available}
      <div class="modsel">
        <label for="map-mod" class="sr-only">{$t('map.module')}</label>
        <select id="map-mod" class="no-print" value={module ?? ''} onchange={(e) => go({ module: e.currentTarget.value || null })}>
          <option value="">{$t('map.all_modules')}</option>
          {#each m.modules as x}<option value={x}>{x}</option>{/each}
        </select>
        <dl class="mapstats" aria-label={$t('cc.map_stats')}>
          {#each [['source_ips', 'ips'], ['locations', 'locations'], ['countries', 'countries'], ['modules', 'modules'], ['dest_pods', 'pods'], ['requests', 'requests']] as [key, lbl]}
            <div><dt>{$t(`map.kpi.${lbl}`)}</dt><dd>{num(m.kpi[key], $lang)}</dd></div>
          {/each}
        </dl>
      </div>
      <div class="grid">
        <FlowMap data={m} {folder} module={m.module} {server} aside={attention} tall />
      </div>
    {:else}
      <div class="grid">{@render attention()}</div>
      <Note>{$t('map.no_nginx')}</Note>
    {/if}
  </div>
{/if}

<style>
  .content { transition: opacity 0.15s; }
  .content.dim { opacity: 0.6; }
  .cmp { margin-left: auto; display: inline-flex; align-items: center; gap: 8px; flex-wrap: wrap; }
  .cmpnote { margin: -6px 0 10px; text-align: right; }
  .ccbar { display: flex; flex-wrap: wrap; align-items: center; justify-content: flex-end; gap: 6px 12px; margin: -4px 0 12px; }
  .ccbar .btn { display: inline-flex; align-items: center; gap: 6px; }
  .small { font-size: 0.75rem; }
  .modsel { display: flex; flex-wrap: wrap; align-items: center; gap: 10px 22px; margin-bottom: 14px; }
  .modsel select { min-width: 220px; max-width: 100%; }
  .mapstats { display: flex; flex-wrap: wrap; gap: 6px 18px; margin: 0; font-size: 0.8125rem; }
  .mapstats div { display: flex; gap: 6px; align-items: baseline; }
  .mapstats dt { color: var(--muted); }
  .mapstats dd { margin: 0; color: var(--fg); font-weight: 600; font-variant-numeric: tabular-nums; }
  .calm h2 { font-size: 0.9375rem; font-weight: 600; color: var(--heading); margin: 0 0 8px; }
  .calm p { margin: 0; font-size: 0.8125rem; }
  .hourly { margin-top: 0; }
  .print-only { display: none; }
  .printing :global(.mapwrap.tall) { height: 300px; min-height: 0; }   /* while preparing to print: the map is redrawn shorter */
  .snap { display: none; }
  @media (min-width: 1200px) { .kpis.cc { grid-template-columns: repeat(6, minmax(0, 1fr)); } }

  /* PDF summary (browser print): one landscape A4 page with header, KPIs, map numbers, map, attention items */
  @media print {
    @page { size: A4 landscape; margin: 8mm; }
    :global(html), :global(body) { background: #fff !important; }
    :global(.side), :global(.backdrop), :global(.skip), :global(header.top .tools), :global(.band), :global(.toast) { display: none !important; }
    :global(.wrap) { margin: 0 !important; padding: 0 !important; }
    :global(html), :global(body), :global(#app), :global(.wrap), :global(main) { min-height: 0 !important; height: auto !important; }
    .content :global(.wide-slot:has(.dt)) { display: none !important; }   /* flow table below the map */
    :global(header.top) { position: static !important; box-shadow: none !important; margin: 0 0 4px !important; padding: 6px 10px !important; }
    .content { zoom: 0.7; }
    .content :global(.fm) { display: none !important; }   /* the interactive map is replaced by its image (.snap) */
    .content :global(.side-row) { grid-template-columns: minmax(0, 1fr) !important; gap: 8px !important; }
    .snap { display: block; margin: 0; }
    .snap img { width: 100%; height: auto; max-height: 300px; object-fit: contain; display: block; border-radius: 10px; border: 1px solid #d5dbe1; }
    .snap figcaption { font-size: 0.75rem; color: #555; margin-top: 4px; }
    .print-only { display: flex; justify-content: space-between; gap: 12px; margin: 0 0 8px; font-size: 0.9rem; }
    .no-print, .content :global(.dt), .content :global(.note), .content :global(.skip), .content :global(.mb) { display: none !important; }
    .content :global(.card), .content :global(.kpi) { box-shadow: none !important; break-inside: avoid; }
    .content :global(.alert) { break-inside: auto !important; margin: 0; }
    .content :global(.alert ol) { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 6px; }
    .content :global(.alert li) { padding: 6px 10px; break-inside: avoid; }
    .content :global(.alert a) { display: none; }
    .kpis.cc { grid-template-columns: repeat(6, minmax(0, 1fr)); margin-bottom: 8px; }
    * { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
  }
</style>
