<!-- URL lengkap endpoint serangan (inv. §2.4): per upstream, METODE + base URL upstream (bila diketahui dari
     konfigurasi hosts) + path ter-decode; upstream tanpa host -> "[Host tidak tercatat]" ("-" = ditolak di
     ingress). Teks data selalu dirender sebagai teks (Svelte meng-escape), jadi URL berisi <script> atau ${jndi:
     tidak pernah dieksekusi. Di bawahnya User-Agent. -->
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
