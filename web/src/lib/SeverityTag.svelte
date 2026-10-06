<!-- Tag tingkat bahaya (DRD §4.5): pil 11 px tebal dengan titik; tingkat dibedakan juga oleh teks (§9.2).
     level: 3 kritis, 2 sedang, 1 rendah/netral, 'ok' (Jaringan Ombudsman, Ada log). -->
<script>
  let { level = 1, text } = $props();
</script>

<span class="tag sev{level}">{text}</span>

<style>
  .tag {
    display: inline-flex; align-items: center; gap: 6px; padding: 2px 10px; border-radius: 999px; border: 1px solid color-mix(in srgb, currentColor 35%, transparent);
    font-size: 0.6875rem; font-weight: 600; white-space: nowrap; text-transform: capitalize;
  }
  .tag::before { content: ''; width: 6px; height: 6px; border-radius: 50%; background: currentColor; flex: none; }
  .sev3 { color: var(--sev3-fg); background: color-mix(in srgb, var(--err) 14%, transparent); }
  .sev2 { color: var(--sev2-fg); background: color-mix(in srgb, var(--warn) 14%, transparent); }
  .sev1 { color: var(--sev1-fg); background: rgba(148, 163, 184, 0.14); }
  .sevok { color: var(--sevok-fg); background: color-mix(in srgb, var(--ok) 14%, transparent); }
</style>
