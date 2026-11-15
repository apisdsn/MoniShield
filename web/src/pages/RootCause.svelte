<!-- Root Cause (DRD §3.5, inv. §2.5): "Ringkasan akar masalah" (up to 5 items), 4 charts, 3 tables.
     New (B07): "Refresh token kedaluwarsa: N" below the JWT age chart. DNS upstream from configuration (old: hard-coded).
     One request: GET /api/v1/folders/{folder}/rootcause. -->
<script>
  import { lang, t } from '../i18n.js';
  import { api } from '../api.js';
  import { num, sysName, cut } from '../format.js';
  import { build } from '../state.js';
  import { formatName } from '../anyfmt.js';
  import AnalysisInfo from '../lib/AnalysisInfo.svelte';
  import Kpi from '../lib/Kpi.svelte';
  import ChartCard from '../lib/ChartCard.svelte';
  import DataTable from '../lib/DataTable.svelte';
  import Note from '../lib/Note.svelte';
  import Summary from '../lib/Summary.svelte';
  import Skeleton from '../lib/Skeleton.svelte';
  import ErrorState from '../lib/ErrorState.svelte';

  let { folder, dnsUpstream = '', reloadKey = 0, onready = null, admin = false } = $props();
  let data = $state.raw(null), busy = $state(false), error = $state(null);
  let seq = 0;
  async function load() {
    const my = ++seq;
    busy = true; error = null; onready?.(false);
    try {
      const j = await api.get(`/api/v1/folders/${encodeURIComponent(folder)}/root-causes`);
      if (my === seq) data = j;
    } catch (e) {
      if (my === seq) error = e;
    } finally {
      if (my === seq) { busy = false; onready?.(true); }
    }
  }
  $effect(() => { void [folder, reloadKey]; if (folder) load(); });

  const BUCKETS = ['< 5 Menit', '5–60 Menit', '1–24 Jam', '1–7 Hari', '> 7 Hari'];
  const bucketKey = (b) => `jwt.b${BUCKETS.indexOf(b)}`;
  // DNS timeout impact per domain (old: DNS_IMPACT); others "Resolusi domain eksternal"
  const IMPACT = [[/backup|s3\./i, 'rc.impact.backup'], [/pg-|postgres|\.local\.?$/i, 'rc.impact.db'], [/rancher|longhorn/i, 'rc.impact.rancher']];
  const impact = (d) => (IMPACT.find(([r]) => r.test(d)) || [0, 'rc.impact.external'])[1];
  const pct0 = (a, b) => (b ? `${num((a / b) * 100, $lang, 0)}%` : '-');

  const summary = $derived.by(() => {
    if (!data) return [];
    const T = data.tables, out = [];
    const c = T.c401?.rows?.[0];
    if (c) out.push([{ b: $t('rc.s.c401.b') }, { t: $t('rc.s.c401.t1', { ip: c.client.ip }) }, { code: c.endpoint },
                     { t: $t('rc.s.c401.t2', { n: num(c.n, $lang), peak: c.peak_per_min }) }]);
    if (data.jwt_total) out.push([{ b: $t('rc.s.jwt.b', { n: num(data.jwt_total, $lang) }) }, { t: $t('rc.s.jwt.t', { pct: pct0(data.jwt_over_1h, data.jwt_total) }) }]);
    if (data.pdf.fail) out.push([{ b: $t('rc.s.pdf.b', { n: num(data.pdf.fail, $lang) }) }, { t: $t('rc.s.pdf.t1') }, { code: 'Jasper template path : null' },
                                 { t: $t('rc.s.pdf.t2', { n: num(data.pdf.templates_failed, $lang) }) }]);
    if (data.dns_total) {
      const doms = (T.dns?.rows || []).filter((d) => IMPACT.some(([r]) => r.test(d.domain))).slice(0, 3).map((d) => d.domain);
      const parts = [{ b: $t('rc.s.dns.b', { n: num(data.dns_total, $lang) }) }, { t: $t('rc.s.dns.t', { dns: dnsUpstream }) }];
      if (doms.length) { parts.push({ t: $t('rc.s.dns.incl') }); doms.forEach((d, i) => { if (i) parts.push({ t: ', ' }); parts.push({ code: d }); }); }
      parts.push({ t: '.' });
      out.push(parts);
    }
    if (data.upstream_error_kinds.length)
      out.push([{ b: $t('rc.s.uperr.b', { n: num(data.upstream_errors_total, $lang) }) }, { t: $t('rc.s.uperr.t', { kind: data.upstream_error_kinds[0][0] }) }]);
    return out;
  });
  const jwtSvcs = $derived(Object.keys(data?.jwt || {}));
  // stage 62: error messages and upstream errors of any source
  const g = $derived(data?.generic);
  const hhmm = (v) => (v ? v.slice(11) : '–');
  const rawHref = (m) => build({ tab: 'raw-logs', service: null, folder, module: null, q: m.search, svc: m.service, pod: null });
  const legacyData = $derived(!!data && (data.tables.c401?.total || data.jwt_total || data.pdf.fail || data.dns_total || data.upstream_error_kinds.length));
  const info = $derived.by(() => {
    if (!g) return '';
    const apps = g.app_logs.join(', ');
    if (!g.access) return $t('any.rc.info_noaccess', { apps: apps || '–' });
    return $t('any.rc.info', { apps: apps || '–', svc: g.access.service });
  });
  const upTotal = $derived(g ? (g.upstream.legacy ? data.upstream_errors_total : g.upstream.total) : 0);
  const refresh = $derived(Object.values(data?.refresh_expired || {}).reduce((a, b) => a + b, 0));
</script>

{#if error && !data}
  <ErrorState {error} onretry={load} />
{:else if !data}
  <Skeleton kpis={0} charts={4} />
{:else}
  {@const T = data.tables}
  <div class="content" class:dim={busy}>
    {#if g}
      <AnalysisInfo {admin} text={info} />
      <div class="kpis four">
        <Kpi icon="alert" label={$t('any.rc.error_lines')} value={g.error_lines} tone="err" caption={$t(g.error_services === 1 ? 'any.rc.in_service' : 'any.rc.in_services', { n: num(g.error_services, $lang) })} />
        <Kpi icon="lines" label={$t('any.rc.distinct')} value={g.distinct} caption={$t('any.rc.distinct_sub')} />
        <Kpi icon="server" label={$t('any.rc.upstream')} value={g.access || g.upstream.legacy ? upTotal : null} tone="err" missing={$t('any.rc.no_access_short')} caption={$t('any.rc.upstream_sub')} />
        <Kpi icon="clock" label={$t('any.rc.busiest')} value={g.busiest ? g.busiest.hour.slice(11) + ':00' : null} missing={$t('any.rc.no_times')}
          caption={g.busiest ? $t('any.rc.busiest_sub', { n: num(g.busiest.n, $lang) }) : null} />
      </div>
      <div class="grid one">
        {#if g.messages.length}
          <DataTable title={$t('any.rc.freq')} chip={$t('any.rc.freq_note')} rows={g.messages} limit={25} columns={[
            { key: 'key', label: $t('col.message'), type: 'code', fmt: (r) => r.key.split(' | ').slice(1).join(' | ') || r.key, sort: true, minw: 260 },
            { key: 'service', label: $t('col.service'), sort: true },
            { key: 'n', label: $t('col.lines'), type: 'num', sort: true },
            { key: 'first', label: $t('any.rc.first'), fmt: (r) => hhmm(r.first), cls: () => 'nowrap', sort: true },
            { key: 'last', label: $t('any.rc.last'), fmt: (r) => hhmm(r.last), cls: () => 'nowrap', sort: true },
            { key: 'raw', label: '', custom: true },
          ]}>
            {#snippet cell(r)}<a class="open" href={rawHref(r)}>{$t('any.rc.open_raw')}</a>{/snippet}
          </DataTable>
        {:else}
          <Note>{$t('any.rc.no_errors')}</Note>
        {/if}
        {#if !g.upstream.legacy && g.upstream.rows.length}
          <DataTable title={$t('any.rc.up_title')} chip={$t('any.rc.up_note')} rows={g.upstream.rows} limit={25} columns={[
            { key: 'backend', label: $t('any.rc.backend'), type: 'code', fmt: (r) => r.backend || $t('any.rc.unknown_backend'), sort: true },
            { key: 'n502', label: '502', type: 'num', sort: true },
            { key: 'n503', label: '503', type: 'num', sort: true },
            { key: 'n504', label: '504', type: 'num', sort: true },
            { key: 'last', label: $t('any.rc.last_seen'), fmt: (r) => hhmm(r.last), sort: true },
          ]} />
        {/if}
      </div>
    {/if}
    {#if summary.length}
      <Summary title={$t('rc.summary')} items={summary} />
    {:else if !g?.messages.length}
      <Note>{$t('rc.none')}</Note>
    {/if}
    <div class="grid">
      {#if T.c401?.total}
        {@const top = T.c401.rows.slice(0, 10)}
        <ChartCard title={$t('rc.c401_chart')} type="bar" labels={top.map((r) => cut(`${r.client.ip} ${r.endpoint}`, 48))}
          datasets={[{ label: '401', data: top.map((r) => r.n), color: '--err' }]}
          tooltipTitle={(i) => [`${top[i].client.ip} ${top[i].endpoint}`, ...(top[i].client.org ? [top[i].client.org] : [])]}
          options={{ indexAxis: 'y', plugins: { legend: { display: false } } }} />
      {/if}
      {#if data.jwt_total}
        <ChartCard title={$t('rc.jwt_chart')} type="bar" labels={BUCKETS.map((b) => $t(bucketKey(b)))}
          datasets={jwtSvcs.map((s, i) => ({ label: sysName(s), data: BUCKETS.map((b) => data.jwt[s][b] || 0), color: `--c${i + 1}` }))}
          options={{ scales: { x: { stacked: true }, y: { stacked: true } } }}>
          {#snippet footer()}
            <span class="refresh">{$t('rc.refresh_expired', { n: num(refresh, $lang) })}{#if Object.keys(data.refresh_expired).length > 1}{' '}({Object.entries(data.refresh_expired).map(([s, n]) => `${sysName(s)} ${num(n, $lang)}`).join(', ')}){/if}</span>
          {/snippet}
        </ChartCard>
      {/if}
      {#if T['pdf-templates']?.total}
        {@const top = T['pdf-templates'].rows.slice(0, 12)}
        <ChartCard title={$t('rc.pdf_chart')} type="bar" labels={top.map((r) => cut(r.template, 40))}
          datasets={[{ label: $t('rc.ok'), data: top.map((r) => r.ok), color: '--ok' }, { label: $t('rc.fail'), data: top.map((r) => r.fail), color: '--err' }]}
          tooltipTitle={(i) => top[i].template}
          options={{ indexAxis: 'y', scales: { x: { stacked: true }, y: { stacked: true } } }} />
      {/if}
      {#if data.upstream_error_kinds.length}
        <ChartCard title={$t('rc.uperr_chart')} type="bar" labels={data.upstream_error_kinds.map((k) => cut(k[0], 48))}
          datasets={[{ label: $t('rc.events'), data: data.upstream_error_kinds.map((k) => k[1]), color: '--err' }]}
          tooltipTitle={(i) => data.upstream_error_kinds[i][0]}
          options={{ indexAxis: 'y', plugins: { legend: { display: false } } }} />
      {/if}

      {#if T.c401?.total}
        <DataTable title={$t('rc.c401_table')} {folder} table="c401" initial={T.c401} columns={[
          { key: 'client', label: 'IP', type: 'ip', sort: true },
          { key: 'endpoint', label: $t('col.endpoint'), type: 'code', sort: true, minw: 220 },
          { key: 'n', label: $t('rc.col.n401'), type: 'num', cls: () => 'ERROR', sort: true },
          { key: 'peak_per_min', label: $t('rc.col.peak'), type: 'num', sort: true },
          { key: 'first', label: $t('col.time'), type: 'range', to: 'last', cls: () => 'nowrap', sort: true },
        ]} />
      {/if}
      {#if T['pdf-templates']?.total}
        <DataTable wide={false} title={$t('rc.pdf_table')} {folder} table="pdf-templates" initial={T['pdf-templates']} columns={[
          { key: 'template', label: $t('rc.col.template'), type: 'code', sort: true },
          { key: 'ok', label: $t('rc.ok'), type: 'num', sort: true },
          { key: 'fail', label: $t('rc.col.fail_null'), type: 'num', cls: (r) => (r.fail ? 'ERROR' : ''), sort: true },
        ]} />
      {/if}
      {#if T.dns?.total}
        <DataTable wide={false} title={$t('rc.dns_table')} {folder} table="dns" initial={T.dns} columns={[
          { key: 'domain', label: $t('col.domain'), type: 'code', sort: true },
          { key: 'n', label: $t('table.count'), type: 'num', sort: true },
          { key: 'impact', label: $t('rc.col.impact'), fmt: (r) => $t(impact(r.domain)) },
        ]} />
      {/if}
    </div>
    {#if g && !legacyData}
      <div class="after"><Note>{$t('any.rc.k8s_note')}</Note></div>
    {/if}
  </div>
{/if}

<style>
  .after { margin-top: 18px; }
  .grid.one { grid-template-columns: minmax(0, 1fr); margin-bottom: 18px; }
  .open { display: inline-flex; align-items: center; min-height: var(--touch); color: var(--accent-text); white-space: nowrap; }
  .content { transition: opacity 0.15s; }
  .content.dim { opacity: 0.6; }
  .refresh { font-weight: 500; }
</style>
