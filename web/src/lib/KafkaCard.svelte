<!-- Kartu "Log dari Kafka" (permintaan pemilik 2026-10-07: "bagaimana cara mengecek hasil logging dari Kafka? bisa dibuat
     seperti logging yang sekarang?"; API monishield/api/kafka.py). Menampilkan status konsumen (tersambung / galat),
     pesan diterima, ditulis ke folder, dilewati (+ alasan contoh), per layanan, ingest terakhir, dan 50 pesan terakhir.
     "Cek pesan di topic" mengambil pesan TERAKHIR langsung dari Kafka (tanpa menggeser posisi baca) dan menunjukkan file
     tujuan masing-masing — cara memastikan format Rancher terbaca sebelum/tanpa menunggu ingest.
     Dipakai di layar Ingest & impor dan di bagian Kafka layar Konfigurasi (`compact`). -->
<script>
  import { onMount } from 'svelte';
  import { lang, t } from '../i18n.js';
  import { api } from '../api.js';
  import { num, tWIB, utcToWib } from '../format.js';
  import { errText } from '../srv.js';
  import { toast } from './Toast.svelte';
  import SeverityTag from './SeverityTag.svelte';

  let { compact = false } = $props();
  let s = $state.raw(null), err = $state(null), peek = $state.raw(null), peekErr = $state(null), busy = $state('');

  export async function load() { try { s = await api.get('/api/admin/kafka'); err = null; } catch (e) { err = $errText(e); } }
  onMount(() => { load(); const iv = setInterval(() => { if (!document.hidden) load(); }, 5000); return () => clearInterval(iv); });

  async function doPeek() {
    busy = 'peek'; peekErr = null; peek = null;
    try { peek = await api.post('/api/admin/kafka/peek', { n: 10 }); } catch (e) { peekErr = $errText(e); } finally { busy = ''; }
  }
  async function ingestNow() {
    busy = 'ingest';
    try { await api.post('/api/admin/kafka/ingest', {}); toast($t('kf.ingest_started')); setTimeout(load, 800); } catch (e) { toast($errText(e)); } finally { busy = ''; }
  }
  const STATE = { running: ['ok', 'kf.st.running'], connecting: [1, 'kf.st.connecting'], error: [3, 'kf.st.error'], off: [1, 'kf.st.off'] };
  const when = (x) => (x ? tWIB(utcToWib(x.replace('T', ' ')), $lang) : '—');
  const svc = $derived(s ? Object.entries(s.per_service).sort((a, b) => b[1] - a[1]) : []);
</script>

<section class="card wide kf" class:compact aria-labelledby="kf-h">
  <header>
    <h2 id="kf-h">{$t('kf.title')}</h2>
    {#if s}{@const st = STATE[s.state] || STATE.off}<SeverityTag level={st[0]} text={$t(st[1])} />{/if}
  </header>
  {#if err}<p class="err" role="alert">{err}</p>
  {:else if !s}<p class="muted small">{$t('state.loading')}</p>
  {:else if !s.configured}
    <p class="muted small">{$t('kf.not_configured')}</p>
  {:else}
    <p class="small">{$t('kf.source', { topic: s.topic, brokers: s.brokers })}{#if !s.enabled} · <b>{$t('kf.disabled')}</b>{/if}</p>
    {#if s.error}<p class="err small" role="alert">{$errText(s.error)}</p>{/if}
    <dl class="nums">
      <div><dt>{$t('kf.received')}</dt><dd>{num(s.received, $lang)}</dd></div>
      <div><dt>{$t('kf.written')}</dt><dd>{num(s.written, $lang)}</dd></div>
      <div><dt>{$t('kf.skipped')}</dt><dd class:warn={s.skipped}>{num(s.skipped, $lang)}</dd></div>
      <div><dt>{$t('kf.last_msg')}</dt><dd class="sm">{when(s.last_message_at)}</dd></div>
      <div><dt>{$t('kf.last_ingest')}</dt><dd class="sm">{when(s.last_ingest_at)}</dd></div>
      <div><dt>{$t('kf.live_folder')}</dt><dd class="sm">{s.live_folder}</dd></div>
    </dl>
    <p class="muted xs">{$t('kf.folder_note', { m: s.ingest_minutes })}</p>
    {#if s.last_skip}<p class="warnline xs">{$t('kf.skip_reason', { why: s.last_skip.reason })} <code>{s.last_skip.sample}</code></p>{/if}
    {#if svc.length && !compact}
      <ul class="svc">{#each svc as [k, n]}<li><code>{k}</code> <span class="muted">{num(n, $lang)}</span></li>{/each}</ul>
    {/if}
    <div class="acts">
      <button class="btn" onclick={doPeek} disabled={busy !== ''}>{busy === 'peek' ? $t('kf.peeking') : $t('kf.peek')}</button>
      {#if s.pending.length}<button class="btn" onclick={ingestNow} disabled={busy !== ''}>{$t('kf.ingest_now', { list: s.pending.join(', ') })}</button>{/if}
    </div>
    <div aria-live="polite">
      {#if peekErr}<p class="err small" role="alert">{peekErr}</p>{/if}
      {#if peek}
        <p class="small">{$t('kf.peek_sum', { n: num(peek.messages.length, $lang), topic: peek.topic, p: peek.partitions, total: num(peek.messages_retained, $lang) })}</p>
        {#if !peek.messages.length}<p class="muted small">{$t('kf.peek_empty')}</p>{/if}
        <ol class="msgs">
          {#each peek.messages as m}
            <li>
              <div class="meta"><SeverityTag level={m.ok ? 'ok' : 3} text={m.ok ? $t('kf.ok') : $t('kf.bad')} />
                <span class="muted xs">{when(m.at)} · p{m.partition}#{m.offset}</span></div>
              {#if m.ok}<div class="xs">→ <code>{m.target}</code></div>{:else}<div class="xs warnline">{m.reason}</div>{/if}
              <pre>{m.raw}</pre>
            </li>
          {/each}
        </ol>
      {/if}
    </div>
    {#if s.recent.length && !compact}
      <details class="recent">
        <summary>{$t('kf.recent', { n: num(s.recent.length, $lang) })}</summary>
        <ol>{#each s.recent as r}<li><span class="muted xs">{when(r.at)} · {r.ns}/{r.svc}/{r.pod}</span><pre>{r.line}</pre></li>{/each}</ol>
      </details>
    {/if}
  {/if}
</section>

<style>
  header { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-bottom: 6px; }
  h2 { font-size: 1rem; font-weight: 600; color: var(--heading); }
  .compact { box-shadow: none; border: 1px solid var(--line); margin-top: 14px; }
  .small { font-size: 0.8125rem; margin-top: 4px; } .xs { font-size: 0.75rem; margin-top: 4px; }
  .nums { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 10px; margin: 12px 0 4px; }
  .nums div { border: 1px solid var(--line); border-radius: 12px; padding: 8px 10px; }
  dt { font-size: 0.75rem; color: var(--kpi-label); }
  dd { font-size: 1.15rem; font-weight: 600; margin: 2px 0 0; } dd.sm { font-size: 0.875rem; } dd.warn { color: var(--warn); }
  .svc { list-style: none; padding: 0; margin: 8px 0 0; display: flex; flex-wrap: wrap; gap: 6px 16px; font-size: 0.8125rem; }
  .acts { display: flex; gap: 10px; flex-wrap: wrap; margin-top: 12px; } .acts .btn { min-height: var(--touch); }
  .msgs, .recent ol { list-style: none; padding: 0; margin: 10px 0 0; display: grid; gap: 8px; max-height: 420px; overflow: auto; }
  .msgs li, .recent li { border: 1px solid var(--line); border-radius: 10px; padding: 8px 10px; min-width: 0; }
  .meta { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
  pre { margin: 6px 0 0; font-size: 0.75rem; white-space: pre-wrap; word-break: break-all; font-family: var(--mono, ui-monospace, monospace); color: var(--fg); }
  code { font-size: 0.75rem; word-break: break-all; }
  .recent { margin-top: 12px; font-size: 0.8125rem; }
  .recent summary { cursor: pointer; min-height: var(--touch); display: flex; align-items: center; color: var(--accent-text); font-weight: 600; }
  .err { color: var(--err); } .warnline { color: var(--warn); }
</style>
