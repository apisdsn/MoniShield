<!-- MoniShield-styled date picker (owner request 2026-10-07: the browser's built-in date input is "kurang bagus").
     Button holding the formatted date (ID/EN) -> popup calendar: previous/next month, Monday on the left, today
     ringed, selected in accent color, dates after `max` disabled, "Hari ini" and "Kosongkan".
     Keyboard (ARIA grid pattern): arrows ±1 day/±1 week, PageUp/PageDown ±1 month, Home/End start/end of week,
     Enter/Space selects, Esc closes and returns focus to the button. Value = 'YYYY-MM-DD' or ''. -->
<script>
  import { tick } from 'svelte';
  import { lang, t } from '../i18n.js';
  import { dLabel, locale } from '../format.js';
  import Icon from './Icon.svelte';

  let { value = $bindable(''), id, disabled = false, max = null, onchange = null } = $props();

  const iso = (d) => d.toISOString().slice(0, 10);
  const parse = (s) => new Date(`${s}T00:00:00Z`);
  const add = (s, days) => { const d = parse(s); d.setUTCDate(d.getUTCDate() + days); return iso(d); };
  const addMonth = (s, n) => {
    const d = parse(s), day = d.getUTCDate();
    d.setUTCDate(1); d.setUTCMonth(d.getUTCMonth() + n);
    const last = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 1, 0)).getUTCDate();
    d.setUTCDate(Math.min(day, last)); return iso(d);
  };
  const wib = () => iso(new Date(Date.now() + 7 * 3600e3));   // folder date = WIB
  const today = $derived(wib());
  const limit = $derived(max ?? today);

  let open = $state(false), focus = $state(''), root = $state(), trigger = $state(), grid = $state();
  const month = $derived(focus.slice(0, 7));
  const title = $derived(focus ? new Intl.DateTimeFormat(locale($lang), { month: 'long', year: 'numeric', timeZone: 'UTC' }).format(parse(focus)) : '');
  const weekdays = $derived(Array.from({ length: 7 }, (_, i) =>
    new Intl.DateTimeFormat(locale($lang), { weekday: 'short', timeZone: 'UTC' }).format(new Date(Date.UTC(2024, 0, 1 + i)))));   // 1 Jan 2024 = Monday
  const weeks = $derived.by(() => {
    if (!focus) return [];
    const first = `${month}-01`, shift = (parse(first).getUTCDay() + 6) % 7;   // Monday = 0
    const start = add(first, -shift);
    return Array.from({ length: 6 }, (_, w) => Array.from({ length: 7 }, (_, d) => add(start, w * 7 + d)));
  });

  async function show() {
    if (disabled) return;
    focus = value || (today > limit ? limit : today); open = true;
    await tick(); grid?.querySelector('[tabindex="0"]')?.focus();
  }
  function close(back = true) { open = false; if (back) trigger?.focus(); }
  function pick(d) {
    if (d > limit) return;
    value = d; close(); onchange?.(d);
  }
  function clear() { value = ''; close(); onchange?.(''); }
  async function move(d) {
    focus = d; await tick();
    grid?.querySelector('[tabindex="0"]')?.focus();
  }
  function key(e) {
    const k = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7 }[e.key];
    if (k) { e.preventDefault(); move(add(focus, k)); }
    else if (e.key === 'PageUp') { e.preventDefault(); move(addMonth(focus, -1)); }
    else if (e.key === 'PageDown') { e.preventDefault(); move(addMonth(focus, 1)); }
    else if (e.key === 'Home') { e.preventDefault(); move(add(focus, -((parse(focus).getUTCDay() + 6) % 7))); }
    else if (e.key === 'End') { e.preventDefault(); move(add(focus, 6 - ((parse(focus).getUTCDay() + 6) % 7))); }
    else if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); pick(focus); }
  }
  function outside(e) { if (open && root && !root.contains(e.target)) close(false); }
</script>

<svelte:window onpointerdown={outside} />

<div class="dp" bind:this={root} onkeydown={(e) => open && e.key === 'Escape' && (e.stopPropagation(), close())} role="presentation">
  <div class="field" class:on={open} class:dis={disabled}>
    <button {id} bind:this={trigger} type="button" class="trig" onclick={() => (open ? close() : show())} {disabled}
      aria-haspopup="dialog" aria-expanded={open}>
      <Icon name="calendar" size={17} />
      <span class:muted={!value}>{value ? dLabel(value, $lang) : $t('dp.placeholder')}</span>
    </button>
    {#if value && !disabled}
      <button type="button" class="x" onclick={clear} aria-label={$t('dp.clear')} title={$t('dp.clear')}>×</button>
    {/if}
  </div>

  {#if open}
    <div class="pop" role="dialog" aria-label={$t('dp.dialog')}>
      <div class="head">
        <button type="button" class="nav" onclick={() => move(addMonth(focus, -1))} aria-label={$t('dp.prev')}>‹</button>
        <span class="ttl" aria-live="polite">{title}</span>
        <button type="button" class="nav" onclick={() => move(addMonth(focus, 1))} aria-label={$t('dp.next')} disabled={`${month}-01` > limit}>›</button>
      </div>
      <table bind:this={grid} role="grid" aria-label={title} onkeydown={key}>
        <thead><tr>{#each weekdays as w}<th scope="col" abbr={w}>{w.slice(0, 3)}</th>{/each}</tr></thead>
        <tbody>
          {#each weeks as wk}
            <tr>
              {#each wk as d}
                {@const out = d.slice(0, 7) !== month}
                <td role="gridcell" aria-selected={d === value}>
                  <button type="button" class="day" class:out class:today={d === today} class:sel={d === value}
                    tabindex={d === focus ? 0 : -1} disabled={d > limit} onclick={() => pick(d)}
                    aria-label={dLabel(d, $lang)} aria-current={d === today ? 'date' : undefined}>{+d.slice(8)}</button>
                </td>
              {/each}
            </tr>
          {/each}
        </tbody>
      </table>
      <div class="foot">
        <button type="button" class="link" onclick={() => pick(today > limit ? limit : today)}>{$t('dp.today')}</button>
        {#if value}<button type="button" class="link muted" onclick={clear}>{$t('dp.clear')}</button>{/if}
      </div>
    </div>
  {/if}
</div>

<style>
  .dp { position: relative; display: inline-block; }
  .field {
    display: flex; align-items: center; min-height: var(--touch); min-width: 190px; border-radius: 12px;
    border: 1px solid var(--line-strong); background: var(--bg2); transition: border-color 0.15s, box-shadow 0.15s;
  }
  .field:hover:not(.dis), .field.on { border-color: var(--accent); }
  .field.on { box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 22%, transparent); }
  .field.dis { opacity: 0.55; }
  .trig {
    flex: 1; display: flex; align-items: center; gap: 10px; min-height: calc(var(--touch) - 2px); padding: 0 12px;
    background: none; border: 0; color: var(--fg); font: inherit; font-size: 0.9375rem; cursor: pointer; text-align: left; border-radius: 12px;
  }
  .trig :global(svg) { color: var(--accent-text); }
  .trig:disabled { cursor: not-allowed; }
  .muted { color: var(--muted); }
  .x { width: 32px; height: 32px; margin-right: 6px; border-radius: 8px; border: 0; background: none; color: var(--muted); font-size: 1.1rem; cursor: pointer; }
  .x:hover { background: var(--nav-hover); color: var(--fg); }
  .pop {
    position: absolute; z-index: 40; top: calc(100% + 8px); left: 0; width: 304px; padding: 12px;
    background: var(--card-bg, var(--bg2)); border: 1px solid var(--line-strong); border-radius: 16px; box-shadow: var(--glow), 0 18px 40px rgba(0, 0, 0, 0.35);
  }
  .head { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 8px; }
  .ttl { font-weight: 600; text-transform: capitalize; }
  .nav { width: 34px; height: 34px; border-radius: 10px; border: 1px solid var(--line); background: none; color: var(--fg); font-size: 1.1rem; cursor: pointer; }
  .nav:hover:not(:disabled) { border-color: var(--accent); color: var(--accent-text); }
  .nav:disabled { opacity: 0.35; cursor: default; }
  table { width: 100%; border-collapse: collapse; table-layout: fixed; }
  th { font-size: 0.6875rem; font-weight: 500; color: var(--muted); text-transform: uppercase; letter-spacing: 0.04em; padding: 4px 0 6px; text-align: center; }
  td { padding: 2px; text-align: center; }
  .day {
    width: 36px; height: 36px; border-radius: 10px; border: 1px solid transparent; background: none; color: var(--fg);
    font: inherit; font-size: 0.875rem; font-variant-numeric: tabular-nums; cursor: pointer;
  }
  .day:hover:not(:disabled):not(.sel) { background: var(--nav-hover); border-color: var(--line); }
  .day.out { color: var(--muted); opacity: 0.6; }
  .day.today { border-color: var(--accent); color: var(--accent-text); font-weight: 600; }
  .day.sel { background: var(--accent); color: var(--brand-fg); font-weight: 600; border-color: var(--accent); }
  .day:disabled { opacity: 0.25; cursor: not-allowed; }
  .day:focus-visible, .nav:focus-visible, .trig:focus-visible, .x:focus-visible, .link:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
  .foot { display: flex; justify-content: space-between; margin-top: 8px; padding-top: 8px; border-top: 1px solid var(--line); }
  .link { background: none; border: 0; color: var(--accent-text); font: inherit; font-size: 0.8125rem; font-weight: 600; cursor: pointer; padding: 6px 4px; border-radius: 6px; }
  .link.muted { color: var(--muted); }
  @media (max-width: 420px) { .pop { width: min(304px, calc(100vw - 32px)); } .day { width: 100%; } }
</style>
