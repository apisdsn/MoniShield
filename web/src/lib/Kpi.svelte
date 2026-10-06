<!-- Kartu KPI (DRD §4.1). value null = log yang dibutuhkan tidak ada -> "–" + keterangan (U16, ASUMSI D3/Q6).
     tone: 'grad' (netral, gradien aksen) | 'err' | 'warn' | 'ok' | 'muted'. delta dari format.delta(). -->
<script>
  import { lang, t } from '../i18n.js';
  import { num } from '../format.js';
  import InfoTip from './InfoTip.svelte';
  let { label, value, tone = 'grad', delta = null, info = null, missing = null, format = null } = $props();
  const shown = $derived(value === null || value === undefined ? '–' : format ? format(value, $lang) : typeof value === 'number' ? num(value, $lang) : value);
</script>

<div class="kpi">
  <div class="l">{label}{#if info}<InfoTip text={info} />{/if}</div>
  <div class="v {tone}" class:none={shown === '–'}>{shown}</div>
  {#if shown === '–'}
    <span class="dl">{missing ?? $t('kpi.no_log')}</span>
  {:else if delta}
    <span class="dl {delta.tone ?? ''}"><span aria-hidden="true">{delta.text}</span><span class="sr-only">{delta.spoken ?? delta.text}</span></span>
  {/if}
</div>

<style>
  .kpi { padding: 18px 20px; min-width: 0; }
  .l { color: var(--kpi-label); font-size: 0.84375rem; font-weight: 500; text-transform: capitalize; display: flex; align-items: center; flex-wrap: wrap; }
  .v { font-size: 2.125rem; font-weight: 600; margin-top: 8px; font-variant-numeric: tabular-nums; letter-spacing: -0.01em; line-height: 1.15; overflow-wrap: anywhere; }
  .v.grad { background: var(--kpi-grad); -webkit-background-clip: text; background-clip: text; color: transparent; }
  .v.err { color: var(--err); } .v.warn { color: var(--warn); } .v.ok { color: var(--ok); } .v.muted, .v.none { color: var(--muted); background: none; }
  .dl { display: block; font-size: 0.71875rem; margin-top: 4px; color: var(--muted); }
  .dl.bad { color: var(--err); } .dl.good { color: var(--ok-text); }
  @media (max-width: 900px) { .v { font-size: 1.75rem; } }
</style>
