<!-- User menu (DRD §2.1 U28, §8.2): button holding the display name; list: name + role, Account email and Change password (pop-ups, lib/AccountDialogs.svelte), (admin) Manage
     users, Ingest & import, Log out. Standard menu pattern: Enter/Space opens, arrows move, Esc closes and
     returns focus. Reload lives in this menu too. Language and theme are in the header (LangMenu, ThemeSwitch). -->
<script>
  import { tick } from 'svelte';
  import { t } from '../i18n.js';
  import { build } from '../state.js';
  import Icon from './Icon.svelte';
  import { openAccount } from './AccountDialogs.svelte';
  import { restoreFocus } from './focus.js';
  let { me, route, onlogout, onreload } = $props();

  let open = $state(false);
  let btn = $state(), list = $state();
  const items = () => [...(list?.querySelectorAll('[role^="menuitem"]') || [])];

  async function toggle(focusLast = false) {
    open = !open;
    if (open) { await tick(); const a = items(); (focusLast ? a[a.length - 1] : a[0])?.focus(); }
  }
  function close(refocus = true) { open = false; if (refocus) restoreFocus(btn); }
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
  const link = (tab) => build({ ...route, tab, service: null, q: null });
  // initials avatar (reference style): no photo, no outside service
  const initials = $derived((me.display_name || me.username).split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0].toUpperCase()).join(''));
</script>

<svelte:window onclick={outside} />

<div class="um">
  <button bind:this={btn} class="btn who" aria-haspopup="menu" aria-expanded={open} aria-controls="user-menu"
    onclick={() => toggle()} onkeydown={btnKey} title={$t('menu.label')}>
    <span class="av" aria-hidden="true">{initials}</span><span class="name">{me.display_name || me.username}</span><span class="car" aria-hidden="true">▾</span>
  </button>
  {#if open}
    <!-- svelte-ignore a11y_interactive_supports_focus -->
    <div bind:this={list} id="user-menu" class="menu" role="menu" tabindex="-1" aria-label={$t('menu.label')} onkeydown={onkey}>
      <div class="me" role="presentation">
        <b>{me.display_name || me.username}</b>
        <span class="muted">{me.username} · {$t(`role.${me.role}`)}</span>
      </div>
      <div class="sep" role="separator"></div>
      <button role="menuitem" onclick={() => { close(); onreload(); }}><Icon name="refresh" />{$t('action.reload')}</button>
      <div class="sep" role="separator"></div>
      <button role="menuitem" onclick={() => { close(); openAccount('email'); }}><Icon name="mail" />{$t('menu.email')}</button>
      <button role="menuitem" onclick={() => { close(); openAccount('password'); }}><Icon name="key" />{$t('menu.password')}</button>
      {#if me.role === 'admin'}
        <a role="menuitem" href={link('admin/users')} onclick={() => close(false)}><Icon name="users" />{$t('menu.users')}</a>
        <a role="menuitem" href={link('admin/ingest')} onclick={() => close(false)}><Icon name="database" />{$t('menu.ingest')}</a>
      {/if}
      <a role="menuitem" href="/api/v1/docs" target="_blank" rel="noopener" onclick={() => close(false)}><Icon name="code" />{$t('menu.api_docs')}</a>
      <div class="sep" role="separator"></div>
      <button role="menuitem" class="out" onclick={() => { close(false); onlogout(); }}><Icon name="logout" />{$t('menu.logout')}</button>
    </div>
  {/if}
</div>

<style>
  .um { position: relative; }
  .who {
    max-width: 220px; padding: 0 1.1rem 0 6px; gap: 8px; height: var(--touch); min-height: 0; border-radius: var(--r-ctl);
    border: 1px solid var(--line-strong); background: var(--bg2);   /* same box as the other header controls */
  }
  .who:hover { background: var(--ctl-hover); }
  .av {
    width: 30px; height: 30px; border-radius: 50%; display: grid; place-items: center; flex: none;
    font-size: 0.75rem; font-weight: 700; color: var(--brand-fg); background: var(--brand-bg);
  }
  .car { color: var(--muted); font-size: 0.75rem; }
  @media (max-width: 900px) {
    .who { padding: 0; min-width: var(--touch); }
    .car { display: none; }
    .name { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }   /* still the button's name */
  }
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
    display: flex; align-items: center; gap: 12px; color: var(--fg); font-size: 0.875rem;
  }
  .menu :global(svg) { color: var(--muted); }   /* icons support the text */
  .menu .out, .menu .out :global(svg) { color: var(--err); }
  .menu button:hover, .menu a:hover, .menu button:focus-visible, .menu a:focus-visible { background: var(--nav-hover); }
  .menu :focus-visible { outline: 2px solid var(--focus); outline-offset: -2px; }
</style>
