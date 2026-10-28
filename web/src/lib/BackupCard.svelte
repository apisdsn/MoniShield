<!-- "Backup" card on the Ingest & import screen (owner request 2026-10-27; API monishield/interfaces/api/admin.py /backup).
     Shows the schedule (S4_BACKUP_*), the next run, the last result (with the error when it failed), the backups on disk,
     and a "Back up now" button. Backups cover both sources and the account database, so the card ignores the source switch. -->
<script>
  import { onMount } from 'svelte';
  import { lang, t } from '../i18n.js';
  import { api } from '../api.js';
  import { num, bytes, dLabel, tWIB, utcToWib } from '../format.js';
  import { errText } from '../srv.js';
  import { toast } from './Toast.svelte';
  import SeverityTag from './SeverityTag.svelte';

  let { onfinished = null } = $props();
  let s = $state.raw(null), err = $state(null), busy = $state(false);

  async function load() { try { s = await api.get('/api/admin/backup'); err = null; } catch (e) { err = $errText(e); } }
  onMount(() => {
    load();
    const iv = setInterval(() => { if (!document.hidden && (s?.running || busy)) load(); }, 3000);
    return () => clearInterval(iv);
  });

  async function run() {
    busy = true;
    try {
      s = await api.post('/api/admin/backup/run', {});
      toast($t('bk.done', { day: dLabel(s.last.day, $lang), size: bytes(s.last.bytes, $lang) }));
    } catch (e) { toast($errText(e)); await load(); }
    finally { busy = false; onfinished?.(); }
  }
  const when = (x) => (x ? tWIB(utcToWib(x), $lang) : '—');
</script>

<section class="card wide bk" aria-labelledby="bk-h">
  <header>
    <h2 id="bk-h">{$t('bk.title')}</h2>
    <button class="btn" onclick={run} disabled={busy || s?.running}>{busy || s?.running ? $t('bk.running') : $t('bk.now')}</button>
  </header>
  {#if err}<p class="err small" role="alert">{err}</p>
  {:else if !s}<p class="muted small">{$t('state.loading')}</p>
  {:else}
    <p class="small">
      {#if s.enabled}{$t('bk.schedule', { h: String(s.hour).padStart(2, '0'), keep: num(s.keep, $lang), dir: s.dir })}
      {:else}<b>{$t('bk.off')}</b>{/if}
    </p>
    <dl class="nums">
      {#if s.enabled}<div><dt>{$t('bk.next')}</dt><dd>{when(s.next)}</dd></div>{/if}
      <div>
        <dt>{$t('bk.last')}</dt>
        <dd>
          {#if s.last}
            {when(s.last.at)} <SeverityTag level={s.last.ok ? 'ok' : 3} text={s.last.ok ? $t('bk.ok') : $t('bk.fail')} />
          {:else if s.backups.length}{when(s.backups[0].finished)}{:else}—{/if}
        </dd>
      </div>
    </dl>
    <div aria-live="polite">
      {#if s.last && !s.last.ok}<p class="err small" role="alert">{$errText({ message: s.last.error })}</p>{/if}
      {#if s.last?.uploaded}<p class="muted xs">{$t('bk.copied', { to: s.last.uploaded })}</p>{/if}
    </div>
    {#if !s.backups.length}<p class="muted small">{$t('bk.none')}</p>
    {:else}
      <details class="list">
        <summary>{$t('bk.list', { n: num(s.backups.length, $lang) })}</summary>
        <div class="scroll">
          <table>
            <thead><tr><th>{$t('bk.col.day')}</th><th>{$t('bk.col.size')}</th><th>{$t('bk.col.files')}</th><th class="wide-only">{$t('bk.col.finished')}</th></tr></thead>
            <tbody>
              {#each s.backups as b}
                <tr><td class="nowrap">{dLabel(b.day, $lang)}</td><td class="nowrap">{bytes(b.bytes, $lang)}</td>
                  <td>{b.files.map((f) => f.split('.')[0]).join(', ')}</td><td class="nowrap wide-only">{when(b.finished)}</td></tr>
              {/each}
            </tbody>
          </table>
        </div>
      </details>
    {/if}
    <p class="muted xs">{$t('bk.hint')}</p>
  {/if}
</section>

<style>
  header { display: flex; align-items: center; justify-content: space-between; gap: 10px; flex-wrap: wrap; margin-bottom: 6px; }
  header .btn { min-height: var(--touch); }
  h2 { font-size: 1rem; font-weight: 600; color: var(--heading); }
  .small { font-size: 0.8125rem; margin-top: 4px; } .xs { font-size: 0.75rem; margin-top: 8px; }
  .nums { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 10px; margin: 12px 0 4px; }
  .nums div { border: 1px solid var(--line); border-radius: 12px; padding: 8px 10px; }
  dt { font-size: 0.75rem; color: var(--kpi-label); }
  dd { font-size: 0.875rem; font-weight: 600; margin: 2px 0 0; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
  .list { margin-top: 10px; font-size: 0.8125rem; }
  .list summary { cursor: pointer; min-height: var(--touch); display: flex; align-items: center; color: var(--accent-text); font-weight: 600; }
  .scroll { overflow-x: auto; }
  table { width: 100%; border-collapse: collapse; margin-top: 6px; }
  th, td { text-align: left; padding: 6px 8px; border-bottom: 1px solid var(--line); vertical-align: top; }
  th { font-size: 0.75rem; color: var(--kpi-label); font-weight: 600; }
  .nowrap { white-space: nowrap; }
  @media (max-width: 560px) { .wide-only { display: none; } }
  .path { word-break: break-all; }
  .err { color: var(--err); }
</style>
