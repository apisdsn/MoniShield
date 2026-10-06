<!-- Peta di halaman layanan (DRD §3.10, ASUMSI Q5: terlipat): ingress nginx = semua alur; modul di belakang ingress =
     alur modul itu saja. Ada alur atau tidak dibaca dari respons halaman layanan (`has_flows`); bila ada, data peta
     diminta saat halaman dibuka dan peta (MapLibre) baru dibuat saat bagian ini dibuka. Tanpa alur: tidak tampil. -->
<script>
  import { lang, t } from '../i18n.js';
  import { api } from '../api.js';
  import { num } from '../format.js';
  import FlowMap from './FlowMap.svelte';

  let { folder, service, hasFlows = false, server = null } = $props();
  const NG = 'nginx-ingress-controller';
  let data = $state.raw(null), open = $state(false);
  $effect(() => {
    const f = folder, s = service;
    data = null; open = false;
    if (!hasFlows) return;   // dari respons halaman layanan: tanpa alur -> tidak meminta peta (yang menjawab 404)
    const q = s === NG ? '' : `?module=${encodeURIComponent(s)}`;
    api.get(`/api/folders/${encodeURIComponent(f)}/map${q}`).then((j) => { if (f === folder && s === service) data = j; }, () => {});
  });
</script>

{#if data?.available && data.kpi.requests}
  <details class="card wide sm" bind:open>
    <summary>
      <span class="h">{$t('map.title')}</span>
      <span class="muted">{$t('map.svc_summary', { n: num(data.kpi.requests, $lang), loc: num(data.kpi.locations, $lang) })}</span>
    </summary>
  </details>
  {#if open}<FlowMap {data} {folder} module={data.module} {server} />{/if}
{/if}

<style>
  .sm summary { cursor: pointer; display: flex; flex-wrap: wrap; align-items: baseline; gap: 6px 14px; min-height: 28px; list-style: none; }
  .sm summary::before { content: '▸'; color: var(--accent-text); }
  .sm[open] summary::before { content: '▾'; }
  .sm summary::-webkit-details-marker { display: none; }
  .h { font-size: 0.9375rem; font-weight: 600; color: var(--heading); text-transform: capitalize; }
  .muted { font-size: 0.8125rem; }
</style>
