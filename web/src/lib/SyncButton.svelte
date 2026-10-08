<!-- "Sinkronkan data" button in the header (admin only): ingests new log folders / changed files without opening
     the Ingest screen. Every minute (and when the tab becomes active again) reads GET /api/admin/ingest/status: badge = number of date
     folders on disk not yet in the database. Click -> POST /api/admin/ingest (only new/changed files are processed;
     409 = already running, wait along) -> progress -> onsynced({folders_changed}) so App reloads and switches to the
     newest folder. ASSUMPTION: admin only, because ingest writes to the database (Stage 10 role matrix).
     When automatic S3 sync is on (status.s3.enabled), a click checks S3 first (POST /api/admin/import/sync: new date
     folders downloaded + ingested), and only then ingests local folders (owner request 2026-10-07). -->
<script>
  import { srv, errText } from '../srv.js';
  import { onMount } from 'svelte';
  import { lang, t } from '../i18n.js';
  import { api } from '../api.js';
  import { num, dLabel } from '../format.js';
  import { toast } from './Toast.svelte';
  import Icon from './Icon.svelte';

  let { onsynced = null } = $props();
  let pending = $state([]), running = $state(false), progress = $state(''), s3on = $state(false);

  async function check() {
    try {
      const s = await api.get('/api/admin/ingest/status');
      pending = s.new_folders || []; s3on = !!s.s3?.enabled;
      if (s.running && !running) follow();    // ingest from another screen / schedule: show it here too
    } catch { /* session expired / offline: handled by App */ }
  }
  async function follow(fromS3 = null) {
    running = true;
    try {
      for (;;) {
        await new Promise((r) => setTimeout(r, 1000));
        const s = await api.get('/api/admin/ingest/status');
        progress = s.total ? $t('sync.progress', { done: num(s.done, $lang), total: num(s.total, $lang) }) : $t('sync.scanning');
        if (s.running) continue;
        pending = s.new_folders || [];
        if (s.error) toast($t('sync.failed', { msg: $srv(s.error) }));
        else {
          const f = s.last?.folders_changed || [];
          if (f.length) toast($t('sync.done', { n: num(f.length, $lang), list: f.slice(-3).map((x) => dLabel(x, $lang)).join(', ') }));
          else if (!fromS3?.length) toast($t('sync.nothing'));   // folders from S3 already announced
          onsynced?.(s.last);
        }
        break;
      }
    } catch (e) { toast($t('sync.failed', { msg: $errText(e) })); }
    finally { running = false; progress = ''; }
  }
  /** Check S3 then wait until done. -> folders fetched/updated (for the message), or null when not run. */
  async function syncS3() {
    try { await api.post('/api/admin/import/sync', {}); }
    catch (e) { if (e.code !== 'import_running') { toast($t('sync.s3_failed', { msg: $errText(e) })); return null; } }
    for (;;) {
      await new Promise((r) => setTimeout(r, 1000));
      const s = (await api.get('/api/admin/ingest/status')).s3;
      progress = s.phase === 'download' && s.total ? $t('sync.s3_fetch', { done: num(s.done + 1, $lang), total: num(s.total, $lang) })
        : s.phase === 'ingest' ? $t('sync.scanning') : $t('sync.s3_check');
      if (s.running) continue;
      if (s.last_errors?.length) toast($t('sync.s3_failed', { msg: $errText(s.last_errors[0]) }));
      return s.last_imported || [];
    }
  }
  async function sync() {
    if (running) return;
    running = true;
    let fromS3 = null;
    await check();   // S3 sync settings may have just been changed on the Ingest & import screen
    try { if (s3on) fromS3 = await syncS3(); } catch { /* handled below: local ingest still runs */ }
    if (fromS3?.length) toast($t('sync.s3_done', { n: num(fromS3.length, $lang), list: fromS3.slice(-3).map((x) => dLabel(x, $lang)).join(', ') }));
    running = false;
    try { await api.post('/api/admin/ingest', {}); }
    catch (e) { if (e.status !== 409) { toast($t('sync.failed', { msg: $errText(e) })); return; } }
    follow(fromS3);
  }
  onMount(() => {
    check();
    const id = setInterval(check, 60000);
    const vis = () => document.visibilityState === 'visible' && check();
    document.addEventListener('visibilitychange', vis);
    window.addEventListener('monishield:watch-changed', check);   // sent by the S3 Import card after settings are saved
    return () => { clearInterval(id); document.removeEventListener('visibilitychange', vis); window.removeEventListener('monishield:watch-changed', check); };
  });
  const label = $derived(running ? `${$t('sync.running')}${progress ? ` · ${progress}` : ''}`
    : pending.length ? $t('sync.button_new', { n: num(pending.length, $lang), list: pending.map((d) => dLabel(d, $lang)).join(', ') })
    : $t(s3on ? 'sync.button_s3' : 'sync.button'));
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
