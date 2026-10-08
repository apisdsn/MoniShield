<!-- Large proportion bar (reference style "Run Success Rate"): segments in a fixed order (e.g. success first, DRD §9.2),
     label + number on the largest segment, dotted legend below. segments: [{label, value, tone: 'ok'|'err'|'warn'|'muted'}] -->
<script>
  import { lang } from '../i18n.js';
  import { num } from '../format.js';
  let { segments = [], label = '' } = $props();
  const total = $derived(segments.reduce((a, s) => a + (s.value || 0), 0));
  const big = $derived(segments.reduce((m, s, i) => (s.value > (segments[m]?.value ?? -1) ? i : m), 0));
</script>

{#if total}
  <div class="sb" role="img" aria-label="{label}: {segments.map((s) => `${s.label} ${num(s.value, $lang)}`).join(', ')}">
    {#each segments as s, i}
      {#if s.value}
        <div class="seg {s.tone}" style="flex-grow:{s.value}">
          {#if i === big}<span class="in"><small>{s.label}</small><b>{num(s.value, $lang)}</b></span>{/if}
        </div>
      {/if}
    {/each}
  </div>
  <div class="lg" aria-hidden="true">
    {#each segments as s}<span><span class="dot {s.tone}"></span>{s.label} <b>{num(s.value, $lang)}</b></span>{/each}
  </div>
{/if}

<style>
  .sb { display: flex; gap: 6px; height: 56px; }
  .seg { min-width: 6px; border-radius: 10px; display: flex; align-items: center; justify-content: flex-end; padding: 0 14px; overflow: hidden; }
  .seg.ok { background: linear-gradient(90deg, color-mix(in srgb, var(--accent) 75%, transparent), var(--accent)); color: var(--brand-fg); }
  .seg.err { background: color-mix(in srgb, var(--err) 80%, transparent); color: #fff; }
  .seg.warn { background: color-mix(in srgb, var(--warn) 80%, transparent); color: #1f1300; }
  .seg.muted { background: var(--line-strong); }
  .in { display: flex; flex-direction: column; align-items: flex-end; line-height: 1.1; white-space: nowrap; }
  .in small { font-size: 0.6875rem; font-weight: 500; opacity: 0.85; }
  .in b { font-size: 1.375rem; font-weight: 700; font-variant-numeric: tabular-nums; }
  .lg { display: flex; flex-wrap: wrap; gap: 6px 16px; margin-top: 10px; font-size: 0.75rem; color: var(--muted); }
  .lg b { color: var(--fg); font-weight: 600; }
  .dot.muted { background: var(--line-strong); }
</style>
