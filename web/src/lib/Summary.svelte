<!-- Dotted summary box (DRD §4.6 "Ringkasan akar masalah"): each item = a sequence of text, bold, or code pieces,
     so bilingual sentences can contain <code> without HTML in strings. items: [[{t}|{b}|{code}], …] -->
<script>
  let { title, items = [] } = $props();
</script>

{#if items.length}
  <section class="alert card wide" aria-label={title}>
    <h2>{title}</h2>
    <ul>
      {#each items as parts}
        <li>{#each parts as p}{#if p.b !== undefined}<b>{p.b}</b>{:else if p.code !== undefined}<code>{p.code}</code>{:else}{p.t}{/if}{/each}</li>
      {/each}
    </ul>
  </section>
{/if}

<style>
  .alert { margin-bottom: 18px; box-shadow: inset 3px 0 0 var(--err), var(--glow); }
  h2 { margin: 0 0 6px; }
  ul { margin: 0; padding-left: 1.2rem; }
  li { margin: 6px 0; color: var(--fg); overflow-wrap: anywhere; }
  b { font-weight: 600; }
</style>
