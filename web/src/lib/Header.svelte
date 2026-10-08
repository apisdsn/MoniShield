<!-- Page header (DRD §2.1 U3, §8.2, §12 style). Wide screen: one sticky card holding the title + compact status line
     (left) and the folder picker, language, theme, reload, user menu (right); when both do not fit on one line, the tools
     move to a second line. ≤ 900 px: sticky 52 px bar
     [☰] MoniShield [Folder ▾] [⋯] (language, theme, reload, user menu contents go into ⋯); the title flows below it.
     DOM order = Tab order: tools first, title (h1, tabindex -1) after; visual placement set by the grid. -->
<script>
  import Logo from './Logo.svelte';
  import { lang, t } from '../i18n.js';
  import { theme } from '../theme.js';
  import FolderPicker from './FolderPicker.svelte';
  import UserMenu from './UserMenu.svelte';
  import GlobalSearch from './GlobalSearch.svelte';
  import SyncButton from './SyncButton.svelte';
  import Icon from './Icon.svelte';
  import { APP_NAME } from '../brand.js';
  let { me, route, folders, folder, folderDisabled = false, onfolder, onreload, onlogout, onmenu, drawerOpen = false,
        menuBtn = $bindable(), onsynced = null, title, sysTitle = false, suffix = '', status = [], titleEl = $bindable() } = $props();

  function segKey(e, values, current, set) {
    if (!['ArrowLeft', 'ArrowRight'].includes(e.key)) return;
    e.preventDefault();
    const i = values.indexOf(current), n = values[(i + (e.key === 'ArrowRight' ? 1 : values.length - 1)) % values.length];
    set(n);
    e.currentTarget.querySelector(`[data-v="${n}"]`)?.focus();
  }
</script>

<header class="top">
  <div class="bar">
    <button bind:this={menuBtn} class="icon-btn burger" onclick={onmenu} aria-expanded={drawerOpen} aria-controls="side" aria-label={$t('nav.open')}>☰</button>
    <span class="brand" aria-hidden="true"><Logo size={24} />{APP_NAME}</span>
    <div class="tools">
      {#if folders?.length}
        <FolderPicker {folders} value={folder} disabled={folderDisabled} onchange={onfolder} />
        <GlobalSearch {folder} />
      {/if}
      {#if me?.role === 'admin'}<SyncButton {onsynced} />{/if}
      <div class="wide-only">
        <div class="seg" role="radiogroup" aria-label={$t('ui.language')} tabindex="-1" onkeydown={(e) => segKey(e, ['id', 'en'], $lang, (v) => lang.set(v))}>
          <button role="radio" data-v="id" aria-checked={$lang === 'id'} tabindex={$lang === 'id' ? 0 : -1} onclick={() => lang.set('id')}>ID</button>
          <button role="radio" data-v="en" aria-checked={$lang === 'en'} tabindex={$lang === 'en' ? 0 : -1} onclick={() => lang.set('en')}>EN</button>
        </div>
        <div class="seg" role="radiogroup" aria-label={$t('ui.theme')} tabindex="-1" onkeydown={(e) => segKey(e, ['light', 'dark'], $theme, (v) => theme.set(v))}>
          <button role="radio" data-v="light" aria-checked={$theme === 'light'} tabindex={$theme === 'light' ? 0 : -1} onclick={() => theme.set('light')}
            aria-label={$t('theme.light')} title={$t('theme.light')}>☀</button>
          <button role="radio" data-v="dark" aria-checked={$theme === 'dark'} tabindex={$theme === 'dark' ? 0 : -1} onclick={() => theme.set('dark')}
            aria-label={$t('theme.dark')} title={$t('theme.dark')}>☾</button>
        </div>
        <button class="icon-btn" onclick={onreload} aria-label={$t('action.reload')} title={$t('action.reload')}><Icon name="refresh" size={17} /></button>
        <UserMenu {me} {route} {onlogout} {onreload} />
      </div>
      <div class="narrow-only"><UserMenu {me} {route} {onlogout} {onreload} extended /></div>
    </div>
  </div>
  <div class="ttl">
    <h1 bind:this={titleEl} tabindex="-1"><span class:sys={sysTitle}>{title}</span>{#if suffix}<span class="sfx">&nbsp;— {suffix}</span>{/if}</h1>
    {#if status.length}
      <p class="status">
        {#each status as s, i}{#if i}<span class="sep" aria-hidden="true">·</span>{/if}<span class="it"><span class="dot {s.tone || ''}" aria-hidden="true"></span>{#if s.n !== undefined}<b>{s.n}</b>&nbsp;{/if}{s.text}</span>{/each}
      </p>
    {/if}
  </div>
</header>

<style>
  .top {
    position: sticky; top: 10px; z-index: 20; margin: 14px 0 10px;
    display: flex; flex-wrap: wrap; align-items: center; gap: 12px 18px;
    padding: 14px 18px; border-radius: var(--r-card); border: 1px solid var(--card-border);
    background: color-mix(in srgb, var(--card) 92%, transparent); backdrop-filter: blur(10px); box-shadow: var(--glow);
  }
  .bar { display: contents; }
  /* the title keeps at least ~22rem; when the tools do not fit next to it they move to their own line (right-aligned)
     instead of squeezing the title into one word per line (owner report 2026-10-08, 1280 px in English) */
  .tools { order: 1; flex: 0 1 auto; margin-left: auto; display: flex; flex-wrap: wrap; justify-content: flex-end; align-items: center; gap: 10px; min-width: 0; }
  .ttl { order: 0; flex: 1 1 22rem; min-width: 0; }
  h1 { font-size: 1.375rem; font-weight: 600; line-height: 1.25; color: var(--heading); text-transform: capitalize; overflow-wrap: break-word; text-wrap: balance; }
  h1:focus { outline: none; }
  h1:focus-visible { outline: 2px solid var(--focus); outline-offset: 2px; }
  .sfx { color: var(--muted); font-weight: 500; white-space: nowrap; }
  .status { margin: 4px 0 0; font-size: 0.78rem; color: var(--muted); display: flex; flex-wrap: wrap; align-items: center; gap: 2px 8px; }
  .it { display: inline-flex; align-items: center; white-space: nowrap; }
  .status .it :global(b) { color: var(--fg); font-weight: 600; }
  .sep { color: var(--line-strong); }
  .wide-only { display: flex; align-items: center; gap: 8px; }
  .narrow-only, .burger, .brand { display: none; }
  .seg button { min-width: 2.5rem; }
  @media (max-width: 900px) {
    .top { display: contents; }
    .bar {
      display: flex; position: sticky; top: 0; z-index: 20; align-items: center; justify-content: space-between; gap: 8px;
      min-height: 52px; padding: 4px 16px; margin: 0 -16px 8px; border-bottom: 1px solid var(--line);
      background: color-mix(in srgb, var(--bg) 90%, transparent); backdrop-filter: blur(8px);
    }
    .burger, .narrow-only { display: inline-grid; }
    .brand { display: flex; align-items: center; gap: 8px; font-weight: 600; white-space: nowrap; }
    .wide-only { display: none; }
    .tools { flex: 1; flex-wrap: nowrap; margin-left: 0; justify-content: flex-end; gap: 8px; }
    .tools :global(.fp) { flex: 1; justify-content: flex-end; max-width: 60vw; }
    .ttl { margin: 6px 0 12px; }
    h1 { font-size: 1.5rem; }
    .sfx { display: none; }   /* the date is already shown in the folder picker in the top bar */
  }
  @media (max-width: 420px) { .brand { display: none; } .tools :global(.fp) { max-width: none; } }
</style>
