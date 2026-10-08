<!-- Modal dialog (DRD §3.11): the browser's built-in <dialog> with showModal(), so content behind it cannot be
     focused (focus trapped inside), Esc closes, and the title becomes the accessible name. Focus returns to the element
     that opened it. Full screen on phones (≤ 560 px). open = $bindable; onclose is called every time it closes. -->
<script>
  import { tick } from 'svelte';
  import { t } from '../i18n.js';
  let { open = $bindable(false), title, onclose = null, returnFocus = null, children, footer = null } = $props();   // returnFocus: fallback when the trigger is already gone from the page
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

<dialog bind:this={el} class="dlg card" aria-labelledby={id} onclose={closed}>
  <header>
    <h2 {id}>{title}</h2>
    <button type="button" class="icon-btn x" aria-label={$t('action.close')} title={$t('action.close')} onclick={() => (open = false)}>×</button>
  </header>
  <div class="body">{@render children?.()}</div>
  {#if footer}<footer>{@render footer()}</footer>{/if}
</dialog>

<style>
  .dlg {
    width: min(520px, calc(100vw - 32px)); max-height: calc(100vh - 48px); padding: 0; color: var(--fg);
    border: 1px solid var(--line-strong); overflow: auto;
  }
  .dlg::backdrop { background: rgba(3, 7, 10, 0.62); }
  header { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 18px 20px 6px; }
  .dlg h2 { font-size: 1.0625rem; font-weight: 600; color: var(--heading); text-transform: none; }   /* title contains the user name: as is */
  .x { width: 36px; height: 36px; font-size: 1.25rem; }
  .body { padding: 6px 20px 20px; }
  footer { display: flex; gap: 10px; flex-wrap: wrap; padding: 0 20px 20px; }
  @media (max-width: 560px) {
    .dlg { width: 100vw; max-width: 100vw; height: 100dvh; max-height: 100dvh; margin: 0; border-radius: 0; border: 0; }
  }
</style>
