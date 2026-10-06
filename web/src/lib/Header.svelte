<!-- Baris alat yang menempel di atas (DRD §2.1 U3, §8.2): pemilih folder, bahasa, tema, muat ulang, menu user.
     ≤ 900 px: bar 52 px [☰] SIMPEL4 Log [Folder ▾] [⋯]; bahasa, tema, muat ulang, dan isi menu user masuk ⋯. -->
<script>
  import { lang, t } from '../i18n.js';
  import { theme } from '../theme.js';
  import FolderPicker from './FolderPicker.svelte';
  import UserMenu from './UserMenu.svelte';
  let { me, route, folders, folder, folderDisabled = false, onfolder, onreload, onlogout, onmenu, drawerOpen = false, menuBtn = $bindable() } = $props();

  function segKey(e, values, current, set) {
    if (!['ArrowLeft', 'ArrowRight'].includes(e.key)) return;
    e.preventDefault();
    const i = values.indexOf(current), n = values[(i + (e.key === 'ArrowRight' ? 1 : values.length - 1)) % values.length];
    set(n);
    e.currentTarget.querySelector(`[data-v="${n}"]`)?.focus();
  }
</script>

<header class="top">
  <button bind:this={menuBtn} class="icon-btn burger" onclick={onmenu} aria-expanded={drawerOpen} aria-controls="side" aria-label={$t('nav.open')}>☰</button>
  <span class="brand" aria-hidden="true">SIMPEL4 Log</span>
  <div class="tools">
    {#if folders?.length}
      <FolderPicker {folders} value={folder} disabled={folderDisabled} onchange={onfolder} />
    {/if}
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
      <button class="icon-btn" onclick={onreload} aria-label={$t('action.reload')} title={$t('action.reload')}>↻</button>
      <UserMenu {me} {route} {onlogout} {onreload} />
    </div>
    <div class="narrow-only"><UserMenu {me} {route} {onlogout} {onreload} extended /></div>
  </div>
</header>

<style>
  .top {
    position: sticky; top: 0; z-index: 20; display: flex; align-items: center; justify-content: flex-end; gap: 10px;
    min-height: 56px; padding: 8px 0; margin-bottom: 4px;
    background: color-mix(in srgb, var(--bg) 88%, transparent); backdrop-filter: blur(8px);
  }
  .tools { display: flex; align-items: center; gap: 10px; min-width: 0; }
  .wide-only { display: flex; align-items: center; gap: 10px; }
  .narrow-only, .burger, .brand { display: none; }
  .seg button { min-width: 2.75rem; }
  @media (max-width: 900px) {
    .top { min-height: 52px; padding: 4px 16px; margin: 0 -16px 8px; justify-content: space-between; border-bottom: 1px solid var(--line); }
    .burger, .narrow-only { display: inline-grid; }
    .brand { display: block; font-weight: 600; white-space: nowrap; }
    .wide-only { display: none; }
    .tools { flex: 1; justify-content: flex-end; gap: 8px; }
    .tools :global(.fp) { flex: 1; justify-content: flex-end; max-width: 60vw; }
  }
  @media (max-width: 420px) { .brand { display: none; } .tools :global(.fp) { max-width: none; } }
</style>
