<!-- Per-row table action menu (DRD §3.11 "[⋯]"): the same menu pattern as the user menu (arrows, Home/End, Esc
     returns focus). The list is placed `position: fixed` from the button position, so it is not clipped by a scrolling
     table container. Items not offered stay visible, disabled, with their reason (aria-disabled + text). -->
<script>
  import { tick } from 'svelte';
  /** items: [{label, onpick, disabled?: reason text, danger?}] */
  let { label, items = [], btn = $bindable() } = $props();
  let open = $state(false), list = $state(), pos = $state('');
  const els = () => [...(list?.querySelectorAll('[role="menuitem"]') || [])];

  async function toggle() {
    if (open) return close();
    const r = btn.getBoundingClientRect(), w = Math.min(260, innerWidth - 32);
    const left = Math.max(16, Math.min(r.right - w, innerWidth - w - 16));
    pos = r.bottom + 260 > innerHeight && r.top > 260 ? `left:${left}px;bottom:${innerHeight - r.top + 6}px;width:${w}px` : `left:${left}px;top:${r.bottom + 6}px;width:${w}px`;
    open = true;
    await tick(); els()[0]?.focus();
  }
  function close(refocus = true) { open = false; if (refocus) btn?.focus(); }
  function onkey(e) {
    const a = els(), i = a.indexOf(document.activeElement);
    if (e.key === 'Escape') { e.preventDefault(); close(); }
    else if (e.key === 'ArrowDown') { e.preventDefault(); a[(i + 1) % a.length]?.focus(); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); a[(i - 1 + a.length) % a.length]?.focus(); }
    else if (e.key === 'Home') { e.preventDefault(); a[0]?.focus(); }
    else if (e.key === 'End') { e.preventDefault(); a[a.length - 1]?.focus(); }
    else if (e.key === 'Tab') close(false);
  }
  function pick(it) { if (it.disabled) return; close(); it.onpick(); }   // focus ⋯ first: a dialog that opens returns there
  function outside(e) { if (open && !btn?.contains(e.target) && !list?.contains(e.target)) open = false; }
</script>

<svelte:window onclick={outside} onresize={() => open && close(false)} onscroll={() => open && close(false)} />

<button bind:this={btn} type="button" class="icon-btn rm" aria-haspopup="menu" aria-expanded={open} aria-label={label} title={label} onclick={toggle}>⋯</button>
{#if open}
  <!-- svelte-ignore a11y_interactive_supports_focus -->
  <div bind:this={list} class="menu" role="menu" tabindex="-1" aria-label={label} style={pos} onkeydown={onkey}>
    {#each items as it}
      <button type="button" role="menuitem" aria-disabled={!!it.disabled} class:danger={it.danger} onclick={() => pick(it)}>
        <span>{it.label}</span>
        {#if it.disabled}<small>{it.disabled}</small>{/if}
      </button>
    {/each}
  </div>
{/if}

<style>
  .rm { width: 36px; height: 36px; font-size: 1.1rem; }
  .menu {
    position: fixed; z-index: 70; background: var(--card); border: 1px solid var(--line-strong); border-radius: 14px;
    box-shadow: var(--glow); padding: 6px; display: flex; flex-direction: column;
  }
  .menu button {
    all: unset; box-sizing: border-box; padding: 9px 12px; border-radius: 10px; cursor: pointer; min-height: var(--touch);
    display: flex; flex-direction: column; justify-content: center; gap: 2px; color: var(--fg); font-size: 0.875rem;
  }
  .menu button:hover, .menu button:focus-visible { background: var(--nav-hover); }
  .menu button:focus-visible { outline: 2px solid var(--focus); outline-offset: -2px; }
  .menu .danger { color: var(--err); }
  .menu [aria-disabled='true'] { color: var(--muted); cursor: not-allowed; }
  small { font-size: 0.75rem; color: var(--muted); }
</style>
