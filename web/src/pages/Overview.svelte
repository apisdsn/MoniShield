<!-- Overview (DRD §3.1, inv. §2.1). Sources (TRD §5.3): /overview (period, hourly errors per service, top 25
     messages), folder summary from App (/api/folders/{f}: KPIs, services, files), and /services/nginx-ingress-controller
     for the "Traffic HTTP seluruh sistem" section (nginx service cards without the map and without the message card). The two
     page requests run concurrently and are shown together (U31).
     Redesign 2026-10-27 (mockup "Overview — sebelum & sesudah"): a status card first (Critical / Needs a look / All clear,
     with up to three reasons and links), the four main numbers large, then the hourly error chart next to "Services to
     check". Total log lines and HTTP requests are in the volume band above every page (lib/VolumeBand.svelte, 2026-10-28). The "incomplete folder" and "not compared" notes are in the status
     card, once. -->
<script>
  import { untrack } from 'svelte';
  import { lang, t } from '../i18n.js';
  import { api } from '../api.js';
  import { num, delta, sysName, dLabel, logDay, SPARSE_LINES } from '../format.js';
  import { build, route } from '../state.js';
  import { cmpNote } from '../lib/compare.js';
  import InfoTip from '../lib/InfoTip.svelte';
  import Icon from '../lib/Icon.svelte';
  import Kpi from '../lib/Kpi.svelte';
  import ChartCard from '../lib/ChartCard.svelte';
  import DataTable from '../lib/DataTable.svelte';
  import MessagesTable from '../lib/MessagesTable.svelte';
  import ServiceCards from '../lib/ServiceCards.svelte';
  import Skeleton from '../lib/Skeleton.svelte';
  import ErrorState from '../lib/ErrorState.svelte';

  let { folder, summary, reloadKey = 0, onready = null } = $props();
  const NG = 'nginx-ingress-controller';

  // view = snapshot of the data being shown; on folder change the old content stays visible (dimmed) until the new one arrives
  let view = $state(null), busy = $state(false), error = $state(null);
  let seq = 0, loadedKey = '';
  const current = $derived(summary?.folder === folder ? summary : null);

  async function load(sum) {
    const my = ++seq;
    busy = true; error = null; onready?.(false);
    const f = encodeURIComponent(sum.folder);
    const hasNg = sum.services.some((s) => s.service === NG && s.lines);
    try {
      const [o, n] = await Promise.all([api.get(`/api/folders/${f}/overview`), hasNg ? api.get(`/api/folders/${f}/services/${NG}`) : null]);
      if (my === seq) view = { folder: sum.folder, summary: sum, page: o, nginx: n };
    } catch (e) {
      if (my === seq) error = e;
    } finally {
      if (my === seq) { busy = false; onready?.(true); }
    }
  }
  // load once per (folder, reload), after that folder's summary arrives (knowing whether nginx exists)
  $effect(() => {
    const key = `${folder}|${reloadKey}`;
    if (!current || key === loadedKey) return;
    loadedKey = key;
    untrack(() => load(current));
  });

  const page = $derived(view?.page), nginx = $derived(view?.nginx), summ = $derived(view?.summary);
  const svc = $derived(summ?.services || []);
  const ngRow = $derived(svc.find((s) => s.service === NG && s.lines) || null);

  // change vs the previous folder only over comparable services (old: comparable/dlt, inv. §2.0)
  const cmp = $derived(svc.filter((s) => s.lines && s.prev && s.prev.lines >= 0.5 * s.lines));
  const sum = (list, k) => list.reduce((a, s) => a + (s[k] || 0), 0);
  const d = (k, good = false) => summ?.prev_folder
    ? delta(sum(cmp, k), sum(cmp.map((s) => s.prev), k), summ.prev_folder, $lang, { good, comparable: cmp.length > 0 }) : null;
  const files = $derived(summ?.files || []);
  const nCorrupt = $derived(files.filter((f) => f.status === 'corrupt').length);
  const rate = (n, dg) => `${num((n / ngRow.requests) * 100, $lang, dg)}%`;

  // ---- status card: the rule is also in its (i) tooltip (ov.st.info)
  const errTotal = $derived(sum(svc, 'err'));
  const errSvcs = $derived(svc.filter((s) => s.err).sort((a, b) => b.err - a.err));
  const attack = $derived(summ?.attack_ip_count || 0);
  const r4 = $derived(ngRow?.requests ? ngRow.n4xx / ngRow.requests : null);
  const r5 = $derived(ngRow?.requests ? ngRow.n5xx / ngRow.requests : null);
  const enough = $derived((ngRow?.requests || 0) >= 50);   // a handful of requests says little about a rate
  const level = $derived(r5 !== null && enough && r5 >= 0.05 ? 'crit'
    : errTotal || attack || nCorrupt || (r4 !== null && enough && r4 >= 0.1) ? 'check' : 'ok');
  const reasons = $derived.by(() => {
    const out = [];
    if (r5 !== null && enough && r5 >= 0.05) out.push($t('ov.st.r5xx', { p: rate(ngRow.n5xx, 1) }));
    if (errTotal) out.push($t('ov.st.err', { n: num(errTotal, $lang), m: num(errSvcs.length, $lang), list: errSvcs.slice(0, 3).map((s) => sysName(s.service)).join(', ') + (errSvcs.length > 3 ? ', …' : '') }));
    if (attack) out.push($t('ov.st.attack', { n: num(attack, $lang) }));
    if (r4 !== null && enough && r4 >= 0.1) out.push($t('ov.st.r4xx', { p: rate(ngRow.n4xx, 1) }));
    if (nCorrupt) out.push($t('ov.st.corrupt', { n: num(nCorrupt, $lang) }));
    return out.slice(0, 3);
  });
  const lines = $derived(sum(svc, 'lines'));
  const sparse = $derived(lines < SPARSE_LINES);
  const note = $derived([...$cmpNote.values()][0] || '');
  const href = (tab) => build({ ...$route, tab, service: null, q: null });
  const svcHref = (s) => build({ ...$route, tab: 'service', service: s, q: null });
  const toCheck = $derived(svc.filter((s) => s.err || s.files_corrupt).sort((a, b) => b.err - a.err || b.files_corrupt - a.files_corrupt));

  // hourly errors per service: stacked bars, hours combined across all services
  const errSeries = $derived(Object.entries(page?.err_by_hour || {}));
  const hours = $derived([...new Set(errSeries.flatMap(([, pts]) => pts.map((p) => p[0])))].sort());
</script>

{#if error && !view}
  <ErrorState {error} onretry={() => current && load(current)} />
{:else if !view}
  <Skeleton kpis={8} charts={3} />
{:else}
  {#if error}<ErrorState {error} onretry={() => current && load(current)} />{/if}
  <div class="content" class:dim={busy || view.folder !== folder}>
    <section class="status card {level}" aria-labelledby="st-h">
      <div class="st-main">
        <div class="st-head">
          <span class="pill {level}"><span class="dot" aria-hidden="true"></span>{$t(`ov.st.${level}`)}</span>
          <h2 id="st-h">{$t('ov.st.title', { date: dLabel(logDay(view.folder), $lang) })}</h2>
          <InfoTip text={$t('ov.st.info')} />
        </div>
        {#if reasons.length}
          <ul>{#each reasons as r}<li>{r}</li>{/each}</ul>
        {:else}
          <p class="calm">{$t('ov.st.none')}</p>
        {/if}
      </div>
      <div class="st-acts">
        {#if attack}<a class="btn {level !== 'ok' ? 'primary' : ''}" href={href('security')}>{$t('ov.st.to_security')}</a>{/if}
        {#if errTotal || level === 'crit'}<a class="btn {!attack && level !== 'ok' ? 'primary' : ''}" href={href('root-causes')}>{$t('tab.root-causes')}</a>{/if}
        {#if nCorrupt && !attack && !errTotal}<a class="btn" href={href('pods')}>{$t('tab.pods')}</a>{/if}
      </div>
      {#if sparse || note}
        <p class="st-note">
          {[sparse ? $t('band.sparse', { n: num(lines, $lang), m: num(nCorrupt, $lang) }) : '', note ? `${note}.` : ''].filter(Boolean).join(' ')}
          {#if sparse}<a href={href('pods')}>{$t('band.to_pods')}</a>{/if}
        </p>
      {/if}
    </section>

    <div class="kpis four">
      <Kpi size="lg" icon="alert" label={$t('kpi.error')} value={errTotal} tone="err" delta={d('err')}
        sub={errSvcs.length ? [{ text: $t('ov.n_services', { n: num(errSvcs.length, $lang) }) }] : null}
        info={$t('kpi.error_info', { http: num(sum(svc, 'err_http'), $lang), log: num(sum(svc, 'err_log'), $lang) })} />
      <Kpi size="lg" icon="shield" label={$t('ov.attack_ips')} value={attack} tone="err" />
      <Kpi size="lg" icon="alert" label={$t('ov.warn_4xx')} value={sum(svc, 'warn')} tone="warn" delta={d('warn')} info={$t('ov.warn_4xx_info')} />
      <Kpi size="lg" icon="trend" label={$t('kpi.rate5xx')} value={ngRow?.requests ? rate(ngRow.n5xx, 2) : null} tone={r5 !== null && enough && r5 >= 0.05 ? 'err' : null}
        missing={$t('ov.no_nginx')} sub={ngRow?.requests && !(enough && r5 >= 0.05) ? [{ tone: 'ok', text: $t('ov.safe5') }] : null} />
    </div>

    <div class="top2">
      <ChartCard title={$t('ov.err_per_hour')} type="bar" timeAxis labels={hours} chip={$t('chip.hourly')}
        info={$t('svc.hour_err_info')}
        datasets={errSeries.map(([s, pts], i) => { const m = Object.fromEntries(pts); return { label: sysName(s), data: hours.map((h) => m[h] || 0), color: `--c${(i % 10) + 1}` }; })}
        options={{ scales: { x: { stacked: true }, y: { stacked: true } } }} />
      <section class="card check" aria-labelledby="ck-h">
        <h2 id="ck-h">{$t('ov.check_title')}</h2>
        {#if toCheck.length}
          <ul>
            {#each toCheck.slice(0, 8) as s}
              <li><a href={svcHref(s.service)}><span class="sys">{sysName(s.service)}</span>
                {#if s.err}<span class="tag err">{$t('ov.badge_err', { n: num(s.err, $lang) })}</span>{:else}<span class="tag warn">{$t('ov.badge_corrupt')}</span>{/if}</a></li>
            {/each}
          </ul>
          {#if svc.length - toCheck.length}<p class="muted small">{$t('ov.check_rest', { n: num(svc.length - toCheck.length, $lang) })}</p>{/if}
        {:else}
          <p class="muted small">{$t('ov.check_none')}</p>
        {/if}
      </section>
    </div>

    <div class="grid">
      <ChartCard title={$t('ov.err_warn_per_service')} type="bar" labels={svc.map((s) => sysName(s.service))}
        datasets={[{ label: $t('kpi.error'), data: svc.map((s) => s.err), color: '--err' }, { label: 'Warn', data: svc.map((s) => s.warn), color: '--warn' }]}
        options={{ indexAxis: 'y' }} />
      <ChartCard title={$t('ov.lines_per_service')} type="bar" labels={svc.map((s) => sysName(s.service))}
        datasets={[{ label: $t('col.lines'), data: svc.map((s) => s.lines), color: '--accent' }]}
        options={{ indexAxis: 'y', plugins: { legend: { display: false } } }} />
      <DataTable wide={false} title={$t('ov.service_summary')} rows={svc} limit={50} columns={[
        { key: 'service', label: $t('col.service'), fmt: (r) => sysName(r.service), cls: () => 'nowrap', sort: true },
        { key: 'lines', label: $t('col.lines'), type: 'num', sort: true },
        { key: 'err', label: $t('kpi.error'), type: 'num', sort: true },
        { key: 'warn', label: 'Warn', type: 'num', sort: true },
        { key: 'files', label: $t('col.pod'), type: 'num', sort: true },
      ]} />
      <DataTable wide={false} title={$t('kpi.files')} rows={files} limit={50} columns={[
        { key: 'pod', label: $t('col.pod'), fmt: (r) => `${sysName(r.service)} / ${sysName(r.pod)}`, sort: true },
        { key: 'lines', label: $t('col.lines'), type: 'num', sort: true },
        { key: 'size_bytes', label: $t('col.size'), type: 'num', fmt: (r) => `${num(r.size_bytes / 1048576, $lang, 2)} MB`, sort: true },
      ]} />
      <MessagesTable title={$t('ov.top_msgs')} folder={view.folder} initial={page.tables.messages} crossService chip={$t('chip.all_data')} />
    </div>

    {#if nginx?.available}
      <section class="traffic" aria-labelledby="traffic-h">
        <h2 id="traffic-h">{$t('ov.traffic')}</h2>
        <p class="muted">{$t('ov.traffic_note')}</p>
        <div class="grid"><ServiceCards data={nginx} folder={view.folder} withMsgs={false} /></div>
      </section>
    {/if}
  </div>
{/if}

<style>
  .content { transition: opacity 0.15s; }
  .content.dim { opacity: 0.6; }
  .status { display: flex; flex-wrap: wrap; align-items: flex-start; gap: 16px 20px; margin-bottom: 16px; padding: 20px 22px; }
  .status.check { border-color: color-mix(in srgb, var(--warn) 40%, transparent); }
  .status.crit { border-color: color-mix(in srgb, var(--err) 50%, transparent); }
  .st-main { flex: 1 1 420px; min-width: 0; display: flex; flex-direction: column; gap: 10px; }
  .st-head { display: flex; align-items: center; gap: 10px 12px; flex-wrap: wrap; }
  .st-head h2 { margin: 0; font-size: 1.25rem; font-weight: 600; color: var(--heading); text-transform: none; }
  .pill { display: inline-flex; align-items: center; gap: 6px; font-size: 0.75rem; font-weight: 600; padding: 4px 12px; border-radius: 999px; }
  .pill .dot { width: 7px; height: 7px; border-radius: 50%; background: currentColor; }
  .pill.ok { color: var(--sevok-fg); background: color-mix(in srgb, var(--ok) 14%, transparent); }
  .pill.check { color: var(--sev2-fg); background: color-mix(in srgb, var(--warn) 14%, transparent); }
  .pill.crit { color: var(--sev3-fg); background: color-mix(in srgb, var(--err) 16%, transparent); }
  .status ul { margin: 0; padding-left: 18px; display: flex; flex-direction: column; gap: 4px; font-size: 0.9375rem; color: var(--kpi-label); }
  .calm { margin: 0; color: var(--kpi-label); }
  .st-acts { display: flex; gap: 10px; flex-wrap: wrap; }
  .st-acts .btn { min-height: var(--touch); }
  .st-note { flex-basis: 100%; margin: 0; padding-top: 12px; border-top: 1px solid var(--line); font-size: 0.8125rem; color: var(--muted); }
  .top2 { display: grid; grid-template-columns: minmax(0, 2fr) minmax(0, 1fr); gap: 18px; margin-bottom: 18px; }
  .check h2 { font-size: 1rem; font-weight: 600; color: var(--heading); margin: 0 0 6px; }
  .check ul { list-style: none; margin: 0; padding: 0; }
  .check li a { display: flex; justify-content: space-between; align-items: center; gap: 10px; min-height: var(--touch); color: var(--fg); text-decoration: none; border-bottom: 1px solid var(--row-line); }
  .check li a:hover { color: var(--accent-text); }
  .check .sys { overflow-wrap: anywhere; }
  .tag { flex: none; font-size: 0.75rem; padding: 2px 10px; border-radius: 999px; }
  .tag.err { color: var(--badge-fg); background: var(--badge-bg); }
  .tag.warn { color: var(--sev2-fg); background: color-mix(in srgb, var(--warn) 14%, transparent); }
  .small { font-size: 0.8125rem; margin: 10px 0 0; }
  @media (max-width: 1100px) { .top2 { grid-template-columns: minmax(0, 1fr); } }
  @media (max-width: 900px) {
    .status { padding: 16px; }
    .st-acts { flex-basis: 100%; }
    .st-acts .btn { flex: 1; justify-content: center; }
  }
  .traffic { margin-top: 26px; }
  .traffic h2 { font-size: 1rem; font-weight: 600; color: var(--heading); text-transform: capitalize; margin: 0 0 4px; }
  .traffic > p { margin: 0 0 14px; font-size: 0.75rem; }
</style>
