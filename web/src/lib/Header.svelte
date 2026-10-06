<!-- Kepala halaman (DRD §2.1 U3, §8.2, gaya §12). Layar lebar: satu kartu lekat berisi judul + baris status ringkas
     (kiri) dan pemilih folder, bahasa, tema, muat ulang, menu user (kanan). ≤ 900 px: bar 52 px lekat
     [☰] SIMPeL4 Dashboard [Folder ▾] [⋯] (bahasa, tema, muat ulang, isi menu user masuk ⋯); judul mengalir di bawahnya.
     Urutan DOM = urutan Tab: alat dulu, judul (h1, tabindex -1) sesudahnya; letak visual diatur grid. -->
<script>
  import { lang, t } from '../i18n.js';
  import { theme } from '../theme.js';
  import FolderPicker from './FolderPicker.svelte';
  import UserMenu from './UserMenu.svelte';
  import Icon from './Icon.svelte';
  import { APP_NAME } from '../brand.js';
  let { me, route, folders, folder, folderDisabled = false, onfolder, onreload, onlogout, onmenu, drawerOpen = false,
        menuBtn = $bindable(), title, suffix = '', status = [], titleEl = $bindable() } = $props();

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
    <span class="brand" aria-hidden="true">{APP_NAME}</span>
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
        <button class="icon-btn" onclick={onreload} aria-label={$t('action.reload')} title={$t('action.reload')}><Icon name="refresh" size={17} /></button>
        <UserMenu {me} {route} {onlogout} {onreload} />
      </div>
      <div class="narrow-only"><UserMenu {me} {route} {onlogout} {onreload} extended /></div>
    </div>
  </div>
  <div class="ttl">
    <h1 bind:this={titleEl} tabindex="-1">{title}{#if suffix}<span class="sfx">&nbsp;— {suffix}</span>{/if}</h1>
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
    display: grid; grid-template-columns: minmax(0, 1fr) auto; grid-template-areas: 'ttl tools'; align-items: center; gap: 12px 18px;
    padding: 14px 18px; border-radius: var(--r-card); border: 1px solid var(--card-border);
    background: color-mix(in srgb, var(--card) 92%, transparent); backdrop-filter: blur(10px); box-shadow: var(--glow);
  }
  .bar { display: contents; }
  .tools { grid-area: tools; display: flex; align-items: center; gap: 10px; min-width: 0; }
  .ttl { grid-area: ttl; min-width: 0; }
  h1 { font-size: 1.375rem; font-weight: 600; line-height: 1.25; color: var(--heading); text-transform: capitalize; overflow-wrap: anywhere; }
  h1:focus { outline: none; }
  h1:focus-visible { outline: 2px solid var(--focus); outline-offset: 2px; }
  .sfx { color: var(--muted); font-weight: 500; }
  .status { margin: 4px 0 0; font-size: 0.78rem; color: var(--muted); display: flex; flex-wrap: wrap; align-items: center; gap: 2px 8px; }
  .it { display: inline-flex; align-items: center; white-space: nowrap; }
  .status .it :global(b) { color: var(--fg); font-weight: 600; }
  .sep { color: var(--line-strong); }
  .wide-only { display: flex; align-items: center; gap: 8px; }
  .narrow-only, .burger, .brand { display: none; }
  .seg button { min-width: 2.5rem; }
  @media (max-width: 1180px) {
    .top { grid-template-columns: minmax(0, 1fr); grid-template-areas: 'tools' 'ttl'; }
    .tools { justify-content: flex-end; }
  }
  @media (max-width: 900px) {
    .top { display: contents; }
    .bar {
      display: flex; position: sticky; top: 0; z-index: 20; align-items: center; justify-content: space-between; gap: 8px;
      min-height: 52px; padding: 4px 16px; margin: 0 -16px 8px; border-bottom: 1px solid var(--line);
      background: color-mix(in srgb, var(--bg) 90%, transparent); backdrop-filter: blur(8px);
    }
    .burger, .narrow-only { display: inline-grid; }
    .brand { display: block; font-weight: 600; white-space: nowrap; }
    .wide-only { display: none; }
    .tools { flex: 1; justify-content: flex-end; gap: 8px; }
    .tools :global(.fp) { flex: 1; justify-content: flex-end; max-width: 60vw; }
    .ttl { margin: 6px 0 12px; }
    h1 { font-size: 1.5rem; }
    .sfx { display: none; }   /* tanggal sudah tampil di pemilih folder pada bar atas */
  }
  @media (max-width: 420px) { .brand { display: none; } .tools :global(.fp) { max-width: none; } }
</style>
