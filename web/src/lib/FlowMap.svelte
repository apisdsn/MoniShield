<!-- Kartu "Peta IP Asal → IP Tujuan" + legenda + tabel alur + catatan (DRD §3.2, §7; inv. §2.2). Dipakai halaman
     Peta IP dan halaman layanan (terlipat). `data` = respons GET /api/folders/{folder}/map[?module=…]. Tabel alur
     adalah pengganti peta (§7.9): tautan "Lewati peta" melompat ke sana; "Lihat di tabel" mengisi filternya.
     `aside` (Command Center, Tahap 22): kartu yang tampil di samping peta pada layar lebar, di bawahnya pada layar sempit;
     `tall`: peta setinggi layar dan `aside` selalu di bawah peta (permintaan pemilik: peta Command Center selebar layar). -->
<script>
  import { tick } from 'svelte';
  import { lang, t, countryName } from '../i18n.js';
  import { num } from '../format.js';
  import MapView from './MapView.svelte';
  import DataTable from './DataTable.svelte';
  import Note from './Note.svelte';

  let { data, folder, module = null, server = null, aside = null, tall = false } = $props();
  let preset = $state('id'), search = $state(null), seq = 0;
  const uid = `fm-${Math.random().toString(36).slice(2, 8)}`;

  const place = (l) => [l.city, l.region, $countryName(l.cc)].filter(Boolean).filter((x, i, a) => a.indexOf(x) === i).join(', ');
  const where = (r) => (r.location === 'internal' ? $t('map.internal') : r.location ? place(r.location) || $t('map.unknown') : $t('map.unknown'));
  async function pick(name) {
    search = { text: name, seq: ++seq };
    await tick();
    const el = document.getElementById(`${uid}-flows`);
    el?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    el?.querySelector('input[data-filter]')?.focus({ preventScroll: true });
  }
</script>

{#snippet mapCard()}
<section class="card wide fm" aria-labelledby="{uid}-h">
  <header>
    <h2 id="{uid}-h">{$t('map.title')}</h2>
    <div class="seg" role="group" aria-label={$t('map.preset')}>
      <button type="button" aria-pressed={preset === 'id'} onclick={() => (preset = 'id')}>Indonesia</button>
      <button type="button" aria-pressed={preset === 'world'} onclick={() => (preset = 'world')}>{$t('map.world')}</button>
    </div>
  </header>
  <a class="skip" href="#{uid}-flows">{$t('map.skip')}</a>
  <MapView points={data.points} {server} {tall} bind:preset onpick={pick} label={$t('map.aria')} />
  <div class="legend">
    <span><i class="dot loc"></i>{$t('map.lg.loc')}</span>
    <span><i class="dot srv"></i>{$t('map.lg.srv')}</span>
    <span><i class="dot cl"></i>{$t('map.lg.cluster')}</span>
    <span><i class="flow" aria-hidden="true"></i>{$t('map.lg.flow')}</span>
    <span class="muted">{$t('map.lg.sentence', { abroad: num(data.abroad_requests, $lang), unloc: num(data.unlocated_requests, $lang) })}</span>
  </div>
</section>
{/snippet}
{#if aside}<div class="wide-slot side-row" class:stack={tall}>{@render mapCard()}{@render aside()}</div>{:else}{@render mapCard()}{/if}
<div id="{uid}-flows" class="wide-slot">
  <DataTable title={$t('map.flows')} {folder} table="flows" params={module ? { module } : {}} initial={data.tables.flows} {search} columns={[
    { key: 'src', label: $t('map.col.src'), type: 'ip', sort: true },
    { key: 'location', label: $t('map.col.location'), fmt: (r) => where(r), minw: 180 },
    { key: 'module', label: $t('map.col.module'), cls: () => 'nowrap sys', sort: true },
    { key: 'pods', label: $t('map.col.pods'), custom: true, minw: 170 },
    { key: 'requests', label: $t('col.requests'), type: 'num', sort: true },
  ]}>
    {#snippet cell(r)}<div class="small">{#each r.pods as [p, n]}<div class="nowrap"><code>{p}</code> ×{num(n, $lang)}</div>{/each}</div>{/snippet}
  </DataTable>
</div>
<Note>{$t('map.note', { server: server?.ip ?? '' })}</Note>

<style>
  .fm header { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; margin-bottom: 12px; }
  .seg { display: inline-flex; border: 1px solid var(--line-strong); border-radius: 999px; padding: 3px; gap: 2px; }
  .seg button { all: unset; cursor: pointer; padding: 6px 14px; border-radius: 999px; font-size: 0.8125rem; min-height: 28px; display: inline-flex; align-items: center; }
  .seg button[aria-pressed='true'] { background: var(--accent); color: var(--brand-fg); font-weight: 600; }
  .seg button:focus-visible { outline: 2px solid var(--focus); outline-offset: 1px; }
  .skip { position: absolute; left: -9999px; }
  .skip:focus { position: static; display: inline-block; margin-bottom: 8px; }
  .legend { display: flex; flex-wrap: wrap; gap: 6px 18px; align-items: center; margin-top: 10px; font-size: 0.8125rem; }
  .legend span { display: inline-flex; align-items: center; gap: 6px; }
  .dot { width: 12px; height: 12px; border-radius: 50%; display: inline-block; }
  .dot.loc { background: var(--accent); box-shadow: 0 0 0 2px color-mix(in srgb, var(--accent) 45%, transparent); }
  .dot.srv { background: var(--c10); }
  .dot.cl { width: 16px; height: 16px; background: color-mix(in srgb, var(--accent) 28%, transparent); box-shadow: inset 0 0 0 2px var(--accent); }
  .flow { width: 26px; height: 3px; border-radius: 2px; display: inline-block; position: relative;
    background: linear-gradient(90deg, color-mix(in srgb, var(--accent) 20%, transparent), var(--accent)); }
  .flow::after { content: ''; position: absolute; right: -2px; top: -2.5px; width: 8px; height: 8px; border-radius: 50%; background: var(--c10); }
  .wide-slot { grid-column: 1 / -1; min-width: 0; }
  .small { font-size: 0.75rem; }
  .side-row { display: grid; gap: 18px; grid-template-columns: minmax(0, 1fr); align-items: start; }
  .side-row > :global(.card) { grid-column: auto; margin-bottom: 0; }
  @media (min-width: 1200px) { .side-row:not(.stack) { grid-template-columns: minmax(0, 2fr) minmax(300px, 1fr); } }
  @media (max-width: 900px) { .seg button { min-height: 38px; } }
</style>
