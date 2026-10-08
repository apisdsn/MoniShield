<!-- Change password (DRD §3.11): rules are stated before typing; per-field errors below the field (aria-describedby).
     forced = required (first login / after reset): shown alone, without "Batal"; the only other way out is "Keluar".
     embedded = inside the account dialog (lib/AccountDialogs.svelte), which supplies the card and the title. -->
<script>
  import { srv, errText } from '../srv.js';
  import { t } from '../i18n.js';
  import { api } from '../api.js';
  import { toast } from '../lib/Toast.svelte';
  import Note from '../lib/Note.svelte';
  let { forced = false, embedded = false, ondone, oncancel = null, onlogout = null } = $props();

  const MIN = 12;
  let old = $state(''), nw = $state(''), again = $state(''), busy = $state(false);
  let errs = $state({}), general = $state(null);

  async function submit(e) {
    e.preventDefault();
    errs = {}; general = null;
    if (!old) errs.old = $t('pw.required');
    if (nw.length < MIN) errs.nw = $t('pw.too_short', { n: MIN });
    else if (nw === old) errs.nw = $t('pw.same');
    if (again !== nw) errs.again = $t('pw.mismatch');
    if (Object.keys(errs).length) return;
    busy = true;
    try {
      await api.post('/api/me/password', { old_password: old, new_password: nw });
      old = nw = again = '';
      toast($t('pw.done'));
      ondone();
    } catch (err) {
      if (err.code === 'wrong_password') errs = { old: $t('pw.wrong') };
      else if (err.code === 'invalid_password') errs = { nw: $errText(err) };
      else general = err.status === 0 ? $t('state.error_network') : $t('state.error_text');
    } finally {
      busy = false;
    }
  }
</script>

<div class:screen={forced}>
  <section class="pwc" class:card={!embedded} aria-labelledby={embedded ? undefined : 'pw-title'}>
    {#if forced}<h1 id="pw-title">{$t('pw.title')}</h1>{:else if !embedded}<h2 id="pw-title" class="sr-only">{$t('pw.title')}</h2>{/if}
    {#if forced}<Note wide={false}>{$t('pw.forced')}</Note>{/if}
    <form onsubmit={submit} novalidate>
      <label for="pw-old">{$t('pw.old')}</label>
      <input id="pw-old" type="password" autocomplete="current-password" bind:value={old} aria-invalid={!!errs.old} aria-describedby={errs.old ? 'pw-old-e' : undefined} />
      {#if errs.old}<p id="pw-old-e" class="err">{errs.old}</p>{/if}

      <label for="pw-new">{$t('pw.new')}</label>
      <input id="pw-new" type="password" autocomplete="new-password" bind:value={nw} aria-invalid={!!errs.nw} aria-describedby="pw-rule{errs.nw ? ' pw-new-e' : ''}" />
      <p id="pw-rule" class="muted rule">{$t('pw.rule', { n: MIN })}</p>
      {#if errs.nw}<p id="pw-new-e" class="err">{errs.nw}</p>{/if}

      <label for="pw-again">{$t('pw.again')}</label>
      <input id="pw-again" type="password" autocomplete="new-password" bind:value={again} aria-invalid={!!errs.again} aria-describedby={errs.again ? 'pw-again-e' : undefined} />
      {#if errs.again}<p id="pw-again-e" class="err">{errs.again}</p>{/if}

      {#if general}<p class="err" role="alert">{general}</p>{/if}
      <div class="acts">
        <button class="btn primary" type="submit" disabled={busy}>{busy ? $t('action.saving') : $t('action.save')}</button>
        {#if !forced && oncancel}<button class="btn" type="button" onclick={oncancel}>{$t('action.cancel')}</button>{/if}
        {#if forced && onlogout}<button class="btn" type="button" onclick={onlogout}>{$t('menu.logout')}</button>{/if}
      </div>
    </form>
  </section>
</div>

<style>
  .screen { min-height: 100vh; display: grid; place-items: center; padding: 32px 16px; }
  .pwc { width: 100%; max-width: 520px; }
  h1 { font-size: 1.5rem; font-weight: 600; margin-bottom: 14px; color: var(--heading); }
  .pwc :global(.note) { margin-bottom: 14px; }
  form { display: flex; flex-direction: column; gap: 4px; }
  label { font-size: 0.8125rem; color: var(--kpi-label); margin-top: 12px; }
  input { width: 100%; border-radius: 12px; min-height: var(--touch); font-size: 1rem; }
  input[aria-invalid='true'] { border-color: var(--err); }
  .rule { font-size: 0.8125rem; margin: 4px 0 0; }
  .err { color: var(--err); font-size: 0.8125rem; margin: 4px 0 0; }
  .acts { display: flex; gap: 10px; margin-top: 18px; flex-wrap: wrap; }
  .acts .btn { min-height: var(--touch); }
</style>
