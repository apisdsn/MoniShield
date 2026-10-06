<!-- Dialog modal (DRD §3.11): <dialog> bawaan browser dengan showModal(), jadi isi di belakangnya tidak bisa
     difokus (fokus terkunci di dalam), Esc menutup, dan judul menjadi nama aksesibel. Fokus kembali ke elemen yang
     membukanya. Di ponsel (≤ 560 px) layar penuh. open = $bindable; onclose dipanggil setiap kali tertutup. -->
<script>
  import { tick } from 'svelte';
  import { t } from '../i18n.js';
  let { open = $bindable(false), title, onclose = null, returnFocus = null, children, footer = null } = $props();   // returnFocus: cadangan bila pemicunya sudah hilang dari halaman
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
  .dlg h2 { font-size: 1.0625rem; font-weight: 600; color: var(--heading); text-transform: none; }   /* judul memuat nama user: apa adanya */
  .x { width: 36px; height: 36px; font-size: 1.25rem; }
  .body { padding: 6px 20px 20px; }
  footer { display: flex; gap: 10px; flex-wrap: wrap; padding: 0 20px 20px; }
  @media (max-width: 560px) {
    .dlg { width: 100vw; max-width: 100vw; height: 100dvh; max-height: 100dvh; margin: 0; border-radius: 0; border: 0; }
  }
</style>
