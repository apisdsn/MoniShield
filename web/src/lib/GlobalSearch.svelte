<!-- Pencarian global (Tahap 24 butir 6): tombol 🔍 di kepala (juga Ctrl+K / ⌘K; "/" sudah dipakai untuk filter tabel) membuka dialog; ketik IP,
     akun, requestId, atau potongan URL -> GET /api/search?q=…&folder=… (folder yang sedang dipilih). Hasil dikelompokkan
     per jenis; Enter / klik membuka halaman tujuan dengan filter tabelnya terisi (?cari=…). Semua teks hasil = teks biasa. -->
<script>
  import { srv, errText } from '../srv.js';
  import { lang, t } from '../i18n.js';
  import { api } from '../api.js';
  import { num } from '../format.js';
  import { go } from '../state.js';
  import Dialog from './Dialog.svelte';
  import Icon from './Icon.svelte';

  let { folder = null } = $props();
  let open = $state(false), q = $state(''), res = $state(null), busy = $state(false), error = $state(null), active = $state(0);
  let timer, seq = 0, btn = $state();

  function show() { open = true; q = ''; res = null; error = null; active = 0; }
  function onKey(e) {   // Ctrl+K / ⌘K di mana saja membuka pencarian
    if (open || e.altKey || e.shiftKey || !(e.ctrlKey || e.metaKey) || e.key.toLowerCase() !== 'k') return;
    e.preventDefault(); show();
  }
  function onInput() {
    clearTimeout(timer);
    const text = q.trim();
    if (text.length < 2) { res = null; error = null; return; }
    timer = setTimeout(async () => {
      const my = ++seq;
      busy = true; error = null;
      try {
        const j = await api.get(`/api/search?q=${encodeURIComponent(text)}${folder ? `&folder=${encodeURIComponent(folder)}` : ''}`);
        if (my === seq) { res = j; active = 0; }
      } catch (e) { if (my === seq) error = e; }
      finally { if (my === seq) busy = false; }
    }, 250);
  }
  const ORDER = ['ip', 'account', 'request', 'url'];
  const groups = $derived(ORDER.map((k) => [k, (res?.results || []).filter((r) => r.type === k)]).filter(([, l]) => l.length));
  const flat = $derived(groups.flatMap(([, l]) => l));
  function pick(r) {
    open = false;
    go({ tab: r.target.tab, service: r.target.service ?? null, folder: res?.folder || folder, module: null, q: r.target.q ?? null });
  }
  function nav(e) {
    if (!flat.length) return;
    if (e.key === 'ArrowDown') { e.preventDefault(); active = (active + 1) % flat.length; }
    else if (e.key === 'ArrowUp') { e.preventDefault(); active = (active + flat.length - 1) % flat.length; }
    else if (e.key === 'Enter') { e.preventDefault(); pick(flat[active]); }
  }
  const sub = (r) => r.type === 'ip' ? [r.sub, $t('gs.n_req', { n: num(r.n, $lang) })].filter(Boolean).join(' · ')
    : r.type === 'account' ? $t('gs.acc', { fail: num(r.n, $lang), ok: num(r.ok, $lang) })
    : r.type === 'request' ? `${r.sub} · ${r.ip}`
    : `${r.sub} · ${$t('gs.n_req', { n: num(r.n, $lang) })}`;
</script>

<svelte:window onkeydown={onKey} />
<button bind:this={btn} class="icon-btn" onclick={show} aria-label={$t('gs.open')} title={$t('gs.open')} aria-keyshortcuts="Control+K Meta+K"><Icon name="search" size={17} /></button>

<Dialog bind:open title={$t('gs.title')} returnFocus={btn}>
  <label for="gs-q" class="sr-only">{$t('gs.title')}</label>
  <input id="gs-q" type="search" autocomplete="off" spellcheck="false" placeholder={$t('gs.placeholder')} bind:value={q} oninput={onInput} onkeydown={nav}
    role="combobox" aria-expanded={!!flat.length} aria-controls="gs-list" aria-activedescendant={flat.length ? `gs-${active}` : undefined} />
  <p class="muted hint">{$t('gs.hint')}</p>
  <div id="gs-list" role="listbox" aria-label={$t('gs.results')} aria-busy={busy}>
    {#if error}<p class="err">{$errText(error)}</p>
    {:else if res && !flat.length}<p class="muted">{$t('gs.none', { q: res.q })}</p>{/if}
    {#each groups as [kind, list]}
      <p class="grp">{$t(`gs.type.${kind}`)}</p>
      {#each list as r}
        {@const i = flat.indexOf(r)}
        <div id="gs-{i}" role="option" tabindex="-1" aria-selected={i === active} class="opt" class:on={i === active}
          onclick={() => pick(r)} onkeydown={(e) => e.key === 'Enter' && pick(r)} onmousemove={() => (active = i)}>
          <span class="lbl">{r.label}</span>
          <span class="muted small">{sub(r)}</span>
        </div>
      {/each}
    {/each}
  </div>
</Dialog>

<style>
  input { width: 100%; }
  .hint { margin: 6px 0 10px; font-size: 0.75rem; }
  .grp { margin: 12px 0 4px; font-size: 0.6875rem; font-weight: 600; letter-spacing: 0.07em; text-transform: uppercase; color: var(--th-fg); }
  .opt { display: flex; flex-direction: column; gap: 2px; padding: 8px 10px; border-radius: 10px; cursor: pointer; min-height: 36px; }
  .opt.on { background: var(--row-hover); box-shadow: inset 3px 0 0 var(--accent); }
  .lbl { font-family: var(--mono); font-size: 0.8125rem; overflow-wrap: anywhere; color: var(--fg); }
  .small { font-size: 0.75rem; overflow-wrap: anywhere; }
  .err { color: var(--err-text, var(--err)); }
</style>
