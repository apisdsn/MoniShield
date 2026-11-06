<!-- What a collector sends, as chips on ONE line (Collectors table). When the column is too narrow for all of them, the chips that
     fit are shown plus a "+N" chip whose title and accessible name list the rest, so a row keeps its height whether or not the
     detail panel narrows the table. The widths are measured in the browser; fitCount (collectors.js) does the arithmetic. -->
<script>
  import { fitCount } from '../collectors.js';
  let { texts = [], empty = '' } = $props();
  let box = $state(null), shown = $state(null);   // shown = number of chips that fit (null until measured: all are shown)
  const GAP = 6;
  const keep = $derived(shown === null ? texts.length : Math.min(shown, texts.length));
  const rest = $derived(texts.slice(keep));

  function measure() {
    if (!box) return;
    const widths = [...box.querySelectorAll('.chip.c')].map((e) => e.offsetWidth);
    const plus = box.querySelector('.chip.probe')?.offsetWidth || 36;
    shown = fitCount(widths, box.clientWidth, GAP, plus);
  }
  $effect(() => {
    texts.length;   // measure again when the chips change
    if (!box) return;
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(box);
    return () => ro.disconnect();
  });
</script>

<span class="chips" bind:this={box}>
  {#each texts as tx, i}<span class="chip c" class:off={i >= keep}>{tx}</span>{:else}<span class="muted">{empty}</span>{/each}
  {#if rest.length}<span class="chip more" role="img" title={rest.join(', ')} aria-label={`+${rest.length}: ${rest.join(', ')}`}>+{rest.length}</span>{/if}
  <span class="chip probe" aria-hidden="true">+99</span>
</span>

<style>
  .chips { display: flex; flex-wrap: nowrap; gap: 6px; align-items: center; min-width: 0; overflow: hidden; position: relative; font-variant-numeric: tabular-nums; }
  .chip { flex: none; white-space: nowrap; }
  .off, .probe { position: absolute; visibility: hidden; pointer-events: none; }
  .more { cursor: default; }
</style>
