<!-- Folder picker (DRD §6.1, ASSUMPTION D1): the browser's built-in select, newest on top, grouped per month when
     folders > 60. One date per entry: the day the logs cover (format.js logDay), the same for S3 and Kafka folders. ◀ ▶ arrows for previous/next folder (U14; shortcuts [ ] in App). Disabled in Trends.
     Redesign 2026-10-27: the only place the date is shown; the source is the switch next to it, and the log period and
     update time are in the tooltip (`info`). Arrows and select form one pill, on phones too. -->
<script>
  import { lang, t } from '../i18n.js';
  import { dLabel, fLabel, logDay } from '../format.js';
  let { folders = [], value, info = '', disabled = false, onchange } = $props();

  const idx = $derived(folders.findIndex((f) => f.folder === value));   // folders: newest first
  const groups = $derived.by(() => {
    if (folders.length <= 60) return [{ label: null, items: folders }];
    const g = new Map();
    for (const f of folders) {
      const k = logDay(f.folder).slice(0, 7);
      if (!g.has(k)) g.set(k, { label: dLabel(`${k}-01`, $lang).replace(/^1 /, ''), items: [] });
      g.get(k).items.push(f);
    }
    return [...g.values()];
  });
  function label(f) {
    let s = fLabel(f.folder, $lang);
    if (!f.lines) s += ` · ${f.files_corrupt ? $t('folder.corrupt') : $t('folder.empty')}`;
    return s;
  }
</script>

<div class="fp">
  <button class="icon-btn arrow" onclick={() => onchange(folders[idx + 1].folder)} disabled={disabled || idx < 0 || idx >= folders.length - 1}
    aria-label={$t('folder.prev')} title="{$t('folder.prev')} ([)">◀</button>
  <label class="sr-only" for="folder-select">{$t('folder.label')}</label>
  <select id="folder-select" {value} {disabled} onchange={(e) => onchange(e.currentTarget.value)}
    title={disabled ? $t('folder.disabled_trends') : info || undefined}>
    {#each groups as g}
      {#if g.label}
        <optgroup label={g.label}>{#each g.items as f}<option value={f.folder}>{label(f)}</option>{/each}</optgroup>
      {:else}
        {#each g.items as f}<option value={f.folder}>{label(f)}</option>{/each}
      {/if}
    {/each}
  </select>
  <button class="icon-btn arrow" onclick={() => onchange(folders[idx - 1].folder)} disabled={disabled || idx <= 0}
    aria-label={$t('folder.next')} title="{$t('folder.next')} (])">▶</button>
</div>

<style>
  .fp { display: flex; align-items: center; gap: 2px; min-width: 0; padding: 3px; border: 1px solid var(--line-strong); border-radius: 999px; background: var(--bg2); }
  select {
    flex: 1; font-weight: 600; letter-spacing: 0.01em; color: var(--fg); padding: 0.4rem 34px 0.4rem 12px; cursor: pointer;
    min-height: 2.375rem; max-width: 100%; min-width: 0; text-overflow: ellipsis; text-align: center;
    border: 0; background-color: var(--bg2); background-image: var(--chev); background-position: right 12px center;
  }
  select:disabled { color: var(--muted); cursor: not-allowed; }
  /* focus: the pill's own border turns into the ring (no second rounded ring inside the pill) */
  select:focus, select:focus-visible { outline: none; box-shadow: none; }
  .fp:has(select:focus-visible) { border-color: var(--focus); box-shadow: 0 0 0 1px var(--focus); }
  .arrow:focus-visible { outline-offset: -2px; }
  .arrow { width: 2.375rem; height: 2.375rem; flex: none; font-size: 0.7rem; color: var(--muted); border: 0; background: transparent; }
  .arrow:hover:not(:disabled) { color: var(--fg); background: var(--nav-hover); }
  @media (max-width: 900px) { select { font-size: 1rem; } }
</style>
