<!-- Analysis Settings (admin, stage 62): which log of each source is its access log, which are its application logs, which field carries the
     request ID, and the business metrics the site counts itself. One draft per source; nothing is stored until "Save Settings": the server
     validates, writes analysis.toml and uses it at once. "Test on This Folder" counts the rules over the newest folder without saving.
     "Business Metrics" rules can also arrive prefilled from the Business page (sessionStorage `analysis-prefill`).
     All calls are POST/PUT with the parameters in the encrypted body: service names never stand in a URL. -->
<script>
  import { onMount } from 'svelte';
  import { lang, t } from '../i18n.js';
  import { errText } from '../srv.js';
  import { api } from '../api.js';
  import { num } from '../format.js';
  import { route } from '../state.js';
  import { formatName } from '../anyfmt.js';
  import Dialog from '../lib/Dialog.svelte';
  import Icon from '../lib/Icon.svelte';
  import Skeleton from '../lib/Skeleton.svelte';
  import ErrorState from '../lib/ErrorState.svelte';

  let { onready = null } = $props();
  const BASE = '/api/v1/admin/analysis';
  const SOURCES = ['s3', 'kafka', 'collector'];
  const METHODS = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE'];
  const CLASSES = ['2xx', '3xx', '4xx', '5xx'];

  let data = $state.raw(null), error = $state(null), draft = $state.raw({}), source = $state(SOURCES.includes($route.source) ? $route.source : 's3');
  let busy = $state(false), saveErr = $state(''), saved = $state(false), test = $state.raw(null);

  const adopt = (d) => { data = d; draft = Object.fromEntries(SOURCES.map((s) => [s, structuredClone(d.sources[s].settings)])); };
  async function load() {
    try {
      adopt(await api.post(`${BASE}/view`)); error = null; onready?.(true);
      let pre = null;
      try { pre = JSON.parse(sessionStorage.getItem('analysis-prefill') || 'null'); sessionStorage.removeItem('analysis-prefill'); } catch { /* none */ }
      if (pre?.rule && SOURCES.includes(pre.source)) { source = pre.source; edit(-1, pre.rule); }
    } catch (e) { error = e; onready?.(true); }
  }
  onMount(load);

  const cur = $derived(draft[source]);
  const info = $derived(data?.sources[source]);
  const dirty = $derived(!!data && JSON.stringify(cur) !== JSON.stringify(data.sources[source].settings));
  const services = $derived((info?.services || []).map((s) => s.service));
  const fmt = (svc) => formatName(info?.services.find((s) => s.service === svc)?.format);
  const set = (patch) => { draft = { ...draft, [source]: { ...cur, ...patch } }; saved = false; saveErr = ''; test = null; };
  const withNames = (list) => [...new Set([...list.filter(Boolean), ...services])];

  // Log roles
  const accessOptions = $derived(withNames(cur?.access_log && cur.access_log !== 'auto' ? [cur.access_log] : []));
  const appsMode = $derived(cur?.app_logs === 'auto' ? 'auto' : 'list');
  const appsList = $derived(cur?.app_logs === 'auto' ? [] : cur?.app_logs || []);
  const ridMode = $derived(cur?.request_id === 'auto' ? 'auto' : 'custom');
  const toggleApp = (svc, on) => set({ app_logs: on ? [...appsList, svc] : appsList.filter((x) => x !== svc) });
  const ridFound = $derived(info ? info.request_id.access[0] > 0 || Object.values(info.request_id.app).some((v) => v[0] > 0) : false);
  const accessNote = $derived.by(() => {
    if (!info) return '';
    if (cur.access_log !== 'auto') return $t('as.access.chosen', { svc: cur.access_log });
    return info.access ? $t('as.access.auto', { fmt: formatName(info.access.format) }) : $t('as.access.none');
  });
  const appsNote = $derived(appsMode === 'auto' ? (info?.app_logs.join(', ') || $t('as.apps.none')) : $t('as.apps.chosen', { n: num(appsList.length, $lang) }));
  const k8s = $derived(info?.kubernetes);
  const k8sNames = $derived(k8s ? k8s.present.map((r) => (r === 'events' ? `${k8s.names.events} (${k8s.tag})` : k8s.names[r] || r)) : []);

  // Business metrics
  let dlg = $state(false), ed = $state({ i: -1, f: null, err: '' });
  const blank = () => ({ name: '', service: services[0] || '', match: 'request', method: '', path: '', status: '', text: '' });
  function edit(i, rule = null) {
    const r = rule ? { ...blank(), ...rule } : i >= 0 ? { ...cur.business[i] } : blank();
    const code = r.status && !CLASSES.includes(r.status);
    ed = { i, err: '', f: { ...r, statusKind: code ? 'code' : r.status || '', statusCode: code ? r.status : '' } };
    dlg = true;
  }
  function apply() {
    const f = ed.f;
    const status = f.statusKind === 'code' ? f.statusCode.trim() : f.statusKind;
    if (!f.name.trim()) { ed.err = $t('as.err_name'); return; }
    if (!f.service) { ed.err = $t('as.err_service'); return; }
    if (f.match === 'log_line' && !f.text.trim()) { ed.err = $t('as.err_text'); return; }
    if (f.match === 'request' && !(f.method || f.path.trim() || status)) { ed.err = $t('as.err_rule'); return; }
    const rule = f.match === 'log_line' ? { name: f.name.trim(), service: f.service, match: 'log_line', method: '', path: '', status: '', text: f.text.trim() }
      : { name: f.name.trim(), service: f.service, match: 'request', method: f.method, path: f.path.trim(), status, text: '' };
    if (cur.business.some((b, j) => j !== ed.i && b.name.toLowerCase() === rule.name.toLowerCase())) { ed.err = $t('as.err_dup'); return; }
    const list = [...cur.business];
    if (ed.i >= 0) list[ed.i] = rule; else list.push(rule);
    set({ business: list }); dlg = false;
  }
  function remove() { set({ business: cur.business.filter((_, j) => j !== ed.i) }); dlg = false; }
  const ruleText = (r) => (r.match === 'log_line' ? $t('any.bz.rule_line', { text: r.text })
    : [[r.method, r.path].filter(Boolean).join(' '), r.status ? $t('any.bz.rule_status', { s: r.status }) : ''].filter(Boolean).join(' · '));
  const countOf = (r) => {
    if (test?.counts && r.name in test.counts) return test.counts[r.name];
    const saved_ = data.sources[source].settings.business.find((b) => JSON.stringify(b) === JSON.stringify(r));
    return saved_ ? data.sources[source].counts[r.name] : null;
  };

  async function save() {
    busy = true; saveErr = '';
    try { adopt(await api.put(BASE, { source, settings: cur })); saved = true; test = null; }
    catch (e) { saveErr = $errText(e); }
    busy = false;
  }
  async function runTest() {
    busy = true; saveErr = '';
    try { test = await api.post(`${BASE}/test`, { source, business: cur.business }); }
    catch (e) { saveErr = $errText(e); }
    busy = false;
  }
  const discard = () => { draft = { ...draft, [source]: structuredClone(data.sources[source].settings) }; saved = false; saveErr = ''; test = null; };
</script>

<svelte:head><title>{$t('nav.cfg.analysis')}</title></svelte:head>

{#if error}
  <ErrorState {error} onretry={load} />
{:else if !data}
  <Skeleton kpis={0} charts={0} />
{:else}
  <div class="as">
    <section class="card bar">
      <span class="lbl">{$t('as.for_source')}</span>
      <div class="seg" role="group" aria-label={$t('as.for_source')}>
        {#each SOURCES as s}<button type="button" aria-pressed={source === s} onclick={() => { source = s; test = null; saved = false; saveErr = ''; }}>{$t(`src.${s}`)}</button>{/each}
      </div>
      <span class="muted path">{$t('as.saved_in_note', { path: data.file.path })}</span>
    </section>

    <section class="card roles" aria-labelledby="as-roles">
      <div class="hd"><h2 id="as-roles">{$t('as.roles')}</h2><span class="muted">{$t('as.roles_note')}</span></div>

      <div class="row">
        <div class="nm"><label for="as-access">{$t('as.access')}</label><small class="muted">{$t('as.access_used')}</small></div>
        <div class="ctl">
          <select id="as-access" value={cur.access_log} onchange={(e) => set({ access_log: e.currentTarget.value })}>
            <option value="auto">{$t('as.auto')}{info.access ? ` · ${info.access.service}` : ''}</option>
            {#each accessOptions as s}<option value={s}>{s}{fmt(s) ? ` · ${fmt(s)}` : ''}</option>{/each}
          </select>
        </div>
        <p class="why muted">{accessNote}</p>
      </div>

      <div class="row">
        <div class="nm"><label for="as-apps">{$t('as.apps')}</label><small class="muted">{$t('as.apps_used')}</small></div>
        <div class="ctl">
          <select id="as-apps" value={appsMode} onchange={(e) => set({ app_logs: e.currentTarget.value === 'auto' ? 'auto' : services.filter((s) => s !== info.access?.service) })}>
            <option value="auto">{$t('as.auto')} · {$t('as.apps_auto')}</option>
            <option value="list">{$t('as.apps_pick')}</option>
          </select>
        </div>
        <p class="why muted">{appsNote}</p>
        {#if appsMode === 'list'}
          <fieldset class="picks"><legend class="sr-only">{$t('as.apps')}</legend>
            {#each withNames(appsList) as s}<label class="chk"><input type="checkbox" checked={appsList.includes(s)} onchange={(e) => toggleApp(s, e.currentTarget.checked)} /> {s}</label>{/each}
          </fieldset>
        {/if}
      </div>

      <div class="row">
        <div class="nm"><label for="as-rid">{$t('as.rid')}</label><small class="muted">{$t('as.rid_used')}</small></div>
        <div class="ctl">
          <select id="as-rid" value={ridMode} onchange={(e) => set({ request_id: e.currentTarget.value === 'auto' ? 'auto' : data.id_fields[0] })}>
            <option value="auto">{$t('as.auto')} · {data.id_fields.slice(0, 3).join(', ')}</option>
            <option value="custom">{$t('as.rid_custom')}</option>
          </select>
          {#if ridMode === 'custom'}
            <input type="text" class="mono" aria-label={$t('as.rid')} value={cur.request_id} maxlength="100" autocomplete="off" spellcheck="false" oninput={(e) => set({ request_id: e.currentTarget.value.trim() || 'auto' })} />
          {/if}
        </div>
        <p class="why muted">{ridFound ? $t('as.rid_found') : $t('as.rid_none')} {ridMode === 'custom' ? $t('as.rid_new') : ''}</p>
      </div>

      <div class="row">
        <div class="nm"><span class="l">{$t('as.k8s')}</span><small class="muted">{$t('as.k8s_used')}</small></div>
        <div class="ctl"><div class="ro" role="note">{k8sNames.length ? k8sNames.join(', ') : $t('as.none')}</div></div>
        <p class="why muted">{$t('as.k8s_why')}</p>
      </div>
    </section>

    <section class="card biz" aria-labelledby="as-biz">
      <div class="hd"><h2 id="as-biz">{$t('as.biz')}</h2>
        <button type="button" class="btn" disabled={cur.business.length >= data.max_rules} onclick={() => edit(-1)}><Icon name="plus" size={16} /> {$t('as.add')}</button></div>
      {#if !cur.business.length}
        <p class="muted pad">{$t('as.biz_empty')}</p>
      {:else}
        <div class="tbl" role="table" aria-label={$t('as.biz')}>
          <div class="r h" role="row"><span role="columnheader">{$t('as.col.name')}</span><span role="columnheader">{$t('col.service')}</span><span role="columnheader">{$t('as.col.match')}</span>
            <span role="columnheader">{$t('as.col.rule')}</span><span class="n" role="columnheader">{$t('as.col.today')}</span><span role="columnheader"></span></div>
          {#each cur.business as r, i (r.name)}
            <div class="r" role="row">
              <span class="strong" role="cell">{r.name}</span>
              <span data-label={$t('col.service')} role="cell">{r.service}</span>
              <span data-label={$t('as.col.match')} role="cell">{$t(`as.match.${r.match}`)}</span>
              <span class="mono" data-label={$t('as.col.rule')} role="cell">{ruleText(r)}</span>
              <span class="n" data-label={$t('as.col.today')} role="cell">{countOf(r) === null ? '–' : num(countOf(r), $lang)}</span>
              <span role="cell"><button type="button" class="btn small" onclick={() => edit(i)}>{$t('as.edit')}</button></span>
            </div>
          {/each}
        </div>
      {/if}
    </section>

    {#if test}
      <p class="muted" role="status">{$t('as.tested', { folder: test.folder || '–' })}</p>
    {/if}
    {#if saveErr}<p class="alertline" role="alert">{saveErr}</p>{/if}
    {#if saved && !dirty}<p class="okline" role="status">{$t('as.saved')}</p>{/if}
    <div class="acts">
      {#if dirty}<span class="warn" role="status">{$t('as.unsaved')}</span>{/if}
      <button type="button" class="btn" disabled={busy || !dirty} onclick={discard}>{$t('lf.discard')}</button>
      <button type="button" class="btn" disabled={busy || !cur.business.length} onclick={runTest}>{$t('as.test')}</button>
      <button type="button" class="btn primary" disabled={busy || !dirty} onclick={save}>{$t('as.save')}</button>
    </div>
  </div>

  <Dialog bind:open={dlg} title={$t(ed.i >= 0 ? 'as.edit_title' : 'as.add_title')} wide>
    {#if ed.f}
      <form class="ef" onsubmit={(e) => { e.preventDefault(); apply(); }}>
        <label for="as-name">{$t('as.f.name')}</label>
        <input id="as-name" type="text" bind:value={ed.f.name} maxlength="60" autocomplete="off" />
        <label for="as-svc">{$t('as.f.service')}</label>
        <select id="as-svc" bind:value={ed.f.service}>{#each withNames([ed.f.service]) as s}<option value={s}>{s}</option>{/each}</select>
        <label for="as-match">{$t('as.f.match')}</label>
        <select id="as-match" bind:value={ed.f.match}>
          <option value="request">{$t('as.match.request')}</option><option value="log_line">{$t('as.match.log_line')}</option>
        </select>
        <small class="muted">{$t(ed.f.match === 'request' ? 'as.hint.request' : 'as.hint.log_line')}</small>
        {#if ed.f.match === 'request'}
          <label for="as-method">{$t('as.f.method')}</label>
          <select id="as-method" bind:value={ed.f.method}><option value="">{$t('as.any')}</option>{#each METHODS as m}<option value={m}>{m}</option>{/each}</select>
          <label for="as-path">{$t('as.f.path')}</label>
          <input id="as-path" type="text" class="mono" bind:value={ed.f.path} maxlength="300" autocomplete="off" spellcheck="false" placeholder="/orders" />
          <small class="muted">{$t('as.hint.path')}</small>
          <label for="as-status">{$t('as.f.status')}</label>
          <select id="as-status" bind:value={ed.f.statusKind}>
            <option value="">{$t('as.any')}</option>{#each CLASSES as c}<option value={c}>{c}</option>{/each}<option value="code">{$t('as.status_code')}</option>
          </select>
          {#if ed.f.statusKind === 'code'}<input type="text" class="mono" aria-label={$t('as.status_code')} bind:value={ed.f.statusCode} maxlength="3" inputmode="numeric" placeholder="201" />{/if}
        {:else}
          <label for="as-text">{$t('as.f.text')}</label>
          <input id="as-text" type="text" bind:value={ed.f.text} maxlength="200" autocomplete="off" spellcheck="false" placeholder="Payment received" />
          <small class="muted">{$t('as.hint.text')}</small>
        {/if}
        {#if ed.err}<p class="alertline" role="alert">{ed.err}</p>{/if}
        <div class="fb">
          {#if ed.i >= 0}<button type="button" class="btn danger" onclick={remove}>{$t('as.delete')}</button>{/if}
          <span class="sp"></span>
          <button type="button" class="btn" onclick={() => (dlg = false)}>{$t('action.cancel')}</button>
          <button type="submit" class="btn primary">{$t('lf.apply')}</button>
        </div>
      </form>
    {/if}
  </Dialog>
{/if}

<style>
  .as { display: grid; gap: 14px; min-width: 0; }
  .bar { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; padding: 14px 18px; }
  .bar .lbl { font-size: 0.875rem; color: var(--kpi-label); }
  .bar .path { margin-left: auto; font-size: 0.8125rem; overflow-wrap: anywhere; }
  .seg { min-height: 52px; box-sizing: border-box; align-items: center; }
  .seg button { min-height: var(--touch); padding: 0 14px; }
  .seg button[aria-pressed='true'] { background: var(--seg-on); color: var(--accent-text); }
  .hd { display: flex; justify-content: space-between; align-items: center; gap: 10px; flex-wrap: wrap; padding: 16px 18px; }
  .hd h2 { margin: 0; font-size: 1.0625rem; font-weight: 600; color: var(--heading); }
  .hd span.muted { font-size: 0.8125rem; }
  .roles, .biz { padding: 0; overflow: hidden; }
  .row { display: grid; grid-template-columns: minmax(160px, 1fr) minmax(0, 1.6fr) minmax(0, 1.4fr); gap: 8px 18px; align-items: center; padding: 12px 18px; border-top: 1px solid var(--row-line); }
  .nm { display: grid; gap: 2px; min-width: 0; }
  .nm label, .nm .l { font-weight: 600; font-size: 0.9375rem; }
  .nm small { font-size: 0.75rem; }
  .ctl { display: grid; gap: 8px; min-width: 0; }
  select, input[type='text'] { width: 100%; min-height: var(--touch); box-sizing: border-box; }
  .ro { min-height: var(--touch); box-sizing: border-box; display: flex; align-items: center; padding: 0 12px; border: 1px solid var(--line); border-radius: var(--r-ctl); background: var(--bg2); color: var(--muted); font-size: 0.875rem; overflow-wrap: anywhere; }
  .why { margin: 0; font-size: 0.8125rem; overflow-wrap: anywhere; }
  .picks { grid-column: 1 / -1; border: 0; margin: 0; padding: 0; display: flex; flex-wrap: wrap; gap: 0 18px; }
  .chk { display: inline-flex; align-items: center; gap: 8px; min-height: var(--touch); font-size: 0.875rem; }
  .pad { margin: 0; padding: 4px 18px 18px; font-size: 0.875rem; }
  .tbl { display: grid; }
  .r { display: grid; grid-template-columns: minmax(0, 1.2fr) minmax(0, 1.2fr) 100px minmax(0, 2fr) 80px 80px; gap: 12px; align-items: center; padding: 6px 18px; min-height: 52px; border-top: 1px solid var(--row-line); font-size: 0.875rem; }
  .r.h { min-height: 40px; font-size: 0.75rem; font-weight: 500; color: var(--th-fg); background: var(--bg2); }
  .r > span { min-width: 0; overflow-wrap: anywhere; }
  .n { text-align: right; font-variant-numeric: tabular-nums; }
  .strong { font-weight: 600; }
  .mono { font-family: var(--mono); font-size: 0.8125rem; }
  .btn { min-height: var(--touch); }
  .btn.small { padding: 0 14px; }
  .btn.danger { color: var(--err); }
  .acts { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; justify-content: flex-end; }
  .acts .btn { min-height: 52px; box-sizing: border-box; }
  .warn { color: var(--sev2-fg); font-size: 0.875rem; margin-right: auto; }
  .alertline { margin: 0; color: var(--err); font-size: 0.875rem; }
  .okline { margin: 0; color: var(--ok-text); font-size: 0.875rem; }
  .ef { display: grid; gap: 6px; }
  .ef label { font-weight: 500; margin-top: 8px; }
  .fb { display: flex; gap: 8px; margin-top: 12px; align-items: center; flex-wrap: wrap; }
  .sp { flex: 1; }
  @media (max-width: 900px) {
    .row { grid-template-columns: minmax(0, 1fr); }
    .r.h { display: none; }
    .r { grid-template-columns: minmax(0, 1fr) auto; padding: 12px 16px; gap: 4px 12px; }
    .r > [data-label]::before { content: attr(data-label) ': '; color: var(--muted); }
    .r > .strong { grid-column: 1; }
    .r > :nth-child(2), .r > :nth-child(3), .r > :nth-child(4) { grid-column: 1 / -1; }
    .r > .n { grid-column: 1; text-align: left; }
    .bar .path { margin-left: 0; }
  }
  @media (max-width: 480px) {
    .seg { display: flex; flex: 1 1 100%; } .seg button { flex: 1; padding: 0 6px; }
    .acts { display: grid; grid-template-columns: 1fr 1fr; } .acts .warn { grid-column: 1 / -1; } .acts .primary { grid-column: 1 / -1; }
  }
</style>
