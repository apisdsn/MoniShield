<!-- Empty always explains why and, when possible, what can be done (DRD §6.6). -->
<script>
  let { title, text = '', children } = $props();
</script>

<div class="card empty">
  <h2>{title}</h2>
  {#if text}<p class="muted">{text}</p>{/if}
  {#if children}<div class="act">{@render children()}</div>{/if}
</div>

<style>
  .empty { max-width: 560px; margin: 40px auto; text-align: center; padding: 32px 24px; }
  h2 { font-size: 1.125rem; font-weight: 600; color: var(--heading); }
  p { margin: 8px 0 0; }
  .act { margin-top: 18px; display: flex; gap: 10px; justify-content: center; flex-wrap: wrap; }
</style>
