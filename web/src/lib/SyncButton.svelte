<!-- Tombol "Sinkronkan data" di kepala (khusus admin): memasukkan folder log baru / file yang berubah tanpa membuka
     layar Ingest. Tiap menit (dan saat tab kembali aktif) membaca GET /api/admin/ingest/status: lencana = jumlah folder
     tanggal di disk yang belum ada di basis data. Klik -> POST /api/admin/ingest (hanya file baru/berubah yang diproses;
     409 = sudah berjalan, ikut menunggu) -> progres -> onsynced({folders_changed}) agar App memuat ulang dan pindah ke
     folder terbaru. ASUMSI: hanya admin, karena ingest menulis ke basis data (matriks peran Tahap 10). -->
<script>
  import { onMount } from 'svelte';
  import { lang, t } from '../i18n.js';
  import { api } from '../api.js';
  import { num, dLabel } from '../format.js';
  import { toast } from './Toast.svelte';
  import Icon from './Icon.svelte';

  let { onsynced = null } = $props();
  let pending = $state([]), running = $state(false), progress = $state('');

  async function check() {
    try {
      const s = await api.get('/api/admin/ingest/status');
      pending = s.new_folders || [];
      if (s.running && !running) follow();    // ingest dari layar lain / jadwal: tampilkan juga di sini
    } catch { /* sesi habis / offline: ditangani App */ }
  }
  async function follow() {
    running = true;
    try {
      for (;;) {
        await new Promise((r) => setTimeout(r, 1000));
        const s = await api.get('/api/admin/ingest/status');
        progress = s.total ? $t('sync.progress', { done: num(s.done, $lang), total: num(s.total, $lang) }) : $t('sync.scanning');
        if (s.running) continue;
        pending = s.new_folders || [];
        if (s.error) toast($t('sync.failed', { msg: s.error }));
        else {
          const f = s.last?.folders_changed || [];
          toast(f.length ? $t('sync.done', { n: num(f.length, $lang), list: f.slice(-3).map((x) => dLabel(x, $lang)).join(', ') }) : $t('sync.nothing'));
          onsynced?.(s.last);
        }
        break;
      }
    } catch (e) { toast($t('sync.failed', { msg: e.message })); }
    finally { running = false; progress = ''; }
  }
  async function sync() {
    if (running) return;
    try { await api.post('/api/admin/ingest', {}); }
    catch (e) { if (e.status !== 409) { toast($t('sync.failed', { msg: e.message })); return; } }
    follow();
  }
  onMount(() => {
    check();
    const id = setInterval(check, 60000);
    const vis = () => document.visibilityState === 'visible' && check();
    document.addEventListener('visibilitychange', vis);
    return () => { clearInterval(id); document.removeEventListener('visibilitychange', vis); };
  });
  const label = $derived(running ? `${$t('sync.running')}${progress ? ` · ${progress}` : ''}`
    : pending.length ? $t('sync.button_new', { n: num(pending.length, $lang), list: pending.map((d) => dLabel(d, $lang)).join(', ') }) : $t('sync.button'));
</script>

<button class="icon-btn sync" class:spin={running} onclick={sync} aria-label={label} title={label} aria-busy={running}>
  <Icon name="sync" size={17} />
  {#if pending.length && !running}<span class="badge" aria-hidden="true">{pending.length > 9 ? '9+' : pending.length}</span>{/if}
</button>

<style>
  .sync { position: relative; }
  .badge {
    position: absolute; top: -4px; right: -4px; min-width: 18px; height: 18px; padding: 0 5px; border-radius: 999px;
    display: grid; place-items: center; font-size: 0.6875rem; font-weight: 700; line-height: 1;
    background: var(--accent); color: var(--brand-fg); box-shadow: 0 0 0 2px var(--card);
  }
  .spin :global(svg) { animation: putar 1s linear infinite; }
  @keyframes putar { to { transform: rotate(360deg); } }
  @media (prefers-reduced-motion: reduce) { .spin :global(svg) { animation: none; } }
</style>
