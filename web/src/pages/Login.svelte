<!-- Layar Masuk (DRD §3.11, §6.9): satu kartu di tengah, tanpa sidebar; bahasa dan tema bisa diganti di sini.
     Pesan gagal satu kalimat yang sama untuk nama maupun sandi salah; role="alert" dan fokus kembali ke sandi. -->
<script>
  import { tick } from 'svelte';
  import { lang, t } from '../i18n.js';
  import { theme } from '../theme.js';
  import { api } from '../api.js';
  import { APP_NAME } from '../brand.js';
  let { expired = false, onlogin } = $props();

  let username = $state(''), password = $state(''), reveal = $state(false), busy = $state(false), error = $state(null);
  let pw = $state();

  async function submit(e) {
    e.preventDefault();
    busy = true; error = null;
    try {
      const me = await api.post('/api/auth/login', { username: username.trim(), password });
      password = '';
      onlogin(me);
    } catch (err) {
      const menit = /(\d+)\s*menit/.exec(err.message || '')?.[1];
      error = err.code === 'too_many_attempts' ? (menit ? $t('login.too_many', { n: menit }) : $t('login.too_many_soon'))
        : err.code === 'invalid_credentials' ? $t('login.invalid')
        : err.status === 0 ? $t('state.error_network') : $t('state.error_text');
      password = '';
      await tick();
      pw?.focus();
    } finally {
      busy = false;
    }
  }
</script>

<div class="screen">
  <div class="prefs">
    <div class="seg" role="radiogroup" aria-label={$t('ui.language')}>
      <button role="radio" aria-checked={$lang === 'id'} onclick={() => lang.set('id')}>ID</button>
      <button role="radio" aria-checked={$lang === 'en'} onclick={() => lang.set('en')}>EN</button>
    </div>
    <div class="seg" role="radiogroup" aria-label={$t('ui.theme')}>
      <button role="radio" aria-checked={$theme === 'light'} onclick={() => theme.set('light')} aria-label={$t('theme.light')}>☀</button>
      <button role="radio" aria-checked={$theme === 'dark'} onclick={() => theme.set('dark')} aria-label={$t('theme.dark')}>☾</button>
    </div>
  </div>
  <main id="main" class="card login">
    <div class="logo"><i aria-hidden="true">S4</i><h1>{APP_NAME}</h1></div>
    {#if expired}<p class="info" role="status">{$t('login.expired')}</p>{/if}
    <form onsubmit={submit} novalidate>
      <label for="u">{$t('login.username')}</label>
      <input id="u" type="text" autocomplete="username" autocapitalize="none" spellcheck="false" bind:value={username} required />
      <label for="p">{$t('login.password')}</label>
      <div class="pw">
        <input id="p" bind:this={pw} type={reveal ? 'text' : 'password'} autocomplete="current-password" bind:value={password} required
          aria-describedby={error ? 'login-err' : undefined} />
        <button type="button" class="icon-btn eye" onclick={() => (reveal = !reveal)} aria-pressed={reveal}
          aria-label={reveal ? $t('login.hide') : $t('login.show')}>{reveal ? '◉' : '👁'}</button>
      </div>
      {#if error}<p id="login-err" class="err" role="alert">{error}</p>{/if}
      <button class="btn primary submit" type="submit" disabled={busy}>{busy ? $t('login.checking') : $t('login.submit')}</button>
      <p class="muted hint">{$t('login.forgot')}</p>
    </form>
  </main>
</div>

<style>
  .screen { min-height: 100vh; display: grid; place-items: center; padding: 72px 16px 32px; position: relative; }
  .prefs { position: absolute; top: 16px; left: 16px; display: flex; gap: 8px; }
  .login { width: 100%; max-width: 380px; padding: 28px 26px; }
  .logo { display: flex; align-items: center; gap: 10px; margin-bottom: 18px; }
  .logo i {
    width: 38px; height: 38px; border-radius: 12px; display: grid; place-items: center; font-style: normal; font-weight: 700;
    color: var(--brand-fg); background: var(--brand-bg); box-shadow: 0 0 18px rgba(45, 212, 191, 0.25);
  }
  h1 { font-size: 1.25rem; font-weight: 600; }
  form { display: flex; flex-direction: column; gap: 6px; }
  label { font-size: 0.8125rem; color: var(--kpi-label); margin-top: 8px; }
  input { width: 100%; border-radius: 12px; min-height: var(--touch); font-size: 1rem; }
  .pw { display: flex; gap: 8px; }
  .eye { flex: none; }
  .err { color: var(--err); margin: 10px 0 0; padding-left: 10px; box-shadow: inset 3px 0 0 var(--err); }
  .info { color: var(--accent-text); margin: 0 0 6px; padding-left: 10px; box-shadow: inset 3px 0 0 var(--accent); }
  .submit { margin-top: 16px; min-height: var(--touch); width: 100%; font-size: 0.9375rem; }
  .hint { font-size: 0.8125rem; margin: 10px 0 0; }
</style>
