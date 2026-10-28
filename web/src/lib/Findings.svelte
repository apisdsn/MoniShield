<!-- Security "Temuan utama" (key findings) (inv. §2.4, 9 rules) built from components and keyed dictionaries, not HTML in strings:
     each item = bold part + sentence, both bilingual; data values (IP, account, organization) go in as
     text parameters; continuation sentences in the dictionary carry their own leading space/punctuation ("…internet</b>: 25 …" like the old one). items: [{key, b: {param}, t: {param}}]. Empty -> the card is not shown (old). -->
<script>
  import { t } from '../i18n.js';
  let { items = [] } = $props();
</script>

{#if items.length}
  <section class="alert card wide" aria-labelledby="findings-h">
    <h2 id="findings-h">{$t('sec.findings')}</h2>
    <ul>
      {#each items as it}
        <li><b>{$t(`sec.f.${it.key}.b`, it.b)}</b>{$t(`sec.f.${it.key}.t`, it.t)}</li>
      {/each}
    </ul>
  </section>
{/if}

<style>
  .alert { margin-bottom: 18px; box-shadow: inset 3px 0 0 var(--err), var(--glow); }
  h2 { margin: 0 0 6px; }
  ul { margin: 0; padding-left: 1.2rem; }
  li { margin: 6px 0; color: var(--fg); opacity: 0.92; overflow-wrap: anywhere; }
  b { font-weight: 600; opacity: 1; }
</style>
