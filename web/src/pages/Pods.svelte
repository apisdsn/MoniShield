<!-- Pod (DRD §3.7, inv. §2.7): 5 KPI, catatan, 2 chart, 3 tabel. File log dari ringkasan folder (sudah dimuat kerangka);
     pod backend + restart dari GET /api/folders/{folder}/pods. Berubah: "Pod dengan retry 502" -> "Pod dengan retry"
     (B10); status file "Rusak" (B05). -->
<script>
  import { lang, t } from '../i18n.js';
  import { api } from '../api.js';
  import { num, dur, sysName, cut } from '../format.js';
  import Kpi from '../lib/Kpi.svelte';
  import ChartCard from '../lib/ChartCard.svelte';
  import HBar from '../lib/HBar.svelte';
  import DataTable from '../lib/DataTable.svelte';
  import Note from '../lib/Note.svelte';
  import SeverityTag from '../lib/SeverityTag.svelte';
  import Skeleton from '../lib/Skeleton.svelte';
  import ErrorState from '../lib/ErrorState.svelte';

  let { folder, summary, reloadKey = 0, onready = null } = $props();
  let data = $state.raw(null), busy = $state(false), error = $state(null);
  let seq = 0;
  async function load() {
    const my = ++seq;
    busy = true; error = null; onready?.(false);
    try {
      const j = await api.get(`/api/folders/${encodeURIComponent(folder)}/pods`);
      if (my === seq) data = j;
    } catch (e) {
      if (my === seq) error = e;
    } finally {
      if (my === seq) { busy = false; onready?.(true); }
    }
  }
  $effect(() => { void [folder, reloadKey]; if (folder) load(); });

  const files = $derived(summary?.folder === folder ? summary.files : null);
  const errFiles = $derived((files || []).filter((f) => f.err).sort((a, b) => b.err - a.err).slice(0, 15));
  const pods = $derived(data?.tables['backend-pods'] || { total: 0, rows: [] });
  const topPods = $derived([...pods.rows].sort((a, b) => b.requests - a.requests).slice(0, 15));
  const STATUS = { ok: ['ok', 'pod.has_log'], kosong: [2, 'pod.no_log'], rusak: [2, 'file.rusak'], gagal: [3, 'file.gagal'] };
</script>

{#if error && !data}
  <ErrorState {error} onretry={load} />
{:else if !data || !files}
  <Skeleton kpis={5} charts={2} />
{:else}
  {@const k = data.kpi}
  <div class="content" class:dim={busy}>
    <div class="kpis">
      <Kpi icon="file" label={$t('pod.kpi.files')} value={k.files} />
      <Kpi icon="file" label={$t('pod.kpi.without_log')} value={k.files_without_log} tone={k.files_without_log ? 'warn' : 'ok'} />
      <Kpi icon="box" label={$t('pod.kpi.backend')} value={k.backend_pods} />
      <Kpi icon="refresh" label={$t('pod.kpi.retry')} value={k.pods_with_retry} tone={k.pods_with_retry ? 'err' : 'ok'} info={$t('pod.kpi.retry_info')} />
      <Kpi icon="pulse" label={$t('pod.kpi.restarts')} value={k.restarts} tone={k.restarts ? 'warn' : 'ok'} />
    </div>
    <Note>{$t('pod.note')}</Note>
    <div class="grid">
      <HBar title={$t('pod.err_chart')} rows={errFiles.map((f) => ({ label: f.pod, value: f.err }))} color="--err" valueLabel={$t('kpi.error')} />
      {#if pods.total}
        <HBar title={$t('pod.req_chart')} rows={topPods.map((r) => ({ label: `${r.upstream.replace('-3000', '')} ${r.pod}`, value: r.requests }))} color="--accent" valueLabel={$t('col.requests')} />
      {/if}
      <DataTable title={$t('pod.t.health')} rows={files} limit={500} columns={[
        { key: 'pod', label: $t('pod.col.service_pod'), fmt: (r) => `${sysName(r.service)} / ${r.pod}`, sort: true, minw: 260 },
        { key: 'lines', label: $t('col.lines'), type: 'num', sort: true },
        { key: 'err', label: $t('kpi.error'), type: 'num', cls: (r) => (r.err ? 'ERROR' : ''), sort: true },
        { key: 'warn', label: $t('kpi.warning'), type: 'num', cls: (r) => (r.warn ? 'WARN' : ''), sort: true },
        { key: 'size_bytes', label: $t('col.size'), type: 'num', fmt: (r) => `${num(r.size_bytes / 1048576, $lang, 2)} MB`, sort: true },
        { key: 'status', label: $t('col.status'), custom: true, sort: true },
      ]}>
        {#snippet cell(r)}{@const s = STATUS[r.status] || STATUS.ok}<SeverityTag level={s[0]} text={$t(s[1])} />{/snippet}
      </DataTable>
      {#if pods.total}
        <DataTable title={$t('pod.t.backend')} {folder} table="backend-pods" initial={pods} columns={[
          { key: 'upstream', label: 'Upstream', cls: () => 'nowrap', sort: true },
          { key: 'pod', label: $t('av.col.pod'), type: 'code', sort: true },
          { key: 'requests', label: $t('col.requests'), type: 'num', sort: true },
          { key: 'share', label: $t('pod.col.share'), type: 'pct', sort: true },
          { key: 'n5xx', label: '5xx', type: 'num', cls: (r) => (r.n5xx ? 'ERROR' : ''), sort: true },
          { key: 'retries', label: $t('pod.col.retries'), type: 'num', cls: (r) => (r.retries ? 'ERROR' : ''), sort: true },
        ]} />
      {/if}
      <DataTable title={$t('pod.t.restarts')} {folder} table="restarts" initial={data.tables.restarts} columns={[
        { key: 'time', label: $t('col.time'), type: 'time', cls: () => 'nowrap', sort: true },
        { key: 'pod', label: $t('col.pod'), sort: true },
        { key: 'app', label: $t('pod.col.app') },
        { key: 'seconds', label: $t('pod.col.startup'), type: 'num', fmt: (r) => dur(r.seconds, $lang), sort: true },
      ]} />
    </div>
  </div>
{/if}

<style>
  .content { transition: opacity 0.15s; }
  .content.dim { opacity: 0.6; }
  .content :global(.note) { margin-bottom: 18px; }
</style>
