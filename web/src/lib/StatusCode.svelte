<!-- Kode status HTTP berwarna (2xx hijau, 3xx netral, 4xx kuning, 5xx merah); kodenya selalu tertulis (DRD §9.2).
     `code`: satu kode, atau `counts`: {kode: jumlah} -> '200×3 401×1' (bentuk lama). -->
<script>
  import { lang } from '../i18n.js';
  import { num } from '../format.js';
  let { code = null, counts = null } = $props();
  const items = $derived(counts ? Object.entries(counts).sort(([a], [b]) => a.localeCompare(b)) : [[code, null]]);
  const cls = (c) => (/^[1-5]\d\d$/.test(String(c)) ? `s${String(c)[0]}` : '');
</script>

<span class="st">{#each items as [c, n], i}{#if i}{' '}{/if}<span class={cls(c)}>{c ?? '–'}</span>{#if n !== null}<span class="x">×{num(n, $lang)}</span>{/if}{/each}</span>

<style>
  .st { font-variant-numeric: tabular-nums; white-space: normal; }
  .x { color: var(--muted); font-weight: 400; }
</style>
