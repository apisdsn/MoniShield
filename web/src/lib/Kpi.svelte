<!-- Kartu KPI (DRD §4.1, gaya §12): ikon dalam kotak + label (+ keterangan "(i)"), angka besar dengan akhiran redup
     (mis. "/40") dan lencana perubahan ▲/▼ di sebelahnya, lalu baris kecil (perbandingan atau titik status).
     value null = log yang dibutuhkan tidak ada -> "–" + keterangan (U16, Q6). tone mewarnai angka bila bermakna
     ('err' | 'warn' | 'ok' | 'muted'); netral = putih. Perubahan selalu disertai teks untuk pembaca layar (§9.2). -->
<script>
  import { lang, t } from '../i18n.js';
  import { num } from '../format.js';
  import InfoTip from './InfoTip.svelte';
  import Icon from './Icon.svelte';
  let { label, value, tone = null, delta = null, info = null, missing = null, format = null, icon = null, suffix = null, sub = null } = $props();
  const shown = $derived(value === null || value === undefined ? '–' : format ? format(value, $lang) : typeof value === 'number' ? num(value, $lang) : value);
  const pct = $derived(delta && (delta.kind === 'up' || delta.kind === 'down'));
</script>

<div class="kpi">
  <div class="hd">
    {#if icon}<span class="ic"><Icon name={icon} size={17} /></span>{/if}
    <span class="l">{label}</span>
    {#if info}<InfoTip text={info} />{/if}
  </div>
  <div class="vrow">
    <span class="v {tone ?? ''}" class:none={shown === '–'}>{shown}</span>
    {#if suffix && shown !== '–'}<span class="sfx">{suffix}</span>{/if}
    {#if pct}<span class="badge {delta.tone ?? ''}" aria-hidden="true">{delta.short}</span>{/if}
  </div>
  {#if shown === '–'}
    <span class="dl">{missing ?? $t('kpi.no_log')}</span>
  {:else if sub?.length}
    <span class="dl dots">{#each sub as s}<span><span class="dot {s.tone || ''}" aria-hidden="true"></span>{s.text}</span>{/each}</span>
  {/if}
  {#if delta && shown !== '–'}
    <span class="dl"><span aria-hidden="true">{pct ? delta.rest : delta.text}</span><span class="sr-only">{delta.spoken ?? delta.text}</span></span>
  {/if}
</div>

<style>
  .kpi { padding: 16px 18px; min-width: 0; display: flex; flex-direction: column; gap: 6px; }
  .hd { display: flex; align-items: center; gap: 10px; min-width: 0; }
  .ic {
    width: 32px; height: 32px; border-radius: 9px; display: grid; place-items: center; flex: none;
    background: var(--icon-bg); border: 1px solid var(--icon-border); color: var(--kpi-label);
  }
  .l { color: var(--kpi-label); font-size: 0.84375rem; font-weight: 500; text-transform: capitalize; min-width: 0; }
  .vrow { display: flex; align-items: baseline; gap: 8px; flex-wrap: wrap; margin-top: 4px; }
  .v { font-size: 1.875rem; font-weight: 600; font-variant-numeric: tabular-nums; letter-spacing: -0.01em; line-height: 1.15; color: var(--fg); overflow-wrap: anywhere; }
  .v.err { color: var(--err); } .v.warn { color: var(--warn); } .v.ok { color: var(--ok); } .v.muted, .v.none { color: var(--muted); }
  .sfx { color: var(--muted); font-size: 1rem; font-weight: 500; }
  .badge { font-size: 0.75rem; font-weight: 600; color: var(--muted); white-space: nowrap; }
  .badge.bad { color: var(--err); } .badge.good { color: var(--ok-text); }
  .dl { display: block; font-size: 0.75rem; color: var(--muted); }
  .dots { display: flex; flex-wrap: wrap; gap: 4px 12px; }
  @media (max-width: 900px) { .v { font-size: 1.625rem; } .kpi { padding: 14px; } }
</style>
