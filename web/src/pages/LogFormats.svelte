<!-- Log Formats (admin, stage 59 / stage 52 step 1e): how MoniShield reads the lines of each service. Two tabs over ONE draft of the rules:
     Services (a Format select per service; choosing one writes a rule `namespace/service` above the rule that reads it today, so other
     services are untouched) and Rules (Advanced) (the rules in order, edit, move, delete, add). Nothing is saved until "Save Rules": the
     server validates, writes log-formats.toml and uses the rules at once; "Read Today Again" reads today's folder anew with them.
     Test Lines reads the service's newest lines with the format shown (nothing is stored). Helpers: web/src/logformats.js.
     All calls are POST/PUT with the parameters in the encrypted body: host names and log lines never stand in a URL. -->
<script>
  import { onMount } from 'svelte';
  import { lang, t } from '../i18n.js';
  import { srv, errText } from '../srv.js';
  import { api } from '../api.js';
  import { num } from '../format.js';
  import { toast } from '../lib/Toast.svelte';
  import Dialog from '../lib/Dialog.svelte';
  import Icon from '../lib/Icon.svelte';
  import Skeleton from '../lib/Skeleton.svelte';
  import ErrorState from '../lib/ErrorState.svelte';
  import EmptyState from '../lib/EmptyState.svelte';
  import { PRESET_KIND, FEATURES, DURATION_UNITS, matchIndex, blankRule, override, changeCount, moveRule, removeRule, putRule, formatLines, parseLines,
           optionsFor, filterServices, readsBadly, pctText } from '../logformats.js';

  let { onready = null } = $props();
  const BASE = '/api/v1/admin/log-formats';
  let data = $state.raw(null), draft = $state.raw([]), error = $state(null), saveErr = $state(''), busy = $state(false);
  let view = $state('services'), q = $state(''), source = $state('all'), onlyBad = $state(false), saved = $state(false);
  let sugg = $state.raw({}), test = $state.raw(null), reading = $state(false);

  async function load() {
    try {
      data = await api.post(`${BASE}/list`); draft = data.rules; error = null;
      onready?.(true);
      suggestAll();
    } catch (e) { error = e; onready?.(true); }
  }
  onMount(load);

  const keyOf = (s) => `${s.source}|${s.namespace}|${s.service}`;
  const saved_ = $derived(data?.rules || []);
  const n = $derived(changeCount(saved_, draft));
  const rows = $derived.by(() => (data?.services || []).map((s) => {
    const i = matchIndex(draft, s.namespace, s.service), r = draft[i], j = matchIndex(saved_, s.namespace, s.service);
    const changed = JSON.stringify(r) !== JSON.stringify(saved_[j]);
    const sg = sugg[keyOf(s)], hint = sg?.better && sg.suggested.format !== r?.format ? sg.suggested.format : null;
    return { ...s, rule: r, idx: i, fmt: r?.format || '', changed, read: changed ? null : s.read_pct, hint, bad: readsBadly(changed ? null : s.read_pct, hint) };
  }));
  const shown = $derived(filterServices(rows, { q, source, bad: onlyBad }));
  const covers = $derived(draft.map((_, i) => rows.filter((r) => r.idx === i).length));
  const sources = $derived(['all', ...['s3', 'kafka', 'collector'].filter((s) => (data?.services || []).some((x) => x.source === s))]);
  const readSources = $derived(['s3', 'kafka', 'collector'].filter((s) => (data?.services || []).some((x) => x.source === s && x.lines_today > 0)));

  // a suggestion for every service that may read badly: three at a time, newest answer wins
  async function suggestAll() {
    const todo = (data?.services || []).filter((s) => s.read_pct === null || s.read_pct < 100 || ['spring-boot', 'plain', 'auto'].includes(s.format));
    let next = 0;
    const worker = async () => {
      while (next < todo.length) {
        const s = todo[next++];
        try { const r = await api.post(`${BASE}/suggest`, { source: s.source, namespace: s.namespace, service: s.service }); if (r.available) sugg = { ...sugg, [keyOf(s)]: r }; }
        catch { /* a suggestion is a convenience: no hint */ }
      }
    };
    await Promise.all([worker(), worker(), worker()]);
  }

  async function runTest(row, rule) {
    test = { row, busy: true };
    try { test = { row, rule, res: await api.post(`${BASE}/test`, { source: row.source, namespace: row.namespace, service: row.service, rule }) }; }
    catch (e) { test = { row, rule, err: e }; }
  }
  function choose(row, fmt) {
    const next = override(draft, row.namespace, row.service, fmt);
    if (!next) { toast($t('lf.err_name')); return; }
    draft = next; saved = false; saveErr = '';
    runTest(row, next[matchIndex(next, row.namespace, row.service)]);
  }
  const discard = () => { draft = data.rules; saved = false; saveErr = ''; };
  async function save() {
    busy = true; saveErr = '';
    try {
      data = await api.put(BASE, { rules: draft }); draft = data.rules; saved = true;
      suggestAll();
    } catch (e) { saveErr = $errText(e); }
    busy = false;
  }
  async function readToday(src) {
    try { await api.post(`${BASE}/read-today`, { source: src }); toast($t('lf.read_toast')); }
    catch (e) { toast($errText(e)); }
  }
  const move = (i, d) => { const r = moveRule(draft, i, d); if (r) { draft = r; saved = false; } };
  const remove = (i) => { const r = removeRule(draft, i); if (r) { draft = r; saved = false; } };

  // Edit dialog
  let dlg = $state(false), ed = $state({ i: -1, f: null, err: '' });
  const FORMATS = Object.keys(PRESET_KIND);
  function edit(i) {
    const r = i >= 0 ? draft[i] : blankRule('', 'json');
    ed = { i, err: '', f: { match: r.match, format: r.format, kind: r.kind && r.kind !== PRESET_KIND[r.format] ? r.kind : '', features: [...r.features], fields: formatLines(r.fields), pattern: r.pattern,
                            time_format: r.time_format, multiline: r.multiline, levels: formatLines(r.levels), tag: r.tag, ip_header: r.ip_header, duration_unit: r.duration_unit } };
    dlg = true;
  }
  function apply() {
    const f = ed.f, fields = parseLines(f.fields), levels = parseLines(f.levels);
    if (!f.match.trim()) { ed.err = $t('lf.err_match'); return; }
    if (fields.error || levels.error) { ed.err = $t('lf.err_lines', { n: fields.error || levels.error }); return; }
    const has = (list) => list.includes(f.format);
    const rule = { match: f.match.trim(), format: f.format, kind: f.kind || (PRESET_KIND[f.format] ?? null), fields: has(['json', 'logfmt', 'caddy-json']) ? fields.map : {},
                   pattern: f.format === 'regex' ? f.pattern : '', time_format: f.time_format.trim() || 'iso', multiline: f.multiline, levels: levels.map,
                   tag: f.format === 'events-json' ? f.tag.trim() : '', features: FEATURES.filter((x) => f.features.includes(x)),
                   ip_header: (f.kind || PRESET_KIND[f.format]) === 'http' ? f.ip_header.trim() : '', duration_unit: has(['json', 'logfmt']) ? f.duration_unit : 'ms' };
    draft = putRule(draft, ed.i, rule); saved = false; dlg = false;
  }
  const isLast = (i) => i === draft.length - 1;
  const hint = $derived((k) => $t(`lf.f_hint.${k}`));

  const testTitle = $derived(test ? $t('lf.test_title', { svc: test.row.service }) : '');
  const bad = $derived(test?.res ? test.res.total - test.res.read : 0);
</script>

<svelte:head><title>{$t('nav.cfg.logformats')}</title></svelte:head>

{#if error}
  <ErrorState {error} onretry={load} />
{:else if !data}
  <Skeleton />
{:else}
  <div class="lf">
    <section class="card head"><p class="muted intro">{$t('lf.intro')}</p></section>

    <div class="bar">
      <div class="seg" role="tablist" aria-label={$t('lf.aria_view')}>
        {#each ['services', 'rules'] as v}
          <button type="button" role="tab" aria-selected={view === v} onclick={() => (view = v)}>{$t(`lf.tab.${v}`)}</button>
        {/each}
      </div>
      <div class="acts">
        {#if n}<span class="warn" role="status">{$t(n === 1 ? 'lf.one_unsaved_sub' : 'lf.n_unsaved_sub', { n: num(n, $lang) })}</span>{/if}
        <button type="button" class="btn" disabled={!n || busy} onclick={discard}>{$t('lf.discard')}</button>
        <button type="button" class="btn primary" disabled={!n || busy} onclick={save}>{$t('lf.save')}</button>
      </div>
    </div>
    {#if saveErr}<p class="alertline" role="alert">{saveErr}</p>{/if}

    {#if saved && !n}
      <div class="ok" role="status">
        <span>{$t('lf.saved_done')}</span>
        <span class="okbtns">{#each readSources as s}<button type="button" class="btn" onclick={() => readToday(s)}>{$t('lf.read_today')}{readSources.length > 1 ? ` · ${$t(`src.${s}`)}` : ''}</button>{/each}</span>
      </div>
    {/if}

    {#if view === 'services'}
      {#if !data.services.length}
        <EmptyState title={$t('lf.empty_title')} text={$t('lf.empty_text')} />
      {:else}
        <div class="tools">
          <label class="find"><Icon name="search" size={18} /><span class="sr-only">{$t('lf.search_ph')}</span>
            <input type="search" bind:value={q} placeholder={$t('lf.search_ph')} autocomplete="off" spellcheck="false" maxlength="100" /></label>
          <div class="seg" role="group" aria-label={$t('lf.aria_source')}>
            {#each sources as s}<button type="button" aria-pressed={source === s} onclick={() => (source = s)}>{s === 'all' ? $t('lf.src_all') : $t(`src.${s}`)}</button>{/each}
          </div>
          <button type="button" class="btn tog" aria-pressed={onlyBad} onclick={() => (onlyBad = !onlyBad)}>{$t('lf.only_bad')}</button>
        </div>
        {#if !shown.length}
          <EmptyState title={$t('lf.none_title')} />
        {:else}
          <div class="card tbl" role="table" aria-label={$t('nav.cfg.logformats')}>
            <div class="r h" role="row">
              <span role="columnheader">{$t('lf.col.service')}</span><span role="columnheader">{$t('lf.col.source')}</span><span role="columnheader">{$t('lf.col.host')}</span>
              <span role="columnheader">{$t('lf.col.read')}</span><span role="columnheader">{$t('lf.col.format')}</span><span role="columnheader"></span>
            </div>
            {#each shown as s (keyOf(s))}
              <div class="r" class:chg={s.changed} role="row">
                <span class="svc" role="cell"><b>{s.service}</b><small class="muted">{$t('lf.lines_today', { n: num(s.lines_today, $lang) })}</small></span>
                <span class="muted" data-label={$t('lf.col.source')} role="cell">{$t(`src.${s.source}`)}</span>
                <span class="mono muted" data-label={$t('lf.col.host')} role="cell">{s.namespace}</span>
                <span class="read" class:bad={s.read !== null && s.read < data.read_bad_pct} data-label={$t('lf.col.read')} role="cell"
                  title={s.read === null && !s.changed ? $t('lf.read_na_tip') : null}>{s.changed ? $t('lf.after_save') : s.read === null ? '–' : pctText(s.read, $lang)}</span>
                <span class="fmt" data-label={$t('lf.col.format')} role="cell">
                  <select class:chg={s.changed} aria-label={$t('lf.aria_format', { svc: s.service })} value={s.fmt} onchange={(e) => choose(s, e.currentTarget.value)}>
                    {#each optionsFor(data.formats, s.fmt) as f}<option value={f}>{f}</option>{/each}
                  </select>
                  {#if s.hint}<small class="sug">{$t('lf.suggested', { f: s.hint })}</small>{/if}
                </span>
                <span role="cell"><button type="button" class="btn small" onclick={() => runTest(s, s.rule)}>{$t('lf.test_btn')}</button></span>
              </div>
            {/each}
          </div>
          <p class="muted note">{$t('lf.table_hint')}</p>
        {/if}
      {/if}
    {:else}
      <p class="muted">{$t('lf.rules_intro')}</p>
      <ol class="rules">
        {#each draft as r, i}
          <li class="card rule" class:last={isLast(i)}>
            <span class="mv">
              <button type="button" class="arr" aria-label={$t('lf.up_aria')} disabled={i === 0 || isLast(i)} onclick={() => move(i, -1)}><Icon name="up" size={14} /></button>
              <button type="button" class="arr" aria-label={$t('lf.down_aria')} disabled={isLast(i) || i === draft.length - 2} onclick={() => move(i, 1)}><Icon name="down" size={14} /></button>
            </span>
            <span class="who"><span class="mono">{r.match}</span>
              <small class="muted">{isLast(i) ? $t('lf.last_text') : covers[i] === 0 ? $t('lf.covers_none') : $t(covers[i] === 1 ? 'lf.one_covers_sub' : 'lf.covers_n', { n: num(covers[i], $lang) })}</small></span>
            <span><span class="chip mono">{r.format}</span></span>
            <span class="muted">{r.kind ? $t(`lf.kind.${r.kind}`) : $t('lf.kind.auto')}</span>
            <span class="muted small">{r.features.length ? r.features.map((f) => $t(`lf.feat.${f}`)).join(', ') : '–'}</span>
            <span class="rb">
              <button type="button" class="btn small" onclick={() => edit(i)}>{$t('lf.edit')}</button>
              {#if !isLast(i)}<button type="button" class="btn small sq" aria-label={$t('lf.delete_aria')} title={$t('lf.delete_aria')} onclick={() => remove(i)}><Icon name="close" size={16} /></button>{/if}
            </span>
          </li>
        {/each}
      </ol>
      <button type="button" class="btn add" onclick={() => edit(-1)}><Icon name="plus" size={16} /> {$t('lf.add')}</button>
      {#if data.file.exists}<p class="muted note">{$t('lf.comments_note')}</p>{:else}<p class="muted note">{$t('lf.builtin_note')}</p>{/if}
    {/if}

    {#if test}
      <section class="card testp" aria-live="polite" aria-labelledby="lf-tt">
        <div class="th"><h2 id="lf-tt">{testTitle}</h2>
          <span class="muted small">{test.res?.available ? $t('lf.test_text', { f: test.res.format, n: test.res.rows.length, day: test.res.folder }) : ''}</span></div>
        {#if test.busy}<p class="muted">{$t('lf.test_busy_text')}</p>
        {:else if test.err}<p class="alertline" role="alert">{$errText(test.err)}</p>
        {:else if !test.res.available}<p class="muted">{$t('lf.test_none_text')}</p>
        {:else}
          <div class="tt" role="table" aria-label={testTitle}>
            <div class="tr th2" role="row"><span role="columnheader">{$t('lf.t.time')}</span><span role="columnheader">{$t('lf.t.level')}</span><span role="columnheader">{$t('lf.t.ip')}</span>
              <span role="columnheader">{$t('lf.t.method')}</span><span role="columnheader">{$t('lf.t.path')}</span><span role="columnheader">{$t('lf.t.status')}</span></div>
            {#each test.res.rows as x}
              <div class="tr mono" class:unread={!x.read} role="row">
                {#if x.read}
                  <span data-label={$t('lf.t.time')} role="cell">{x.time || '–'}</span><span data-label={$t('lf.t.level')} role="cell">{x.level || '–'}</span><span data-label={$t('lf.t.ip')} role="cell">{x.ip || '–'}</span>
                  <span data-label={$t('lf.t.method')} role="cell">{x.method || '–'}</span><span class="pm" data-label={$t('lf.t.path')} role="cell" title={x.path || x.message}>{x.path || x.message || '–'}</span><span data-label={$t('lf.t.status')} role="cell">{x.status ?? '–'}</span>
                {:else}
                  <span class="raw" role="cell" title={x.text}>{x.text}</span>
                {/if}
              </div>
            {/each}
          </div>
          <p class="note2" class:okc={!bad} class:errc={bad > 0}>{bad ? $t('lf.test_bad_text', { bad: num(bad, $lang), n: num(test.res.total, $lang) }) : $t('lf.test_ok_text')}</p>
        {/if}
      </section>
    {/if}
  </div>

  <Dialog bind:open={dlg} title={$t(ed.i >= 0 ? 'lf.edit_title' : 'lf.add')} wide>
    {#if ed.f}
      <form class="ef" onsubmit={(e) => { e.preventDefault(); apply(); }}>
        <label for="lf-match">{$t('lf.f.match')}</label>
        <input id="lf-match" type="text" bind:value={ed.f.match} disabled={ed.i >= 0 && isLast(ed.i)} autocomplete="off" spellcheck="false" maxlength="200" />
        <small class="muted">{hint('match')}</small>

        <label for="lf-format">{$t('lf.f.format')}</label>
        <select id="lf-format" bind:value={ed.f.format}>{#each FORMATS as f}<option value={f}>{f}</option>{/each}</select>

        <label for="lf-kind">{$t('lf.f.kind')}</label>
        <select id="lf-kind" bind:value={ed.f.kind}>
          <option value="">{$t('lf.kind.default')}</option><option value="http">{$t('lf.kind.http')}</option><option value="app">{$t('lf.kind.app')}</option>
        </select>

        <fieldset><legend>{$t('lf.f.features')}</legend>
          {#each FEATURES as f}<label class="chk"><input type="checkbox" value={f} bind:group={ed.f.features} /> {$t(`lf.feat.${f}`)}</label>{/each}
        </fieldset>

        {#if ['json', 'logfmt', 'caddy-json'].includes(ed.f.format)}
          <label for="lf-fields">{$t('lf.f.fields')}</label>
          <textarea id="lf-fields" rows="4" bind:value={ed.f.fields} spellcheck="false" placeholder="time = ts"></textarea>
          <small class="muted">{hint('fields')}</small>
        {/if}
        {#if ed.f.format === 'regex'}
          <label for="lf-pattern">{$t('lf.f.pattern')}</label>
          <textarea id="lf-pattern" rows="3" bind:value={ed.f.pattern} spellcheck="false"></textarea>
          <small class="muted">{hint('pattern')}</small>
        {/if}
        <label for="lf-tf">{$t('lf.f.time_format')}</label>
        <input id="lf-tf" type="text" bind:value={ed.f.time_format} autocomplete="off" spellcheck="false" maxlength="100" />
        <small class="muted">{hint('time_format')}</small>

        <label for="lf-ml">{$t('lf.f.multiline')}</label>
        <input id="lf-ml" type="text" bind:value={ed.f.multiline} autocomplete="off" spellcheck="false" maxlength="500" />
        <small class="muted">{hint('multiline')}</small>

        <label for="lf-levels">{$t('lf.f.levels')}</label>
        <textarea id="lf-levels" rows="3" bind:value={ed.f.levels} spellcheck="false" placeholder="SEVERE = ERROR"></textarea>
        <small class="muted">{hint('levels')}</small>

        {#if ed.f.format === 'events-json'}
          <label for="lf-tag">{$t('lf.f.tag')}</label>
          <input id="lf-tag" type="text" bind:value={ed.f.tag} autocomplete="off" spellcheck="false" maxlength="20" />
          <small class="muted">{hint('tag')}</small>
        {/if}
        {#if (ed.f.kind || PRESET_KIND[ed.f.format]) === 'http'}
          <label for="lf-iph">{$t('lf.f.ip_header')}</label>
          <input id="lf-iph" type="text" bind:value={ed.f.ip_header} autocomplete="off" spellcheck="false" maxlength="100" />
          <small class="muted">{hint('ip_header')}</small>
        {/if}
        {#if ['json', 'logfmt'].includes(ed.f.format)}
          <label for="lf-du">{$t('lf.f.duration_unit')}</label>
          <select id="lf-du" bind:value={ed.f.duration_unit}>{#each DURATION_UNITS as u}<option value={u}>{u}</option>{/each}</select>
          <small class="muted">{hint('duration_unit')}</small>
        {/if}

        {#if ed.err}<p class="alertline" role="alert">{ed.err}</p>{/if}
        <div class="fb"><button type="button" class="btn" onclick={() => (dlg = false)}>{$t('action.cancel')}</button><button type="submit" class="btn primary">{$t('lf.apply')}</button></div>
      </form>
    {/if}
  </Dialog>
{/if}

<style>
  .lf { display: grid; gap: 14px; min-width: 0; }
  .head { padding: 14px 18px; }
  .intro { margin: 0; }
  .bar { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; justify-content: space-between; }
  .acts { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
  .warn { color: var(--sev2-fg); font-size: 0.875rem; }
  .seg button { min-height: var(--touch); padding: 0 14px; }
  .seg button[aria-selected='true'] { background: var(--seg-on); color: var(--accent-text); }
  .btn { min-height: var(--touch); }
  .btn.small { min-height: 40px; padding: 0 12px; font-size: 0.8125rem; }
  .btn.sq { width: 40px; padding: 0; }
  .btn.tog[aria-pressed='true'] { border: 1.5px solid var(--accent); background: var(--seg-on); color: var(--accent-text); font-weight: 600; }
  .alertline { margin: 0; color: var(--err); font-size: 0.875rem; }
  .ok { border: 1px solid color-mix(in srgb, var(--ok) 45%, transparent); background: color-mix(in srgb, var(--ok) 9%, transparent); border-radius: var(--r-card); padding: 12px 16px;
        display: flex; flex-wrap: wrap; gap: 12px; align-items: center; justify-content: space-between; font-size: 0.875rem; }
  .okbtns { display: flex; flex-wrap: wrap; gap: 8px; }
  .tools { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; }
  .find { flex: 1 1 260px; display: flex; align-items: center; gap: 8px; min-height: calc(var(--touch) + 8px); box-sizing: border-box; padding: 0 12px; border: 1px solid var(--line-strong); border-radius: var(--r-ctl); background: var(--bg2); color: var(--muted); }
  .find input { flex: 1; min-width: 0; border: 0; background: transparent; color: var(--fg); font-size: 1rem; outline: none; min-height: 40px; padding: 0; }
  .find:focus-within { outline: 2px solid var(--focus); outline-offset: 2px; }
  .tbl { overflow: hidden; padding: 0; }
  .r { display: grid; grid-template-columns: minmax(0, 1.4fr) 110px minmax(0, 1fr) 100px minmax(0, 1.2fr) 120px; gap: 12px; align-items: center; padding: 10px 16px; border-bottom: 1px solid var(--row-line); font-size: 0.875rem; }
  .r:last-child { border-bottom: 0; }
  .r.h { font-size: 0.75rem; font-weight: 500; color: var(--th-fg); border-bottom: 1px solid var(--line); }
  .r.chg { background: var(--seg-on); }
  .svc { display: grid; gap: 2px; min-width: 0; overflow-wrap: anywhere; }
  .mono { font-family: var(--mono); font-size: 0.75rem; overflow-wrap: anywhere; }
  .read { font-weight: 600; font-variant-numeric: tabular-nums; color: var(--ok); }
  .read.bad { color: var(--err); }
  .fmt { display: grid; gap: 4px; min-width: 0; }
  .fmt select { min-height: 40px; font-family: var(--mono); font-size: 0.8125rem; max-width: 100%; }
  .fmt select.chg { border-color: var(--accent); }
  .sug { color: var(--accent-text); }
  .note { margin: 0; font-size: 0.8125rem; }
  .rules { list-style: none; margin: 0; padding: 0; display: grid; gap: 8px; }
  .rule { display: grid; grid-template-columns: 44px minmax(0, 1.3fr) minmax(0, 1fr) 90px minmax(0, 1fr) 150px; gap: 12px; align-items: center; padding: 10px 14px; font-size: 0.875rem; }
  .rule.last { border-style: dashed; }
  .mv { display: grid; gap: 2px; }
  .arr { width: 44px; height: 22px; display: grid; place-items: center; border: 1px solid var(--line-strong); border-radius: 6px; background: var(--card-bg); color: var(--muted); cursor: pointer; padding: 0; }
  .arr:disabled { opacity: 0.4; cursor: not-allowed; }
  .who { display: grid; gap: 2px; min-width: 0; }
  .rb { display: flex; gap: 6px; justify-content: flex-end; }
  .add { justify-self: start; display: inline-flex; align-items: center; gap: 6px; }
  .small { font-size: 0.75rem; }
  .testp { padding: 16px 18px; display: grid; gap: 10px; }
  .th { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 8px; align-items: baseline; }
  .th h2 { margin: 0; font-size: 1rem; color: var(--heading); }
  .tt { display: grid; }
  .tr { display: grid; grid-template-columns: 70px 70px 130px 70px minmax(0, 1fr) 60px; gap: 10px; padding: 8px 4px; border-top: 1px solid var(--row-line); font-size: 0.75rem; align-items: center; }
  .tr.th2 { border-top: 0; font-weight: 600; color: var(--th-fg); font-family: inherit; }
  .tr span { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .tr.unread { color: var(--err); }
  .raw { grid-column: 1 / -1; }
  .note2 { margin: 0; font-size: 0.8125rem; }
  .okc { color: var(--ok); } .errc { color: var(--err); }
  .ef { display: grid; gap: 6px; }
  .ef label { font-weight: 500; margin-top: 8px; }
  .ef input[type='text'], .ef select, .ef textarea { width: 100%; min-height: var(--touch); box-sizing: border-box; }
  .ef textarea { font-family: var(--mono); font-size: 0.8125rem; }
  .ef fieldset { border: 0; padding: 0; margin: 8px 0 0; display: flex; flex-wrap: wrap; gap: 4px 18px; }
  .ef legend { font-weight: 500; padding: 0; margin-bottom: 4px; }
  .chk { display: inline-flex; align-items: center; gap: 8px; min-height: var(--touch); margin: 0 !important; font-weight: 400 !important; }
  .fb { display: flex; justify-content: flex-end; gap: 8px; margin-top: 12px; }
  @media (max-width: 900px) {
    .r.h, .tr.th2 { display: none; }
    .r { grid-template-columns: minmax(0, 1fr); gap: 6px; padding: 14px 16px; }
    .r > [data-label]::before { content: attr(data-label) ': '; color: var(--muted); font-weight: 400; }
    .fmt { grid-template-columns: minmax(0, 1fr); }
    .rule { grid-template-columns: 44px minmax(0, 1fr); }
    .rule > :nth-child(n + 3) { grid-column: 2; }
    .rb { justify-content: flex-start; }
    .tr { grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); }
    .tr > [data-label]::before { content: attr(data-label) ': '; color: var(--muted); }
    .tr span { white-space: normal; overflow-wrap: anywhere; }
    .tr .pm { grid-column: 1 / -1; }
  }
</style>
