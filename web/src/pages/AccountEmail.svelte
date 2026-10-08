<!-- Own account email (owner request 2026-10-08; API /api/me/email, monishield/application/account_service.py).
     Changing it needs the current password, a code sent to the CURRENT email (when there is one) and a code sent to
     the NEW email, so a stolen session alone cannot move the account to another address.
     embedded = inside the account dialog (lib/AccountDialogs.svelte), which supplies the card and the title. -->
<script>
  import { onMount, tick } from 'svelte';
  import { lang, t } from '../i18n.js';
  import { api } from '../api.js';
  import { errText } from '../srv.js';
  import { toast } from '../lib/Toast.svelte';
  import Icon from '../lib/Icon.svelte';
  import Note from '../lib/Note.svelte';
  import Skeleton from '../lib/Skeleton.svelte';
  let { ondone = null, embedded = false } = $props();

  let v = $state.raw(null), busy = $state(false), err = $state(null), sentOld = $state(''), sentNew = $state('');
  let f = $state({ email: '', password: '', old: '', nw: '' });
  let codeEl = $state();
  async function load() { try { v = await api.get('/api/me/email'); err = null; } catch (e) { err = $errText(e); } }
  onMount(load);

  const EMAIL = /^[^@\s<>(),;:"[\]]{1,64}@[A-Za-z0-9-]{1,63}(\.[A-Za-z0-9-]{1,63})*\.[A-Za-z]{2,24}$/;
  async function start(e) {
    e.preventDefault();
    err = null;
    if (!EMAIL.test(f.email.trim())) { err = $t('adm.err.invalid_email'); return; }
    if (!f.password) { err = $t('pw.required'); return; }
    busy = true;
    try {
      const r = await api.post('/api/me/email/start', { new_email: f.email.trim(), password: f.password, lang: $lang });
      v = r; sentOld = r.sent_old || ''; sentNew = r.sent_new; f.password = ''; f.old = ''; f.nw = '';
      await tick(); codeEl?.focus();
    } catch (e2) { err = $errText(e2); } finally { busy = false; }
  }
  async function confirm(e) {
    e.preventDefault();
    err = null; busy = true;
    try {
      v = await api.post('/api/me/email/confirm', { old_code: f.old.trim(), new_code: f.nw.trim(), lang: $lang });
      f = { email: '', password: '', old: '', nw: '' };
      toast($t('em.done', { email: v.email })); ondone?.();
    } catch (e2) { err = $errText(e2); if (e2.code === 'too_many_attempts' || e2.code === 'email_change_missing') await load(); }
    finally { busy = false; }
  }
  async function cancel() { busy = true; try { v = await api.del('/api/me/email/start'); err = null; } catch (e2) { err = $errText(e2); } finally { busy = false; } }
  const digits = (s) => s.replace(/\D/g, '').slice(0, 6);
</script>

{#if !v && !err}
  {#if embedded}<p class="muted" role="status">{$t('state.loading')}</p>{:else}<Skeleton kpis={0} charts={1} />{/if}
{:else}
  <section class="em" class:card={!embedded} aria-labelledby={embedded ? undefined : 'em-h'}>
    {#if !embedded}<h2 id="em-h">{$t('em.change')}</h2>{/if}
    <p class="cur"><Icon name="mail" /><span>{$t('em.current')}</span>
      <b>{v?.email || $t('em.none')}</b></p>
    <p class="muted small">{$t('em.why')}</p>

    {#if v && !v.mail_ready}
      <Note wide={false}>{$t('em.no_mail')}</Note>
    {:else if v?.pending}
      <form onsubmit={confirm} novalidate>
        <p class="small">{v.pending.needs_old ? $t('em.sent_both', { old: sentOld || $t('em.old_addr'), new: v.pending.new_email }) : $t('em.sent_new', { new: v.pending.new_email })}</p>
        {#if v.pending.needs_old}
          <label for="em-old">{$t('em.code_old')}</label>
          <input id="em-old" bind:this={codeEl} inputmode="numeric" autocomplete="one-time-code" maxlength="6" value={f.old} oninput={(e) => (f.old = e.currentTarget.value = digits(e.currentTarget.value))} />
        {/if}
        <label for="em-new">{$t('em.code_new')}</label>
        {#if v.pending.needs_old}
          <input id="em-new" inputmode="numeric" autocomplete="one-time-code" maxlength="6" value={f.nw} oninput={(e) => (f.nw = e.currentTarget.value = digits(e.currentTarget.value))} />
        {:else}
          <input id="em-new" bind:this={codeEl} inputmode="numeric" autocomplete="one-time-code" maxlength="6" value={f.nw} oninput={(e) => (f.nw = e.currentTarget.value = digits(e.currentTarget.value))} />
        {/if}
        <p class="muted small">{$t('em.code_help')}</p>
        {#if err}<p class="err" role="alert">{err}</p>{/if}
        <div class="acts">
          <button class="btn primary" type="submit" disabled={busy || f.nw.length !== 6 || (v.pending.needs_old && f.old.length !== 6)}>{busy ? $t('action.saving') : $t('em.confirm')}</button>
          <button class="btn" type="button" disabled={busy} onclick={cancel}>{$t('action.cancel')}</button>
        </div>
      </form>
    {:else}
      <form onsubmit={start} novalidate>
        <label for="em-email">{$t('em.new')}</label>
        <input id="em-email" type="email" autocomplete="email" autocapitalize="none" spellcheck="false" maxlength="254" bind:value={f.email} placeholder="nama@contoh.go.id" />
        <label for="em-pw">{$t('pw.old')}</label>
        <input id="em-pw" type="password" autocomplete="current-password" bind:value={f.password} />
        <ol class="steps small">
          <li>{$t('em.step1')}</li>
          {#if v?.email}<li>{$t('em.step2')}</li>{/if}
          <li>{v?.email ? $t('em.step3') : $t('em.step3_one')}</li>
        </ol>
        {#if err}<p class="err" role="alert">{err}</p>{/if}
        <div class="acts">
          <button class="btn primary" type="submit" disabled={busy}>{busy ? $t('forgot.sending') : $t('em.send')}</button>
          {#if embedded}<button class="btn" type="button" onclick={() => ondone?.()}>{$t('action.cancel')}</button>{/if}
        </div>
      </form>
    {/if}
  </section>
{/if}

<style>
  .em { max-width: 560px; }
  h2 { font-size: 1rem; font-weight: 600; color: var(--heading); margin-bottom: 10px; }
  .cur { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin: 0 0 6px; }
  .cur :global(svg) { color: var(--muted); }
  .cur b { word-break: break-all; }
  .small { font-size: 0.8125rem; margin: 6px 0 0; }
  form { display: flex; flex-direction: column; gap: 4px; margin-top: 10px; }
  label { font-size: 0.8125rem; color: var(--kpi-label); margin-top: 12px; }
  input { width: 100%; border-radius: 12px; min-height: var(--touch); font-size: 1rem; }
  input[inputmode='numeric'] { padding-left: 14px; font-family: var(--mono, ui-monospace, monospace); letter-spacing: 0.3em; font-size: 1.125rem; }
  .steps { margin: 12px 0 0; padding-left: 20px; color: var(--muted); display: flex; flex-direction: column; gap: 2px; }
  .err { color: var(--err); font-size: 0.8125rem; margin: 8px 0 0; }
  .acts { display: flex; gap: 10px; margin-top: 16px; flex-wrap: wrap; }
  .acts .btn { min-height: var(--touch); }
  .em :global(.note) { margin-top: 12px; }
</style>
