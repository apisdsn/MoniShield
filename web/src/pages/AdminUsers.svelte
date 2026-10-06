<!-- Kelola user (DRD §3.11, TRD §8.4), hanya admin: tabel user + menu aksi per baris (Ubah, Reset sandi,
     Nonaktifkan/Aktifkan, Hapus) dan dialog. Di atas API Tahap 10 (/api/admin/users). Yang tidak ditawarkan (nonaktif
     dengan sebabnya): menghapus atau menonaktifkan diri sendiri, menghapus/menurunkan/menonaktifkan admin aktif
     terakhir. Sandi sementara hasil reset ditampilkan SEKALI dan tidak disimpan di mana pun. -->
<script>
  import { onMount } from 'svelte';
  import { lang, t } from '../i18n.js';
  import { api } from '../api.js';
  import { tWIB, utcToWib } from '../format.js';
  import { toast } from '../lib/Toast.svelte';
  import DataTable from '../lib/DataTable.svelte';
  import Dialog from '../lib/Dialog.svelte';
  import RowMenu from '../lib/RowMenu.svelte';
  import Skeleton from '../lib/Skeleton.svelte';
  import ErrorState from '../lib/ErrorState.svelte';
  import SeverityTag from '../lib/SeverityTag.svelte';

  let { me, onme = null } = $props();
  let users = $state.raw(null), error = $state(null);
  async function load() {
    try { users = (await api.get('/api/admin/users')).users; error = null; }
    catch (e) { error = e; }
  }
  onMount(load);

  const PW_MIN = 12;
  const NAME = /^[a-z0-9._-]{3,32}$/;
  const activeAdmins = $derived((users || []).filter((u) => u.role === 'admin' && u.active).length);
  const lastAdmin = (u) => u.role === 'admin' && u.active && activeAdmins <= 1;
  const isMe = (u) => u.username === me.username;
  // galat server per kode -> kamus (pesan server berbahasa Indonesia); kode lain: pesan server apa adanya
  const errText = (e) => (e.status === 0 ? $t('state.error_network') : ['invalid_username', 'invalid_password', 'username_taken', 'last_admin', 'self_delete', 'not_found', 'invalid_role'].includes(e.code)
    ? $t(`adm.err.${e.code}`, { n: PW_MIN }) : e.message || $t('state.error_text'));

  // ---------------------------------------------------------------- dialog
  let dlg = $state(null);            // {kind: 'add' | 'edit' | 'reset' | 'reset-done' | 'deactivate' | 'delete', user?}
  let open = $state(false), busy = $state(false), errs = $state({}), general = $state(null);
  let f = $state({ username: '', display_name: '', role: 'user', password: '' });
  let temp = $state(''), addBtn = $state();
  function show(kind, user = null) {
    dlg = { kind, user }; errs = {}; general = null; busy = false;
    if (kind === 'add') f = { username: '', display_name: '', role: 'user', password: '' };
    if (kind === 'edit') f = { username: user.username, display_name: user.display_name, role: user.role, password: '' };
    open = true;
  }
  function randomPassword() {
    const abc = 'abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789';
    const v = crypto.getRandomValues(new Uint32Array(16));
    f.password = [...v].map((x) => abc[x % abc.length]).join('');
  }
  async function act(fn, done) {
    busy = true; general = null;
    try { await fn(); await load(); done?.(); }
    catch (e) {
      if (e.code === 'invalid_username' || e.code === 'username_taken') errs = { username: errText(e) };
      else if (e.code === 'invalid_password') errs = { password: errText(e) };
      else general = errText(e);
    } finally { busy = false; }
  }
  function submitAdd(e) {
    e.preventDefault();
    errs = {};
    const u = f.username.trim().toLowerCase();
    if (!NAME.test(u)) errs.username = $t('adm.err.invalid_username');
    if (f.password.length < PW_MIN) errs.password = $t('adm.err.invalid_password', { n: PW_MIN });
    else if (f.password === u) errs.password = $t('adm.err.password_is_name');
    if (Object.keys(errs).length) return;
    act(() => api.post('/api/admin/users', { username: u, display_name: f.display_name.trim(), role: f.role, password: f.password }),
      () => { open = false; toast($t('adm.done.add', { user: u })); });
  }
  function submitEdit(e) {
    e.preventDefault();
    const u = dlg.user;
    act(() => api.patch(`/api/admin/users/${u.user_id}`, { display_name: f.display_name.trim(), role: f.role }),
      () => { open = false; toast($t('adm.done.edit', { user: u.username })); if (isMe(u)) onme?.(); });
  }
  const reset = (u) => act(async () => { temp = (await api.post(`/api/admin/users/${u.user_id}/reset-password`)).temporary_password; },
    () => { dlg = { kind: 'reset-done', user: u }; });
  const setActive = (u, active) => act(() => api.patch(`/api/admin/users/${u.user_id}`, { active }),
    () => { open = false; toast($t(active ? 'adm.done.activate' : 'adm.done.deactivate', { user: u.username })); });
  const remove = (u) => act(() => api.del(`/api/admin/users/${u.user_id}`), () => { open = false; toast($t('adm.done.delete', { user: u.username })); });
  async function copy() {
    try { await navigator.clipboard.writeText(temp); toast($t('adm.copied')); } catch { /* izin papan klip ditolak: sandi tetap terlihat untuk disalin manual */ }
  }
  function closed() { temp = ''; dlg = null; }   // sandi sementara dibuang dari memori halaman begitu dialog ditutup

  function items(u) {
    const no = (cond, why) => (cond ? why : null);
    return [
      { label: $t('adm.act.edit'), onpick: () => show('edit', u) },
      { label: $t('adm.act.reset'), onpick: () => show('reset', u) },
      u.active
        ? { label: $t('adm.act.deactivate'), onpick: () => show('deactivate', u),
            disabled: no(isMe(u), $t('adm.why.self')) || no(lastAdmin(u), $t('adm.why.last_admin')) }
        : { label: $t('adm.act.activate'), onpick: () => setActive(u, true) },
      { label: $t('adm.act.delete'), danger: true, onpick: () => show('delete', u),
        disabled: no(isMe(u), $t('adm.why.self')) || no(lastAdmin(u), $t('adm.why.last_admin')) },
    ];
  }
  const title = $derived(dlg && $t(`adm.dlg.${dlg.kind}`, { user: dlg.user?.username ?? '' }));
</script>

{#if error && !users}
  <ErrorState {error} onretry={load} />
{:else if !users}
  <Skeleton kpis={0} charts={1} />
{:else}
  <div class="bar">
    <p class="muted">{$t('adm.count', { n: users.length, a: activeAdmins })}</p>
    <button bind:this={addBtn} class="btn primary add" onclick={() => show('add')}><span aria-hidden="true">+</span> {$t('adm.add')}</button>
  </div>
  <div class="grid">
    <DataTable title={$t('menu.users')} rows={users} limit={500} columns={[
      { key: 'username', label: $t('adm.col.username'), custom: true, sort: true },
      { key: 'display_name', label: $t('adm.col.display_name'), sort: true },
      { key: 'role', label: $t('adm.col.role'), custom: true, sort: true },
      { key: 'active', label: $t('col.status'), custom: true, sort: true },
      { key: 'last_login_at', label: $t('adm.col.last_login'), fmt: (r) => (r.last_login_at ? tWIB(utcToWib(r.last_login_at), $lang) : '–'), cls: () => 'nowrap', sort: true },
      { key: 'actions', label: $t('adm.col.actions'), custom: true },
    ]}>
      {#snippet cell(r, c)}
        {#if c.key === 'username'}<b class="nowrap">{r.username}</b>{#if isMe(r)}{' '}<span class="muted small">({$t('adm.you')})</span>{/if}
        {:else if c.key === 'role'}{#if r.role === 'admin'}<SeverityTag level={1} text={$t('role.admin')} />{:else}{$t('role.user')}{/if}
        {:else if c.key === 'active'}{#if r.active}<SeverityTag level="ok" text={$t('adm.active')} />{:else}<span class="muted">{$t('adm.inactive')}</span>{/if}{#if r.locked}{' '}<SeverityTag level={2} text={$t('adm.locked')} />{/if}{#if r.must_change_password && r.active}<div class="muted small">{$t('adm.must_change')}</div>{/if}
        {:else}<RowMenu label={$t('adm.actions_for', { user: r.username })} items={items(r)} />{/if}
      {/snippet}
    </DataTable>
  </div>
{/if}

<Dialog bind:open {title} onclose={closed} returnFocus={addBtn}>
  {#if dlg?.kind === 'add' || dlg?.kind === 'edit'}
    {@const add = dlg.kind === 'add'}
    {@const roleLocked = !add && lastAdmin(dlg.user)}
    <form onsubmit={add ? submitAdd : submitEdit} novalidate>
      {#if add}
        <label for="u-name">{$t('adm.col.username')}</label>
        <input id="u-name" type="text" autocomplete="off" autocapitalize="none" spellcheck="false" bind:value={f.username}
          aria-invalid={!!errs.username} aria-describedby="u-name-r{errs.username ? ' u-name-e' : ''}" />
        <p id="u-name-r" class="muted rule">{$t('adm.rule.username')}</p>
        {#if errs.username}<p id="u-name-e" class="err">{errs.username}</p>{/if}
      {/if}
      <label for="u-disp">{$t('adm.col.display_name')}</label>
      <input id="u-disp" type="text" autocomplete="off" bind:value={f.display_name} maxlength="80" />
      <fieldset disabled={roleLocked} aria-describedby={roleLocked ? 'u-role-lock' : undefined}>
        <legend>{$t('adm.col.role')}</legend>
        <label class="radio"><input type="radio" name="role" value="user" bind:group={f.role} /> {$t('role.user')}</label>
        <label class="radio"><input type="radio" name="role" value="admin" bind:group={f.role} /> {$t('role.admin')}</label>
        <p class="muted rule">{$t('adm.rule.role_user')}<br />{$t('adm.rule.role_admin')}</p>
        {#if roleLocked}<p id="u-role-lock" class="muted rule">{$t('adm.why.last_admin')}</p>{/if}
      </fieldset>
      {#if add}
        <label for="u-pw">{$t('adm.initial_password')}</label>
        <div class="row">
          <input id="u-pw" type="text" autocomplete="off" autocapitalize="none" spellcheck="false" bind:value={f.password}
            aria-invalid={!!errs.password} aria-describedby="u-pw-r{errs.password ? ' u-pw-e' : ''}" />
          <button type="button" class="btn" onclick={randomPassword}>{$t('adm.random')}</button>
        </div>
        <p id="u-pw-r" class="muted rule">{$t('adm.rule.password', { n: PW_MIN })}</p>
        {#if errs.password}<p id="u-pw-e" class="err">{errs.password}</p>{/if}
      {/if}
      {#if general}<p class="err" role="alert">{general}</p>{/if}
      <div class="acts">
        <button class="btn primary" type="submit" disabled={busy}>{busy ? $t('action.saving') : $t('action.save')}</button>
        <button class="btn" type="button" onclick={() => (open = false)}>{$t('action.cancel')}</button>
      </div>
    </form>
  {:else if dlg?.kind === 'reset'}
    <p>{$t('adm.confirm.reset', { user: dlg.user.username })}</p>
    {#if general}<p class="err" role="alert">{general}</p>{/if}
    <div class="acts">
      <button class="btn primary" disabled={busy} onclick={() => reset(dlg.user)}>{$t('adm.act.reset')}</button>
      <button class="btn" onclick={() => (open = false)}>{$t('action.cancel')}</button>
    </div>
  {:else if dlg?.kind === 'reset-done'}
    <p>{$t('adm.temp_for', { user: dlg.user.username })}</p>
    <div class="row temp">
      <code class="pw" aria-label={$t('adm.temp_label')}>{temp}</code>
      <button class="btn" onclick={copy}>{$t('adm.copy')}</button>
    </div>
    <p class="warnline" role="note">{$t('adm.temp_once')}</p>
    <div class="acts"><button class="btn primary" onclick={() => (open = false)}>{$t('adm.done_btn')}</button></div>
  {:else if dlg?.kind === 'deactivate' || dlg?.kind === 'delete'}
    {@const del = dlg.kind === 'delete'}
    <p>{$t(del ? 'adm.confirm.delete' : 'adm.confirm.deactivate', { user: dlg.user.username })}</p>
    {#if general}<p class="err" role="alert">{general}</p>{/if}
    <div class="acts">
      <button class="btn danger" disabled={busy} onclick={() => (del ? remove(dlg.user) : setActive(dlg.user, false))}>
        {$t(del ? 'adm.act.delete' : 'adm.act.deactivate')}</button>
      <button class="btn" onclick={() => (open = false)}>{$t('action.cancel')}</button>
    </div>
  {/if}
</Dialog>

<style>
  .bar { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 14px; }
  .bar p { font-size: 0.875rem; }
  .small { font-size: 0.75rem; }
  form { display: flex; flex-direction: column; gap: 4px; }
  label { font-size: 0.8125rem; color: var(--kpi-label); margin-top: 12px; }
  input[type='text'] { width: 100%; border-radius: 12px; min-height: var(--touch); font-size: 1rem; }
  input[aria-invalid='true'] { border-color: var(--err); }
  fieldset { border: 0; padding: 0; margin: 12px 0 0; min-width: 0; }
  legend { font-size: 0.8125rem; color: var(--kpi-label); }
  .radio { display: inline-flex; align-items: center; gap: 8px; margin: 8px 18px 0 0; min-height: var(--touch); color: var(--fg); font-size: 0.9375rem; }
  .radio input { width: 18px; height: 18px; accent-color: var(--accent); }
  fieldset:disabled .radio { opacity: 0.6; }
  .rule { font-size: 0.8125rem; margin: 4px 0 0; }
  .err { color: var(--err); font-size: 0.8125rem; margin: 6px 0 0; }
  .row { display: flex; gap: 8px; align-items: center; }
  .row input { flex: 1; min-width: 0; }
  .acts { display: flex; gap: 10px; margin-top: 18px; flex-wrap: wrap; }
  .acts .btn { min-height: var(--touch); }
  .temp { margin: 12px 0 8px; }
  .pw { flex: 1; font-size: 1.0625rem; padding: 10px 14px; border-radius: 12px; background: var(--bg2); border: 1px solid var(--line-strong); word-break: break-all; user-select: all; }
  .warnline { color: var(--warn); font-size: 0.8125rem; }
  .btn.danger { border-color: var(--err); color: var(--err); }
  @media (max-width: 560px) {
    .add { position: fixed; left: 16px; right: 16px; bottom: 16px; z-index: 30; min-height: var(--touch); box-shadow: var(--glow); }
    .grid { padding-bottom: 72px; }
  }
</style>
