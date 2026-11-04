<!-- Language menu in the header (owner request 2026-11-04): a globe button with the current code, opening a small menu with
     one radio row per language. Same keyboard pattern as the user menu: Enter/Space/arrows open, arrows move, Esc closes
     and returns focus to the button, a click outside closes. -->
<script>
  import { tick } from 'svelte';
  import { lang, t } from '../i18n.js';
  import Icon from './Icon.svelte';

  const LANGS = [{ id: 'id', name: 'Bahasa Indonesia' }, { id: 'en', name: 'English' }];
  let open = $state(false), shift = $state(0);
  let btn = $state(), list = $state();
  const items = () => [...(list?.querySelectorAll('[role="menuitemradio"]') || [])];

  async function toggle(focusLast = false) {
    open = !open;
    if (!open) return;
    shift = 0;
    await tick();
    const r = list?.getBoundingClientRect();   // on a narrow phone the button sits left of the screen edge: keep the menu on screen
    if (r && r.left < 8) shift = 8 - r.left;
    const a = items(), cur = a.findIndex((x) => x.getAttribute('aria-checked') === 'true');
    (focusLast ? a[a.length - 1] : a[Math.max(cur, 0)])?.focus();
  }
  function close(refocus = true) { open = false; if (refocus) btn?.focus(); }
  function pick(id) { lang.set(id); close(); }
  function onkey(e) {
    const a = items(), i = a.indexOf(document.activeElement);
    if (e.key === 'Escape') { e.preventDefault(); close(); }
    else if (e.key === 'ArrowDown') { e.preventDefault(); a[(i + 1) % a.length]?.focus(); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); a[(i - 1 + a.length) % a.length]?.focus(); }
    else if (e.key === 'Home') { e.preventDefault(); a[0]?.focus(); }
    else if (e.key === 'End') { e.preventDefault(); a[a.length - 1]?.focus(); }
    else if (e.key === 'Tab') close(false);
  }
  function btnKey(e) {
    if (e.key === 'ArrowDown' && !open) { e.preventDefault(); toggle(); }
    if (e.key === 'ArrowUp' && !open) { e.preventDefault(); toggle(true); }
  }
  function outside(e) { if (open && !btn?.contains(e.target) && !list?.contains(e.target)) open = false; }
</script>

<svelte:window onclick={outside} />

<div class="lm">
  <button bind:this={btn} class="lbtn" type="button" aria-haspopup="menu" aria-expanded={open} aria-controls="lang-menu"
    aria-label={$t('ui.language')} title={$t('ui.language')} onclick={() => toggle()} onkeydown={btnKey}>
    <Icon name="globe" size={18} /><span class="cur">{$lang.toUpperCase()}</span>
  </button>
  {#if open}
    <!-- svelte-ignore a11y_interactive_supports_focus -->
    <div bind:this={list} id="lang-menu" class="menu" role="menu" tabindex="-1" aria-label={$t('ui.language')} onkeydown={onkey} style:transform={shift ? `translateX(${shift}px)` : null}>
      {#each LANGS as l}
        <button role="menuitemradio" aria-checked={$lang === l.id} onclick={() => pick(l.id)}>
          <span class="code" aria-hidden="true">{l.id.toUpperCase()}</span><span class="nm">{l.name}</span><span class="dot" aria-hidden="true"></span>
        </button>
      {/each}
    </div>
  {/if}
</div>

<style>
  .lm { position: relative; }
  .lbtn {
    display: inline-flex; align-items: center; justify-content: center; gap: 7px; height: var(--touch); min-width: var(--touch); padding: 0 12px;
    border: 1px solid var(--line-strong); border-radius: var(--r-ctl); background: var(--bg2); color: var(--fg); cursor: pointer;
  }
  .lbtn:hover { background: var(--nav-hover); }
  .cur { font-family: var(--mono); font-size: 0.8125rem; font-weight: 700; }
  .menu {
    position: absolute; right: 0; top: calc(100% + 8px); z-index: 50; width: 240px; max-width: calc(100vw - 16px);
    background: var(--card); border: 1px solid var(--line-strong); border-radius: 14px; box-shadow: var(--glow); padding: 6px;
    display: flex; flex-direction: column; gap: 2px;
  }
  .menu button {
    all: unset; box-sizing: border-box; padding: 8px 12px; border-radius: 10px; cursor: pointer; min-height: var(--touch);
    display: flex; align-items: center; gap: 12px; color: var(--fg); font-size: 0.875rem;
  }
  .menu button:hover, .menu button:focus-visible { background: var(--nav-hover); }
  .menu :focus-visible { outline: 2px solid var(--focus); outline-offset: -2px; }
  .code {
    flex: none; min-width: 34px; padding: 3px 0; text-align: center; font-family: var(--mono); font-size: 0.75rem; font-weight: 700; line-height: 1.2;
    border: 1.5px solid var(--line-strong); border-radius: 8px; color: var(--muted);
  }
  .nm { flex: 1; min-width: 0; }
  .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--accent); flex: none; visibility: hidden; margin-right: 4px; }
  [aria-checked='true'] { font-weight: 600; }
  [aria-checked='true'] .code { border-color: var(--accent); color: var(--accent-text); }
  [aria-checked='true'] .dot { visibility: visible; }
  @media (max-width: 420px) { .cur { display: none; } .lbtn { padding: 0; width: var(--touch); } }
</style>
