<!-- Volume band (owner choice 2026-10-28, mockup "Volume B"): the day's total log lines and HTTP requests, large, at the top of
     the folder-wide analysis pages (not on a service or IP page: their own numbers would read as contradicting it; the labels
     name the scope), each with the last 7 days as small bars (the shown day highlighted) so a short or missing day stands out.
     Data: the folder list of /api/meta (lines, requests per folder) and the folder summary (files, 4xx/5xx of nginx-ingress).
     The bars are decoration for sighted users; the same facts are in the text and in each bar's title. -->
<script>
  import { lang, t } from '../i18n.js';
  import { num, fLabel } from '../format.js';
  let { folders = [], folder, summary = null } = $props();
  const NG = 'nginx-ingress-controller';

  const info = $derived(folders.find((f) => f.folder === folder) || null);
  // the shown day and the six before it, oldest first (folders: newest first)
  const week = $derived.by(() => {
    const i = folders.findIndex((f) => f.folder === folder);
    return i < 0 ? [] : folders.slice(i, i + 7).reverse();
  });
  const ng = $derived(summary?.folder === folder ? summary.services.find((s) => s.service === NG && s.lines) : null);
  const req = $derived(info?.requests ?? ng?.requests ?? null);
  const rate = (n, digits) => `${num((n / req) * 100, $lang, digits)}%`;
  function bars(key) {
    const max = Math.max(...week.map((f) => f[key] || 0), 1);
    return week.map((f) => ({ h: Math.max(4, Math.round(((f[key] || 0) / max) * 100)), now: f.folder === folder,
                              tip: `${fLabel(f.folder, $lang)}: ${f[key] == null ? '–' : num(f[key], $lang)}` }));
  }
</script>

{#if info}
  <section class="vb" aria-label={$t('vb.label')}>
    <div class="cell">
      <div class="txt">
        <span class="l">{$t('kpi.lines')} <span class="scope">· {$t('vb.scope')}</span></span>
        <span class="v">{num(info.lines, $lang)}</span>
        <span class="s">{$t('vb.files', { files: num(info.files, $lang), svc: num(info.services, $lang), empty: num(info.files_empty, $lang), corrupt: num(info.files_corrupt, $lang) })}</span>
      </div>
      {#if week.length > 1}
        <div class="spark" title={$t('vb.days')}>
          <div class="bars" aria-hidden="true">{#each bars('lines') as b}<span class:now={b.now} style="height:{b.h}%" title={b.tip}></span>{/each}</div>
          <span class="days">{$t('vb.days')}</span>
        </div>
      {/if}
    </div>
    <div class="cell">
      <div class="txt">
        <span class="l">{$t('kpi.http')} <span class="scope">· {$t('vb.scope_http')}</span></span>
        <span class="v" class:none={req == null}>{req == null ? '–' : num(req, $lang)}</span>
        <span class="s">{req == null ? $t('ov.no_nginx') : ng ? $t('vb.rates', { r4: rate(ng.n4xx, 1), r5: rate(ng.n5xx, 2) }) : ''}</span>
      </div>
      {#if week.length > 1 && req != null}
        <div class="spark" title={$t('vb.days')}>
          <div class="bars req" aria-hidden="true">{#each bars('requests') as b}<span class:now={b.now} style="height:{b.h}%" title={b.tip}></span>{/each}</div>
          <span class="days">{$t('vb.days')}</span>
        </div>
      {/if}
    </div>
  </section>
{/if}

<style>
  .vb {
    display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); margin-bottom: 16px;
    background: var(--card-bg); border: 1px solid var(--card-border); border-radius: var(--r-card); box-shadow: var(--glow);
  }
  .cell { display: flex; align-items: center; gap: 20px; padding: 18px 24px; min-width: 0; }
  .cell + .cell { border-left: 1px solid var(--line); }
  .txt { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 4px; }
  .l { font-size: 0.875rem; font-weight: 500; color: var(--kpi-label); }
  .scope { font-weight: 400; color: var(--muted); }
  .v { font-size: 2.75rem; font-weight: 600; line-height: 1.1; font-variant-numeric: tabular-nums; letter-spacing: -0.01em; color: var(--fg); overflow-wrap: anywhere; }
  .v.none { color: var(--muted); }
  .s { font-size: 0.75rem; color: var(--muted); }
  .spark { display: flex; flex-direction: column; align-items: flex-end; gap: 6px; flex: none; }
  .bars { display: flex; align-items: flex-end; gap: 4px; height: 44px; }
  .bars span { width: 10px; border-radius: 2px; background: var(--line-strong); opacity: 0.45; }
  .bars span.now { background: var(--c1); opacity: 1; }
  .bars.req span.now { background: var(--c2); }
  .days { font-size: 0.6875rem; color: var(--muted); }
  @media (max-width: 900px) {
    .vb { grid-template-columns: minmax(0, 1fr); }
    .cell { padding: 14px 16px; }
    .cell + .cell { border-left: 0; border-top: 1px solid var(--line); }
    .v { font-size: 2rem; }
  }
</style>
