<!-- Ingest & impor (DRD §3.11, TRD §8.4), hanya admin: status ingest terakhir (dari database, bertahan setelah server
     dimulai ulang) dan yang sedang berjalan, tombol "Ingest sekarang", kemajuan (diperbarui tiap 2 detik, diumumkan
     sopan ke pembaca layar), peringatan; kartu impor S3 + sinkron otomatis (lib/ImportCard, Tahap 19); unggah folder dari komputer (lib/UploadCard); kelola folder log (lib/FolderManager: hapus/pulihkan); catatan audit (500 terbaru, 50 pertama tampil).
     Dashboard tetap bisa dipakai selama ingest (ingest berjalan di thread server, K1). -->
<script>
  import { srv, errText } from '../srv.js';
  import { onMount } from 'svelte';
  import { lang, t } from '../i18n.js';
  import { api } from '../api.js';
  import { num, tWIB, utcToWib } from '../format.js';
  import { toast } from '../lib/Toast.svelte';
  import DataTable from '../lib/DataTable.svelte';
  import ImportCard from '../lib/ImportCard.svelte';
  import UploadCard from '../lib/UploadCard.svelte';
  import KafkaCard from '../lib/KafkaCard.svelte';
  import FolderManager from '../lib/FolderManager.svelte';
  import Skeleton from '../lib/Skeleton.svelte';
  import ErrorState from '../lib/ErrorState.svelte';

  let { onfinished = null } = $props();
  const AUDIT_MAX = 500;
  let st = $state.raw(null), audit = $state.raw(null), error = $state(null), starting = $state(false);
  let fmKey = $state(0);   // daftar folder dimuat ulang tiap ingest selesai (hasil sinkron S3 / unggahan baru terlihat)
  let timer = null, watching = false;   // watching: ingest dimulai dari layar ini (bisa selesai sebelum status pertama dibaca)

  async function loadStatus() {
    try {
      const s = await api.get('/api/admin/ingest/status');
      const selesai = (st?.running || watching) && !s.running;
      if (!s.running) watching = false;
      st = s; error = null;
      if (selesai) {
        toast(s.error ? $t('ing.toast_fail') : $t('ing.toast_done', { n: num(s.last_run?.files_changed ?? 0, $lang) }));
        loadAudit(); onfinished?.(); fmKey++;
      }
    } catch (e) { error = e; }
    clearTimeout(timer);
    if (st?.running) timer = setTimeout(loadStatus, 2000);
  }
  async function loadAudit() {
    try { audit = await api.get(`/api/admin/audit?limit=${AUDIT_MAX}`); } catch (e) { error = e; }
  }
  onMount(() => { loadStatus(); loadAudit(); return () => clearTimeout(timer); });

  async function start() {
    starting = true;
    try { await api.post('/api/admin/ingest', {}); watching = true; toast($t('ing.started')); }
    catch (e) { toast(e.code === 'ingest_running' ? $t('ing.already') : $errText(e)); }
    finally { starting = false; await loadStatus(); loadAudit(); }
  }

  const last = $derived(st?.last_run);
  const STATUS = { ok: 'ing.st.ok', failed: 'ing.st.fail', running: 'ing.st.running' };
  const phase = $derived(!st?.running ? '' : st.phase === 'parse' && st.total
    ? $t('ing.ph.parse', { done: num(st.done, $lang), total: num(st.total, $lang) })
    : st.phase === 'load' && st.folder ? $t('ing.ph.load', { folder: st.folder }) : $t('ing.ph.scan'));
  const pct = $derived(st?.running && st.phase === 'parse' && st.total ? Math.round((st.done / st.total) * 100) : null);
</script>

{#if error && !st}
  <ErrorState {error} onretry={() => { loadStatus(); loadAudit(); }} />
{:else if !st}
  <Skeleton kpis={0} charts={1} />
{:else}
  <div class="grid">
    <section class="card wide ing" aria-labelledby="ing-h">
      <header>
        <h2 id="ing-h">{$t('ing.title')}</h2>
        <button class="btn primary" onclick={start} disabled={st.running || starting}>{st.running ? $t('ing.running') : $t('ing.now')}</button>
      </header>
      <p class="lastline">
        {#if last}
          {$t('ing.last')} <b>{tWIB(utcToWib(last.finished_at), $lang)}</b> ·
          <span class={last.status === 'ok' ? 'ok' : 'ERROR'}>{$t(STATUS[last.status] || 'ing.st.fail')}</span> ·
          {$t('ing.changed', { n: num(last.files_changed ?? 0, $lang), seen: num(last.files_seen ?? 0, $lang) })}
        {:else}<span class="muted">{$t('ing.never')}</span>{/if}
      </p>
      <div class="live" aria-live="polite">
        {#if st.running}
          <div class="prog" role="progressbar" aria-label={$t('ing.title')} aria-valuemin="0" aria-valuemax="100" aria-valuenow={pct ?? undefined} aria-valuetext={phase}>
            <div class="fill" class:indet={pct === null} style={pct !== null ? `width:${pct}%` : undefined}></div>
          </div>
          <p class="muted ph">{phase}{#if st.started_by} · {$t('ing.by', { user: $srv(st.started_by) })}{/if}</p>
        {/if}
      </div>
      {#if st.error}<p class="err" role="alert">{$t('ing.error')} {$srv(st.error)}</p>{/if}
      {#if last?.warnings?.length}
        <details class="warns">
          <summary>{$t('ing.warnings', { n: num(last.warnings.length, $lang) })}</summary>
          <ul>{#each last.warnings as w}<li><code>{$srv(w)}</code></li>{/each}</ul>
        </details>
      {/if}
      <p class="muted small">{$t('ing.hint')}</p>
    </section>

    <ImportCard onfinished={() => { loadStatus(); loadAudit(); onfinished?.(); fmKey++; }} />

    <KafkaCard />

    <UploadCard onfinished={() => { watching = true; setTimeout(loadStatus, 700); loadAudit(); }} />

    {#key fmKey}<FolderManager onchanged={() => { loadStatus(); loadAudit(); onfinished?.(); }} />{/key}

    {#if audit}
      <DataTable title={$t('ing.audit')} rows={audit.rows} limit={50} columns={[
        { key: 'at', label: $t('col.time'), fmt: (r) => tWIB(utcToWib(r.at), $lang), cls: () => 'nowrap', sort: true },
        { key: 'username', label: 'User', fmt: (r) => r.username || '–', sort: true },
        { key: 'action', label: $t('ing.col.action'), type: 'code', sort: true },
        { key: 'detail', label: $t('ing.col.detail'), fmt: (r) => $srv(r.detail || ''), cls: () => 'small', minw: 220 },
        { key: 'ip', label: 'IP', type: 'code', fmt: (r) => r.ip || '–' },
      ]} />
      {#if audit.total > AUDIT_MAX}<p class="muted small">{$t('ing.audit_more', { n: num(AUDIT_MAX, $lang), m: num(audit.total, $lang) })}</p>{/if}
    {/if}
  </div>
{/if}

<style>
  .ing header, section > header { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; margin-bottom: 10px; }
  h2 { font-size: 1rem; font-weight: 600; color: var(--heading); }
  .ing header .btn { min-height: var(--touch); }
  .lastline { font-size: 0.875rem; }
  .ok { color: var(--ok); font-weight: 600; }
  .prog { height: 8px; border-radius: 999px; background: var(--bg2); overflow: hidden; margin-top: 14px; border: 1px solid var(--line); }
  .fill { height: 100%; background: linear-gradient(90deg, var(--accent), var(--violet)); transition: width 0.4s; }
  .fill.indet { width: 35%; animation: slide 1.4s ease-in-out infinite; }
  @keyframes slide { from { transform: translateX(-100%); } to { transform: translateX(300%); } }
  @media (prefers-reduced-motion: reduce) { .fill.indet { animation: none; width: 100%; opacity: 0.5; } }
  .ph { font-size: 0.8125rem; margin-top: 6px; }
  .err { color: var(--err); font-size: 0.875rem; margin-top: 10px; }
  .warns { margin-top: 12px; font-size: 0.8125rem; }
  .warns summary { cursor: pointer; color: var(--warn); font-weight: 600; min-height: var(--touch); display: flex; align-items: center; }
  .warns ul { margin: 6px 0 0 18px; display: grid; gap: 4px; }
  .warns code { word-break: break-all; }
  .small { font-size: 0.75rem; margin-top: 10px; }
</style>
