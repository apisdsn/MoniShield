<!-- KPI card (DRD §4.1, §12 style): icon in a box + label (+ "(i)" tooltip), large number with a dimmed suffix
     (e.g. "/40") and a ▲/▼ change badge next to it, then a small line (comparison or status dot).
     value null = the required log is missing -> "–" + explanation (U16, Q6). tone colors the number when meaningful
     ('err' | 'warn' | 'ok' | 'muted'); neutral = white. Changes always come with text for screen readers (§9.2).
     Redesign 2026-10-27: a zero ("0", "0,00%") is always neutral, so colour means "look here"; a change that could not be
     computed ("… not compared") is not repeated under every KPI but registered once per page (lib/compare.js);
     `size="lg"` = one of the page's main numbers. On phones a KPI is a row: icon and label left, number right. -->
<script>
  import { lang, t } from '../i18n.js';
  import { num } from '../format.js';
  import InfoTip from './InfoTip.svelte';
  import Icon from './Icon.svelte';
  import { holdNote } from './compare.js';
  let { label, value, tone = null, delta = null, info = null, missing = null, format = null, icon = null, suffix = null, sub = null, size = null } = $props();
  const shown = $derived(value === null || value === undefined ? '–' : format ? format(value, $lang) : typeof value === 'number' ? num(value, $lang) : value);
  const zero = $derived(value === 0 || /^[0.,]+\s*%?$/.test(String(shown)));
  const pct = $derived(delta && (delta.kind === 'up' || delta.kind === 'down'));
  const shownDelta = $derived(delta?.kind === 'incomplete' ? null : delta);
  $effect(() => { if (delta?.kind === 'incomplete' && value !== null && value !== undefined) return holdNote(delta.text); });
</script>

<div class="kpi" class:lg={size === 'lg'}>
  <div class="hd">
    {#if icon}<span class="ic"><Icon name={icon} size={17} /></span>{/if}
    <span class="l">{label}</span>
    {#if info}<InfoTip text={info} />{/if}
  </div>
  <div class="vrow">
    <span class="v {zero ? '' : tone ?? ''}" class:none={shown === '–'}>{shown}</span>
    {#if suffix && shown !== '–'}<span class="sfx">{suffix}</span>{/if}
    {#if pct}<span class="badge {delta.tone ?? ''}" aria-hidden="true">{delta.short}</span>{/if}
  </div>
  {#if shown === '–'}
    <span class="dl">{missing ?? $t('kpi.no_log')}</span>
  {:else if sub?.length}
    <span class="dl dots">{#each sub as s}<span><span class="dot {s.tone || ''}" aria-hidden="true"></span>{s.text}</span>{/each}</span>
  {/if}
  {#if shownDelta && shown !== '–'}
    <span class="dl"><span aria-hidden="true">{pct ? shownDelta.rest : shownDelta.text}</span><span class="sr-only">{shownDelta.spoken ?? shownDelta.text}</span></span>
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
  .lg .v { font-size: 2.5rem; }
  .lg .l { font-size: 0.875rem; }
  @media (max-width: 900px) {
    /* a row: label (and its notes) left, number right */
    .kpi { display: grid; grid-template-columns: minmax(0, 1fr) auto; align-items: center; gap: 2px 12px; padding: 12px 14px; }
    .hd { grid-column: 1; grid-row: 1; }
    .ic { width: 28px; height: 28px; border-radius: 8px; }
    .vrow { grid-column: 2; grid-row: 1 / span 3; margin: 0; justify-content: flex-end; }
    .dl { grid-column: 1; padding-left: 38px; }
    .v, .lg .v { font-size: 1.375rem; }
  }
</style>
