<!-- Kartu "Impor dari S3" di layar Ingest & impor (DRD §3.11, TRD §3.8): status kredensial (hanya tersedia/tidak dan
     sumbernya), formulir tempel kredensial sementara (memori server saja), kolom tautan dengan bentuk yang diterima,
     "Coba dulu" (hanya mendaftar objek), "Impor" (konfirmasi, kemajuan, lalu ingest), dan riwayat impor.
     Nilai kredensial tidak pernah dikirim balik oleh server; kolomnya dikosongkan begitu terkirim. -->
<script>
  import { onMount } from 'svelte';
  import { lang, t } from '../i18n.js';
  import { api } from '../api.js';
  import { num, bytes, tWIB, utcToWib } from '../format.js';
  import { toast } from './Toast.svelte';
  import DataTable from './DataTable.svelte';
  import Dialog from './Dialog.svelte';
  import Note from './Note.svelte';
  import SeverityTag from './SeverityTag.svelte';

  let { onfinished = null } = $props();
  let ov = $state.raw(null), error = $state(null);
  let url = $state(''), busy = $state(false), job = $state.raw(null), fail = $state(null);
  let showCred = $state(false), ak = $state(''), sk = $state(''), stok = $state(''), credErr = $state(null), credBusy = $state(false);
  let confirm = $state(false), timer = null;

  async function load() {
    try { ov = await api.get('/api/admin/import'); error = null; } catch (e) { error = e; }
    if (ov?.running && ov.state?.job_id && !timer) poll(ov.state.job_id);
  }
  onMount(() => { load(); return () => clearTimeout(timer); });

  // galat: bahasa Indonesia = pesan server apa adanya (memuat rincian, mis. awalan yang diizinkan); EN = kamus per kode
  const why = (e) => (e.status === 0 ? $t('state.error_network') : $lang === 'en' && e.code ? $t(`imp.err.${e.code}`) : e.message || $t('state.error_text'));
  const whyJob = (j) => ($lang === 'en' && j.result?.error?.code ? $t(`imp.err.${j.result.error.code}`) : j.result?.error?.message || j.message || '');

  async function start(dry) {
    confirm = false; fail = null; busy = true; job = null;
    try {
      const r = await api.post('/api/admin/import', { url: url.trim(), dry_run: dry });
      poll(r.job_id);
    } catch (e) { fail = why(e); busy = false; }
  }
  async function poll(id) {
    clearTimeout(timer); timer = null; busy = true;
    try {
      const j = await api.get(`/api/admin/import/${id}`);
      job = j;
      if (j.running || (j.status === 'berjalan') || (!j.result && j.status !== 'gagal')) { timer = setTimeout(() => poll(id), 1000); return; }
      busy = false; timer = null;
      if (j.status === 'gagal') fail = whyJob(j);
      else if (j.status === 'selesai') { toast($t('imp.toast_done', { n: num(j.result.downloaded, $lang), folder: j.folder })); onfinished?.(); }
      load();
    } catch (e) { busy = false; fail = why(e); }
  }
  async function saveCred(e) {
    e.preventDefault(); credErr = null; credBusy = true;
    try {
      await api.post('/api/admin/import/credentials', { access_key_id: ak.trim(), secret_access_key: sk, session_token: stok });
      ak = sk = stok = ''; showCred = false; toast($t('imp.cred_saved')); load();
    } catch (err) { credErr = why(err); } finally { credBusy = false; }
  }
  async function clearCred() {
    try { await api.del('/api/admin/import/credentials'); toast($t('imp.cred_cleared')); load(); } catch (e) { toast(why(e)); }
  }

  const prog = $derived(job?.progress);
  const phase = $derived(!prog ? $t('imp.ph.daftar') : prog.phase === 'unduh' && prog.total ? $t('imp.ph.unduh', { done: num(prog.done, $lang), total: num(prog.total, $lang) })
    : $t(`imp.ph.${['daftar', 'ingest'].includes(prog.phase) ? prog.phase : 'daftar'}`));
  const res = $derived(job?.result && !job.result.error ? job.result : null);
  const ST = { selesai: ['ok', 'imp.st.done'], coba: [1, 'imp.st.dry'], gagal: [3, 'imp.st.fail'], berjalan: [2, 'imp.st.running'] };
  const MB = (n) => bytes(n ?? 0, $lang);
</script>

<section class="card wide imp" aria-labelledby="imp-h">
  <header><h2 id="imp-h">{$t('ing.import_title')}</h2></header>
  {#if error && !ov}
    <p class="err" role="alert">{why(error)}</p>
  {:else if ov && !ov.enabled}
    <Note wide={false}>{$t('imp.disabled')}</Note>
  {:else if ov && ov.library === false}
    <Note wide={false}>{$t('imp.no_library')}</Note>
  {:else if ov}
    {@const c = ov.credentials}
    <p class="cred">
      {$t('imp.cred')}
      {#if c.available}<SeverityTag level="ok" text={$t('imp.cred_ok')} /> <span class="muted">({$t(c.source === 'tempel' ? 'imp.src.pasted' : 'imp.src.env')}{#if c.pasted_at} · {tWIB(utcToWib(c.pasted_at), $lang)}{/if})</span>
      {:else}<SeverityTag level={3} text={$t('imp.cred_none')} />{/if}
    </p>
    <div class="credacts">
      {#if c.pasted}<button class="btn" onclick={clearCred}>{$t('imp.cred_clear')}</button>{/if}
      {#if c.available && !showCred}<button class="btn" onclick={() => (showCred = true)} aria-expanded={showCred}>{$t('imp.cred_other')}</button>{/if}
    </div>
    {#if !c.available || showCred}
      <form class="credf" onsubmit={saveCred} novalidate aria-labelledby="cred-h">
        <h3 id="cred-h">{$t('imp.cred_form')}</h3>
        <p class="muted small">{$t('imp.cred_note')}</p>
        <label for="c-ak">{$t('imp.c.ak')}</label>
        <input id="c-ak" type="password" autocomplete="off" spellcheck="false" bind:value={ak} />
        <label for="c-sk">{$t('imp.c.sk')}</label>
        <input id="c-sk" type="password" autocomplete="off" spellcheck="false" bind:value={sk} />
        <label for="c-st">{$t('imp.c.st')}</label>
        <input id="c-st" type="password" autocomplete="off" spellcheck="false" bind:value={stok} />
        {#if credErr}<p class="err" role="alert">{credErr}</p>{/if}
        <div class="acts">
          <button class="btn primary" type="submit" disabled={credBusy || !ak || !sk}>{$t('imp.cred_save')}</button>
          {#if c.available}<button class="btn" type="button" onclick={() => { showCred = false; ak = sk = stok = ''; credErr = null; }}>{$t('action.cancel')}</button>{/if}
        </div>
      </form>
    {/if}

    <label for="imp-url" class="lbl">{$t('imp.url')}</label>
    <input id="imp-url" class="url" type="text" autocomplete="off" spellcheck="false" placeholder={ov.allowed[0]?.replace('<YYYY-MM-DD>', '2026-09-26')}
      bind:value={url} aria-describedby="imp-hint" />
    <p id="imp-hint" class="muted small">{$t('imp.only', { allowed: ov.allowed.join(' · ') })}</p>
    <div class="acts">
      <button class="btn" disabled={busy || !url.trim() || !c.available} onclick={() => start(true)}>{$t('imp.dry')}</button>
      <button class="btn primary" disabled={busy || !url.trim() || !c.available} onclick={() => (confirm = true)}>{$t('imp.go')}</button>
    </div>

    <div aria-live="polite" class="live">
      {#if busy && job}
        <div class="prog" role="progressbar" aria-label={$t('ing.import_title')} aria-valuetext={phase}
          aria-valuemin="0" aria-valuemax="100" aria-valuenow={prog?.total ? Math.round((prog.done / prog.total) * 100) : undefined}>
          <div class="fill" class:indet={!prog?.total} style={prog?.total ? `width:${Math.round((prog.done / prog.total) * 100)}%` : undefined}></div>
        </div>
        <p class="muted small">{phase}</p>
      {:else if busy}
        <p class="muted small">{$t('imp.ph.daftar')}</p>
      {/if}
      {#if fail}<p class="err" role="alert">{fail}</p>{/if}
      {#if res && !busy}
        <p class="sum">
          {#if res.dry_run}{$t('imp.res.dry', { n: num(res.take, $lang), size: MB(res.bytes), m: num(res.skipped, $lang) })}
          {:else}{$t('imp.res.done', { n: num(res.downloaded, $lang), size: MB(res.downloaded_bytes), m: num(res.skipped, $lang), folder: res.folder })}{#if res.extracted}{' '}{$t('imp.res.extracted', { n: num(res.extracted, $lang) })}{/if}{#if res.ingest}{' '}{$t('imp.res.ingest', { n: num(res.ingest.files_changed, $lang) })}{/if}{/if}
        </p>
        {#each res.warnings || [] as w}<p class="warnline small">{w}</p>{/each}
        <details class="objs">
          <summary>{$t('imp.objects', { n: num(res.objects.length, $lang) })}</summary>
          <ul>
            {#each res.objects as o}
              <li><span class={o.action === 'ambil' ? 'ok' : 'muted'}>{o.action === 'ambil' ? $t('imp.take') : $t('imp.skip')}</span>
                <code>{o.rel}</code> <span class="muted">{MB(o.size)}{#if o.reason} · {o.reason}{/if}</span></li>
            {/each}
          </ul>
        </details>
      {/if}
    </div>
  {/if}
</section>

{#if ov?.enabled}
  <DataTable title={$t('imp.history')} rows={ov.jobs} limit={20} columns={[
    { key: 'started_at', label: $t('col.time'), fmt: (r) => tWIB(utcToWib(r.started_at), $lang), cls: () => 'nowrap', sort: true },
    { key: 'prefix', label: $t('imp.col.link'), type: 'code', fmt: (r) => `s3://${r.bucket}/${r.prefix}`, minw: 240 },
    { key: 'folder', label: 'Folder', cls: () => 'nowrap', sort: true },
    { key: 'files', label: $t('imp.col.objects'), type: 'num', fmt: (r) => (r.files == null ? '–' : num(r.files, $lang)) },
    { key: 'bytes', label: $t('col.size'), type: 'num', fmt: (r) => (r.bytes == null ? '–' : MB(r.bytes)) },
    { key: 'status', label: $t('col.status'), custom: true, sort: true },
    { key: 'requested_by', label: $t('imp.col.by'), fmt: (r) => r.requested_by || '–' },
  ]}>
    {#snippet cell(r)}{@const s = ST[r.status] || ST.gagal}<SeverityTag level={s[0]} text={$t(s[1])} />{#if r.message}<div class="muted small msg">{r.message}</div>{/if}{/snippet}
  </DataTable>
{/if}

<Dialog bind:open={confirm} title={$t('imp.confirm_title')}>
  <p>{$t('imp.confirm', { url: url.trim() })}</p>
  <div class="acts">
    <button class="btn primary" onclick={() => start(false)}>{$t('imp.go')}</button>
    <button class="btn" onclick={() => (confirm = false)}>{$t('action.cancel')}</button>
  </div>
</Dialog>

<style>
  header { margin-bottom: 10px; }
  h2 { font-size: 1rem; font-weight: 600; color: var(--heading); }
  h3 { font-size: 0.875rem; font-weight: 600; color: var(--heading); }
  .cred { font-size: 0.875rem; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
  .credacts { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 8px; }
  .credf { margin-top: 12px; padding: 14px; border: 1px dashed var(--line-strong); border-radius: 12px; display: flex; flex-direction: column; gap: 4px; max-width: 560px; }
  label { font-size: 0.8125rem; color: var(--kpi-label); margin-top: 10px; }
  .lbl { display: block; margin-top: 18px; }
  input { width: 100%; border-radius: 12px; min-height: var(--touch); font-size: 0.9375rem; }
  .url { font-family: var(--mono, ui-monospace, monospace); max-width: 720px; display: block; margin-top: 4px; }
  .small { font-size: 0.75rem; margin-top: 6px; }
  .acts { display: flex; gap: 10px; flex-wrap: wrap; margin-top: 12px; }
  .acts .btn { min-height: var(--touch); }
  .err { color: var(--err); font-size: 0.875rem; margin-top: 10px; }
  .warnline { color: var(--warn); }
  .sum { font-size: 0.875rem; margin-top: 12px; }
  .ok { color: var(--ok); font-weight: 600; }
  .prog { height: 8px; border-radius: 999px; background: var(--bg2); overflow: hidden; margin-top: 14px; border: 1px solid var(--line); max-width: 720px; }
  .fill { height: 100%; background: linear-gradient(90deg, var(--accent), var(--violet)); transition: width 0.4s; }
  .fill.indet { width: 35%; animation: slide 1.4s ease-in-out infinite; }
  @keyframes slide { from { transform: translateX(-100%); } to { transform: translateX(300%); } }
  @media (prefers-reduced-motion: reduce) { .fill.indet { animation: none; width: 100%; opacity: 0.5; } }
  .objs { margin-top: 10px; font-size: 0.8125rem; }
  .objs summary { cursor: pointer; min-height: var(--touch); display: flex; align-items: center; color: var(--accent-text); font-weight: 600; }
  .objs ul { list-style: none; display: grid; gap: 4px; max-height: 320px; overflow: auto; }
  .objs code { word-break: break-all; }
  .msg { max-width: 360px; white-space: normal; }
</style>
