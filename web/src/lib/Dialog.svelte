<!-- Modal dialog (DRD §3.11): the browser's built-in <dialog> with showModal(), so content behind it cannot be
     focused (focus trapped inside), Esc closes, and the title becomes the accessible name. Focus returns to the element
     that opened it. Full screen on phones (≤ 560 px). open = $bindable; onclose is called every time it closes.
     wide = up to 860 px (configuration forms with several columns). -->
<script>
  import { tick } from 'svelte';
  import { t } from '../i18n.js';
  let { open = $bindable(false), title, onclose = null, returnFocus = null, children, footer = null, wide = false } = $props();   // returnFocus: fallback when the trigger is already gone from the page
  let el = $state(), trigger = null;
  const id = `dlg-${Math.random().toString(36).slice(2, 8)}`;

  $effect(() => {
    if (!el) return;
    if (open && !el.open) {
      trigger = document.activeElement;
      el.showModal();
      tick().then(() => (el.querySelector('[autofocus], input:not([disabled]), select, textarea, button:not(.x)') || el).focus());
    } else if (!open && el.open) el.close();
  });
  function closed() {
    open = false;
    onclose?.();
    (trigger?.isConnected ? trigger : returnFocus)?.focus?.();
    trigger = null;
  }
</script>

<dialog bind:this={el} class="dlg card" class:wide aria-labelledby={id} onclose={closed}>
  <header>
    <h2 {id}>{title}</h2>
    <button type="button" class="icon-btn x" aria-label={$t('action.close')} title={$t('action.close')} onclick={() => (open = false)}>×</button>
  </header>
  <div class="body">{@render children?.()}</div>
  {#if footer}<footer>{@render footer()}</footer>{/if}
</dialog>

<style>
  /* Only the body scrolls: the title and buttons stay in place, and the scrollbar stops short of the rounded corners
     (owner report 2026-10-30: a scrolling dialog cut its own corners). */
  .dlg {
    width: min(520px, calc(100vw - 32px)); max-height: calc(100vh - 48px); padding: 0; color: var(--fg);
    border: 1px solid var(--line-strong); overflow: hidden;
  }
  .dlg[open] { display: flex; flex-direction: column; }
  .dlg:focus-visible { outline: none; }   /* focus lands on the dialog itself when it has no field: no ring around the whole box */
  .dlg.wide { width: min(860px, calc(100vw - 32px)); }
  .dlg[open] { animation: dlg-in 0.18s ease-out; }
  @keyframes dlg-in { from { opacity: 0; transform: translateY(8px) scale(0.985); } }
  @media (prefers-reduced-motion: reduce) { .dlg[open] { animation: none; } }
  .dlg::backdrop { background: rgba(3, 7, 10, 0.62); }
  header { flex: none; display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 18px 20px 6px; }
  .dlg h2 { font-size: 1.0625rem; font-weight: 600; color: var(--heading); text-transform: none; }   /* title contains the user name: as is */
  .x { width: 36px; height: 36px; font-size: 1.25rem; }
  .body {
    flex: 1 1 auto; min-height: 0; overflow-y: auto; overscroll-behavior: contain;
    padding: 6px 14px 14px 20px; margin: 0 6px 6px 0;   /* 14 + 6 = the 20 px edge of the header; the bar ends above the corner */
    scrollbar-width: thin; scrollbar-color: var(--line-strong) transparent; scrollbar-gutter: stable;
  }
  .body::-webkit-scrollbar { width: 8px; }
  .body::-webkit-scrollbar-thumb { background: var(--line-strong); border-radius: 8px; }
  .body::-webkit-scrollbar-track { background: transparent; margin: 4px 0; }
  footer { flex: none; display: flex; gap: 10px; flex-wrap: wrap; padding: 12px 20px 20px; border-top: 1px solid var(--line); }
  @media (max-width: 560px) {
    .dlg, .dlg.wide { width: 100vw; max-width: 100vw; height: 100dvh; max-height: 100dvh; margin: 0; border-radius: 0; border: 0; }
  }
</style>
