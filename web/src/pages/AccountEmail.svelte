<!-- Own account email (owner request 2026-10-08; API /api/me/email, monishield/application/account_service.py).
     Changing it needs the current password, a code sent to the CURRENT email (when there is one) and a code sent to
     the NEW email, so a stolen session alone cannot move the account to another address.
     embedded = inside the account dialog (lib/AccountDialogs.svelte), which supplies the card and the title. -->
<script>
  import { onMount, tick, untrack } from 'svelte';
  import { lang, t } from '../i18n.js';
  import { api } from '../api.js';
  import { errText } from '../srv.js';
  import { toast } from '../lib/Toast.svelte';
  import Icon from '../lib/Icon.svelte';
  import OtpInput from '../lib/OtpInput.svelte';
  import Note from '../lib/Note.svelte';
  import Skeleton from '../lib/Skeleton.svelte';
  let { ondone = null, embedded = false } = $props();

  let v = $state.raw(null), busy = $state(false), err = $state(null), wrong = $state(false);
  let f = $state({ email: '', password: '', old: '', nw: '' });
  let oldEl = $state(), newEl = $state();
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
      v = r; f.password = ''; f.old = ''; f.nw = ''; wrong = false;
      await tick(); (r.pending?.needs_old ? oldEl : newEl)?.focus();
    } catch (e2) { err = $errText(e2); } finally { busy = false; }
  }
  async function confirm(e) {
    e.preventDefault();
    if (!ready) return;
    err = null; busy = true;
    try {
      v = await api.post('/api/me/email/confirm', { old_code: f.old.trim(), new_code: f.nw.trim(), lang: $lang });
      f = { email: '', password: '', old: '', nw: '' };
      toast($t('em.done', { email: v.email })); ondone?.();
    } catch (e2) {
      err = $errText(e2); wrong = e2.code === 'wrong_code';
      if (e2.code === 'too_many_attempts' || e2.code === 'email_change_missing') await load();
      else if (wrong) { busy = false; await tick(); const el = v.pending?.needs_old ? oldEl : newEl; el?.focus(); el?.select(); }
    } finally { busy = false; }
  }
  async function cancel() { busy = true; try { v = await api.del('/api/me/email/start'); err = null; } catch (e2) { err = $errText(e2); } finally { busy = false; } }
  const ready = $derived(!!v?.pending && f.nw.length === 6 && (!v.pending.needs_old || f.old.length === 6));
  $effect(() => { void f.old; void f.nw; untrack(() => { if (wrong) { wrong = false; err = null; } }); });   // typing clears the red boxes and the message
</script>

{#if !v && !err}
  {#if embedded}<p class="muted" role="status">{$t('state.loading')}</p>{:else}<Skeleton kpis={0} charts={1} />{/if}
{:else}
  <section class="em" class:card={!embedded} aria-labelledby={embedded ? undefined : 'em-h'}>
    {#if !embedded}<h2 id="em-h">{$t('em.change')}</h2>{/if}
    <p class="cur"><Icon name="mail" /><span>{$t('em.current')}</span>
      <b>{v?.email || $t('em.none')}</b></p>
    {#if !v?.pending}<p class="muted small">{$t('em.why')}</p>{/if}

    {#if v && !v.mail_ready}
      <Note wide={false}>{$t('em.no_mail')}</Note>
    {:else if v?.pending}
      <form class="codes" onsubmit={confirm} novalidate>
        <p class="lead">{v.pending.needs_old ? $t('em.enter_both') : $t('em.enter_one')}</p>
        {#if v.pending.needs_old}
          <div class="codebox">
            <div class="ch"><span class="ic"><Icon name="mail" /></span>
              <span><label for="em-old">{$t('em.code_old')}</label><span class="addr">{$t('em.sent_to', { email: v.email })}</span></span></div>
            <OtpInput id="em-old" bind:value={f.old} bind:ref={oldEl} invalid={wrong} describedby="em-help"
              oncomplete={() => (f.nw.length === 6 ? null : newEl?.focus())} />
          </div>
        {/if}
        <div class="codebox">
          <div class="ch"><span class="ic"><Icon name="mail" /></span>
            <span><label for="em-new">{$t('em.code_new')}</label><span class="addr">{$t('em.sent_to', { email: v.pending.new_email })}</span></span></div>
          <OtpInput id="em-new" bind:value={f.nw} bind:ref={newEl} invalid={wrong} describedby="em-help" />
        </div>
        <p id="em-help" class="muted small">{$t('em.code_help')}</p>
        {#if err}<p class="err" role="alert">{err}</p>{/if}
        <div class="acts">
          <button class="btn primary" type="submit" disabled={busy || !ready}>{busy ? $t('action.saving') : $t('em.confirm')}</button>
          <button class="btn" type="button" disabled={busy} onclick={cancel}>{$t('em.restart')}</button>
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
  .lead { margin: 4px 0 6px; }
  .codebox { display: flex; flex-direction: column; gap: 10px; padding: 14px; margin-top: 8px; border: 1px solid var(--line); border-radius: 14px;
    background: color-mix(in srgb, var(--accent) 4%, transparent); }
  .ch { display: flex; align-items: center; gap: 10px; min-width: 0; }
  .ch > span:last-child { display: flex; flex-direction: column; min-width: 0; }
  .ch label { margin: 0; color: var(--heading); font-weight: 600; font-size: 0.875rem; }
  .ic { flex: none; width: 32px; height: 32px; border-radius: 10px; display: grid; place-items: center;
    background: color-mix(in srgb, var(--accent) 14%, transparent); color: var(--accent-text); }
  .addr { font-size: 0.8125rem; color: var(--muted); word-break: break-all; }
  .codes .acts .btn { flex: 1 1 140px; }
  .steps { margin: 12px 0 0; padding-left: 20px; color: var(--muted); display: flex; flex-direction: column; gap: 2px; }
  .err { color: var(--err); font-size: 0.8125rem; margin: 8px 0 0; }
  .acts { display: flex; gap: 10px; margin-top: 16px; flex-wrap: wrap; }
  .acts .btn { min-height: var(--touch); }
  .em :global(.note) { margin-top: 12px; }
</style>
