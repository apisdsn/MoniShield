<!-- Info strip of the analysis pages (stage 62): which log the page read and why, with a link to Analysis Settings for admins (others read the
     text only). `text` is a sentence already translated by the page. -->
<script>
  import { t } from '../i18n.js';
  import { build } from '../state.js';
  import Icon from './Icon.svelte';
  let { text, admin = false } = $props();
</script>

<div class="strip" role="note">
  <Icon name="settings" size={18} />
  <span class="tx">{text}</span>
  {#if admin}<a class="btn" href={build({ tab: 'admin/analysis', service: null, q: null })}>{$t('any.change')}</a>{/if}
</div>

<style>
  .strip {
    display: flex; align-items: center; gap: 12px; flex-wrap: wrap; padding: 10px 16px; border-radius: 14px; margin: 0 0 14px; font-size: 0.875rem;
    background: color-mix(in srgb, var(--accent) 12%, var(--card)); box-shadow: inset 3px 0 0 var(--accent);
  }
  .strip :global(svg) { flex: none; color: var(--accent-text); }
  .tx { flex: 1 1 280px; min-width: 0; overflow-wrap: anywhere; }
  .btn { display: inline-flex; align-items: center; min-height: var(--touch); text-decoration: none; }
  @media (max-width: 480px) { .btn { width: 100%; justify-content: center; box-sizing: border-box; } }
</style>
