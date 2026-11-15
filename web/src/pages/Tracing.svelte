<!-- Request Tracing (DRD §3.9, inv. §2.9): 6 KPIs, notes, 2 charts, table of failed/slow nginx → application traces.
     One request: GET /api/v1/folders/{folder}/tracing. Changed from the old one: traces are not truncated at 300 (TRD §4.4 item 1;
     KPIs and charts computed from all traces, table shows the first 300 + "show more"); "slow ≥ 5 s" includes
     all statuses except failed (item 9). ASSUMPTION: with no matching request at all (matched = 0) a note is shown,
     not a page full of zeros like the old one (DRD §6.6). -->
<script>
  import { srv, errText } from '../srv.js';
  import { lang, t } from '../i18n.js';
  import { api } from '../api.js';
  import { num, durMs } from '../format.js';
  import Kpi from '../lib/Kpi.svelte';
  import HBar from '../lib/HBar.svelte';
  import DataTable from '../lib/DataTable.svelte';
  import AttackUrl from '../lib/AttackUrl.svelte';
  import Note from '../lib/Note.svelte';
  import { build } from '../state.js';
  import { formatName } from '../anyfmt.js';
  import AnalysisInfo from '../lib/AnalysisInfo.svelte';
  import CopyBlock from '../lib/CopyBlock.svelte';
  import SeverityTag from '../lib/SeverityTag.svelte';
  import Skeleton from '../lib/Skeleton.svelte';
  import ErrorState from '../lib/ErrorState.svelte';

  let { folder, hosts = {}, reloadKey = 0, onready = null, admin = false } = $props();
  let data = $state.raw(null), busy = $state(false), error = $state(null);
  let seq = 0;
  async function load() {
    const my = ++seq;
    busy = true; error = null; onready?.(false);
    try {
      const j = await api.get(`/api/v1/folders/${encodeURIComponent(folder)}/tracing`);
      if (my === seq) data = j;
    } catch (e) {
      if (my === seq) error = e;
    } finally {
      if (my === seq) { busy = false; onready?.(true); }
    }
  }
  $effect(() => { void [folder, reloadKey]; if (folder) load(); });

  const pct1 = (a, b) => (b ? `${num((a / b) * 100, $lang, 1)}%` : '-');
  // stage 62: any source, matched by the request ID that the access log and an application log both write
  const rawHref = (id) => build({ tab: 'raw-logs', service: null, folder, module: null, q: id, svc: null, pod: null });
  const short = (id) => (id.length > 14 ? `${id.slice(0, 6)}…${id.slice(-4)}` : id);
  const CADDY = ['example.com {', '  request_header X-Request-ID {http.request.uuid}', '  log_append request_id {http.request.uuid}', '  log', '  reverse_proxy app:8000', '}'];
  const APP = ['# any framework: read the header, add it to the line', 'rid = request.headers.get("X-Request-ID")', 'log.info("saved order", extra={"request_id": rid})',
               '# JSON line: {"level":"info","request_id":"7f3a…","msg":"saved order"}'];
  const SAMPLE = [['7f3a…c21e', 'POST', '/api/v1/collector/logs', 200, 120, 'ok'], ['b19d…04aa', 'GET', '/api/v1/overview', 502, 1400, 'timeout'], ['c2e8…9f10', 'GET', '/api/v1/servers', 200, 84, 'ok']];
  const appWith = (g) => Object.values(g.ids.app).reduce((a, v) => a + v[0], 0);
  // long URLs truncated to 200 characters (old); full text in the cell tooltip
  const cut200 = (s) => (s.length > 200 ? s.slice(0, 199) + '…' : s);
</script>

{#if error && !data}
  <ErrorState {error} onretry={load} />
{:else if !data}
  <Skeleton kpis={6} charts={2} />
{:else if !data.available}
  <Note>{$t(data.reason === 'no_events_service' ? 'any.trc.none' : 'trc.none')}{#if admin} <a href={build({ tab: 'admin/log-formats', service: null, q: null })}>{$t('nav.cfg.logformats')}</a> · <a href={build({ tab: 'admin/analysis', service: null, q: null })}>{$t('nav.cfg.analysis')}</a>{/if}</Note>
{:else if data.mode === 'generic'}
  {@const ids = data.ids}
  <div class="content" class:dim={busy}>
    <AnalysisInfo {admin} text={$t(data.matched ? 'any.trc.info' : 'any.trc.info_none', { access: data.access.service, apps: data.app_logs.join(', ') || '–', field: data.field === 'auto' ? $t('any.trc.field_auto') : data.field })} />
    {#if data.matched}
      <div class="kpis four">
        <Kpi icon="route" label={$t('any.trc.kpi.traced')} value={data.kpi.traced} />
        <Kpi icon="file" label={$t('any.trc.kpi.with_id')} value={data.kpi.with_id} caption={data.access.service} />
        <Kpi icon="pulse" label={$t('trc.kpi.rate')} value={pct1(data.kpi.traced, data.kpi.with_id)} />
        <Kpi icon="alert" label={$t('any.trc.kpi.failed')} value={data.kpi.failed} tone="err" info={$t('any.trc.kpi.failed_info')} />
      </div>
      <DataTable title={$t('any.trc.table')} rows={data.traced} limit={50} columns={[
        { key: 'id', label: $t('any.trc.col.id'), custom: true, sort: true, minw: 130 },
        { key: 'path', label: $t('col.endpoint'), custom: true, minw: 240 },
        { key: 'status', label: $t('col.status'), type: 'status', sort: true },
        { key: 'ms', label: $t('any.trc.col.duration'), type: 'dur', sort: true },
        { key: 'services', label: $t('any.trc.col.services'), custom: true, minw: 200 },
      ]}>
        {#snippet cell(r, c)}
          {#if c.key === 'id'}<a class="mono open" href={rawHref(r.id)} title={r.id}>{short(r.id)}</a>
          {:else if c.key === 'path'}<span class="mono">{[r.method, r.path].filter(Boolean).join(' ')}</span>
          {:else}<span>{[data.access.service, ...r.services].join(' → ')}</span>{#if r.errors} <SeverityTag level={3} text={$t('any.trc.with_errors')} />{/if}{/if}
        {/snippet}
      </DataTable>
    {:else}
      <section class="card setup">
        <h2>{$t('any.trc.setup_title')}</h2>
        <p class="muted">{$t('any.trc.setup_text')}</p>
        <div class="tiles">
          <div class="tile">
            <p class="th"><span class="st {ids.access[0] ? 'ok' : 'miss'}">{$t(ids.access[0] ? 'any.trc.ready' : 'any.trc.missing')}</span><b>{$t('any.trc.access_log')}</b></p>
            <p class="muted small">{$t('any.trc.tile_lines', { svc: data.access.service, n: num(ids.access[0], $lang), m: num(ids.access[1], $lang) })}</p>
          </div>
          <div class="tile">
            <p class="th"><span class="st {appWith(data) ? 'ok' : 'miss'}">{$t(appWith(data) ? 'any.trc.ready' : 'any.trc.missing')}</span><b>{$t('any.trc.app_log')}</b></p>
            {#each Object.entries(ids.app) as [svc, v]}<p class="muted small">{$t('any.trc.tile_lines', { svc, n: num(v[0], $lang), m: num(v[1], $lang) })}</p>{:else}<p class="muted small">{$t('any.trc.no_app')}</p>{/each}
          </div>
          <div class="tile">
            <p class="th"><span class="st ok">{$t('any.trc.ready')}</span><b>{$t('nav.cfg.logformats')}</b></p>
            <p class="muted small">{$t('any.trc.tile_formats', { fmt: formatName(data.access.format), ids: data.id_fields.slice(0, 4).join(', ') })}</p>
          </div>
        </div>
        <div class="code">
          <div><h3>{$t('any.trc.step1')}</h3><CopyBlock lines={CADDY} label={$t('any.trc.step1')} /></div>
          <div><h3>{$t('any.trc.step2')}</h3><CopyBlock lines={APP} label={$t('any.trc.step2')} /></div>
        </div>
        <p class="muted small">{$t('any.trc.nginx')}</p>
        <p class="muted small">{$t('any.trc.new_lines')}</p>
      </section>
      <section class="card preview" aria-label={$t('any.trc.preview_title')}>
        <div class="ph"><h2>{$t('any.trc.preview_title')}</h2><span class="muted small">{$t('any.trc.preview_note')}</span></div>
        <div class="pt" role="table" aria-label={$t('any.trc.preview_title')}>
          <div class="pr h" role="row"><span role="columnheader">{$t('any.trc.col.id')}</span><span role="columnheader">{$t('col.endpoint')}</span><span class="r" role="columnheader">{$t('col.status')}</span>
            <span class="r" role="columnheader">{$t('any.trc.col.duration')}</span><span role="columnheader">{$t('any.trc.col.services')}</span></div>
          {#each SAMPLE as r}
            <div class="pr" role="row"><span class="mono" role="cell">{r[0]}</span><span class="mono" role="cell">{r[1]} {r[2]}</span><span class="r" class:bad={r[3] >= 500} role="cell">{r[3]}</span>
              <span class="r" role="cell">{durMs(r[4], $lang)}</span><span role="cell">{$t(r[5] === 'ok' ? 'any.trc.sample_ok' : 'any.trc.sample_timeout')}</span></div>
          {/each}
        </div>
      </section>
    {/if}
  </div>
{:else if !data.corr.matched}
  <Note>{$t('trc.none')}</Note>
{:else}
  {@const k = data.kpi}
  {@const c = data.corr}
  <div class="content" class:dim={busy}>
    <div class="kpis">
      <Kpi icon="route" label={$t('trc.kpi.total')} value={c.total} />
      <Kpi icon="route" label={$t('trc.kpi.matched')} value={c.matched} />
      <Kpi icon="pulse" label={$t('trc.kpi.rate')} value={pct1(c.matched, c.total)} />
      <Kpi icon="alert" label={$t('trc.kpi.failed')} value={k.failed_requests} tone="err" />
      <Kpi icon="globe" label={$t('trc.kpi.failed_ips')} value={k.failed_ips} tone="warn" />
      <Kpi icon="clock" label={$t('trc.kpi.slow')} value={k.slow_requests} tone="warn" info={$t('trc.kpi.slow_info')} />
    </div>
    <Note>{$t('trc.note', { pct: pct1(c.total - c.matched, c.total) })}</Note>
    <div class="grid">
      {#if data.by_ip.length}
        <HBar title={$t('trc.ip_chart')} rows={data.by_ip.map((r) => ({ label: r.ip, value: r.n, org: r.org }))} color="--err" valueLabel={$t('trc.kpi.failed')} />
      {/if}
      {#if data.by_error.length}
        <HBar title={$t('trc.err_chart')} rows={data.by_error.map(([l, n]) => ({ label: $srv(l), value: n }))} color="--warn" valueLabel={$t('col.request')} />
      {/if}
      <DataTable title={$t('trc.t.trace')} {folder} table="trace" initial={data.tables.trace} columns={[
        { key: 'client', label: 'IP', type: 'ip', sort: true },
        { key: 'status', label: $t('col.status'), type: 'status', sort: true },
        { key: 'error', label: 'Error', fmt: (r) => $srv(r.error), cls: () => 'small', sort: true, minw: 150 },
        { key: 'url', label: $t('trc.col.url'), custom: true, minw: 320 },
        { key: 'n', label: $t('table.count'), type: 'num', sort: true },
        { key: 'max_ms', label: $t('trc.col.max'), type: 'dur', sort: true },
        { key: 'first', label: $t('col.time'), type: 'range', to: 'last', sort: true, minw: 130 },
      ]}>
        {#snippet cell(r)}<span title={r.url}><AttackUrl methodPath={cut200(r.url)} upstreams={[r.upstream]} ua={r.ua} {hosts} /></span>{/snippet}
      </DataTable>
    </div>
  </div>
{/if}

<style>
  .setup { padding: 20px 22px; margin-bottom: 18px; display: grid; gap: 12px; }
  .setup h2, .preview h2 { margin: 0; font-size: 1.0625rem; font-weight: 600; color: var(--heading); }
  .setup p { margin: 0; }
  .small { font-size: 0.8125rem; }
  .tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 240px), 1fr)); gap: 12px; }
  .tile { border: 1px solid var(--line); border-radius: var(--r-ctl); padding: 12px 14px; display: grid; gap: 4px; align-content: start; min-width: 0; }
  .th { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
  .st { font-size: 0.75rem; font-weight: 600; padding: 1px 8px; border-radius: 6px; }
  .st.ok { color: var(--ok-text); background: color-mix(in srgb, var(--ok) 14%, transparent); }
  .st.miss { color: var(--sev2-fg); background: color-mix(in srgb, var(--warn) 16%, transparent); }
  .code { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 360px), 1fr)); gap: 16px; }
  .code h3 { margin: 0; font-size: 0.875rem; font-weight: 600; }
  .preview { padding: 0; overflow: hidden; opacity: 0.65; }
  .ph { display: flex; justify-content: space-between; align-items: baseline; gap: 8px; flex-wrap: wrap; padding: 16px 18px; }
  .pr { display: grid; grid-template-columns: 8rem minmax(0, 2fr) 5rem 6rem minmax(0, 1.4fr); gap: 12px; align-items: center; padding: 0 18px; min-height: 44px; border-top: 1px solid var(--row-line); font-size: 0.875rem; }
  .pr.h { font-size: 0.75rem; font-weight: 500; color: var(--th-fg); background: var(--bg2); }
  .pr .r { text-align: right; font-variant-numeric: tabular-nums; }
  .pr .bad { color: var(--err); }
  .mono { font-family: var(--mono); font-size: 0.8125rem; overflow-wrap: anywhere; }
  .open { display: inline-block; padding: 12px 0; margin: -12px 0; line-height: 1.25rem; color: var(--accent-text); white-space: nowrap; }
  @media (max-width: 900px) {
    .pr { grid-template-columns: minmax(0, 1fr) auto; padding: 8px 14px; }
    .pr.h { display: none; }
    .pr > :nth-child(2) { grid-column: 1 / -1; order: 3; }
  }
  .content { transition: opacity 0.15s; }
  .content.dim { opacity: 0.6; }
  .content :global(.note) { margin-bottom: 18px; }
</style>
