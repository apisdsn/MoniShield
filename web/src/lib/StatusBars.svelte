<!-- Status code classes as bars with count and share (stage 62, Availability). rows: [[class '2xx', count]]; total = the requests. -->
<script>
  import { lang, t } from '../i18n.js';
  import { num } from '../format.js';
  import { share } from '../anyfmt.js';
  let { title, rows = [], total = 0, note = '' } = $props();
  const TONE = { '2xx': 'ok', '3xx': 'muted', '4xx': 'warn', '5xx': 'err' };
</script>

<section class="card sb" aria-label={title}>
  <div class="hd"><h2>{title}</h2><span class="muted note">{note}</span></div>
  <ul>
    {#each rows as [c, n]}
      <li>
        <span class="c">{c}</span>
        <span class="bar" aria-hidden="true"><span class="fill {TONE[c]}" style:width="{total ? Math.max(n ? 1 : 0, (n / total) * 100) : 0}%"></span></span>
        <span class="n">{num(n, $lang)}</span>
        <span class="p muted">{share(n, total, num, $lang)}</span>
      </li>
    {/each}
  </ul>
</section>

<style>
  .sb { padding: 16px 18px; min-width: 0; }
  .hd { display: flex; justify-content: space-between; align-items: baseline; gap: 8px; flex-wrap: wrap; margin-bottom: 14px; }
  h2 { margin: 0; font-size: 1rem; font-weight: 600; color: var(--heading); }
  .note { font-size: 0.8125rem; font-variant-numeric: tabular-nums; }
  ul { list-style: none; margin: 0; padding: 0; display: grid; gap: 4px; }
  li { display: grid; grid-template-columns: 3rem minmax(0, 1fr) 4.5rem 4rem; gap: 12px; align-items: center; min-height: 44px; font-size: 0.875rem; }
  .c { font-weight: 600; }
  .bar { height: 10px; border-radius: 999px; background: var(--bg2); overflow: hidden; }
  .fill { display: block; height: 100%; border-radius: 999px; }
  .fill.ok { background: var(--ok); } .fill.muted { background: var(--muted); } .fill.warn { background: var(--warn); } .fill.err { background: var(--err); }
  .n, .p { text-align: right; font-variant-numeric: tabular-nums; }
  @media (max-width: 480px) { li { grid-template-columns: 2.5rem minmax(0, 1fr) 3.5rem 3.5rem; gap: 8px; } }
</style>
