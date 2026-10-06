<!-- Pemilih folder (DRD §6.1, ASUMSI D1): select bawaan browser, terbaru di atas, dikelompokkan per bulan bila
     folder > 60. Panah ◀ ▶ untuk folder sebelum/berikut (U14; pintasan [ ] di App). Nonaktif di Tren. -->
<script>
  import { lang, t } from '../i18n.js';
  import { dLabel, dShort } from '../format.js';
  import { onMount } from 'svelte';
  let { folders = [], value, disabled = false, onchange } = $props();

  // layar sempit: label pendek (tanggal saja) agar tidak terpotong; nama "Folder log" tetap di <label> tersembunyi
  let compact = $state(false);
  onMount(() => {
    const mq = matchMedia('(max-width: 900px)');
    compact = mq.matches;
    const f = (e) => (compact = e.matches);
    mq.addEventListener('change', f);
    return () => mq.removeEventListener('change', f);
  });

  const idx = $derived(folders.findIndex((f) => f.folder === value));   // folders: terbaru dulu
  const groups = $derived.by(() => {
    if (folders.length <= 60) return [{ label: null, items: folders }];
    const g = new Map();
    for (const f of folders) {
      const k = f.folder.slice(0, 7);
      if (!g.has(k)) g.set(k, { label: dLabel(`${k}-01`, $lang).replace(/^1 /, ''), items: [] });
      g.get(k).items.push(f);
    }
    return [...g.values()];
  });
  function label(f) {
    let s = compact ? dLabel(f.folder, $lang) : $t('folder.option', { date: dLabel(f.folder, $lang) });
    if (!compact && f.range_start) s += ` · ${$t('folder.log_of', { date: dShort(f.range_start, $lang) })}`;
    if (!f.lines) s += ` · ${f.files_corrupt ? $t('folder.corrupt') : $t('folder.empty')}`;
    return s;
  }
</script>

<div class="fp">
  <button class="icon-btn arrow" onclick={() => onchange(folders[idx + 1].folder)} disabled={disabled || idx < 0 || idx >= folders.length - 1}
    aria-label={$t('folder.prev')} title="{$t('folder.prev')} ([)">◀</button>
  <label class="sr-only" for="folder-select">{$t('folder.label')}</label>
  <select id="folder-select" {value} {disabled} onchange={(e) => onchange(e.currentTarget.value)}
    title={disabled ? $t('folder.disabled_trends') : undefined}>
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
  .fp { display: flex; align-items: center; gap: 6px; min-width: 0; }
  select {
    font-weight: 600; letter-spacing: 0.02em; color: var(--accent-text); padding: 0.55rem 40px 0.55rem 18px; cursor: pointer;
    min-height: 2.75rem; max-width: 100%; min-width: 0; text-overflow: ellipsis; background-image: var(--chev-accent);
  }
  select:disabled { color: var(--muted); cursor: not-allowed; background-image: var(--chev); }
  .arrow { width: 2.25rem; height: 2.25rem; font-size: 0.7rem; color: var(--muted); }
  @media (max-width: 900px) {
    select { font-size: 1rem; padding: 0.5rem 38px 0.5rem 16px; background-position: right 14px center; }
    .arrow { display: none; }
  }
</style>
