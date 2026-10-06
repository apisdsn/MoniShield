<!-- Menu user (DRD §2.1 U28, §8.2): tombol berisi nama tampilan; daftar: nama + peran, Ganti sandi, (admin) Kelola
     user, Ingest & impor, Keluar. Pola menu standar: Enter/Spasi membuka, panah berpindah, Esc menutup dan
     mengembalikan fokus. `extended` (layar sempit, tombol ⋯): bahasa, tema, dan muat ulang ikut masuk menu. -->
<script>
  import { tick } from 'svelte';
  import { lang, t } from '../i18n.js';
  import { theme } from '../theme.js';
  import { build } from '../state.js';
  let { me, route, extended = false, onlogout, onreload } = $props();

  let open = $state(false);
  let btn = $state(), list = $state();
  const items = () => [...(list?.querySelectorAll('[role^="menuitem"]') || [])];

  async function toggle(focusLast = false) {
    open = !open;
    if (open) { await tick(); const a = items(); (focusLast ? a[a.length - 1] : a[0])?.focus(); }
  }
  function close(refocus = true) { open = false; if (refocus) btn?.focus(); }
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
  const link = (tab) => build({ ...route, tab, service: null });
</script>

<svelte:window onclick={outside} />

<div class="um">
  <button bind:this={btn} class={extended ? 'icon-btn' : 'btn who'} aria-haspopup="menu" aria-expanded={open} aria-controls="user-menu"
    onclick={() => toggle()} onkeydown={btnKey} aria-label={extended ? $t('menu.more') : undefined}>
    {#if extended}⋯{:else}<span class="name">{me.display_name || me.username}</span><span aria-hidden="true">▾</span>{/if}
  </button>
  {#if open}
    <!-- svelte-ignore a11y_interactive_supports_focus -->
    <div bind:this={list} id="user-menu" class="menu" role="menu" tabindex="-1" aria-label={$t('menu.label')} onkeydown={onkey}>
      <div class="me" role="presentation">
        <b>{me.display_name || me.username}</b>
        <span class="muted">{me.username} · {$t(`role.${me.role}`)}</span>
      </div>
      {#if extended}
        <div class="sep" role="separator"></div>
        <button role="menuitemradio" aria-checked={$lang === 'id'} onclick={() => lang.set('id')}>Bahasa Indonesia</button>
        <button role="menuitemradio" aria-checked={$lang === 'en'} onclick={() => lang.set('en')}>English</button>
        <div class="sep" role="separator"></div>
        <button role="menuitemradio" aria-checked={$theme === 'light'} onclick={() => theme.set('light')}>☀ {$t('theme.light')}</button>
        <button role="menuitemradio" aria-checked={$theme === 'dark'} onclick={() => theme.set('dark')}>☾ {$t('theme.dark')}</button>
        <div class="sep" role="separator"></div>
        <button role="menuitem" onclick={() => { close(); onreload(); }}>↻ {$t('action.reload')}</button>
      {/if}
      <div class="sep" role="separator"></div>
      <a role="menuitem" href={link('sandi')} onclick={() => close(false)}>{$t('menu.password')}</a>
      {#if me.role === 'admin'}
        <a role="menuitem" href={link('admin/user')} onclick={() => close(false)}>{$t('menu.users')}</a>
        <a role="menuitem" href={link('admin/ingest')} onclick={() => close(false)}>{$t('menu.ingest')}</a>
      {/if}
      <div class="sep" role="separator"></div>
      <button role="menuitem" onclick={() => { close(false); onlogout(); }}>{$t('menu.logout')}</button>
    </div>
  {/if}
</div>

<style>
  .um { position: relative; }
  .who { max-width: 200px; }
  .name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .menu {
    position: absolute; right: 0; top: calc(100% + 8px); z-index: 50; min-width: 240px; max-width: calc(100vw - 32px);
    background: var(--card); border: 1px solid var(--line-strong); border-radius: 14px; box-shadow: var(--glow); padding: 6px;
    display: flex; flex-direction: column;
  }
  .me { padding: 8px 12px; display: flex; flex-direction: column; }
  .me .muted { font-size: 0.75rem; }
  .sep { height: 1px; background: var(--line); margin: 4px 6px; }
  .menu button, .menu a {
    all: unset; box-sizing: border-box; padding: 10px 12px; border-radius: 10px; cursor: pointer; min-height: var(--touch);
    display: flex; align-items: center; gap: 8px; color: var(--fg); font-size: 0.875rem;
  }
  .menu button:hover, .menu a:hover, .menu button:focus-visible, .menu a:focus-visible { background: var(--nav-hover); }
  .menu :focus-visible { outline: 2px solid var(--focus); outline-offset: -2px; }
  .menu [aria-checked='true'] { color: var(--accent-text); font-weight: 600; }
  .menu [aria-checked='true']::after { content: '✓'; margin-left: auto; }
</style>
