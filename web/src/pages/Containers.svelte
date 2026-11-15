<!-- Containers (stage 62): the Pods page of a collector source whose services are Docker containers. The folder's log lines per container
     next to what the Servers metrics know (image, restarts in 24 h). One request: GET /api/v1/folders/{folder}/containers.
     Kubernetes data keeps the Pods page (pages/Pods.svelte). -->
<script>
  import { lang, t } from '../i18n.js';
  import { api } from '../api.js';
  import { num } from '../format.js';
  import { build } from '../state.js';
  import AnalysisInfo from '../lib/AnalysisInfo.svelte';
  import Kpi from '../lib/Kpi.svelte';
  import DataTable from '../lib/DataTable.svelte';
  import Note from '../lib/Note.svelte';
  import Skeleton from '../lib/Skeleton.svelte';
  import ErrorState from '../lib/ErrorState.svelte';

  let { folder, reloadKey = 0, onready = null, admin = false } = $props();
  let data = $state.raw(null), busy = $state(false), error = $state(null);
  let seq = 0;
  async function load() {
    const my = ++seq;
    busy = true; error = null; onready?.(false);
    try {
      const j = await api.get(`/api/v1/folders/${encodeURIComponent(folder)}/containers`);
      if (my === seq) data = j;
    } catch (e) {
      if (my === seq) error = e;
    } finally {
      if (my === seq) { busy = false; onready?.(true); }
    }
  }
  $effect(() => { void [folder, reloadKey]; if (folder) load(); });

  const logs = (host, c) => build({ tab: 'raw-logs', service: null, folder, module: null, q: null, pod: host, svc: c });
</script>

{#if error && !data}
  <ErrorState {error} onretry={load} />
{:else if !data}
  <Skeleton kpis={4} charts={0} />
{:else if !data.available}
  <Note>{$t('any.ctr.none')}</Note>
{:else}
  {@const k = data.kpi}
  <div class="content" class:dim={busy}>
    <AnalysisInfo {admin} text={$t('any.ctr.info', { hosts: data.hosts.map((h) => h.host).join(', ') })} />
    <div class="kpis four">
      <Kpi icon="box" label={$t('any.ctr.kpi.with_logs')} value={k.with_logs} caption={$t('any.ctr.of_running', { n: num(k.running, $lang) })} />
      <Kpi icon="file" label={$t('any.ctr.kpi.without_logs')} value={k.without_logs.length} tone={k.without_logs.length ? 'warn' : null} caption={k.without_logs.slice(0, 2).join(', ') || ' '} />
      <Kpi icon="alert" label={$t('kpi.error')} value={k.err} tone="err" caption={$t(k.err_containers === 1 ? 'any.ctr.in_container' : 'any.ctr.in_containers', { n: num(k.err_containers, $lang) })} />
      <Kpi icon="refresh" label={$t('any.ctr.kpi.restarts')} value={k.restarts} tone={k.restarts ? 'warn' : null} caption={$t('any.ctr.from_metrics')} />
    </div>
    <div class="tables">
      {#each data.hosts as h (h.cid + '/' + h.host)}
        <DataTable title={$t('any.ctr.on_host', { host: h.host })} chip={null} rows={h.rows} limit={100} columns={[
          { key: 'container', label: $t('any.ctr.col.container'), cls: () => 'strong', sort: true, minw: 180 },
          { key: 'image', label: $t('any.ctr.col.image'), type: 'code', sort: true },
          { key: 'lines', label: $t('col.lines'), type: 'num', sort: true },
          { key: 'err', label: $t('kpi.error'), type: 'num', cls: (r) => (r.err ? 'ERROR' : ''), sort: true },
          { key: 'warn', label: $t('kpi.warning'), type: 'num', cls: (r) => (r.warn ? 'WARN' : ''), sort: true },
          { key: 'restarts', label: $t('any.ctr.col.restarts'), type: 'num', cls: (r) => (r.restarts ? 'WARN' : ''), sort: true },
          { key: 'raw', label: '', custom: true },
        ]}>
          {#snippet cell(r)}{#if r.lines}<a class="open" href={logs(h.host, r.container)}>{$t('any.rc.open_raw')}</a>{:else}<span class="muted">{$t('any.ctr.no_lines_sub')}</span>{/if}{/snippet}
        </DataTable>
      {/each}
    </div>
    <Note>{$t('any.ctr.note')}</Note>
  </div>
{/if}

<style>
  .content { transition: opacity 0.15s; }
  .content.dim { opacity: 0.6; }
  .tables { display: grid; gap: 18px; margin-bottom: 18px; }
  .content :global(.strong) { font-weight: 600; }
  .open { display: inline-block; padding: 12px 0; margin: -12px 0; line-height: 1.25rem; color: var(--accent-text); white-space: nowrap; }
</style>
