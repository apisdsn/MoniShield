<!-- Tabel dengan filter (DRD §4.3, §8.2, §9.4).
     Dua sumber: `rows` (statis, filter/urut di browser) atau `table` (endpoint tabel TRD §5.4: filter, urut, dan
     lanjutan dicari di SELURUH data di server). Jumlah awal = batas lama; "Menampilkan N dari M" + "Tampilkan
     100 berikutnya" (B04). Header lekat; angka rata kanan; urut per kolom (U11, aria-sort); sel panjang terbuka
     saat diklik/fokus. > 4 kolom: kartu baris di ≤ 560 px, gulir mendatar dengan kolom pertama terkunci di 561–900 px. -->
<script>
  import { untrack } from 'svelte';
  import { lang, t } from '../i18n.js';
  import { api, tablePath } from '../api.js';
  import { num, tWIB, tRange, durMs, pct, bytes } from '../format.js';
  import IpCell from './IpCell.svelte';
  import StatusCode from './StatusCode.svelte';
  import SeverityTag from './SeverityTag.svelte';
  import ErrorState from './ErrorState.svelte';

  /**
   * columns: [{key, label, type?, sort?, fmt?(row, lang), clip?, cls?(row), sev?(row) -> {level, text}, detail?(row) -> teks}]
   *   type: 'text' (bawaan) | 'num' | 'ip' | 'ips' | 'status' | 'statuses' | 'sev' | 'time' | 'range' | 'dur' | 'pct' | 'bytes' | 'code' | 'tags'
   * Sumber statis: rows. Sumber server: folder + table (+ params), initial = {total, rows} dari respons halaman.
   */
  let { title, columns, rows = null, folder = null, table = null, params = {}, initial = null, limit = null,
        bar = null, wide = true, maxHeight = 440, rowId = null, highlight = null } = $props();

  const STEP = 100;
  const remote = $derived(!!table);
  const baseLimit = $derived(limit ?? initial?.rows?.length ?? 20);

  let q = $state(''), qSent = $state('');
  let sort = $state(null), dir = $state('desc');
  let shown = $state(0);                       // statis: jumlah baris yang ditampilkan
  let data = $state(null);                     // server: {total, matched, rows}
  let busy = $state(false), error = $state(null);
  let timer;

  // ---------------------------------------------------------------- statis
  const filtered = $derived.by(() => {
    if (remote) return [];
    let r = rows || [];
    const needle = qSent.toLowerCase();
    if (needle) r = r.filter((row) => columns.some((c) => cellText(row, c).toLowerCase().includes(needle)));
    if (sort) {
      const m = dir === 'asc' ? 1 : -1;
      r = [...r].sort((a, b) => (a[sort] > b[sort] ? m : a[sort] < b[sort] ? -m : 0));
    }
    return r;
  });

  // ---------------------------------------------------------------- server
  async function load({ append = false } = {}) {
    busy = true; error = null;
    try {
      const j = await api.get(tablePath(folder, table, { ...params, q: qSent, sort, dir: sort ? dir : null,
        limit: append ? STEP : Math.max(baseLimit, 1), offset: append ? data.rows.length : 0 }));
      data = append ? { ...j, rows: [...data.rows, ...j.rows] } : j;
    } catch (e) {
      error = e;
    } finally {
      busy = false;
    }
  }

  // awal / ganti folder: pakai halaman pertama dari respons halaman bila ada, tanpa permintaan tambahan
  let lastKey = '', lastInit = null;
  $effect(() => {
    const key = JSON.stringify([folder, table, params, rows === null ? null : rows.length]);
    const init = initial;
    if (key === lastKey && init === lastInit) return;   // data halaman baru (muat ulang) juga mengatur ulang tabel
    lastKey = key; lastInit = init;
    untrack(() => {
      q = ''; qSent = ''; sort = null; dir = 'desc'; error = null;
      shown = baseLimit;
      if (remote) {
        if (init) data = { total: init.total, matched: init.total, rows: init.rows };
        else load();
      }
    });
  });

  function onInput() {
    clearTimeout(timer);
    timer = setTimeout(() => apply(), 250);   // jeda ketik 250 ms
  }
  function apply() {
    qSent = q.trim();
    shown = baseLimit;
    if (remote) load();
  }
  function clear() { q = ''; apply(); }
  function sortBy(c) {
    if (!c.sort) return;
    if (sort !== c.key) { sort = c.key; dir = 'desc'; }
    else if (dir === 'desc') dir = 'asc';
    else { sort = null; dir = 'desc'; }
    shown = baseLimit;
    if (remote) load();
  }
  function more() {
    if (remote) load({ append: true });
    else shown += STEP;
  }

  const view = $derived(remote ? data?.rows || [] : filtered.slice(0, shown));
  const total = $derived(remote ? data?.total ?? 0 : (rows || []).length);
  const matched = $derived(remote ? (qSent ? data?.matched ?? 0 : total) : filtered.length);
  const max = $derived(bar ? Math.max(0, ...view.map((r) => +r[bar] || 0)) : 0);
  const cards = $derived(columns.length > 4);

  // ---------------------------------------------------------------- sel
  const ipOf = (v) => (v && typeof v === 'object' ? v.ip : v);
  function cellText(row, c) {
    const v = row[c.key];
    if (c.fmt) return String(c.fmt(row, $lang) ?? '');
    if (v === null || v === undefined) return '';
    if (c.type === 'ip') return [ipOf(v), v.org || ''].join(' ');
    if (c.type === 'ips') return v.map((x) => ipOf(x)).join(' ');
    if (c.type === 'statuses') return Object.keys(v).join(' ');
    if (typeof v === 'object') return JSON.stringify(v);
    return String(v);
  }
  function show(row, c) {
    const v = row[c.key];
    if (c.fmt) return c.fmt(row, $lang);
    if (v === null || v === undefined) return '–';
    switch (c.type) {
      case 'num': return num(v, $lang);
      case 'time': return tWIB(v, $lang);
      case 'range': return tRange(row[c.key], row[c.to], $lang);
      case 'dur': return durMs(v, $lang);
      case 'pct': return pct(v, $lang);
      case 'bytes': return bytes(v, $lang);
      case 'tags': return v.join(', ');
      default: return String(v);
    }
  }
  const numeric = (c) => ['num', 'dur', 'pct', 'bytes'].includes(c.type);
  const ariaSort = (c) => (sort === c.key ? (dir === 'asc' ? 'ascending' : 'descending') : c.sort ? 'none' : undefined);
  const uid = 'tb-' + Math.random().toString(36).slice(2, 9);
</script>

<section class="card dt" class:wide aria-label={title}>
  <header>
    <h2>{title}</h2>
    <div class="filter">
      <label class="sr-only" for="{uid}-q">{$t('table.filter_label', { title })}</label>
      <input id="{uid}-q" type="search" data-filter placeholder={$t('table.filter')} bind:value={q} oninput={onInput}
        onkeydown={(e) => e.key === 'Enter' && (clearTimeout(timer), apply())} autocomplete="off" spellcheck="false" />
      {#if q}<button class="x" onclick={clear} aria-label={$t('table.clear')}>×</button>{/if}
    </div>
  </header>
  <p class="sr-only" aria-live="polite">{qSent ? $t('table.matched', { n: num(matched, $lang) }) : ''}</p>

  <div class="scroll body" class:cards class:busy style="max-height:{maxHeight}px" aria-busy={busy}>
    <table>
      <caption class="sr-only">{title}</caption>
      <thead>
        <tr>
          {#each columns as c}
            <th scope="col" class:n={numeric(c)} aria-sort={ariaSort(c)}>
              {#if c.sort}<button class="sort" onclick={() => sortBy(c)}>{c.label}<span aria-hidden="true">{sort === c.key ? (dir === 'asc' ? ' ▲' : ' ▼') : ''}</span></button>{:else}{c.label}{/if}
            </th>
          {/each}
        </tr>
      </thead>
      <tbody>
        {#each view as row, i (rowId ? row[rowId] : i)}
          <tr class:hl={highlight !== null && rowId && row[rowId] === highlight} id={rowId ? `${uid}-${row[rowId]}` : undefined}>
            {#each columns as c, k}
              <td class={[c.cls?.(row), { n: numeric(c), k: k === 0 }]} data-label={c.label}>
                {#if c.type === 'ip'}
                  <IpCell ip={row[c.key]} more={typeof c.more === 'function' ? c.more(row) : 0} />
                {:else if c.type === 'ips'}
                  {#each row[c.key] || [] as x}<IpCell ip={x} />{/each}
                {:else if c.type === 'status'}
                  <StatusCode code={row[c.key]} />
                {:else if c.type === 'statuses'}
                  <StatusCode counts={row[c.key]} />
                {:else if c.type === 'sev'}
                  {@const s = c.sev(row)}<SeverityTag level={s.level} text={s.text} />
                {:else if c.detail}
                  <details><summary>{show(row, c)}</summary><pre><span class="muted">{$t('table.raw_line')}</span>
{c.detail(row)}</pre></details>
                {:else if c.clip}
                  <button class="clip" class:code={c.type === 'code'}>{show(row, c)}</button>
                {:else if c.type === 'code'}
                  <code>{show(row, c)}</code>
                {:else}
                  {show(row, c)}
                {/if}
                {#if k === 0 && bar && max}<div class="bar" style="width:{(row[bar] / max) * 100}%"></div>{/if}
              </td>
            {/each}
          </tr>
        {:else}
          <tr><td class="none" colspan={columns.length}>{qSent ? $t('table.no_match', { q: qSent }) : $t('table.no_data')}</td></tr>
        {/each}
      </tbody>
    </table>
  </div>

  {#if error}
    <ErrorState compact {error} onretry={() => load({ append: !!data && view.length > 0 && !busy })} />
  {/if}
  {#if matched > view.length}
    <div class="foot">
      <span class="muted">{$t('table.showing', { n: num(view.length, $lang), m: num(matched, $lang) })}</span>
      <button class="btn" onclick={more} disabled={busy}>{$t('table.more', { n: num(Math.min(STEP, matched - view.length), $lang) })}</button>
    </div>
  {/if}
</section>

<style>
  .filter { position: relative; display: flex; align-items: center; }
  .filter input {
    min-width: 220px; padding-left: 34px; padding-right: 34px;
    background: var(--bg2) url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='16' height='16' fill='none' stroke='%237d8fa6' stroke-width='2' viewBox='0 0 24 24'%3E%3Ccircle cx='11' cy='11' r='7'/%3E%3Cpath d='m20 20-3.5-3.5'/%3E%3C/svg%3E") no-repeat 12px center;
  }
  .filter input::-webkit-search-cancel-button { display: none; }
  .x { position: absolute; right: 4px; width: 32px; height: 32px; border: 0; border-radius: 50%; background: transparent; color: var(--muted); cursor: pointer; font-size: 1.1rem; }
  .body { border-radius: var(--r-box); transition: opacity 0.15s; }
  .body.busy { opacity: 0.6; }
  table { width: 100%; border-collapse: collapse; font-size: 0.8125rem; }
  th, td { text-align: left; padding: 10px; border-bottom: 1px solid var(--row-line); vertical-align: top; }
  th {
    color: var(--th-fg); font-weight: 600; font-size: 0.75rem; letter-spacing: 0.06em; text-transform: capitalize;
    position: sticky; top: 0; background: var(--th-bg); z-index: 2;
  }
  th.n, td.n { text-align: right; width: 1%; white-space: nowrap; padding-left: 16px; font-variant-numeric: tabular-nums; }
  tr:hover td { background: var(--row-hover); }
  tr.hl td { background: color-mix(in srgb, var(--accent) 12%, transparent); }
  td.k { word-break: break-all; }
  td.none { color: var(--muted); text-align: left; }
  .sort { all: unset; cursor: pointer; display: inline-flex; gap: 2px; min-height: 24px; align-items: center; }
  .sort:focus-visible { outline: 2px solid var(--focus); outline-offset: 2px; }
  .bar { height: 4px; background: linear-gradient(90deg, var(--accent), var(--violet)); border-radius: 2px; opacity: 0.75; margin-top: 5px; }
  .clip {
    all: unset; display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
    word-break: break-all; cursor: pointer;
  }
  .clip.code { font-family: var(--mono); font-size: 0.75rem; color: var(--code-fg); }
  .clip:focus, .clip:active { -webkit-line-clamp: unset; line-clamp: unset; outline: 2px solid var(--focus); outline-offset: 2px; }
  details summary { cursor: pointer; }
  details pre {
    white-space: pre-wrap; word-break: break-all; background: var(--pre-bg); border: 1px solid var(--line);
    padding: 10px; border-radius: 10px; margin: 8px 0 0;
  }
  .foot { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; margin-top: 12px; font-size: 0.8125rem; }

  /* 561–900 px: tabel lebar gulir mendatar, kolom pertama terkunci, bayangan tepi kanan (DRD §8.2) */
  @media (max-width: 900px) {
    .filter, .filter input { width: 100%; min-width: 0; }
    .card.dt > header { align-items: stretch; flex-direction: column; }
    .cards td.k, .cards th:first-child { position: sticky; left: 0; background: var(--card); z-index: 1; }
    .cards th:first-child { z-index: 3; background: var(--th-bg); }
    .cards {
      background: linear-gradient(to left, var(--card) 30%, transparent) right / 40px 100% no-repeat local,
                  radial-gradient(farthest-side at 100% 50%, rgba(0, 0, 0, 0.35), transparent) right / 14px 100% no-repeat scroll;
    }
    .cards td.k { min-width: 140px; }
    .x { width: var(--touch); height: var(--touch); }
  }
  /* ≤ 560 px: tiap baris jadi kartu; kolom pertama judul, lainnya "label: nilai" */
  @media (max-width: 560px) {
    .cards { max-height: none !important; background: none; }
    .cards table, .cards tbody, .cards tr, .cards td { display: block; width: auto; }
    .cards thead { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); }
    .cards tr { border: 1px solid var(--line); border-radius: var(--r-box); padding: 8px 12px; margin-bottom: 10px; }
    .cards td { border: 0; padding: 4px 0; text-align: left !important; white-space: normal !important; position: static !important; background: none !important; }
    .cards td.k { font-weight: 600; padding-bottom: 6px; border-bottom: 1px solid var(--row-line); margin-bottom: 4px; }
    .cards td:not(.k) { display: grid; grid-template-columns: minmax(90px, 40%) 1fr; gap: 10px; }
    .cards td:not(.k)::before { content: attr(data-label); color: var(--th-fg); font-size: 0.75rem; text-transform: capitalize; }
    .cards td.none { display: block; }
    .cards td.none::before { content: none; }
    .foot .btn { width: 100%; min-height: var(--touch); }
  }
</style>
