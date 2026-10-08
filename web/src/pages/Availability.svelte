<!-- Availability (DRD §3.6, inv. §2.6): 7 KPIs (4 + 3), 3 charts, 4 tables; needs nginx ingress logs (otherwise a note).
     Changed from the old one (TRD §4.4 item 1): pod connection errors are no longer truncated at 200 (KPI = all events, the table can
     be continued). One request: GET /api/folders/{folder}/availability. -->
<script>
  import { lang, t } from '../i18n.js';
  import { api } from '../api.js';
  import { num } from '../format.js';
  import Kpi from '../lib/Kpi.svelte';
  import ChartCard from '../lib/ChartCard.svelte';
  import HBar from '../lib/HBar.svelte';
  import DataTable from '../lib/DataTable.svelte';
  import Note from '../lib/Note.svelte';
  import Skeleton from '../lib/Skeleton.svelte';
  import ErrorState from '../lib/ErrorState.svelte';

  let { folder, reloadKey = 0, onready = null } = $props();
  let data = $state.raw(null), busy = $state(false), error = $state(null);
  let seq = 0;
  async function load() {
    const my = ++seq;
    busy = true; error = null; onready?.(false);
    try {
      const j = await api.get(`/api/folders/${encodeURIComponent(folder)}/availability`);
      if (my === seq) data = j;
    } catch (e) {
      if (my === seq) error = e;
    } finally {
      if (my === seq) { busy = false; onready?.(true); }
    }
  }
  $effect(() => { void [folder, reloadKey]; if (folder) load(); });

  const pct3 = (a, b) => (b ? `${num((a / b) * 100, $lang, 3)}%` : '-');
  // incident duration in minutes: start–end difference + 1 (old)
  const mins = (a, b) => Math.round((new Date(b.replace(' ', 'T')) - new Date(a.replace(' ', 'T'))) / 60000) + 1;
  // requests in the log are encoded; a lone "%" must not make decoding fail (old)
  const decode = (s) => { try { return decodeURIComponent(s.replace(/%(?![0-9a-f]{2})/gi, '%25')); } catch { return s; } };
  const n5ByHour = $derived(Object.fromEntries(data?.n5xx_by_hour || []));
</script>

{#if error && !data}
  <ErrorState {error} onretry={load} />
{:else if !data}
  <Skeleton kpis={7} charts={3} />
{:else if !data.available}
  <Note>{$t('av.no_nginx')}</Note>
{:else}
  {@const k = data.kpi}
  {@const T = data.tables}
  <div class="content" class:dim={busy}>
    <div class="kpis four">
      <Kpi icon="pulse" label={$t('av.kpi.availability')} value={pct3(k.requests - k.n5xx, k.requests)} tone="ok" info={$t('av.kpi.availability_info')} />
      <Kpi icon="alert" label={$t('av.kpi.n5xx')} value={k.n5xx} tone="err" />
      <Kpi icon="clock" label={$t('av.kpi.incidents')} value={k.incidents} tone="warn" />
      <Kpi icon="refresh" label={$t('av.kpi.retries')} value={k.retries} tone="warn" />
      <Kpi icon="server" label={$t('av.kpi.upstream_errors')} value={k.upstream_errors} tone="err" />
      <Kpi icon="trend" label={$t('av.kpi.uptime_checks')} value={k.uptime_checks} />
      <Kpi icon="alert" label={$t('av.kpi.uptime_failed')} value={k.uptime_failed} tone={k.uptime_failed ? 'err' : 'ok'} />
    </div>
    <div class="grid">
      <ChartCard title={$t('av.n5xx_hour')} type="line" timeAxis wide labels={data.hours}
        datasets={[{ label: '5xx', data: data.hours.map((h) => n5ByHour[h] || 0), color: '--err' }]} />
      <HBar title={$t('av.n5xx_upstream')} rows={data.n5xx_by_upstream.map(([u, n]) => ({ label: u, value: n }))} color="--err" valueLabel="5xx" />
      {#if k.uptime_checks}
        <ChartCard title={$t('av.uptime_hour')} type="line" timeAxis labels={data.uptime_by_hour.map((h) => h[0])}
          datasets={[{ label: $t('av.ok'), data: data.uptime_by_hour.map((h) => h[1] - h[2]), color: '--ok' },
                     { label: $t('av.fail'), data: data.uptime_by_hour.map((h) => h[2]), color: '--err' }]}
          options={{ scales: { x: { stacked: true }, y: { stacked: true } } }} />
      {/if}

      <DataTable wide={false} title={$t('av.t.upstreams')} {folder} table="upstreams" initial={T.upstreams} columns={[
        { key: 'upstream', label: 'Upstream', cls: () => 'nowrap', sort: true },
        { key: 'requests', label: $t('col.requests'), type: 'num', sort: true },
        { key: 'n5xx', label: '5xx', type: 'num', cls: (r) => (r.n5xx ? 'ERROR' : ''), sort: true },
        { key: 'avail', label: $t('av.col.availability'), type: 'num', fmt: (r) => pct3(r.requests - r.n5xx, r.requests) },
      ]} />
      {#if T['uptime-targets']?.total}
        <DataTable wide={false} title={$t('av.t.uptime_targets')} {folder} table="uptime-targets" initial={T['uptime-targets']} columns={[
          { key: 'target', label: $t('av.col.target'), type: 'code', sort: true },
          { key: 'n', label: $t('av.col.checks'), type: 'num', sort: true },
        ]} />
      {/if}
      <DataTable title={$t('av.t.incidents')} {folder} table="incidents" initial={T.incidents} columns={[
        { key: 'start', label: $t('av.col.range'), type: 'range', to: 'end', cls: () => 'nowrap', sort: true },
        { key: 'dur', label: $t('av.col.duration'), type: 'num', fmt: (r) => $t('av.minutes', { n: mins(r.start, r.end) }) },
        { key: 'n', label: $t('av.col.n5xx'), type: 'num', cls: () => 'ERROR', sort: true },
        { key: 'upstreams', label: 'Upstream', custom: true, minw: 200 },
        { key: 'statuses', label: $t('col.status'), type: 'statuses' },
      ]}>
        {#snippet cell(r)}<div class="small">{#each Object.entries(r.upstreams) as [u, c]}<div class="nowrap">{u} ×{num(c, $lang)}</div>{/each}</div>{/snippet}
      </DataTable>
      <DataTable title={$t('av.t.upstream_errors')} {folder} table="upstream-errors" initial={T['upstream-errors']} columns={[
        { key: 'time', label: $t('col.time'), type: 'time', cls: () => 'nowrap', sort: true },
        { key: 'kind', label: $t('av.col.kind'), cls: () => 'small', sort: true, minw: 220 },
        { key: 'pod', label: $t('av.col.pod'), type: 'code', sort: true },
        { key: 'request', label: $t('col.request'), fmt: (r) => decode(r.request), cls: () => 'small', minw: 220 },
      ]} />
    </div>
  </div>
{/if}

<style>
  .content { transition: opacity 0.15s; }
  .content.dim { opacity: 0.6; }
</style>
