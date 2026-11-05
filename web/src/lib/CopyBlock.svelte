<!-- A command to copy (Collectors page): the lines as they are typed, wrapped inside the box so nothing scrolls sideways on a
     phone, and a button that copies all of them. If the browser refuses the clipboard, the text stays selectable. -->
<script>
  import { t } from '../i18n.js';
  import { toast } from './Toast.svelte';
  import Icon from './Icon.svelte';
  let { title = '', lines = [], label = null } = $props();   // label: what the copy button is called for screen readers
  async function copy() {
    try { await navigator.clipboard.writeText(lines.join('\n')); toast($t('adm.copied')); } catch { /* no clipboard permission: the text can be selected by hand */ }
  }
</script>

<div class="cb">
  {#if title}<p class="ttl">{title}</p>{/if}
  <div class="box">
    <pre>{lines.join('\n')}</pre>
    <button type="button" class="btn" onclick={copy} aria-label="{$t('cl.copy')}{label || title ? ': ' + (label || title) : ''}"><Icon name="copy" size={16} />{$t('adm.copy')}</button>
  </div>
</div>

<style>
  .cb { margin-top: 12px; }
  .ttl { margin: 0 0 6px; font-size: 0.8125rem; color: var(--kpi-label); }
  .box { display: flex; gap: 8px; align-items: flex-start; }
  pre {
    flex: 1; min-width: 0; margin: 0; padding: 10px 12px; border-radius: var(--r-ctl); background: var(--pre-bg); border: 1px solid var(--line);
    font-family: var(--mono); font-size: 0.75rem; line-height: 1.55; color: var(--code-fg); white-space: pre-wrap; overflow-wrap: anywhere; user-select: all;
  }
  .btn { flex: none; min-height: var(--touch); }
  @media (max-width: 560px) { .box { flex-direction: column; align-items: stretch; } }
</style>
