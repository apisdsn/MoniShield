<!-- Failure (DRD §6.7): a sentence for the user + "Coba lagi"; technical details under "Detail". role="alert". -->
<script>
  import { srv, errText } from '../srv.js';
  import { t } from '../i18n.js';
  let { title = null, message = null, error = null, onretry = null, compact = false } = $props();
  const detail = $derived(error ? `${error.status || ''} ${error.code || ''} ${$errText(error)}`.trim() : '');
</script>

<div class={compact ? 'inline' : 'card wide box'} role="alert">
  {#if !compact}<h2>{title ?? $t('state.error_title')}</h2>{/if}
  <p>{message ?? (error?.status === 0 ? $t('state.error_network') : $t('state.error_text'))}</p>
  <div class="row">
    {#if onretry}<button class="btn" onclick={onretry}>{$t('action.retry')}</button>{/if}
    {#if detail}<details><summary>{$t('state.detail')}</summary><code>{detail}</code></details>{/if}
  </div>
</div>

<style>
  .box { max-width: 640px; margin: 24px auto; box-shadow: inset 3px 0 0 var(--err), var(--glow); }
  h2 { font-size: 1.0625rem; font-weight: 600; color: var(--heading); }
  p { margin: 6px 0 12px; }
  .inline { padding: 10px 4px; }
  .inline p { margin: 0 0 8px; color: var(--err); }
  .row { display: flex; gap: 14px; align-items: center; flex-wrap: wrap; }
  summary { cursor: pointer; color: var(--muted); font-size: 0.8125rem; }
</style>
