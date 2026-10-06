<!-- Kerangka abu seukuran isi akhir (DRD §6.5): baris KPI, kartu chart 280 px, tabel 6 baris. Muncul hanya bila
     data belum tiba dalam 200 ms, supaya perpindahan cepat tidak berkedip. -->
<script>
  import { onMount } from 'svelte';
  import { t } from '../i18n.js';
  let { kpis = 4, charts = 2, table = true } = $props();
  let show = $state(false);
  onMount(() => { const id = setTimeout(() => (show = true), 200); return () => clearTimeout(id); });
</script>

<div class="sk" class:show aria-hidden="true">
  {#if kpis}<div class="kpis">{#each Array(kpis) as _}<div class="kpi blk" style="height:108px"></div>{/each}</div>{/if}
  <div class="grid">
    {#each Array(charts) as _}<div class="card blk" style="height:336px"></div>{/each}
    {#if table}<div class="card wide blk tbl">{#each Array(6) as _}<div class="row"></div>{/each}</div>{/if}
  </div>
</div>
<span class="sr-only" role="status">{$t('state.loading')}</span>

<style>
  .sk { visibility: hidden; }
  .sk.show { visibility: visible; }
  .blk { background: var(--card); box-shadow: none; position: relative; overflow: hidden; }
  .blk::after {
    content: ''; position: absolute; inset: 0;
    background: linear-gradient(90deg, transparent, rgba(148, 163, 184, 0.06), transparent);
    animation: kilau 1.4s infinite;
  }
  .tbl { display: grid; gap: 14px; padding: 24px; }
  .row { height: 14px; border-radius: 6px; background: var(--line); }
  @keyframes kilau { from { transform: translateX(-100%); } to { transform: translateX(100%); } }
</style>
