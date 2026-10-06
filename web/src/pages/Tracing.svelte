<!-- Pelacakan Request (DRD §3.9, inv. §2.9): 6 KPI, catatan, 2 chart, tabel jejak gagal/lambat nginx → aplikasi.
     Satu permintaan: GET /api/folders/{folder}/tracing. Berubah dari lama: jejak tidak dipotong 300 (TRD §4.4 butir 1;
     KPI dan chart dihitung dari semua jejak, tabel 300 pertama + "tampilkan berikutnya"); "lambat ≥ 5 dtk" memuat
     semua status selain gagal (butir 9). ASUMSI: tanpa satu pun request yang cocok (matched = 0) tampil catatan,
     bukan halaman berisi nol seperti lama (DRD §6.6). -->
<script>
  import { lang, t } from '../i18n.js';
  import { api } from '../api.js';
  import { num } from '../format.js';
  import Kpi from '../lib/Kpi.svelte';
  import HBar from '../lib/HBar.svelte';
  import DataTable from '../lib/DataTable.svelte';
  import AttackUrl from '../lib/AttackUrl.svelte';
  import Note from '../lib/Note.svelte';
  import Skeleton from '../lib/Skeleton.svelte';
  import ErrorState from '../lib/ErrorState.svelte';

  let { folder, hosts = {}, reloadKey = 0, onready = null } = $props();
  let data = $state.raw(null), busy = $state(false), error = $state(null);
  let seq = 0;
  async function load() {
    const my = ++seq;
    busy = true; error = null; onready?.(false);
    try {
      const j = await api.get(`/api/folders/${encodeURIComponent(folder)}/tracing`);
      if (my === seq) data = j;
    } catch (e) {
      if (my === seq) error = e;
    } finally {
      if (my === seq) { busy = false; onready?.(true); }
    }
  }
  $effect(() => { void [folder, reloadKey]; if (folder) load(); });

  const pct1 = (a, b) => (b ? `${num((a / b) * 100, $lang, 1)}%` : '-');
  // URL panjang dipotong 200 karakter (lama); teks lengkap di tooltip sel
  const cut200 = (s) => (s.length > 200 ? s.slice(0, 199) + '…' : s);
</script>

{#if error && !data}
  <ErrorState {error} onretry={load} />
{:else if !data}
  <Skeleton kpis={6} charts={2} />
{:else if !data.available || !data.corr.matched}
  <Note>{$t('trc.none')}</Note>
{:else}
  {@const k = data.kpi}
  {@const c = data.corr}
  <div class="content" class:dim={busy}>
    <div class="kpis">
      <Kpi icon="route" label={$t('trc.kpi.total')} value={c.total} />
      <Kpi icon="route" label={$t('trc.kpi.matched')} value={c.matched} />
      <Kpi icon="pulse" label={$t('trc.kpi.rate')} value={pct1(c.matched, c.total)} />
      <Kpi icon="alert" label={$t('trc.kpi.failed')} value={k.failed_requests} tone="err" />
      <Kpi icon="globe" label={$t('trc.kpi.failed_ips')} value={k.failed_ips} tone="warn" />
      <Kpi icon="clock" label={$t('trc.kpi.slow')} value={k.slow_requests} tone="warn" info={$t('trc.kpi.slow_info')} />
    </div>
    <Note>{$t('trc.note', { pct: pct1(c.total - c.matched, c.total) })}</Note>
    <div class="grid">
      {#if data.by_ip.length}
        <HBar title={$t('trc.ip_chart')} rows={data.by_ip.map((r) => ({ label: r.ip, value: r.n, org: r.org }))} color="--err" valueLabel={$t('trc.kpi.failed')} />
      {/if}
      {#if data.by_error.length}
        <HBar title={$t('trc.err_chart')} rows={data.by_error.map(([l, n]) => ({ label: l, value: n }))} color="--warn" valueLabel={$t('col.request')} />
      {/if}
      <DataTable title={$t('trc.t.trace')} {folder} table="trace" initial={data.tables.trace} columns={[
        { key: 'client', label: 'IP', type: 'ip', sort: true },
        { key: 'status', label: $t('col.status'), type: 'status', sort: true },
        { key: 'error', label: 'Error', cls: () => 'small', sort: true, minw: 150 },
        { key: 'url', label: $t('trc.col.url'), custom: true, minw: 320 },
        { key: 'n', label: $t('table.count'), type: 'num', sort: true },
        { key: 'max_ms', label: $t('trc.col.max'), type: 'dur', sort: true },
        { key: 'first', label: $t('col.time'), type: 'range', to: 'last', sort: true, minw: 130 },
      ]}>
        {#snippet cell(r)}<span title={r.url}><AttackUrl methodPath={cut200(r.url)} upstreams={[r.upstream]} ua={r.ua} {hosts} /></span>{/snippet}
      </DataTable>
    </div>
  </div>
{/if}

<style>
  .content { transition: opacity 0.15s; }
  .content.dim { opacity: 0.6; }
  .content :global(.note) { margin-bottom: 18px; }
</style>
