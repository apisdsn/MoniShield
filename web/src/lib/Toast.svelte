<!-- Short notification in the corner, 4 seconds, role="status", does not cover buttons (DRD §6.9). -->
<script module>
  import { writable } from 'svelte/store';
  export const toasts = writable([]);
  let n = 0;
  export function toast(text) {
    const id = ++n;
    toasts.update((a) => [...a, { id, text }]);
    setTimeout(() => toasts.update((a) => a.filter((x) => x.id !== id)), 4000);
  }
</script>

<div class="toasts" role="status" aria-live="polite">
  {#each $toasts as m (m.id)}<div class="t">{m.text}</div>{/each}
</div>

<style>
  .toasts { position: fixed; right: 16px; bottom: 16px; z-index: 60; display: grid; gap: 8px; pointer-events: none; }
  .t {
    background: var(--tooltip-bg); color: #e2ecf3; border: 1px solid var(--tooltip-line); border-radius: 12px;
    padding: 10px 14px; font-size: 0.8125rem; box-shadow: var(--glow); max-width: min(360px, calc(100vw - 32px));
  }
</style>
