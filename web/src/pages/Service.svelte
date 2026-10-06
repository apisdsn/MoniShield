<!-- Halaman layanan (DRD §3.10, inv. §2.10): satu templat untuk semua layanan. KPI: Baris log, Error, Warning,
     (HTTP request, Rate 4xx, Rate 5xx bila ada request), 4 entri pertama distribusi level; lalu kartu 2–19.
     Satu permintaan: GET /api/folders/{folder}/services/{service}. 0 baris -> keadaan kosong (DRD §6.6). -->
<script>
  import { lang, t } from '../i18n.js';
  import { api } from '../api.js';
  import { num } from '../format.js';
  import Kpi from '../lib/Kpi.svelte';
  import Note from '../lib/Note.svelte';
  import SeverityTag from '../lib/SeverityTag.svelte';
  import Skeleton from '../lib/Skeleton.svelte';
  import ErrorState from '../lib/ErrorState.svelte';
  import ServiceCards from '../lib/ServiceCards.svelte';

  let { folder, service, reloadKey = 0, onready = null } = $props();
  let data = $state(null), busy = $state(false), error = $state(null);
  let seq = 0;

  async function load() {
    const my = ++seq;
    busy = true; error = null; onready?.(false);
    try {
      const j = await api.get(`/api/folders/${encodeURIComponent(folder)}/services/${encodeURIComponent(service)}`);
      if (my === seq) data = j;
    } catch (e) {
      if (my === seq) error = e;
    } finally {
      if (my === seq) { busy = false; onready?.(true); }
    }
  }
  $effect(() => { void [folder, service, reloadKey]; if (folder && service) load(); });

  const k = $derived(data?.kpi);
  const rate = (n, d) => (k?.requests ? `${num((n / k.requests) * 100, $lang, d)}%` : null);
  const errInfo = $derived(k && ['nginx-ingress-controller', 'om-fe-inhouse'].includes(service)
    ? $t('kpi.error_info', { http: num(k.err_http, $lang), log: num(k.err_log, $lang) }) : null);
</script>

{#if error && !data}
  <ErrorState {error} onretry={load} />
{:else if !data}
  <Skeleton kpis={6} charts={4} />
{:else}
  <div class="content" class:dim={busy}>
    {#if !data.available}
      <Note>
        {$t('svc.empty')}
        {#if k.files_corrupt}{' '}<SeverityTag level={2} text={$t('file.rusak')} /> {$t('svc.corrupt_files', { n: num(k.files_corrupt, $lang) })}{/if}
      </Note>
    {:else}
      <div class="kpis">
        <Kpi icon="lines" label={$t('svc.kpi_lines')} value={k.lines} />
        <Kpi icon="alert" label={$t('kpi.error')} value={k.err} tone="err" info={errInfo} />
        <Kpi icon="alert" label={$t('kpi.warning')} value={k.warn} tone="warn" />
        {#if k.requests}
          <Kpi icon="pulse" label={$t('kpi.http')} value={k.requests} />
          <Kpi icon="trend" label={$t('kpi.rate4xx')} value={rate(k.n4xx, 1)} tone="warn" />
          <Kpi icon="trend" label={$t('kpi.rate5xx')} value={rate(k.n5xx, 2)} tone="err" />
        {/if}
        {#each data.levels.slice(0, 4) as [lvl, n]}<Kpi label={lvl} value={n} tone="muted" />{/each}
      </div>
      <div class="grid">
        <ServiceCards {data} {folder} />
      </div>
    {/if}
  </div>
{/if}

<style>
  .content { transition: opacity 0.15s; }
  .content.dim { opacity: 0.6; }
</style>
