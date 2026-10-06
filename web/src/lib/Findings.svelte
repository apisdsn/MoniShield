<!-- "Temuan utama" Keamanan (inv. §2.4, 9 aturan) disusun dari komponen dan kamus berkunci, bukan HTML dalam string:
     tiap butir = bagian tebal + kalimat, keduanya dua bahasa; nilai data (IP, akun, organisasi) masuk sebagai
     parameter teks; kalimat lanjutan di kamus memuat spasi/tanda baca awalnya sendiri ("…internet</b>: 25 …" seperti lama). items: [{key, b: {param}, t: {param}}]. Kosong -> kartu tidak tampil (lama). -->
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
