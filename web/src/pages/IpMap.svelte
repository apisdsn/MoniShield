<!-- Peta IP (DRD §3.2, inv. §2.2): pemilih modul (di alamat: ?modul=), 6 KPI, kartu peta + tabel alur (lib/FlowMap).
     Satu permintaan: GET /api/folders/{folder}/map[?module=…]. Ganti modul hanya mengganti data; posisi dan zoom peta
     tetap (komponen peta tidak dibuat ulang). Lokasi IP dari MaxMind GeoLite2 (lama: DB-IP), jadi jumlah lokasi dan
     negara berbeda dari dashboard lama (selisih vendor, rencana Tahap 7). -->
<script>
  import { lang, t } from '../i18n.js';
  import { api } from '../api.js';
  import { route, go } from '../state.js';
  import Kpi from '../lib/Kpi.svelte';
  import FlowMap from '../lib/FlowMap.svelte';
  import Note from '../lib/Note.svelte';
  import Skeleton from '../lib/Skeleton.svelte';
  import ErrorState from '../lib/ErrorState.svelte';

  let { folder, server = null, reloadKey = 0, onready = null } = $props();
  let data = $state.raw(null), busy = $state(false), error = $state(null);
  let seq = 0;
  const module = $derived($route.module || null);
  async function load() {
    const my = ++seq;
    busy = true; error = null; onready?.(false);
    try {
      const q = module ? `?module=${encodeURIComponent(module)}` : '';
      const j = await api.get(`/api/folders/${encodeURIComponent(folder)}/map${q}`);
      if (my === seq) data = j;
    } catch (e) {
      if (my === seq) {
        if (e.status === 404 && module) go({ module: null }, { replace: true });   // modul tidak ada di folder ini -> semua modul
        else error = e;
      }
    } finally {
      if (my === seq) { busy = false; onready?.(true); }
    }
  }
  $effect(() => { void [folder, module, reloadKey]; if (folder) load(); });
</script>

{#if error && !data}
  <ErrorState {error} onretry={load} />
{:else if !data}
  <Skeleton kpis={6} charts={1} />
{:else if !data.available}
  <Note>{$t('map.no_nginx')}</Note>
{:else}
  {@const k = data.kpi}
  <div class="content" class:dim={busy}>
    <p class="modsel">
      <label for="map-mod" class="sr-only">{$t('map.module')}</label>
      <select id="map-mod" value={module ?? ''} onchange={(e) => go({ module: e.currentTarget.value || null })}>
        <option value="">{$t('map.all_modules')}</option>
        {#each data.modules as m}<option value={m}>{m}</option>{/each}
      </select>
    </p>
    <div class="kpis">
      <Kpi icon="globe" label={$t('map.kpi.ips')} value={k.source_ips} />
      <Kpi icon="globe" label={$t('map.kpi.locations')} value={k.locations} />
      <Kpi icon="globe" label={$t('map.kpi.countries')} value={k.countries} />
      <Kpi icon="box" label={$t('map.kpi.modules')} value={k.modules} />
      <Kpi icon="server" label={$t('map.kpi.pods')} value={k.dest_pods} />
      <Kpi icon="pulse" label={$t('map.kpi.requests')} value={k.requests} />
    </div>
    <div class="grid">
      <FlowMap {data} {folder} module={data.module} {server} />
    </div>
  </div>
{/if}

<style>
  .content { transition: opacity 0.15s; }
  .content.dim { opacity: 0.6; }
  .modsel { margin-bottom: 14px; }
  .modsel select { min-width: 220px; max-width: 100%; }
</style>
