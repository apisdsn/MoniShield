<!-- Map on the service page (DRD §3.10, ASSUMPTION Q5: collapsed): nginx ingress = all flows; module behind the ingress =
     that module's flows only. Whether there are flows is read from the service page response (`has_flows`); if there are, map data
     is requested when the page opens and the map (MapLibre) is only created when this section is expanded. No flows: not shown. -->
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
    if (!hasFlows) return;   // from the service page response: no flows -> do not request the map (which answers 404)
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
