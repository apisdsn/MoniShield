<!-- Servers (docs/13-metrics.md): the load of the servers and Docker containers that collectors report. A banner for unusual values
     and almost-full disks, one card per server (CPU, memory and disk bars), the Server Details card and six charts for the chosen server
     and a table of its containers (a list of cards on phones). POST /api/v1/servers and /api/v1/servers/host (parameters in the encrypted body), refreshed every 30 seconds. Numbers and names only. -->
<script>
  import { onMount, untrack } from 'svelte';
  import { lang, t } from '../i18n.js';
  import { api } from '../api.js';
  import { route, build } from '../state.js';
  import { bytes, locale, num } from '../format.js';
  import { TZ } from '../tz.js';
  import { load, save } from '../store.js';
  import { ago, groupNames } from '../collectors.js';
  import { RANGES, alignTo, hostSections, axisLabel, bannerItems, bars, barTone, clockAt, detailTiles, diskIoSets, diskPercent, fullLabel, loadSets, hostKey, hostStatus, last, mainDisk, memoryShare, memoryText, pctText, points,
           rate, share, sparkPoints, unusualValue, upgradeKey, usualBand, zText } from '../servers.js';
  import MetricChart from '../lib/MetricChart.svelte';
  import EmptyState from '../lib/EmptyState.svelte';
  import ErrorState from '../lib/ErrorState.svelte';
  import SeverityTag from '../lib/SeverityTag.svelte';

  let { admin = false, reloadKey = 0, onready = null } = $props();
  const REFRESH_MS = 30000;

  let range = $state(RANGES.includes(load('sv-range', '')) ? load('sv-range', '') : '24h');
  let data = $state.raw(null), error = $state(null);
  let detail = $state.raw(null), detailError = $state(null), sel = $state(null);
  let now = $state(Date.now());
  let seq = 0, dseq = 0;

  async function loadOverview() {
    const my = ++seq;
    try {
      const j = await api.post('/api/v1/servers', { range });
      if (my === seq) { data = j; error = null; }
    } catch (e) { if (my === seq) error = e; }
    onready?.(true);
  }
  const hosts = $derived(data?.hosts || []);
  const current = $derived(hosts.find((h) => hostKey(h) === sel) || hosts[0] || null);

  async function loadDetail() {
    const h = current;
    if (!h) { detail = null; return; }
    const my = ++dseq;
    try {
      const j = await api.post('/api/v1/servers/host', { cid: h.cid, host: h.host, range });
      if (my === dseq) { detail = j; detailError = null; }
    } catch (e) { if (my === dseq) detailError = e; }
  }

  // the server list: again when the range changes, on the reload button and every 30 seconds
  // (untrack: the loads read and write state, which must not make the effect run again; it once asked for the host without end)
  $effect(() => { void [range, reloadKey]; untrack(loadOverview); });
  // the chosen server: again when another one is picked, the range changes or the reload button is used
  $effect(() => {
    const key = current && hostKey(current);
    void [range, reloadKey];
    untrack(() => { if (key && detail && hostKey(detail) !== key) detail = null; loadDetail(); });
  });
  onMount(() => {
    const id = setInterval(() => { now = Date.now(); loadOverview(); loadDetail(); }, REFRESH_MS);
    return () => clearInterval(id);
  });
  function pickRange(r) { range = r; save('sv-range', r); }

  // The banner
  const banner = $derived(bannerItems(data?.unusual, data?.disk_full));
  const nameOf = (it) => it.ctr || it.host;
  const logsHref = (host, ctr) => build({ tab: 'raw-logs', source: 'collector', service: null, folder: null, q: null, module: null, pod: host, svc: ctr });
  const itemText = (it) => it.kind === 'disk' ? $t('sv.u.disk', { mount: it.mount, pct: pctText(it.pct, $lang) })
    : $t(it.what === 'memory' ? 'sv.u.memory' : 'sv.u.cpu', { current: unusualValue(it, it.current, $lang), band: usualBand(it, $lang), z: zText(it.z, $lang) });

  // Groups: headings over the cards and a filter (only when a collector has a group)
  let pick = $state('all');
  const groupList = $derived(groupNames(hosts));
  const secs = $derived(hostSections(hosts, pick));
  const headed = $derived(groupList.length > 0);
  const serverCount = (n) => $t(n === 1 ? 'sv.group.count_one' : 'sv.group.count', { n: num(n, $lang) });

  // Cards
  const barTitle = (b) => $t(`sv.bar.${b.key}`);
  const cardCount = (h) => (h.containers ? $t(h.containers === 1 ? 'sv.ct.count_one' : 'sv.ct.count', { n: num(h.containers, $lang) }) : '');

  // Charts
  const d = $derived(detail && current && hostKey(detail) === hostKey(current) ? detail : null);
  const tzLabel = $derived(TZ.label);
  const labelsOf = (rows) => points(rows).t.map((x) => axisLabel(x, range, TZ.minutes, $lang));
  const tipsOf = (rows) => points(rows).t.map((x) => fullLabel(x, TZ.minutes, tzLabel, $lang));
  const valuesOf = (rows) => points(rows).v;
  const charts = $derived.by(() => {
    if (!d) return null;
    const s = d.series, c = d.current;
    const disk = diskPercent(s.disk_used, s.disk_total);
    const memTotal = last(s.mem_total);
    const memBase = (s.mem_used || []).filter(([, v]) => v !== null);
    const ld = loadSets(s, $t), io = diskIoSets(s, $t), m = d.details?.load || {}, di = d.details?.disk_io || {};
    return {
      cpu: { now: c.cpu === null ? '' : `${pctText(c.cpu, $lang)}%`, labels: labelsOf(s.cpu), tips: tipsOf(s.cpu), sets: [{ label: $t('sv.l.cpu'), data: valuesOf(s.cpu), color: '--accent' }], max: 100 },
      memory: { now: c.mem_used === null ? '' : `${bytes(c.mem_used, $lang)} / ${bytes(c.mem_total, $lang)}`, labels: labelsOf(memBase), tips: tipsOf(memBase), max: memTotal,
                sets: [{ label: $t('sv.l.used'), data: valuesOf(memBase), color: '--accent' }, { label: $t('sv.l.total'), data: alignTo(memBase, s.mem_total), color: '--muted', dashed: true }] },
      disk: { now: s.disk_mount && disk.length ? $t('sv.disk_of', { pct: pctText(last(disk), $lang), mount: s.disk_mount }) : '', labels: labelsOf(disk), tips: tipsOf(disk),
              sets: [{ label: $t('sv.l.disk'), data: valuesOf(disk), color: '--accent' }], max: 100, mount: s.disk_mount || '/' },
      network: { now: c.net_rx === null && c.net_tx === null ? '' : `${rate(c.net_rx, $lang)} / ${rate(c.net_tx, $lang)}`, labels: labelsOf(s.net_rx), tips: tipsOf(s.net_rx),
                 sets: [{ label: $t('sv.l.rx'), data: valuesOf(s.net_rx), color: '--c1' }, { label: $t('sv.l.tx'), data: alignTo((s.net_rx || []).filter(([, v]) => v !== null), s.net_tx), color: '--c2' }] },
      load: { now: m.m1 === null || m.m1 === undefined ? '' : [m.m1, m.m5, m.m15].map((v) => num(v, $lang, 2)).join(' · '), labels: labelsOf(ld.base), tips: tipsOf(ld.base), sets: ld.sets,
              max: s.load?.cores ? s.load.cores * 1.5 : null },
      diskIo: { now: di.read === null || di.read === undefined ? '' : `${rate(di.read, $lang)} / ${rate(di.write, $lang)}`, labels: labelsOf(io.base), tips: tipsOf(io.base), sets: io.sets },
    };
  });

  // Server Details
  const tiles = $derived(d?.details ? detailTiles(d.details, $t, $lang, TZ.minutes) : []);
  const single = $derived(hosts.length === 1 && !headed);

  // Containers
  const containers = $derived(d?.containers || []);
  const locale_ = $derived(locale($lang));
  function seenText(iso) {
    const [v, unit] = ago((now - Date.parse(iso)) / 1000);
    return new Intl.RelativeTimeFormat(locale_, { numeric: 'auto' }).format(-v, unit);
  }
  const net = (c) => `${rate(c.net_rx, $lang)} / ${rate(c.net_tx, $lang)}`;
  const sparkTone = (c) => barTone(memoryShare(c));
</script>

<div class="bar">
  <p class="muted intro">{$t('sv.intro')}</p>
  <div class="seg rng" role="group" aria-label={$t('sv.range')}>
    {#each RANGES as r}<button type="button" aria-pressed={range === r} onclick={() => pickRange(r)}>{$t(`sv.r.${r}`)}</button>{/each}
  </div>
</div>

{#if error && !data}
  <ErrorState {error} onretry={loadOverview} />
{:else if !data}
  <div class="skel" aria-hidden="true">
    <div class="hosts">{#each Array(3) as _}<div class="card blk"></div>{/each}</div>
    <div class="charts">{#each Array(6) as _}<div class="card blk tall"></div>{/each}</div>
  </div>
  <span class="sr-only" role="status">{$t('state.loading')}</span>
{:else if !hosts.length}
  <EmptyState title={$t('sv.empty.title')} text={$t(admin ? 'sv.empty.text' : 'sv.empty.text_user')}>
    {#if admin}<a class="btn primary" href={build({ tab: 'collectors', service: null, q: null })}>{$t('sv.empty.link')}</a>{/if}
  </EmptyState>
{:else}
  {#if error}<ErrorState compact {error} onretry={loadOverview} />{/if}

  {#if banner.items.length}
    <section class="banner" aria-label={$t('sv.unusual')}>
      <ul>
        {#each banner.items as it}
          <li>
            <span class="txt"><b>{nameOf(it)}</b> {itemText(it)}{#if it.started}<span class="st">{$t('sv.u.started', { time: clockAt(it.started, TZ.minutes, $lang) })}</span>{/if}</span>
            {#if it.ctr}<a class="btn" href={logsHref(it.host, it.ctr)}>{$t('sv.u.logs')}</a>{/if}
          </li>
        {/each}
      </ul>
      {#if banner.more}<p class="more muted">{$t('sv.more', { n: num(banner.more, $lang) })}</p>{/if}
    </section>
  {/if}

  {#if headed}
    <div class="gfilter" role="group" aria-label={$t('sv.group.filter')}>
      <button type="button" class="gb" aria-pressed={pick === 'all' || (pick !== '' && !groupList.includes(pick))} onclick={() => (pick = 'all')}>{$t('sv.group.all')}</button>
      {#each groupList as g}<button type="button" class="gb" aria-pressed={pick === g} onclick={() => (pick = g)}>{g}</button>{/each}
      {#if hosts.some((h) => !h.group)}<button type="button" class="gb" aria-pressed={pick === ''} onclick={() => (pick = '')}>{$t('sv.group.none')}</button>{/if}
    </div>
  {/if}

  {#snippet hostCard(h)}
    {@const st = hostStatus(h)}
    <button type="button" class="hc" aria-pressed={current && hostKey(current) === hostKey(h)} onclick={() => (sel = hostKey(h))}>
      <span class="top">
        <span class="nm"><b>{h.host}</b><small>{[h.os, cardCount(h)].filter(Boolean).join(' · ') || h.collector}</small></span>
        <SeverityTag level={st.level} text={$t(`sv.st.${st.key}`)} />
      </span>
      {#each bars(h) as b}
        <span class="b3">
          <span class="lb">{barTitle(b)}</span>
          <span class="trk" aria-hidden="true">{#if b.pct !== null}<span class="fill {barTone(b.pct)}" style:width="{Math.max(2, b.pct)}%"></span>{/if}</span>
          <span class="v" class:none={b.pct === null}>{b.pct === null ? '–' : `${pctText(b.pct, $lang)}%`}</span>
        </span>
      {/each}
      <span class="ft muted">{h.last_seen ? $t('sv.last_data_cap', { time: seenText(h.last_seen) }) : ''}</span>
    </button>
  {/snippet}

  <!-- The details of the chosen server. One server: beside its card (one third, two thirds). Several servers (or groups): the cards keep their grid
       and this card sits below them, full width, with the name of the chosen server. -->
  {#snippet detailsCard()}
    <section class="card dt" aria-labelledby="sv-dt">
      <h2 id="sv-dt">{$t('sv.dt.title')}{#if !single && d}<span class="muted of"> · {d.host}</span>{/if}</h2>
      {#if d?.details}
        <div class="tiles" class:seven={tiles.length === 7}>
          {#each tiles as x (x.key)}
            <div class="tile">
              <span class="tl" title={x.label}>{x.label}</span>
              <span class="tv" class:none={x.value === '–'} title={x.value}>{x.value}</span>
              <span class="ts" title={x.sub || undefined}>{x.sub}</span>
            </div>
          {/each}
        </div>
        {#if d.needs_upgrade}<p class="up muted">{$t(upgradeKey(d.platform))}</p>{/if}
      {:else if detailError}
        <p class="muted up">{$t('state.error_text')}</p>
      {:else}
        <div class="tiles" aria-hidden="true">{#each Array(8) as _}<div class="tile blk"></div>{/each}</div>
      {/if}
    </section>
  {/snippet}

  {#if single}
    <div class="first">
      <div class="hosts one">{@render hostCard(hosts[0])}</div>
      {@render detailsCard()}
    </div>
  {:else}
    {#each secs as g (g.name)}
      <section class="gsec" aria-label={headed ? g.name || $t('sv.group.none') : $t('sv.hosts')}>
        {#if headed}<h2 class="gh">{g.name || $t('sv.group.none')} <span class="muted gc">{serverCount(g.hosts.length)}</span></h2>{/if}
        <div class="hosts">
          {#each g.hosts as h (hostKey(h))}{@render hostCard(h)}{/each}
        </div>
      </section>
    {/each}
    <div class="wide">{@render detailsCard()}</div>
  {/if}

  {#if detailError && !d}
    <ErrorState error={detailError} onretry={loadDetail} />
  {:else if !d || !charts}
    <div class="skel" aria-hidden="true"><div class="charts">{#each Array(6) as _}<div class="card blk tall"></div>{/each}</div></div>
    <span class="sr-only" role="status">{$t('state.loading')}</span>
  {:else}
    <section class="charts" aria-label={$t('sv.charts')}>
      <MetricChart title={$t('sv.chart.cpu')} now={charts.cpu.now} labels={charts.cpu.labels} tips={charts.cpu.tips} datasets={charts.cpu.sets} max={charts.cpu.max}
        fmt={(v) => `${pctText(v, $lang)}%`} caption={$t('sv.chart.cpu_cap')} />
      <MetricChart title={$t('sv.chart.memory')} now={charts.memory.now} labels={charts.memory.labels} tips={charts.memory.tips} datasets={charts.memory.sets} max={charts.memory.max}
        fmt={(v) => bytes(v, $lang)} caption={$t('sv.chart.memory_cap')} />
      <MetricChart title={$t('sv.chart.disk')} now={charts.disk.now} labels={charts.disk.labels} tips={charts.disk.tips} datasets={charts.disk.sets} max={charts.disk.max}
        fmt={(v) => `${pctText(v, $lang)}%`} caption={$t('sv.chart.disk_cap', { mount: charts.disk.mount })} />
      <MetricChart title={$t('sv.chart.network')} now={charts.network.now} labels={charts.network.labels} tips={charts.network.tips} datasets={charts.network.sets}
        fmt={(v) => rate(v, $lang)} caption={$t('sv.chart.network_cap')} />
      <MetricChart title={$t('sv.chart.load')} now={charts.load.now} labels={charts.load.labels} tips={charts.load.tips} datasets={charts.load.sets} max={charts.load.max}
        fmt={(v) => num(v, $lang, 2)} caption={$t('sv.chart.load_cap')} />
      <MetricChart title={$t('sv.chart.disk_io')} now={charts.diskIo.now} labels={charts.diskIo.labels} tips={charts.diskIo.tips} datasets={charts.diskIo.sets}
        fmt={(v) => rate(v, $lang)} caption={$t('sv.chart.disk_io_cap')} />
    </section>

    <section class="card ct" aria-labelledby="sv-ct">
      <header>
        <h2 id="sv-ct">{$t('sv.ct.title', { name: d.host })}</h2>
        <span class="muted cnt">{containers.length === 1 ? $t('sv.ct.count_one') : $t('sv.ct.count', { n: num(containers.length, $lang) })}</span>
      </header>
      {#if !containers.length}
        <p class="muted none">{$t('sv.ct.none')}</p>
      {:else}
        <div class="scroll">
          <table>
            <caption class="sr-only">{$t('sv.ct.title', { name: d.host })}</caption>
            <thead>
              <tr><th scope="col">{$t('sv.col.container')}</th><th scope="col">{$t('sv.col.image')}</th><th scope="col">{$t('sv.col.cpu')}</th><th scope="col">{$t('sv.col.memory')}</th>
                <th scope="col">{$t('sv.col.network')}</th><th scope="col">{$t('sv.col.restarts')}</th><th scope="col">{$t('sv.col.spark')}</th></tr>
            </thead>
            <tbody>
              {#each containers as c (c.name)}
                {@const pts = sparkPoints(c.spark)}
                <tr class:off={!c.running}>
                  <td class="nm">
                    <b title={c.name}>{c.name}</b>
                    <span class="sub">
                      {#if c.logs_today}<a class="lg" href={logsHref(d.host, c.name)}>{$t('sv.logs')}</a>{:else}<span class="lg muted">{$t('sv.no_logs_today')}</span>{/if}
                      {#if !c.running}<small class="muted" title="{$t('sv.stopped')} · {$t('sv.seen', { time: seenText(c.last_seen) })}">{$t('sv.stopped')} · {$t('sv.seen', { time: seenText(c.last_seen) })}</small>{/if}
                    </span>
                  </td>
                  <td class="img" class:none={!c.image} title={c.image || undefined} data-label={$t('sv.col.image')}>{c.image || '–'}</td>
                  <td class="cpu" data-label={$t('sv.col.cpu')}>
                    <span class="n" class:none={c.cpu === null}>{c.cpu === null ? '–' : `${pctText(c.cpu, $lang)}%`}</span>
                    <span class="trk" aria-hidden="true">{#if c.cpu !== null}<span class="fill {barTone(c.cpu)}" style:width="{Math.max(2, Math.min(100, c.cpu))}%"></span>{/if}</span>
                  </td>
                  <td class="mem" data-label={$t('sv.col.memory')}>
                    <span class="n" class:none={memoryText(c, $lang, $t('sv.no_limit')) === '–'}>{memoryText(c, $lang, $t('sv.no_limit'))}</span>
                    <span class="trk" aria-hidden="true">{#if memoryShare(c) !== null}<span class="fill {barTone(memoryShare(c))}" style:width="{Math.max(2, memoryShare(c))}%"></span>{/if}</span>
                  </td>
                  <td class="net" class:none={net(c) === '–'} data-label={$t('sv.col.network')}>{net(c)}</td>
                  <td class="rs" class:none={c.restarts === null} class:hot={c.restarts > 0} data-label={$t('sv.col.restarts')}>{c.restarts === null ? '–' : num(c.restarts, $lang)}</td>
                  <td class="sp" data-label={$t('sv.col.spark')}>
                    {#if pts}
                      <svg width="100" height="28" viewBox="0 0 100 28" preserveAspectRatio="none" role="img" aria-label={$t('sv.spark', { name: c.name })}>
                        <polyline points={pts} fill="none" class="line {sparkTone(c)}" stroke-width="1.6" vector-effect="non-scaling-stroke" />
                      </svg>
                    {:else}<span class="muted" title={$t('sv.spark_none', { name: c.name })}>–</span>{/if}
                  </td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
      {/if}
    </section>
  {/if}
{/if}

<style>
  .bar { display: flex; align-items: center; justify-content: space-between; gap: 12px 18px; margin-bottom: 14px; flex-wrap: wrap; }
  .intro { margin: 0; font-size: 0.875rem; max-width: 62ch; }
  .rng button { min-height: var(--touch); min-width: var(--touch); }

  .banner {
    margin-bottom: 16px; padding: 12px 18px; border-radius: var(--r-card); background: color-mix(in srgb, var(--warn) 9%, var(--card-bg));
    border: 1px solid color-mix(in srgb, var(--warn) 40%, transparent);
  }
  .banner ul { list-style: none; margin: 0; padding: 0; display: grid; gap: 8px; }
  .banner li { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 6px 20px; }
  .txt { font-size: 0.9375rem; line-height: 1.5; min-width: 0; overflow-wrap: anywhere; }
  .banner .btn { min-height: var(--touch); text-decoration: none; }
  .st { margin-left: 0.4em; }
  .more { margin: 8px 0 0; font-size: 0.8125rem; }

  .gfilter { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 14px; }
  .gb { min-height: var(--touch); padding: 0 14px; border-radius: var(--r-ctl); font: inherit; font-size: 0.875rem; cursor: pointer; color: var(--fg); background: var(--bg2); border: 1px solid var(--line-strong); }
  .gb[aria-pressed='true'] { border: 1.5px solid var(--accent); background: var(--seg-on); color: var(--accent-text); font-weight: 600; }
  .gsec { margin-bottom: 16px; }
  .gh { margin: 6px 0 10px; font-size: 1rem; font-weight: 600; color: var(--heading); text-transform: none; }
  .gc { font-weight: 400; font-size: 0.8125rem; }
  .hosts { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 280px), 1fr)); gap: 14px; }
  .hc {
    display: flex; flex-direction: column; gap: 10px; padding: 16px; text-align: left; color: var(--fg); cursor: pointer; font: inherit;
    background: var(--card-bg); border: 1px solid var(--card-border); border-radius: var(--r-card); box-shadow: var(--glow); min-width: 0;
  }
  .hc:hover { background: var(--row-hover); }
  .hc[aria-pressed='true'] { border: 1.5px solid var(--accent); padding: 15.5px; background: color-mix(in srgb, var(--accent) 5%, var(--card-bg)); }
  .top { display: flex; justify-content: space-between; align-items: flex-start; gap: 8px; }
  .nm { display: flex; flex-direction: column; min-width: 0; }
  .nm b { font-size: 0.9375rem; font-weight: 600; overflow-wrap: anywhere; }
  .nm small { font-size: 0.75rem; color: var(--muted); overflow-wrap: anywhere; }
  .none { color: var(--muted); }   /* a dash for "no value" is never coloured */
  .b3 { display: grid; grid-template-columns: 64px minmax(0, 1fr) 48px; gap: 8px; align-items: center; font-size: 0.8125rem; }
  .lb { color: var(--muted); }
  .v { font-family: var(--mono); text-align: right; }
  .trk { display: block; height: 6px; border-radius: 999px; background: var(--line); overflow: hidden; }
  .fill { display: block; height: 100%; border-radius: 999px; background: var(--accent); }
  .fill.warn { background: var(--warn); }
  .fill.err { background: var(--err); }

  .hc .ft { margin-top: auto; padding-top: 10px; border-top: 1px solid var(--line); font-size: 0.75rem; min-height: 1.25rem; box-sizing: content-box; }
  .hosts.one { grid-template-columns: minmax(0, 1fr); }
  .first { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 2fr); gap: 14px; margin-bottom: 16px; align-items: stretch; }
  .first > :global(*), .wide > :global(*) { min-width: 0; }
  .wide { margin-bottom: 16px; }

  /* Server Details: eight tiles of one height; label, value and one line below, each on one line */
  .dt { display: flex; flex-direction: column; gap: 12px; }
  .dt h2 { font-size: 1rem; text-transform: none; margin: 0; }
  .dt .of { font-weight: 400; }
  .tiles { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; }
  .tile { display: flex; flex-direction: column; justify-content: center; gap: 2px; height: 78px; box-sizing: border-box; padding: 0 12px; min-width: 0;
          background: var(--bg2); border: 1px solid var(--line); border-radius: var(--r-ctl); }
  .tile.blk { height: 78px; }
  .tile > span { display: block; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 0.75rem; line-height: 1rem; color: var(--muted); }
  .tile > .tv { font-size: 1rem; line-height: 1.375rem; font-weight: 600; color: var(--fg); font-variant-numeric: tabular-nums; }
  .tile > .tv.none { color: var(--muted); font-weight: 400; }
  .tiles.seven .tile:last-child { grid-column: span 2; }
  .up { margin: 0; font-size: 0.75rem; }

  .charts { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; margin-bottom: 16px; }
  .charts > :global(*) { min-width: 0; }
  .ct { padding: 0; overflow: hidden; }
  .ct > header { padding: 14px 16px; margin: 0; border-bottom: 1px solid var(--line); }
  .ct h2 { font-size: 1rem; text-transform: none; overflow-wrap: anywhere; }
  .cnt { font-size: 0.8125rem; }
  .none { margin: 0; padding: 18px 16px; }
  .scroll { overflow-x: auto; }
  table { width: 100%; min-width: 940px; border-collapse: collapse; }
  th { text-align: left; font-size: 0.75rem; font-weight: 600; color: var(--th-fg); padding: 12px 12px; border-bottom: 1px solid var(--line); white-space: nowrap; }
  td { padding: 12px 12px; border-bottom: 1px solid var(--row-line); vertical-align: middle; font-size: 0.8125rem; }
  tbody td { height: 72px; box-sizing: border-box; }   /* every row the same height, also one that has no numbers */
  tbody tr:last-child td { border-bottom-color: transparent; }   /* the same height as the other rows */
  tr.off { opacity: 0.6; }
  /* one height for every row: names and images stay on one line (an ellipsis, the whole text in the title), the numbers never wrap */
  td.nm, td.img { max-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  td.nm { display: table-cell; width: 26%; min-width: 190px; }
  td.nm b { display: block; font-size: 0.8125rem; font-weight: 600; overflow: hidden; text-overflow: ellipsis; }
  td.nm .sub { display: flex; align-items: center; gap: 8px; min-width: 0; }
  td.nm small { display: block; min-width: 0; font-size: 0.75rem; overflow: hidden; text-overflow: ellipsis; }
  .lg { display: inline-flex; align-items: center; min-height: 28px; font-size: 0.75rem; flex: none; }
  .img { width: 20%; min-width: 120px; font-family: var(--mono); font-size: 0.75rem; }
  .cpu { min-width: 92px; } .mem { min-width: 160px; white-space: nowrap; }
  .cpu .n, .mem .n { display: block; font-family: var(--mono); margin-bottom: 4px; white-space: nowrap; height: 1.25rem; line-height: 1.25rem; }
  .net { min-width: 195px; font-family: var(--mono); font-size: 0.75rem; white-space: nowrap; }
  .rs { font-family: var(--mono); }
  .rs.hot { color: var(--warn); font-weight: 600; }
  .line { stroke: var(--accent); }
  .line.warn { stroke: var(--warn); }
  .line.err { stroke: var(--err); }

  .skel .hosts, .skel .charts { margin-bottom: 14px; }
  .blk { background: var(--card-bg); height: 150px; position: relative; overflow: hidden; }
  .blk.tall { height: 250px; }

  @media (max-width: 1180px) { .charts { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
  @media (max-width: 1100px) { .tiles { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
  @media (max-width: 760px) {
    .first { grid-template-columns: minmax(0, 1fr); }
    .charts { grid-template-columns: minmax(0, 1fr); }
  }
  @media (max-width: 480px) {
    .tiles { grid-template-columns: minmax(0, 1fr); }
    .tiles.seven .tile:last-child { grid-column: auto; }
    .scroll { overflow: visible; }
    .ct { background: none; border: 0; box-shadow: none; }
    .ct > header { padding: 0 2px 10px; border: 0; }
    table, tbody { display: block; min-width: 0; }
    thead { display: none; }
    tr { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 8px 14px; padding: 12px 14px; margin-bottom: 10px; background: var(--card-bg); border: 1px solid var(--card-border); border-radius: var(--r-card); box-shadow: var(--glow); }
    td { display: block; padding: 0; border: 0; min-width: 0; height: auto; }
    td.nm { grid-column: 1 / -1; }
    td.nm b { font-size: 0.9375rem; }
    td.nm, td.img { max-width: none; width: auto; min-width: 0; white-space: normal; overflow: visible; }   /* cards: no fixed row height, so text wraps */
    td.nm b, td.nm small { overflow: visible; text-overflow: clip; overflow-wrap: anywhere; white-space: normal; }
    td.nm .sub { flex-wrap: wrap; }
    td.img { overflow-wrap: anywhere; }
    td.img, td.net, td.rs, td.sp { grid-column: 1 / -1; display: flex; gap: 8px; align-items: center; justify-content: space-between; }
    td[data-label].img::before, td[data-label].net::before, td[data-label].rs::before, td[data-label].sp::before { content: attr(data-label); color: var(--muted); font-family: var(--font); font-size: 0.8125rem; flex: none; }
    td.cpu::before, td.mem::before { content: attr(data-label); display: block; color: var(--muted); font-size: 0.8125rem; font-family: var(--font); }
    .lg { min-height: var(--touch); font-size: 0.875rem; }
    .cpu, .mem { min-width: 0; }
  }
</style>
