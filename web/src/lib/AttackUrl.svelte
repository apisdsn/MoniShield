<!-- Full attack endpoint URL (inv. §2.4): per upstream, METHOD + upstream base URL (when known from the
     hosts configuration) + decoded path; upstream without a host -> "[Host tidak tercatat]" ("-" = rejected at the
     ingress). Data text is always rendered as text (Svelte escapes it), so URLs containing <script> or ${jndi:
     are never executed. User-Agent below it. -->
<script>
  import { t } from '../i18n.js';
  let { methodPath, upstreams = [], ua = '', hosts = {} } = $props();
  const i = $derived(methodPath.indexOf(' '));
  const method = $derived(i > 0 ? methodPath.slice(0, i) : '');
  const path = $derived(i > 0 ? methodPath.slice(i + 1) : methodPath);
</script>

<code class="url">
  {#each upstreams.length ? upstreams : ['-'] as up}
    <div class="ln"><b>{method}</b>
      {#if hosts[up]}<b>{hosts[up]}</b>{:else}<span class="muted">[{up === '-' ? $t('sec.host_rejected') : $t('sec.host_unknown')}]</span>{/if}{path}</div>
  {/each}
</code>
{#if ua}<div class="ua muted">UA: {ua}</div>{/if}

<style>
  .url { display: block; word-break: break-all; max-width: 560px; }
  .ln + .ln { margin-top: 4px; }
  b { color: var(--fg); font-weight: 600; }
  .ua { font-size: 0.6875rem; margin-top: 4px; word-break: break-all; }
</style>
