<!-- Peringatan "Temuan utama" (DRD §4.6): garis kiri merah 3 px, judul tebal, daftar butir. -->
<script>
  let { title, children } = $props();
</script>

<section class="alert" aria-label={title}>
  <b class="cap">{title}</b>
  <ul>{@render children()}</ul>
</section>

<style>
  .alert { padding: 16px 22px; margin-bottom: 18px; box-shadow: inset 3px 0 0 var(--err), var(--glow); }
  ul { margin: 6px 0 0; padding-left: 1.2rem; }
  ul :global(li) { margin: 5px 0; color: var(--fg); opacity: 0.9; }
</style>
