<!-- Sel IP + pemilik jaringan (DRD §4.4): IP tebal monospace; baris "AS<asn> · <cc> · <org>" 11 px (dipotong 2
     baris, lengkap saat diklik/fokus); tag "Jaringan Ombudsman"; IP privat -> "Jaringan Internal (IP Privat)".
     Tombol salin muncul saat hover/fokus (U12). Tidak ada tautan ke layanan pencari IP (privasi). -->
<script>
  import { t } from '../i18n.js';
  import SeverityTag from './SeverityTag.svelte';
  let { ip, more = 0 } = $props();       // ip: {ip, asn?, cc?, org?} dari API, atau teks
  const cell = $derived(typeof ip === 'string' ? { ip } : ip || {});
  const privat = $derived(/^(10\.|127\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.)/.test(cell.ip || ''));
  const omb = $derived(/OMBUDSMAN/i.test(cell.org || ''));
  let open = $state(false), copied = $state(false);
  async function copy() {
    try { await navigator.clipboard.writeText(cell.ip); copied = true; setTimeout(() => (copied = false), 1500); } catch { /* izin ditolak */ }
  }
</script>

<div class="ipc">
  <span class="ip"><b>{cell.ip ?? '–'}</b>{#if more}<span class="more"> +{more}</span>{/if}
    {#if cell.ip}<button class="cp" onclick={copy} aria-label={$t('ip.copy', { ip: cell.ip })} title={$t('ip.copy', { ip: cell.ip })}>{copied ? '✓' : '⧉'}</button>{/if}
  </span>
  {#if cell.org}
    <button class="own" class:open onclick={() => (open = !open)} aria-expanded={open}>{cell.asn ? `AS${cell.asn} · ` : ''}{cell.cc} · {cell.org}</button>
    {#if omb}<div><SeverityTag level="ok" text={$t('ip.ombudsman')} /></div>{/if}
  {:else if privat}
    <div class="own static">{$t('ip.private')}</div>
  {/if}
</div>

<style>
  .ipc { min-width: 140px; }
  .ip { display: inline-flex; align-items: center; gap: 6px; }
  b { font-family: var(--mono); font-size: 0.78rem; font-weight: 600; font-variant-numeric: tabular-nums; white-space: nowrap; }   /* IPv4 tidak dipecah */
  .more { color: var(--muted); font-size: 0.6875rem; }
  .cp {
    opacity: 0; border: 0; background: transparent; color: var(--muted); cursor: pointer; padding: 0 4px;
    min-width: 24px; min-height: 24px; font-size: 0.8rem;
  }
  .ipc:hover .cp, .cp:focus-visible { opacity: 1; }
  @media (hover: none) { .cp { opacity: 1; } }
  .own {
    display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
    font-size: 0.6875rem; color: var(--muted); font-weight: 400; text-align: left; text-transform: none;
    border: 0; background: transparent; padding: 0; cursor: pointer; width: 100%;
  }
  .own.open, .own:focus-visible { -webkit-line-clamp: unset; line-clamp: unset; }
  .own.static { cursor: default; }
</style>
