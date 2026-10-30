<!-- Raw Logs (owner request 2026-10-30, mockup "MoniShield Raw Logs mockup"): search the original lines of every service in
     the folder's log files. GET /api/folders/{folder}/raw (one page of entries + matches per service),
     …/raw/context (lines around one entry), …/raw/download (all matches as a .log file). The text is shown exactly as the
     service wrote it (no masking, owner decision); every new search and every download is recorded in the audit log. -->
<script>
  import { untrack } from 'svelte';
  import { t, lang } from '../i18n.js';
  import { errText } from '../srv.js';
  import { api, withSource } from '../api.js';
  import { route, build } from '../state.js';
  import { num } from '../format.js';
  import Icon from '../lib/Icon.svelte';
  import Note from '../lib/Note.svelte';

  let { folder, summary = null, onready = null } = $props();

  const MODES = ['text', 'regex', 'request', 'ip'];
  const KINDS = ['ERROR', 'WARN', 'INFO', 'DEBUG', '5xx', '4xx', '3xx', '2xx', 'other'];
  const PAGE = 200;

  let text = $state(''), mode = $state('text'), from = $state(''), to = $state(''), order = $state('desc');
  let picked = $state([]), kinds = $state([]), pod = $state('');
  let data = $state.raw(null), rows = $state.raw([]), busy = $state(false), more = $state(false), error = $state(null);
  let sel = $state(null), ctx = $state.raw(null), ctxN = $state(3), ctxBusy = $state(false);
  let asked = null;   // parameters of the search on screen (paging and download repeat them)
  let seq = 0;

  const serviceNames = $derived(data?.services?.map((s) => s.service) || summary?.services?.map((s) => s.service) || []);
  const matchesOf = $derived(Object.fromEntries((data?.services || []).map((s) => [s.service, s.matches])));
  const pods = $derived([...new Set((data?.services || []).filter((s) => !picked.length || picked.includes(s.service)).flatMap((s) => s.pods))].sort());

  function params(extra = {}) {
    const p = new URLSearchParams({ q: text.trim(), mode, order });
    if (picked.length) p.set('services', picked.join(','));
    if (kinds.length) p.set('kinds', kinds.join(','));
    if (pod) p.set('pods', pod);
    if (from) p.set('from', from);
    if (to) p.set('to', to);
    for (const [k, v] of Object.entries(extra)) p.set(k, v);
    return p;
  }
  const base = () => `/api/folders/${encodeURIComponent(folder)}/raw`;

  async function run() {
    if (!text.trim()) return;
    const my = ++seq;
    busy = true; error = null; sel = null; ctx = null;
    asked = params();
    try {
      const j = await api.get(`${base()}?${params({ limit: PAGE })}`);
      if (my === seq) { data = j; rows = j.rows; if (rows.length) pick(0); }
    } catch (e) {
      if (my === seq) error = e;
    } finally {
      if (my === seq) busy = false;
    }
  }

  async function loadMore() {
    if (!asked || more) return;
    more = true;
    try {
      const p = new URLSearchParams(asked); p.set('limit', PAGE); p.set('offset', rows.length);
      const j = await api.get(`${base()}?${p}`);
      rows = [...rows, ...j.rows];
    } catch (e) { error = e; } finally { more = false; }
  }

  async function pick(i) {
    sel = i; ctx = null;
    const r = rows[i];
    if (!r) return;
    ctxBusy = true;
    const my = ++ctxSeq;
    try {
      const j = await api.get(`${base()}/context?${new URLSearchParams({ file: r.file, line: r.line, n: ctxN })}`);
      if (my === ctxSeq) ctx = j;
    } catch { if (my === ctxSeq) ctx = null; } finally { if (my === ctxSeq) ctxBusy = false; }
  }
  let ctxSeq = 0;
  /** Scroll the "lines around it" box so the selected entry is in its middle (not the page). */
  function center(node) {
    const box = node.parentElement;
    box.scrollTop = Math.max(0, node.offsetTop - (box.clientHeight - node.offsetHeight) / 2);
  }

  /** Every line with this request ID, in time order, from every service. */
  function follow(id) {
    text = id; mode = 'request'; picked = []; kinds = []; pod = ''; from = ''; to = ''; order = 'asc';
    run();
  }

  const toggle = (list, v) => (list.includes(v) ? list.filter((x) => x !== v) : [...list, v]);
  const downloadHref = $derived(asked ? withSource(`${base()}/download?${asked}`) : null);

  /** Entry text -> pieces with the matches marked (spans are offsets from the server). */
  function pieces(s, spans) {
    const out = []; let at = 0;
    for (const [a, b] of spans || []) {
      if (a < at) continue;
      if (a > at) out.push({ t: s.slice(at, a) });
      out.push({ t: s.slice(a, b), hit: true }); at = b;
    }
    if (at < s.length) out.push({ t: s.slice(at) });
    return out;
  }
  const clock = (s) => (s ? s.slice(11) : '–');
  const kindClass = (k) => (k === '5xx' ? 's5' : k === '4xx' ? 's4' : k === '3xx' ? 's3' : k === '2xx' ? 's2' : k);
  const ipHref = (ip) => build({ ...$route, tab: 'ip', service: ip, q: null });

  // a global search (?search=…) opens this page with the text filled in and searched
  $effect(() => {
    void folder;
    untrack(() => {
      onready?.(true);
      if ($route.q) { text = $route.q; run(); }
      else if (asked) run();
    });
  });
</script>

<div class="raw" class:dim={busy}>
  <form class="card search" onsubmit={(e) => { e.preventDefault(); run(); }} aria-label={$t('raw.search_label')}>
    <div class="row">
      <label class="q">
        <Icon name="search" />
        <span class="sr-only">{$t('raw.search_label')}</span>
        <input bind:value={text} placeholder={$t(`raw.ph.${mode}`)} autocomplete="off" spellcheck="false" maxlength="500" />
      </label>
      <div class="seg" role="radiogroup" aria-label={$t('raw.mode')}>
        {#each MODES as m}
          <button type="button" role="radio" aria-checked={mode === m} onclick={() => (mode = m)}>{$t(`raw.mode.${m}`)}</button>
        {/each}
      </div>
      <button class="btn primary go" type="submit" disabled={busy || !text.trim()}>{busy ? $t('raw.searching') : $t('raw.search')}</button>
    </div>

    <fieldset class="f">
      <legend>{$t('raw.services')}</legend>
      <div class="chips">
        <button type="button" class="fc" aria-pressed={!picked.length} onclick={() => (picked = [])}>
          {$t('raw.all_services')}{#if data}<span class="n">{num(data.total, $lang)}</span>{/if}
        </button>
        {#each serviceNames as s}
          <button type="button" class="fc" class:zero={data && !matchesOf[s]} aria-pressed={picked.includes(s)} onclick={() => (picked = toggle(picked, s))}>
            {s}{#if data}<span class="n">{num(matchesOf[s] || 0, $lang)}</span>{/if}
          </button>
        {/each}
      </div>
    </fieldset>

    <div class="row filters">
      <fieldset class="f">
        <legend>{$t('raw.time')}</legend>
        <div class="tm">
          <label><span class="sr-only">{$t('raw.from')}</span><input type="time" bind:value={from} /></label>
          <span aria-hidden="true">–</span>
          <label><span class="sr-only">{$t('raw.to')}</span><input type="time" bind:value={to} /></label>
        </div>
      </fieldset>
      <fieldset class="f">
        <legend>{$t('raw.kinds')}</legend>
        <div class="chips">
          {#each KINDS as k}
            <button type="button" class="kc {kindClass(k)}" aria-pressed={kinds.includes(k)} onclick={() => (kinds = toggle(kinds, k))}>{k === 'other' ? $t('raw.other') : k}</button>
          {/each}
        </div>
      </fieldset>
      <label class="f sel">
        <span class="lg">{$t('raw.pod')}</span>
        <select bind:value={pod}>
          <option value="">{$t('raw.all_pods')}</option>
          {#each pods as p}<option value={p}>{p}</option>{/each}
        </select>
      </label>
      <label class="f sel">
        <span class="lg">{$t('raw.order')}</span>
        <select bind:value={order}>
          <option value="desc">{$t('raw.newest')}</option>
          <option value="asc">{$t('raw.oldest')}</option>
        </select>
      </label>
    </div>
  </form>

  {#if error}
    <div class="alert err" role="alert">{$errText(error)}</div>
  {/if}

  {#if !data && !busy}
    <Note>{$t('raw.intro')}</Note>
  {:else if data}
    <div class="bar">
      <p class="sum" aria-live="polite">
        {@html $t('raw.summary', { n: `<b>${num(data.total, $lang)}</b>`, s: num(data.services.filter((s) => s.matches).length, $lang),
          f: num(data.files_searched, $lang), sec: num(data.seconds, $lang, 1) })}
        {#if data.partial}<span class="part">{$t(data.partial === 'time' ? 'raw.partial_time' : 'raw.partial_many')}</span>{/if}
      </p>
      {#if downloadHref && data.total}<a class="btn" href={downloadHref} download><Icon name="download" />{$t('raw.download')}</a>{/if}
    </div>

    {#if !rows.length}
      <Note>{$t('raw.none')}</Note>
    {:else}
      <div class="res">
        <section class="card list" aria-label={$t('raw.results')}>
          <div class="hd" aria-hidden="true"><span>{$t('raw.col.time')}</span><span>{$t('raw.col.service')}</span><span>{$t('raw.col.kind')}</span><span>{$t('raw.col.line')}</span></div>
          <ul>
            {#each rows as r, i (r.file + ':' + r.line)}
              <li>
                <button type="button" class="ln" aria-pressed={sel === i} onclick={() => pick(i)}>
                  <span class="tm" title={r.time_from && r.time_from !== 'line' ? $t(`raw.time_from.${r.time_from}`) : r.time || ''}>{r.time_from && r.time_from !== 'line' ? '≈' : ''}{clock(r.time)}</span>
                  <span class="sv"><b>{r.service}</b><small>{r.pod}</small></span>
                  <span><span class="kb {kindClass(r.kind)}">{r.kind === 'other' ? '–' : r.kind}</span></span>
                  <span class="tx">{#each pieces(r.text, r.spans) as p}{#if p.hit}<mark>{p.t}</mark>{:else}{p.t}{/if}{/each}</span>
                </button>
              </li>
            {/each}
          </ul>
          {#if rows.length < data.total && rows.length < 20000}
            <div class="more"><button class="btn" onclick={loadMore} disabled={more}>{$t('raw.more', { n: num(Math.min(PAGE, data.total - rows.length), $lang) })}</button></div>
          {/if}
        </section>

        {#if sel !== null && rows[sel]}
          {@const r = rows[sel]}
          <aside class="card det" aria-label={$t('raw.selected')}>
            <header><h2>{$t('raw.selected')}</h2><span class="kb {kindClass(r.kind)}">{r.kind === 'other' ? '–' : r.kind}</span></header>
            <dl>
              <dt>{$t('raw.col.time')}</dt><dd class="mono">{r.time || '–'}{#if r.time_from && r.time_from !== 'line'} <small>({$t(`raw.time_from.${r.time_from}`)})</small>{/if}</dd>
              <dt>{$t('raw.col.service')}</dt><dd>{r.service}</dd>
              <dt>Pod</dt><dd class="mono">{r.pod}</dd>
              <dt>{$t('raw.file')}</dt><dd class="mono">{r.file} · {$t('raw.line_no', { n: num(r.line, $lang) })}{#if r.lines > 1} (+{r.lines - 1}){/if}</dd>
              {#if r.request_id}<dt>{$t('raw.request_id')}</dt><dd><button class="lk mono" onclick={() => follow(r.request_id)}>{r.request_id}</button> <small>{$t('raw.follow_hint')}</small></dd>{/if}
              {#if r.ip}<dt>IP</dt><dd><a class="mono" href={ipHref(r.ip)}>{r.ip}</a> <small>{$t('raw.ip_hint')}</small></dd>{/if}
              {#if r.method || r.status}<dt>{$t('raw.request')}</dt><dd class="mono">{[r.method, r.path, r.status].filter(Boolean).join(' ')}</dd>{/if}
            </dl>
            <div class="ctxh">
              <span class="lg">{$t('raw.context')}</span>
              <select bind:value={ctxN} onchange={() => pick(sel)} aria-label={$t('raw.context')}>
                {#each [0, 3, 10, 20] as n}<option value={n}>±{n}</option>{/each}
              </select>
            </div>
            <div class="ctx" aria-busy={ctxBusy}>
              {#if ctx}
                {#each ctx.before as c}<pre class="dimln">{c.text}</pre>{/each}
                <pre class="cur" use:center>{ctx.entry.text}</pre>
                {#each ctx.after as c}<pre class="dimln">{c.text}</pre>{/each}
              {:else}
                <pre class="cur">{r.text}</pre>
              {/if}
            </div>
            <div class="acts">
              {#if r.request_id}<button class="btn accent" onclick={() => follow(r.request_id)}><Icon name="route" />{$t('raw.follow')}</button>{/if}
              <button class="btn" onclick={() => navigator.clipboard?.writeText(r.text)}>{$t('raw.copy')}</button>
            </div>
          </aside>
        {/if}
      </div>
    {/if}
  {/if}
</div>

<style>
  .raw { display: flex; flex-direction: column; gap: 16px; transition: opacity 0.15s; }
  .raw.dim { opacity: 0.6; }
  .search { display: flex; flex-direction: column; gap: 16px; }
  .row { display: flex; flex-wrap: wrap; gap: 10px; align-items: stretch; }
  .q { flex: 999 1 320px; display: flex; align-items: center; gap: 10px; min-height: 46px; padding: 0 14px; border: 1.5px solid var(--accent);
       border-radius: var(--r-box); background: var(--pre-bg); color: var(--muted); }
  .q input { flex: 1; min-width: 0; border: 0; outline: 0; background: transparent; color: var(--fg); font: 0.9375rem var(--mono); }
  .seg { align-self: center; flex-wrap: wrap; }
  .go { min-height: 46px; padding: 0 22px; }
  .f { border: 0; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 8px; min-width: 0; }
  .f legend, .lg { padding: 0; margin-bottom: 8px; font-size: 0.75rem; font-weight: 600; letter-spacing: 0.06em; text-transform: uppercase; color: var(--muted); }
  .sel .lg { margin-bottom: 0; }
  .filters { gap: 20px; align-items: flex-end; }
  .chips { display: flex; flex-wrap: wrap; gap: 6px; }
  .fc, .kc { display: inline-flex; align-items: center; gap: 8px; min-height: 36px; padding: 0 12px; border-radius: 999px; border: 1px solid var(--line);
             background: var(--chip-bg); color: var(--fg); font: inherit; font-size: 0.8125rem; cursor: pointer; }
  .kc { border-radius: 8px; font-family: var(--mono); font-size: 0.78rem; }
  .fc[aria-pressed='true'], .kc[aria-pressed='true'] { background: var(--seg-on); border-color: var(--accent); color: var(--accent-text); }
  .fc.zero { color: var(--muted); border-style: dashed; }
  .fc .n { font-family: var(--mono); font-size: 0.75rem; opacity: 0.85; }
  .tm { display: flex; align-items: center; gap: 8px; color: var(--muted); }
  input[type='time'], select { min-height: 38px; padding: 0 10px; border: 1px solid var(--line); border-radius: 10px; background: var(--pre-bg); color: var(--fg); font: inherit; font-size: 0.875rem; }
  .bar { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; justify-content: space-between; }
  .sum { margin: 0; font-size: 0.875rem; color: var(--kpi-label); }
  .part { margin-left: 8px; color: var(--warn); font-weight: 600; }
  .bar .btn { display: inline-flex; align-items: center; gap: 6px; }
  .res { display: flex; flex-wrap: wrap; gap: 16px; align-items: flex-start; }
  .list { flex: 999 1 560px; min-width: 0; padding: 0; overflow: hidden; }
  .det { flex: 1 1 340px; min-width: 0; display: flex; flex-direction: column; gap: 12px; position: sticky; top: 12px; }
  .det header { margin: 0; }
  .hd, .ln { display: grid; grid-template-columns: 7.5rem 9rem 4.2rem minmax(0, 1fr); gap: 12px; align-items: start; }
  .hd { padding: 12px 16px; border-bottom: 1px solid var(--line); font-size: 0.75rem; font-weight: 600; letter-spacing: 0.06em; text-transform: uppercase; color: var(--th-fg); }
  ul { list-style: none; margin: 0; padding: 0; }
  .ln { width: 100%; padding: 11px 16px; border: 0; border-bottom: 1px solid var(--row-line); background: transparent; color: inherit; font: inherit; text-align: left; cursor: pointer; }
  .ln:hover { background: var(--row-hover); }
  .ln[aria-pressed='true'] { background: color-mix(in srgb, var(--accent) 8%, transparent); box-shadow: inset 3px 0 0 var(--accent); }
  .ln .tm { font: 0.78rem var(--mono); color: var(--kpi-label); }
  .sv { display: flex; flex-direction: column; gap: 2px; min-width: 0; font-size: 0.8125rem; }
  .sv small { font: 0.6875rem var(--mono); color: var(--muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .tx { font: 0.78rem/1.55 var(--mono); color: var(--code-fg); white-space: pre-wrap; overflow-wrap: anywhere; max-height: 14em; overflow: hidden; }
  mark { background: color-mix(in srgb, var(--accent) 28%, transparent); color: var(--fg); border-radius: 3px; padding: 0 1px; }
  .kb { display: inline-block; padding: 2px 7px; border-radius: 6px; font: 600 0.72rem var(--mono); background: var(--chip-bg); }
  .more { display: flex; justify-content: center; padding: 12px; }
  dl { margin: 0; display: grid; grid-template-columns: 6.5rem minmax(0, 1fr); gap: 8px 12px; font-size: 0.8125rem; }
  dt { color: var(--muted); }
  dd { margin: 0; min-width: 0; overflow-wrap: anywhere; }
  dd small { color: var(--muted); }
  .mono { font-family: var(--mono); }
  .lk { padding: 0; border: 0; background: none; color: var(--accent-text); cursor: pointer; text-decoration: underline; font-size: inherit; }
  .ctxh { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
  .ctxh .lg { margin: 0; }
  .ctx { display: flex; flex-direction: column; gap: 6px; padding: 10px 12px; border: 1px solid var(--line); border-radius: var(--r-box); background: var(--pre-bg);
         max-height: 28rem; overflow: auto; position: relative; }
  .ctx pre { margin: 0; font: 0.75rem/1.55 var(--mono); white-space: pre-wrap; overflow-wrap: anywhere; }
  .ctx .dimln { color: var(--neutral); }
  .ctx .cur { color: var(--fg); border-left: 2px solid var(--accent); padding-left: 8px; }
  .acts { display: flex; flex-wrap: wrap; gap: 8px; }
  .acts .btn { display: inline-flex; align-items: center; gap: 6px; }
  @media (max-width: 720px) {
    .hd { display: none; }
    .ln { grid-template-columns: auto minmax(0, 1fr) auto; }
    .ln .tx { grid-column: 1 / -1; }
    .det { position: static; }
  }
</style>
