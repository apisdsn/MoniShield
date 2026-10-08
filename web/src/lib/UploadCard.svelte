<!-- "Unggah folder log" card on the Ingest & import screen (owner request 2026-10-07; API monishield/api/upload.py).
     Choose a folder on the computer (a YYYY-MM-DD date folder, its parent, or one date's contents + its date) -> the server
     checks the file list (non-logs skipped, same size limit as S3 import) -> summary -> "Unggah": files
     sent one by one (3 at a time) with progress -> the server moves them to the inbox and runs ingest. -->
<script>
  import { srv, errText } from '../srv.js';
  import { lang, t } from '../i18n.js';
  import { api } from '../api.js';
  import { num, bytes } from '../format.js';
  import { toast } from './Toast.svelte';
  import DatePicker from './DatePicker.svelte';

  let { onfinished = null } = $props();
  let input = $state(), files = $state.raw([]), folder = $state(''), plan = $state.raw(null), err = $state(null);
  let busy = $state(false), sent = $state(0), total = $state(0), done = $state.raw(null), ctl = null;

  const why = (e) => $errText(e);
  const MB = (n) => bytes(n ?? 0, $lang);

  async function pick() {
    files = [...(input?.files || [])]; done = null;
    await cancel(true);
    if (files.length) await check();
  }
  async function check() {
    err = null; busy = true;
    try {
      plan = await api.post('/api/admin/upload', { files: files.map((f) => ({ path: f.webkitRelativePath || f.name, size: f.size })), folder: folder.trim() });
    } catch (e) { plan = null; err = why(e); }
    finally { busy = false; }
  }
  async function cancel(quiet = false) {
    ctl?.abort(); ctl = null;
    if (plan?.upload_id) { try { await api.del(`/api/admin/upload/${plan.upload_id}`); } catch { /* already expired */ } }
    plan = null; sent = 0; total = 0;
    if (!quiet) { files = []; if (input) input.value = ''; }
  }
  async function go() {
    err = null; busy = true; sent = 0; total = plan.bytes; ctl = new AbortController();
    const part = new Map(), queue = [...plan.files];
    const bump = () => { sent = [...part.values()].reduce((a, b) => a + b, 0); };
    try {
      await Promise.all([0, 1, 2].map(async () => {
        for (let o = queue.shift(); o; o = queue.shift()) {
          await api.putFile(`/api/admin/upload/${plan.upload_id}/${o.i}`, files[o.i], (n) => { part.set(o.i, n); bump(); }, ctl.signal);
          part.set(o.i, o.size); bump();
        }
      }));
      const r = await api.post(`/api/admin/upload/${plan.upload_id}/finish`, {});
      done = r; plan = null; files = []; if (input) input.value = '';
      toast($t('up.toast', { n: num(r.files, $lang), list: r.folders.join(', ') }));
      onfinished?.();
    } catch (e) {
      if (e.code !== 'aborted') { err = why(e); ctl?.abort(); }
    } finally { busy = false; ctl = null; }
  }
  const pct = $derived(total ? Math.min(100, Math.round((sent / total) * 100)) : 0);
  const uploading = $derived(busy && total > 0);
</script>

<section class="card wide up" aria-labelledby="up-h">
  <header><h2 id="up-h">{$t('up.title')}</h2></header>
  <p class="muted small">{$t('up.hint')}</p>
  <div class="row">
    <label class="btn primary pickbtn" class:disabled={busy}>
      <input bind:this={input} id="up-dir" type="file" webkitdirectory multiple onchange={pick} disabled={busy} />
      {$t('up.pick')}
    </label>
    <div class="date">
      <label for="up-date">{$t('up.date')}</label>
      <DatePicker id="up-date" bind:value={folder} disabled={busy} onchange={async () => { if (files.length && !uploading) { await cancel(true); check(); } }} />
    </div>
  </div>
  <p class="muted small">{$t('up.date_hint')}</p>

  <div aria-live="polite">
    {#if busy && !uploading}<p class="muted small">{$t('up.checking', { n: num(files.length, $lang) })}</p>{/if}
    {#if err}<p class="err" role="alert">{err}</p>{/if}
    {#if plan}
      <p class="sum">{$t('up.plan', { n: num(plan.files.length, $lang), size: MB(plan.bytes), list: plan.folders.join(', ') })}
        {#if plan.skipped_count}{' '}{$t('up.skipped', { n: num(plan.skipped_count, $lang) })}{/if}</p>
      {#if plan.skipped_count}
        <details class="objs">
          <summary>{$t('up.skipped_list', { n: num(plan.skipped_count, $lang) })}</summary>
          <ul>{#each plan.skipped as s}<li><code>{s.path}</code> <span class="muted">· {$srv(s.reason)}</span></li>{/each}</ul>
        </details>
      {/if}
      {#if uploading}
        <div class="prog" role="progressbar" aria-label={$t('up.title')} aria-valuemin="0" aria-valuemax="100" aria-valuenow={pct}>
          <div class="fill" style={`width:${pct}%`}></div>
        </div>
        <p class="muted small">{$t('up.sending', { done: MB(sent), total: MB(total), pct })}</p>
      {/if}
      <div class="acts">
        <button class="btn primary" onclick={go} disabled={busy}>{$t('up.go', { n: num(plan.files.length, $lang) })}</button>
        <button class="btn" onclick={() => cancel()}>{$t('action.cancel')}</button>
      </div>
    {/if}
    {#if done}
      <p class="sum ok">{$t('up.done', { n: num(done.files, $lang), size: MB(done.bytes), list: done.folders.join(', ') })}{#if done.extracted}{' '}{$t('imp.res.extracted', { n: num(done.extracted, $lang) })}{/if}</p>
    {/if}
  </div>
</section>

<style>
  header { margin-bottom: 6px; }
  h2 { font-size: 1rem; font-weight: 600; color: var(--heading); }
  .small { font-size: 0.75rem; margin-top: 6px; }
  .row { display: flex; gap: 16px; align-items: flex-end; flex-wrap: wrap; margin-top: 12px; }
  .pickbtn { min-height: var(--touch); display: inline-flex; align-items: center; cursor: pointer; position: relative; }
  .pickbtn input { position: absolute; inset: 0; opacity: 0; cursor: pointer; width: 100%; }
  .pickbtn:focus-within { outline: 2px solid var(--accent); outline-offset: 2px; }
  .pickbtn.disabled { opacity: 0.55; pointer-events: none; }
  .date { display: flex; flex-direction: column; gap: 4px; }
  .date label { font-size: 0.8125rem; color: var(--kpi-label); }
  .sum { font-size: 0.875rem; margin-top: 12px; }
  .ok { color: var(--ok-text); }
  .err { color: var(--err); font-size: 0.875rem; margin-top: 10px; }
  .acts { display: flex; gap: 10px; flex-wrap: wrap; margin-top: 12px; }
  .acts .btn { min-height: var(--touch); }
  .prog { height: 8px; border-radius: 999px; background: var(--bg2); overflow: hidden; margin-top: 14px; border: 1px solid var(--line); max-width: 720px; }
  .fill { height: 100%; background: linear-gradient(90deg, var(--accent), var(--violet)); transition: width 0.3s; }
  .objs { margin-top: 10px; font-size: 0.8125rem; }
  .objs summary { cursor: pointer; min-height: var(--touch); display: flex; align-items: center; color: var(--accent-text); font-weight: 600; }
  .objs ul { list-style: none; display: grid; gap: 4px; max-height: 260px; overflow: auto; }
  .objs code { word-break: break-all; }
</style>
