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
    <div class="brand">
      <svg class="shield" viewBox="0 0 32 32" aria-hidden="true">
        <path class="s" d="M16 2l12 4.5v8.2c0 7.3-5 13.4-12 15.3C9 28.1 4 22 4 14.7V6.5z" />
        <path class="m" d="M10 21V11l6 6 6-6v10" />
      </svg>
      <h1>{APP_NAME}</h1>
      <p class="tag">{$t('login.tagline')}</p>
    </div>
    <p class="welcome">{$t('login.welcome')}</p>
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
  /* identitas aplikasi (Tahap 25): perisai + nama MoniShield + keterangan, di tengah atas kartu */
  .brand { display: flex; flex-direction: column; align-items: center; text-align: center; gap: 6px; margin-bottom: 18px; }
  .shield { width: 60px; height: 60px; filter: drop-shadow(0 0 16px rgba(45, 212, 191, 0.3)); }
  .shield .s { fill: var(--accent); }
  .shield .m { fill: none; stroke: var(--brand-fg); stroke-width: 2.6; stroke-linecap: round; stroke-linejoin: round; }
  h1 { font-size: 1.75rem; font-weight: 700; letter-spacing: 0.01em; color: var(--heading); margin-top: 4px; }
  .tag { margin: 0; font-size: 0.8125rem; color: var(--muted); }
  .welcome { margin: 0 0 14px; padding-top: 14px; border-top: 1px solid var(--line); font-size: 0.875rem; font-weight: 600; color: var(--fg); }
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
