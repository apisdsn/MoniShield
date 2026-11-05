<!-- Collectors (docs/12-collector.md, step 6), admin only: the servers and clusters that send logs to MoniShield. Status counts,
     a table (a list on phones) with what each one sends, a side panel (a section below the list on phones) with its details and
     actions, and dialogs to add a collector, replace its key, change its inputs, revoke and delete. Secrets (the enrollment
     token, a replaced key) are shown once, in a dialog, and dropped from memory when it closes. The server keeps hashes only. -->
<script>
  import { onMount, tick } from 'svelte';
  import { srv, errText } from '../srv.js';
  import { lang, t } from '../i18n.js';
  import { api } from '../api.js';
  import { route, build } from '../state.js';
  import { locale, num, tLocal, utcToLocal } from '../format.js';
  import { PLATFORMS, ago, checkName, checkOptions, counts, defaults, editable, keySteps, payload, sends, updateSteps, upgradeSteps } from '../collectors.js';
  import { toast } from '../lib/Toast.svelte';
  import Dialog from '../lib/Dialog.svelte';
  import ErrorState from '../lib/ErrorState.svelte';
  import CollectorForm from '../lib/CollectorForm.svelte';
  import CollectorInstall from '../lib/CollectorInstall.svelte';
  import CopyBlock from '../lib/CopyBlock.svelte';
  import Icon from '../lib/Icon.svelte';
  import SeverityTag from '../lib/SeverityTag.svelte';

  let { onready = null } = $props();
  const REFRESH_MS = 30000;
  let data = $state.raw(null), error = $state(null), now = $state(Date.now());
  let selId = $state(null), addBtn = $state(), panelEl = $state();

  async function load() {
    try { data = await api.get('/api/admin/collectors'); error = null; }
    catch (e) { error = e; }
    onready?.(true);
  }
  onMount(() => {
    load();
    const id = setInterval(() => { now = Date.now(); load(); }, REFRESH_MS);
    return () => clearInterval(id);
  });

  const rows = $derived(data?.rows || []);
  const base = $derived(data?.receiver || location.origin);
  const selected = $derived(rows.find((r) => r.id === selId) || null);
  const tally = $derived(counts(rows));
  const TONE = { online: 'ok', late: 2, offline: 3, waiting: 1, revoked: 1 };
  const DOT = { online: 'ok', late: 'warn', offline: 'err', waiting: '', revoked: '' };

  // Times: the server sends UTC text; relative with the exact time in the title
  const exact = (s) => (s ? tLocal(utcToLocal(s), $lang) : '');
  function rel(s) {
    if (!s) return '';
    const [v, unit] = ago((now - Date.parse(s.replace(' ', 'T') + 'Z')) / 1000);
    return new Intl.RelativeTimeFormat(locale($lang), { numeric: 'auto' }).format(-v, unit);
  }
  const seen = (r) => (r.last_seen && r.status !== 'waiting' ? rel(r.last_seen) : r.status === 'waiting' ? $t('cl.not_installed') : $t('cl.never'));
  const chipText = (c) => $t(`cl.sends.${c.key}`, { n: num(c.n ?? 0, $lang) });
  const chips = (r) => sends(r.platform, r.options);

  function pick(id) {
    selId = selId === id ? null : id;
    if (selId !== null && matchMedia('(max-width: 900px)').matches) tick().then(() => panelEl?.scrollIntoView({ block: 'nearest' }));
  }
  // Raw Logs of the collector source; filtered to the host when the collector sent for exactly one (a cluster has many pods)
  function logsHref(r) {
    const hosts = r.stats?.hosts || [];
    return build({ tab: 'raw-logs', source: 'collector', service: null, folder: null, q: null, module: null, pod: r.platform !== 'kubernetes' && hosts.length === 1 ? hosts[0] : null });
  }

  // Dialogs: one <Dialog>, the kind decides what it shows
  let dlg = $state(null), open = $state(false), busy = $state(false), general = $state(null);
  const clean = () => { general = null; busy = false; };
  function show(kind, extra = {}) { dlg = { kind, ...extra }; clean(); open = true; }
  function closed() { dlg = null; load(); }   // tokens and keys are dropped with dlg

  // Add
  let f = $state({ name: '', platform: 'linux' }), byPlatform = $state({}), tried = $state(false), nameErr = $state('');
  const opts = $derived(byPlatform[f.platform]);
  function openAdd() {
    f = { name: '', platform: 'linux' }; tried = false; nameErr = '';
    byPlatform = Object.fromEntries(PLATFORMS.map((p) => [p, editable(p, defaults(p))]));
    show('add', { done: null });
  }
  const nameMsg = $derived(nameErr || (f.name && checkName(f.name) ? $t('cl.err.name_invalid') : tried && !f.name ? $t('cl.err.name_empty') : ''));
  function tabKey(e) {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(e.key)) return;
    e.preventDefault();
    const i = PLATFORMS.indexOf(f.platform);
    const n = e.key === 'Home' ? 0 : e.key === 'End' ? PLATFORMS.length - 1 : (i + (e.key === 'ArrowRight' ? 1 : PLATFORMS.length - 1)) % PLATFORMS.length;
    f.platform = PLATFORMS[n];
    document.getElementById(`pt-${PLATFORMS[n]}`)?.focus();
  }
  async function create(e) {
    e.preventDefault();
    tried = true; nameErr = ''; general = null;
    if (checkName(f.name) || Object.keys(checkOptions(f.platform, opts)).length) { general = $t('cl.err.fix'); return; }
    busy = true;
    try {
      const r = await api.post('/api/admin/collectors', { name: f.name, platform: f.platform, options: payload(f.platform, opts) });
      dlg = { kind: 'add', done: { id: r.collector.id, name: r.collector.name, platform: r.collector.platform, token: r.enroll_token, expires: r.expires } };
      selId = r.collector.id;
      await load();
    } catch (err) {
      if (err.code === 'name_taken' || err.code === 'invalid_name') nameErr = $errText(err); else general = $errText(err);
    } finally { busy = false; }
  }

  // Replace key, new token, inputs, revoke, delete (each one asks first or shows its result once)
  async function act(fn) {
    busy = true; general = null;
    try { await fn(); await load(); } catch (err) { general = $errText(err); } finally { busy = false; }
  }
  const rotate = (r) => act(async () => {
    const x = await api.post(`/api/admin/collectors/${r.id}/rotate`);
    dlg = { kind: 'key', r, key: x.key, until: x.previous_valid_until };
  });
  const newToken = (r) => act(async () => {
    const x = await api.post(`/api/admin/collectors/${r.id}/token`);
    dlg = { kind: 'token', r, token: x.enroll_token, expires: x.expires };
  });
  let inOpts = $state(null), inTried = $state(false);
  function openInputs(r) { inOpts = editable(r.platform, r.options); inTried = false; show('inputs', { r, saved: false }); }
  async function saveInputs(e) {
    e.preventDefault();
    inTried = true; general = null;
    if (Object.keys(checkOptions(dlg.r.platform, inOpts)).length) { general = $t('cl.err.fix'); return; }
    const r = dlg.r;
    await act(async () => { await api.put(`/api/admin/collectors/${r.id}/options`, { options: payload(r.platform, inOpts) }); dlg = { ...dlg, saved: true }; toast($t('cl.in.saved', { name: r.name })); });
  }
  const revoke = (r) => act(async () => { await api.post(`/api/admin/collectors/${r.id}/revoke`); open = false; toast($t('cl.rv.done', { name: r.name })); });
  const remove = (r) => act(async () => { await api.del(`/api/admin/collectors/${r.id}`); open = false; if (selId === r.id) selId = null; toast($t('cl.del.done', { name: r.name })); });

  const title = $derived(!dlg ? '' : dlg.kind === 'add' ? (dlg.done ? $t('cl.tok.title', { name: dlg.done.name }) : $t('cl.add'))
    : dlg.kind === 'token' ? $t('cl.tok.title', { name: dlg.r.name }) : $t(`cl.${{ key: 'key', 'key-ask': 'key', inputs: 'in', revoke: 'rv', delete: 'del' }[dlg.kind]}.title`, { name: dlg.r.name }));
  const canDelete = (r) => r.status === 'revoked' || !r.enrolled_at;
  const rejected = (s) => Object.values(s?.rejected || {}).reduce((a, b) => a + b, 0);
</script>

<div class="bar">
  <p class="muted intro">{$t('cl.intro')}</p>
  <button bind:this={addBtn} class="btn primary add" onclick={openAdd}><Icon name="plus" size={16} />{$t('cl.add')}</button>
</div>

{#if error && !data}
  <ErrorState {error} onretry={load} />
{:else if !data}
  <div class="card skel" aria-hidden="true">{#each Array(4) as _}<div class="sk-row"><span class="sk a"></span><span class="sk b"></span><span class="sk c"></span></div>{/each}</div>
  <span class="sr-only" role="status">{$t('state.loading')}</span>
{:else}
  {#if error}<ErrorState compact {error} onretry={load} />{/if}
  <ul class="tiles" aria-label={$t('cl.counts')}>
    {#each ['online', 'late', 'offline', 'waiting'] as s}
      <li class="tile" title={$t(`cl.hint.${s}`)}>
        <span class="dot {DOT[s]}" aria-hidden="true"></span>
        <b class="num">{num(tally[s], $lang)}</b>
        <span class="tl">{$t(`cl.st.${s}`)}</span>
      </li>
    {/each}
  </ul>

  {#if !rows.length}
    <div class="card empty">
      <Icon name="radio" size={28} />
      <h2>{$t('cl.empty.title')}</h2>
      <p class="muted">{$t('cl.empty.text')}</p>
      <button class="btn primary" onclick={openAdd}><Icon name="plus" size={16} />{$t('cl.add')}</button>
    </div>
  {:else}
    <div class="layout" class:two={!!selected}>
      <div class="card list">
        <table>
          <caption class="sr-only">{$t('cl.list')}</caption>
          <thead>
            <tr><th scope="col">{$t('cl.col.name')}</th><th scope="col">{$t('cl.col.sends')}</th><th scope="col">{$t('cl.col.version')}</th>
              <th scope="col">{$t('cl.col.seen')}</th><th scope="col">{$t('col.status')}</th></tr>
          </thead>
          <tbody>
            {#each rows as r (r.id)}
              <!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_noninteractive_element_interactions -->
              <tr class:sel={r.id === selId} onclick={() => pick(r.id)}>
                <td class="nm">
                  <button type="button" class="rowbtn" aria-current={r.id === selId ? 'true' : undefined} aria-controls="cl-panel"
                    aria-label={$t('cl.show', { name: r.name })} onclick={(e) => { e.stopPropagation(); pick(r.id); }}>
                    <b class="sys">{r.name}</b><span class="plat">{$t(`cl.platform.${r.platform}`)}</span>
                  </button>
                </td>
                <td class="snd" data-label={$t('cl.col.sends')}>
                  <span class="chips">{#each chips(r) as c}<span class="chip">{chipText(c)}</span>{:else}<span class="muted">{$t('cl.sends.nothing')}</span>{/each}</span>
                </td>
                <td data-label={$t('cl.col.version')} class="ver">{r.version || $t('cl.none')}</td>
                <td data-label={$t('cl.col.seen')} class="seen" title={exact(r.last_seen)}>{seen(r)}</td>
                <td data-label={$t('col.status')}><SeverityTag level={TONE[r.status]} text={$t(`cl.st.${r.status}`)} /></td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>

      {#if selected}
        {@const r = selected}
        <section class="card panel" id="cl-panel" bind:this={panelEl} aria-labelledby="cl-ph">
          <header>
            <h2 id="cl-ph" class="sys">{r.name}</h2>
            <button type="button" class="icon-btn" onclick={() => (selId = null)} aria-label={$t('cl.panel.close')} title={$t('cl.panel.close')}>×</button>
          </header>
          <p class="pst"><SeverityTag level={TONE[r.status]} text={$t(`cl.st.${r.status}`)} /> <span class="muted">{$t(`cl.hint.${r.status}`)}</span></p>
          <dl>
            <dt>{$t('cl.p.platform')}</dt><dd>{$t(`cl.platform.${r.platform}`)}</dd>
            <dt>{$t('cl.p.version')}</dt><dd>{r.version || $t('cl.none')}</dd>
            <dt>{$t('cl.p.seen')}</dt><dd title={exact(r.last_seen)}>{r.last_seen && r.enrolled_at ? `${rel(r.last_seen)} · ${exact(r.last_seen)}` : $t('cl.never')}</dd>
            <dt>{$t('cl.p.ip')}</dt><dd class="mono">{r.last_ip || $t('cl.none')}</dd>
            <dt>{$t('cl.p.sends')}</dt>
            <dd><span class="chips">{#each chips(r) as c}<span class="chip">{chipText(c)}</span>{:else}{$t('cl.sends.nothing')}{/each}</span></dd>
            <dt>{$t('cl.p.created')}</dt><dd>{exact(r.created_at)}{r.created_by ? ` · ${r.created_by}` : ''}</dd>
            {#if r.revoked_at}<dt>{$t('cl.p.revoked')}</dt><dd>{exact(r.revoked_at)}{r.revoked_by ? ` · ${r.revoked_by}` : ''}</dd>{/if}
            {#if r.previous_valid_until}<dt>{$t('cl.p.prev')}</dt><dd>{exact(r.previous_valid_until)}</dd>{/if}
            {#if r.status === 'waiting'}
              <dt>{$t('cl.p.token')}</dt><dd>{r.enroll_expires ? exact(r.enroll_expires) : $t('cl.p.token_expired')}</dd>
            {/if}
          </dl>
          {#if r.enrolled_at}
            <h3>{$t('cl.p.traffic')}</h3>
            {#if r.stats}
              <dl class="cnt">
                <dt>{$t('cl.p.recv')}</dt><dd class="num">{num(r.stats.received, $lang)}</dd>
                <dt>{$t('cl.p.written')}</dt><dd class="num">{num(r.stats.written, $lang)}</dd>
                <dt>{$t('cl.p.rejected')}</dt><dd class="num">{num(rejected(r.stats), $lang)}</dd>
                {#if r.stats.last_reject}<dt>{$t('cl.p.reason')}</dt><dd>{$srv(r.stats.last_reject.text)}</dd>{/if}
              </dl>
              <p class="muted small">{$t('cl.p.counts_note')}</p>
            {:else}<p class="muted small">{$t('cl.p.no_counts')}</p>{/if}
          {/if}
          {#if r.enrolled_at && r.status !== 'revoked' && r.platform !== 'kubernetes'}
            <h3>{$t('cl.p.upgrade')}</h3>
            <p class="muted small">{$t(`cl.p.upgrade_hint.${r.platform}`)}</p>
            {#each upgradeSteps(r.platform, base) as s}<CopyBlock label={$t('cl.a.upgrade')} lines={s.lines} />{/each}
          {/if}
          <div class="acts">
            {#if r.enrolled_at}<a class="btn accent" href={logsHref(r)}><Icon name="terminal" size={16} />{$t('cl.a.logs')}</a>{/if}
            {#if r.status === 'waiting'}<button class="btn" disabled={busy} onclick={() => newToken(r)}><Icon name="key" size={16} />{$t('cl.a.token')}</button>{/if}
            {#if r.enrolled_at && r.status !== 'revoked'}<button class="btn" disabled={busy} onclick={() => show('key-ask', { r })}><Icon name="key" size={16} />{$t('cl.a.key')}</button>{/if}
            {#if r.status !== 'revoked'}<button class="btn" onclick={() => openInputs(r)}><Icon name="settings" size={16} />{$t('cl.a.inputs')}</button>{/if}
            {#if r.status !== 'revoked'}<a class="btn" href="/api/admin/collectors/{r.id}/config" download={r.platform === 'kubernetes' ? 'values.yaml' : 'config.yaml'}><Icon name="download" size={16} />{$t('cl.a.config')}</a>{/if}
            {#if r.status !== 'revoked'}<button class="btn danger" onclick={() => show('revoke', { r })}><Icon name="ban" size={16} />{$t('cl.a.revoke')}</button>{/if}
            {#if canDelete(r)}<button class="btn danger" onclick={() => show('delete', { r })}><Icon name="archive" size={16} />{$t('cl.a.delete')}</button>{/if}
          </div>
          {#if general && !open}<p class="err" role="alert">{general}</p>{/if}
        </section>
      {/if}
    </div>
  {/if}
{/if}

<Dialog bind:open {title} onclose={closed} returnFocus={addBtn} wide={dlg?.kind === 'add' || dlg?.kind === 'inputs' || dlg?.kind === 'token'}>
  {#if dlg?.kind === 'add' && !dlg.done}
    <form onsubmit={create} novalidate>
      <label for="cl-name">{$t('cl.f.name')}</label>
      <input id="cl-name" type="text" autocomplete="off" autocapitalize="none" spellcheck="false" maxlength="63" bind:value={f.name} oninput={() => (nameErr = '')}
        aria-invalid={!!nameMsg} aria-describedby="cl-name-r{nameMsg ? ' cl-name-e' : ''}" />
      <p id="cl-name-r" class="rule">{$t('cl.f.name_rule')}</p>
      {#if nameMsg}<p id="cl-name-e" class="err">{nameMsg}</p>{/if}

      <p class="lbl" id="cl-pl">{$t('cl.f.platform')}</p>
      <div class="tabs" role="tablist" aria-labelledby="cl-pl" tabindex="-1" onkeydown={tabKey}>
        {#each PLATFORMS as p}
          <button type="button" role="tab" id="pt-{p}" aria-selected={f.platform === p} aria-controls="cl-tabpanel" tabindex={f.platform === p ? 0 : -1}
            onclick={() => (f.platform = p)}>{$t(`cl.platform.${p}`)}</button>
        {/each}
      </div>
      <div id="cl-tabpanel" role="tabpanel" aria-labelledby="pt-{f.platform}">
        {#key f.platform}<CollectorForm platform={f.platform} bind:o={byPlatform[f.platform]} show={tried} idp="add" />{/key}
      </div>
      {#if general}<p class="err" role="alert">{general}</p>{/if}
      <div class="acts">
        <button class="btn primary" type="submit" disabled={busy}>{busy ? $t('cl.f.creating') : $t('cl.f.create')}</button>
        <button class="btn" type="button" onclick={() => (open = false)}>{$t('action.cancel')}</button>
      </div>
    </form>
  {:else if dlg?.kind === 'add'}
    <CollectorInstall {...dlg.done} {base} />
    <div class="acts"><button class="btn primary" onclick={() => (open = false)}>{$t('adm.done_btn')}</button></div>
  {:else if dlg?.kind === 'token'}
    <CollectorInstall id={dlg.r.id} name={dlg.r.name} platform={dlg.r.platform} token={dlg.token} expires={dlg.expires} {base} />
    <div class="acts"><button class="btn primary" onclick={() => (open = false)}>{$t('adm.done_btn')}</button></div>
  {:else if dlg?.kind === 'key-ask'}
    <p>{$t('cl.key.confirm')}</p>
    {#if general}<p class="err" role="alert">{general}</p>{/if}
    <div class="acts">
      <button class="btn primary" disabled={busy} onclick={() => rotate(dlg.r)}>{$t('cl.key.make')}</button>
      <button class="btn" onclick={() => (open = false)}>{$t('action.cancel')}</button>
    </div>
  {:else if dlg?.kind === 'key'}
    <p class="lbl" id="key-l">{$t('cl.key.new')}</p>
    <div class="krow"><code class="tok" aria-labelledby="key-l">{dlg.key}</code>
      <button class="btn" onclick={async () => { try { await navigator.clipboard.writeText(dlg.key); toast($t('adm.copied')); } catch { /* select by hand */ } }}><Icon name="copy" size={16} />{$t('adm.copy')}</button></div>
    <p class="warnline" role="note">{$t('cl.key.once')}</p>
    <p class="small">{$t('cl.key.until', { time: exact(dlg.until) })}</p>
    <p class="small">{$t(`cl.key.where.${dlg.r.platform}`)}</p>
    {#each keySteps(dlg.r.platform, dlg.key) as s}<CopyBlock label={$t('cl.a.key')} lines={s.lines} />{/each}
    <div class="acts"><button class="btn primary" onclick={() => (open = false)}>{$t('adm.done_btn')}</button></div>
  {:else if dlg?.kind === 'inputs'}
    {#if !dlg.saved}
      <form onsubmit={saveInputs} novalidate>
        <p class="muted small">{$t(`cl.platform.${dlg.r.platform}`)}</p>
        <CollectorForm platform={dlg.r.platform} bind:o={inOpts} show={inTried} idp="in" />
        {#if general}<p class="err" role="alert">{general}</p>{/if}
        <div class="acts">
          <button class="btn primary" type="submit" disabled={busy}>{busy ? $t('action.saving') : $t('cl.in.save')}</button>
          <button class="btn" type="button" onclick={() => (open = false)}>{$t('action.cancel')}</button>
        </div>
      </form>
    {:else}
      <p>{dlg.r.enrolled_at ? (dlg.r.platform === 'kubernetes' ? $t('cl.in.next_k8s') : $t('cl.in.upgrade')) : $t('cl.in.waiting')}</p>
      {#if dlg.r.platform === 'kubernetes' && dlg.r.enrolled_at}
        <p class="vals"><a class="btn accent" href="/api/admin/collectors/{dlg.r.id}/config" download="values.yaml"><Icon name="download" size={16} />{$t('cl.tok.values')}</a></p>
      {/if}
      {#if dlg.r.enrolled_at}{#each (dlg.r.platform === 'kubernetes' ? updateSteps : upgradeSteps)(dlg.r.platform, base) as s}<CopyBlock label={$t(dlg.r.platform === 'kubernetes' ? 'cl.a.inputs' : 'cl.a.upgrade')} lines={s.lines} />{/each}{/if}
      <div class="acts"><button class="btn primary" onclick={() => (open = false)}>{$t('adm.done_btn')}</button></div>
    {/if}
  {:else if dlg?.kind === 'revoke' || dlg?.kind === 'delete'}
    {@const del = dlg.kind === 'delete'}
    <p>{$t(del ? 'cl.del.text' : 'cl.rv.text')}</p>
    {#if general}<p class="err" role="alert">{general}</p>{/if}
    <div class="acts">
      <button class="btn danger" disabled={busy} onclick={() => (del ? remove(dlg.r) : revoke(dlg.r))}>{$t(del ? 'cl.a.delete' : 'cl.a.revoke')}</button>
      <button class="btn" onclick={() => (open = false)}>{$t('action.cancel')}</button>
    </div>
  {/if}
</Dialog>

<style>
  .bar { display: flex; align-items: center; justify-content: space-between; gap: 12px 18px; margin-bottom: 14px; flex-wrap: wrap; }
  .intro { margin: 0; font-size: 0.875rem; max-width: 62ch; }
  .add { min-height: var(--touch); }
  .tiles { list-style: none; margin: 0 0 16px; padding: 0; display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }
  .tile {
    display: flex; align-items: center; gap: 8px; padding: 12px 16px; min-height: 52px; background: var(--card-bg); border: 1px solid var(--card-border);
    border-radius: var(--r-card); box-shadow: var(--glow);
  }
  .tile .dot { margin: 0; }
  .tile b { font-size: 1.25rem; font-weight: 600; color: var(--fg); }
  .tl { color: var(--kpi-label); font-size: 0.875rem; }
  .layout { display: grid; grid-template-columns: minmax(0, 1fr); gap: 18px; align-items: start; }
  .layout.two { grid-template-columns: minmax(0, 1fr) minmax(320px, 400px); }
  .list { padding: 6px 8px; overflow-x: auto; }
  table { width: 100%; border-collapse: collapse; }
  th { text-align: left; font-size: 0.75rem; font-weight: 500; color: var(--th-fg); padding: 10px 12px; border-bottom: 1px solid var(--line); white-space: nowrap; }
  td { padding: 6px 12px; border-bottom: 1px solid var(--row-line); vertical-align: middle; }
  tbody tr { cursor: pointer; }
  tbody tr:hover { background: var(--row-hover); }
  tbody tr:last-child td { border-bottom: 0; }
  tr.sel { background: var(--seg-on); }
  .rowbtn {
    display: flex; flex-direction: column; align-items: flex-start; gap: 0; text-align: left; width: 100%; min-height: var(--touch); padding: 4px 6px; margin: 0 -6px;
    background: none; border: 0; border-radius: 10px; color: var(--fg); cursor: pointer; font: inherit;
  }
  .rowbtn b { font-weight: 600; overflow-wrap: anywhere; }
  .rowbtn[aria-current='true'] b { color: var(--accent-text); }
  .plat { font-size: 0.75rem; color: var(--muted); }
  .chips { display: flex; flex-wrap: wrap; gap: 6px; }
  .ver, .seen { white-space: nowrap; font-size: 0.8125rem; color: var(--fg); }
  .ver { font-family: var(--mono); font-size: 0.75rem; }
  .skel { padding: 8px 20px; }
  .sk-row { display: flex; gap: 16px; align-items: center; height: 56px; border-bottom: 1px solid var(--row-line); }
  .sk { height: 12px; border-radius: 6px; background: var(--line); }
  .sk.a { width: 22%; } .sk.b { width: 30%; } .sk.c { width: 12%; margin-left: auto; }
  .empty { display: grid; justify-items: center; gap: 8px; text-align: center; max-width: 560px; margin: 24px auto; padding: 32px 24px; color: var(--muted); }
  .empty h2 { font-size: 1.125rem; font-weight: 600; color: var(--heading); text-transform: none; }
  .empty p { margin: 0 0 8px; }
  .panel { position: sticky; top: 96px; }
  .panel > header { margin-bottom: 6px; }
  .panel h2 { font-size: 1.0625rem; text-transform: none; overflow-wrap: anywhere; }
  .pst { margin: 0 0 10px; display: flex; flex-wrap: wrap; gap: 6px 10px; align-items: center; font-size: 0.8125rem; }
  h3 { margin: 16px 0 4px; font-size: 0.8125rem; font-weight: 600; color: var(--kpi-label); }
  dl { margin: 0; display: grid; grid-template-columns: minmax(0, auto) minmax(0, 1fr); gap: 6px 14px; font-size: 0.8125rem; }
  dt { color: var(--muted); }
  dd { margin: 0; overflow-wrap: anywhere; color: var(--fg); }
  .small { font-size: 0.8125rem; margin: 6px 0 0; }
  .acts { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 18px; }
  .acts .btn { min-height: var(--touch); }
  .btn.danger { border-color: var(--err); color: var(--err); }
  .err { color: var(--err); font-size: 0.8125rem; margin: 6px 0 0; }
  form { display: flex; flex-direction: column; gap: 4px; }
  label, .lbl { font-size: 0.8125rem; color: var(--kpi-label); margin-top: 12px; }
  form label:first-child { margin-top: 0; }
  .rule { font-size: 0.8125rem; margin: 4px 0 0; color: var(--muted); }
  input[type='text'] { width: 100%; min-height: var(--touch); font-size: 1rem; border-radius: var(--r-ctl); }
  input[aria-invalid='true'] { border-color: var(--err); }
  .tabs { display: flex; gap: 4px; padding: 3px; border: 1px solid var(--line-strong); border-radius: var(--r-ctl); background: var(--bg2); margin: 4px 0 6px; }
  .tabs button {
    flex: 1; min-height: 40px; border: 0; background: transparent; color: var(--muted); font-weight: 600; font-size: 0.8125rem; cursor: pointer;
    border-radius: calc(var(--r-ctl) - 3px); padding: 4px 8px;
  }
  .tabs button[aria-selected='true'] { background: var(--seg-on); color: var(--accent-text); }
  .tabs button:hover { color: var(--fg); }
  .krow { display: flex; gap: 8px; align-items: flex-start; }
  .tok { flex: 1; min-width: 0; padding: 10px 12px; border-radius: var(--r-ctl); background: var(--bg2); border: 1px solid var(--line-strong); font-size: 0.875rem; overflow-wrap: anywhere; user-select: all; color: var(--fg); }
  .krow .btn, .vals .btn { min-height: var(--touch); }
  .warnline { color: var(--warn); font-size: 0.8125rem; margin: 8px 0 0; }
  @media (max-width: 1100px) { .layout.two { grid-template-columns: minmax(0, 1fr); } .panel { position: static; } }
  @media (max-width: 900px) {
    .tiles { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .list { padding: 0; overflow: visible; background: none; border: 0; box-shadow: none; }
    table, tbody { display: block; }
    thead { display: none; }
    tr { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 4px 12px; padding: 12px 16px; margin-bottom: 10px; background: var(--card-bg); border: 1px solid var(--card-border); border-radius: var(--r-card); box-shadow: var(--glow); }
    tr.sel { background: var(--seg-on); border-color: var(--accent); }
    td { display: block; padding: 0; border: 0; }
    td.nm { grid-column: 1; grid-row: 1; }
    td:last-child { grid-column: 2; grid-row: 1; align-self: start; }
    td.snd { grid-column: 1 / -1; }
    td.ver, td.seen { grid-column: 1 / -1; display: flex; gap: 8px; font-size: 0.8125rem; white-space: normal; overflow-wrap: anywhere; min-width: 0; }
    td[data-label].ver::before, td[data-label].seen::before { content: attr(data-label); color: var(--muted); min-width: 7.5rem; font-family: var(--font); }
    .acts .btn, .acts a.btn { flex: 1 1 100%; justify-content: flex-start; }
    .krow { flex-direction: column; align-items: stretch; }
  }
</style>
