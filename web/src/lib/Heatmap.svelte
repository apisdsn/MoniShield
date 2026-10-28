<!-- Hour × date heatmap (Stage 24 item 8). One sequential color (light -> dark accent) for magnitude; empty cell =
     no data. 5 classes (linear quantization against the largest value) with a legend. Hover/focus a cell -> caption
     above the grid (text, not color only); "Lihat sebagai tabel" shows the same numbers (DRD §9.2).
     days: ['YYYY-MM-DD', …] (WIB dates), rows: [[24 numbers], …] aligned with days. -->
<script>
  import { lang, t } from '../i18n.js';
  import { num, dLabel } from '../format.js';
  let { title, days = [], rows = [], unit = '', chip = null } = $props();
  let asTable = $state(false), hover = $state(null);
  const uid = `hm-${Math.random().toString(36).slice(2, 8)}`;
  const max = $derived(Math.max(1, ...rows.flat()));
  const STEPS = [18, 36, 56, 78, 100];   // % of accent mixed into the card background
  const cls = (v) => (v <= 0 ? -1 : Math.min(4, Math.floor((v / max) * 5 - 1e-9)));
  const bg = (v) => { const c = cls(v); return c < 0 ? 'var(--card2)' : `color-mix(in srgb, var(--accent) ${STEPS[c]}%, var(--card2))`; };
  const H = Array.from({ length: 24 }, (_, h) => h);
  const hh = (h) => String(h).padStart(2, '0');
  const say = (d, h, v) => $t('hm.cell', { date: dLabel(d, $lang), h: hh(h), v: num(v, $lang), unit });
  const lo = (c) => Math.round((max * c) / 5) + 1, hi = (c) => Math.round((max * (c + 1)) / 5);
</script>

<section class="card wide hm" aria-labelledby="{uid}-h">
  <header>
    <h2 id="{uid}-h">{title}</h2>
    <div class="acts">
      {#if chip}<span class="chip">{chip}</span>{/if}
      <button class="btn sm" aria-pressed={asTable} onclick={() => (asTable = !asTable)}>{asTable ? $t('chart.as_chart') : $t('chart.as_table')}</button>
    </div>
  </header>
  {#if !days.length}
    <p class="muted">{$t('hm.empty')}</p>
  {:else if asTable}
    <div class="scroll tt" tabindex="0" role="region" aria-label={title}>
      <table>
        <caption class="sr-only">{title}</caption>
        <thead><tr><th scope="col">{$t('hm.date')}</th>{#each H as h}<th scope="col" class="n">{hh(h)}</th>{/each}</tr></thead>
        <tbody>{#each days as d, i}<tr><th scope="row" class="nowrap">{dLabel(d, $lang)}</th>{#each H as h}<td class="n">{num(rows[i][h], $lang)}</td>{/each}</tr>{/each}</tbody>
      </table>
    </div>
  {:else}
    <p class="readout" aria-live="polite">{hover ? say(...hover) : $t('hm.hint')}</p>
    <div class="scroll">
      <div class="grid24" role="img" aria-label={$t('hm.aria', { title, n: days.length })}>
        <span></span>{#each H as h}<span class="hx" aria-hidden="true">{h % 3 === 0 ? hh(h) : ''}</span>{/each}
        {#each days as d, i}
          <span class="dy">{dLabel(d, $lang)}</span>
          {#each H as h}
            {@const v = rows[i][h]}
            <span class="cell" style:background={bg(v)} title={say(d, h, v)} tabindex="-1"
              onmouseenter={() => (hover = [d, h, v])} onmouseleave={() => (hover = null)}></span>
          {/each}
        {/each}
      </div>
    </div>
    <div class="legend" aria-hidden="true">
      <span class="muted">{$t('hm.less')}</span>
      <span class="sw" style:background="var(--card2)" title="0"></span>
      {#each STEPS as s, c}<span class="sw" style:background={`color-mix(in srgb, var(--accent) ${s}%, var(--card2))`} title={`${num(lo(c), $lang)}–${num(hi(c), $lang)}`}></span>{/each}
      <span class="muted">{$t('hm.more', { max: num(max, $lang), unit })}</span>
    </div>
  {/if}
</section>

<style>
  header { display: flex; align-items: center; justify-content: space-between; gap: 10px; flex-wrap: wrap; margin-bottom: 10px; }
  h2 { font-size: 0.9375rem; font-weight: 600; color: var(--heading); text-transform: capitalize; }
  .acts { display: flex; align-items: center; gap: 8px; }
  .readout { margin: 0 0 8px; font-size: 0.8125rem; min-height: 1.3em; color: var(--fg); }
  .scroll { overflow-x: auto; }
  .grid24 { display: grid; grid-template-columns: max-content repeat(24, minmax(14px, 1fr)); gap: 2px; min-width: 520px; }
  .hx { font-size: 0.625rem; color: var(--muted); text-align: left; }
  .dy { font-size: 0.6875rem; color: var(--kpi-label); padding-right: 8px; white-space: nowrap; align-self: center; }
  .cell { height: 18px; border-radius: 4px; box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--line) 60%, transparent); }
  .cell:hover { outline: 2px solid var(--focus); outline-offset: 0; }
  .legend { display: flex; align-items: center; gap: 4px; margin-top: 10px; font-size: 0.75rem; flex-wrap: wrap; }
  .sw { width: 16px; height: 12px; border-radius: 3px; box-shadow: inset 0 0 0 1px var(--line); }
  .legend .muted:last-child { margin-left: 4px; }
  table { border-collapse: collapse; font-size: 0.75rem; }
  th, td { padding: 4px 6px; border-bottom: 1px solid var(--row-line); }
  .n { text-align: right; font-variant-numeric: tabular-nums; }
  .tt { max-height: 420px; }
</style>
