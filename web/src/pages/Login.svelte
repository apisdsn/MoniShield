<!-- Layar Masuk (DRD §3.11, §6.9): satu kartu di tengah, tanpa sidebar; bahasa dan tema bisa diganti di sini.
     Pesan gagal satu kalimat yang sama untuk nama maupun sandi salah; role="alert" dan fokus kembali ke sandi. -->
<script>
  import { tick } from 'svelte';
  import { lang, t } from '../i18n.js';
  import { theme } from '../theme.js';
  import { api } from '../api.js';
  import { APP_NAME } from '../brand.js';
  let { expired = false, onlogin } = $props();

  let username = $state(''), password = $state(''), busy = $state(false), error = $state(null);
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
  <!-- perisai besar di belakang form (desain pemilik 2026-10-07): garis tepi teal tebal, isi gelap bernuansa teal -->
  <svg class="bgshield" viewBox="0 0 100 120" aria-hidden="true" focusable="false">
    <path d="M50 4C61 12 78 16.5 95 17.5V54C95 85 75 104 50 116C25 104 5 85 5 54V17.5C22 16.5 39 12 50 4Z" />
  </svg>
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
      <span class="tile" aria-hidden="true">
        <svg viewBox="0 0 24 24" focusable="false">
          <path class="ln" d="M5.5 4h13A1.5 1.5 0 0 1 20 5.5V16H4V5.5A1.5 1.5 0 0 1 5.5 4zM2 19h5.5M16.5 19H22" />
          <path class="sh" d="M12 7.2l4.6 1.7v3.2c0 3-2 5.3-4.6 6.3-2.6-1-4.6-3.3-4.6-6.3V8.9z" />
          <path class="kh" d="M12 10.4a1.35 1.35 0 0 1 .7 2.5l.4 2.4h-2.2l.4-2.4a1.35 1.35 0 0 1 .7-2.5z" />
        </svg>
      </span>
      <h1>SIMPeL4 {APP_NAME}</h1>
    </div>
    {#if expired}<p class="info" role="status">{$t('login.expired')}</p>{/if}
    <form onsubmit={submit} novalidate>
      <label for="u">{$t('login.username')}</label>
      <input id="u" type="text" autocomplete="username" autocapitalize="none" spellcheck="false" bind:value={username} required />
      <label for="p">{$t('login.password')}</label>
      <input id="p" bind:this={pw} type="password" autocomplete="current-password" bind:value={password} required
        aria-describedby={error ? 'login-err' : undefined} />
      {#if error}<p id="login-err" class="err" role="alert">{error}</p>{/if}
      <button class="btn primary submit" type="submit" disabled={busy}>{busy ? $t('login.checking') : $t('login.submit')}</button>
      <p class="muted hint">{$t('login.forgot')}</p>
    </form>
  </main>
</div>

<style>
  .screen { min-height: 100vh; display: grid; place-items: center; padding: 72px 16px 32px; position: relative; overflow: hidden; }
  .prefs { position: absolute; top: 16px; left: 16px; display: flex; gap: 8px; z-index: 2; }
  /* perisai latar: tidak transparan; ukurannya mengikuti layar, kartu login di tengahnya */
  .bgshield {
    position: absolute; left: 50%; top: 50%; transform: translate(-50%, -50%); z-index: 0; pointer-events: none;
    width: clamp(340px, 46vw, 620px); height: auto; overflow: visible;
    filter: drop-shadow(0 0 60px color-mix(in srgb, var(--accent) 22%, transparent));
  }
  .bgshield path {
    fill: color-mix(in srgb, var(--accent) 7%, var(--bg)); stroke: color-mix(in srgb, var(--accent) 40%, var(--bg));
    stroke-width: 4.2; stroke-linejoin: round;
  }
  @media (max-width: 600px) { .bgshield { width: 150vw; } }   /* ponsel: perisai lebih lebar dari kartu agar puncak/ujungnya terlihat */
  .login { position: relative; z-index: 1; width: 100%; max-width: 380px; padding: 28px 26px; }
  .brand { display: flex; flex-direction: column; align-items: center; text-align: center; gap: 14px; margin-bottom: 14px; }
  .tile {
    width: 76px; height: 76px; border-radius: 22px; display: grid; place-items: center;
    background: linear-gradient(145deg, var(--accent), color-mix(in srgb, var(--accent) 78%, #0b3d38));
    box-shadow: 0 0 28px color-mix(in srgb, var(--accent) 40%, transparent);
  }
  .tile svg { width: 56px; height: 56px; }
  .tile .ln { fill: none; stroke: var(--brand-fg); stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; }
  .tile .sh { fill: var(--brand-fg); }
  .tile .kh { fill: var(--accent); }
  h1 { font-size: 1.5rem; font-weight: 700; letter-spacing: 0.005em; color: var(--heading); }
  form { display: flex; flex-direction: column; gap: 6px; }
  label { font-size: 0.8125rem; color: var(--kpi-label); margin-top: 8px; }
  input { width: 100%; border-radius: 12px; min-height: var(--touch); font-size: 1rem; }
  .err { color: var(--err); margin: 10px 0 0; padding-left: 10px; box-shadow: inset 3px 0 0 var(--err); }
  .info { color: var(--accent-text); margin: 0 0 6px; padding-left: 10px; box-shadow: inset 3px 0 0 var(--accent); }
  .submit { margin-top: 16px; min-height: var(--touch); width: 100%; font-size: 0.9375rem; }
  .hint { font-size: 0.8125rem; margin: 10px 0 0; }
</style>
