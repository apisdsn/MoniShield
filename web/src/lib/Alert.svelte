<!-- Kartu perhatian (DRD §4.6, gaya §12 "What needs your attention"): judul + jumlah, butir bernomor berisi judul
     tebal, satu kalimat penjelasan, dan tautan tindakan ("Lihat …  →") ke halaman/tabel terkait.
     items: [{title, text?, href?, link?, tone?: 'err'|'warn'|'accent'}]. Tanpa items: daftar butir biasa (children). -->
<script>
  import Icon from './Icon.svelte';
  let { title, items = null, children = null, wide = false } = $props();
</script>

<section class="alert card" class:wide aria-label={title}>
  <header>
    <h2>{title}</h2>
    {#if items}<span class="count" aria-hidden="true">{items.length}</span>{/if}
  </header>
  {#if items}
    <ol>
      {#each items as it, i}
        <li class={it.tone || 'err'}>
          <span class="no" aria-hidden="true">{i + 1}</span>
          <div class="body">
            <b>{it.title}</b>
            {#if it.text}<p>{it.text}</p>{/if}
            {#if it.href}<a href={it.href}>{it.link}<Icon name="arrow" size={14} /></a>{/if}
          </div>
        </li>
      {/each}
    </ol>
  {:else if children}
    <ul class="plain">{@render children()}</ul>
  {/if}
</section>

<style>
  .alert { margin-bottom: 18px; }
  header { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-bottom: 12px; }
  .count {
    min-width: 22px; height: 22px; padding: 0 7px; border-radius: 999px; display: grid; place-items: center;
    font-size: 0.75rem; font-weight: 700; color: var(--accent-text); border: 1px solid color-mix(in srgb, var(--accent) 45%, transparent);
    background: color-mix(in srgb, var(--accent) 10%, transparent);
  }
  ol { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 10px; }
  li {
    display: flex; gap: 12px; padding: 12px 14px; border-radius: 12px; border: 1px solid var(--card-border);
    background: var(--card2); box-shadow: inset 3px 0 0 var(--err);
  }
  li.warn { box-shadow: inset 3px 0 0 var(--warn); } li.accent { box-shadow: inset 3px 0 0 var(--accent); }
  .no {
    width: 24px; height: 24px; border-radius: 7px; display: grid; place-items: center; flex: none; font-size: 0.75rem; font-weight: 600;
    color: var(--kpi-label); background: var(--icon-bg); border: 1px solid var(--icon-border);
  }
  .body { min-width: 0; display: flex; flex-direction: column; gap: 4px; }
  b { color: var(--fg); font-weight: 600; overflow-wrap: anywhere; }
  p { margin: 0; color: var(--muted); font-size: 0.8125rem; }
  a { display: inline-flex; align-items: center; gap: 4px; color: var(--accent-text); font-size: 0.8125rem; font-weight: 500; text-decoration: none; width: fit-content; min-height: 24px; }
  a:hover { text-decoration: underline; }
  .plain { margin: 0; padding-left: 1.2rem; }
  .plain :global(li) { margin: 5px 0; display: list-item; border: 0; background: none; box-shadow: none; padding: 0; color: var(--fg); }
  @media (max-width: 900px) { a { min-height: var(--touch); } }
</style>
