<!-- Catatan (DRD §4.6): kartu bergaris putus, teks muted; kalimat tidak dikapitalisasi (U13). -->
<script>
  let { children, wide = true } = $props();
</script>

<div class="card note" class:wide>{@render children()}</div>

<style>
  .note { color: var(--muted); border-style: dashed; box-shadow: none; font-size: 0.8125rem; }
</style>
