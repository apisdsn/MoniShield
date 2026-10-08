<!-- Notifications (owner request 2026-10-07; API /api/admin/alerts, monishield/alerts.py), admin only.
     Three channels (Telegram, Discord, email): on/off + credentials + "Kirim uji" (send test). Secret fields (bot token, webhook URL,
     SMTP password) are never refilled from the server: shown as "sudah diisi"; left empty on save = not
     changed; "Hapus" removes them. Events sent, message language, dashboard address for links, daily folder check
     time. History of the last 30 sends. Messages never contain IP addresses (project rule). -->
<script>
  import { onMount } from 'svelte';
  import { lang, t } from '../i18n.js';
  import { api } from '../api.js';
  import { tWIB, utcToWib } from '../format.js';
  import { errText } from '../srv.js';
  import { toast } from '../lib/Toast.svelte';
  import DataTable from '../lib/DataTable.svelte';
  import SeverityTag from '../lib/SeverityTag.svelte';
  import Skeleton from '../lib/Skeleton.svelte';
  import ErrorState from '../lib/ErrorState.svelte';

  let v = $state.raw(null), error = $state(null), f = $state(null), busy = $state(false), err = $state(null), testing = $state('');
  // secret fields typed anew (empty = unchanged)
  let sec = $state({ tg_token: '', dc_hook: '', em_pass: '' });

  function fill(r) {
    v = r;
    const c = r.channels;
    f = {
      tg: { enabled: c.telegram.enabled, chat_id: c.telegram.chat_id },
      dc: { enabled: c.discord.enabled },
      em: { enabled: c.email.enabled, host: c.email.host, port: c.email.port, security: c.email.security, username: c.email.username, sender: c.email.sender, to: c.email.to },
      events: { ...r.events }, lang: r.lang, dashboard_url: r.dashboard_url || location.origin, missing_hour: r.missing_hour,
    };
    sec = { tg_token: '', dc_hook: '', em_pass: '' };
  }
  async function load() { try { fill(await api.get('/api/admin/alerts')); error = null; } catch (e) { error = e; } }
  onMount(load);

  const body = (clear = []) => ({
    channels: {
      telegram: { enabled: f.tg.enabled, chat_id: f.tg.chat_id, bot_token: sec.tg_token },
      discord: { enabled: f.dc.enabled, webhook_url: sec.dc_hook },
      email: { ...f.em, port: Number(f.em.port), password: sec.em_pass },
    },
    events: f.events, lang: f.lang, dashboard_url: f.dashboard_url, missing_hour: Number(f.missing_hour), clear,
  });
  async function save(clear = []) {
    err = null; busy = true;
    try { fill(await api.put('/api/admin/alerts', body(clear))); toast($t('al.saved')); }
    catch (e) { err = $errText(e); } finally { busy = false; }
  }
  async function test(ch) {
    err = null; testing = ch;
    await save();                     // the test uses the SAVED settings: save the form first
    if (err) { testing = ''; return; }
    try { await api.post('/api/admin/alerts/test', { channel: ch }); toast($t('al.test_ok', { ch: $t(`al.ch.${ch}`) })); }
    catch (e) { err = $errText(e); } finally { testing = ''; await load(); }
  }
  const has = (ch, k) => v?.channels[ch][k] === true;
</script>

{#if error && !v}
  <ErrorState {error} onretry={load} />
{:else if !f}
  <Skeleton kpis={0} charts={1} />
{:else}
  <div class="grid">
    <section class="card wide" aria-labelledby="al-h">
      <header><h2 id="al-h">{$t('al.title')}</h2></header>
      <p class="muted small">{$t('al.intro')}</p>

      <form onsubmit={(e) => { e.preventDefault(); save(); }} novalidate>
        <div class="chs">
          <!-- Telegram -->
          <fieldset class="ch">
            <legend><label class="sw"><input type="checkbox" bind:checked={f.tg.enabled} /> {$t('al.ch.telegram')}</label></legend>
            <label for="tg-token">{$t('al.tg.token')}</label>
            <input id="tg-token" type="password" autocomplete="off" spellcheck="false" bind:value={sec.tg_token}
              placeholder={has('telegram', 'bot_token') ? $t('al.secret_set') : '123456789:AA…'} />
            {#if has('telegram', 'bot_token')}<button type="button" class="link" onclick={() => save(['telegram.bot_token'])}>{$t('al.clear')}</button>{/if}
            <label for="tg-chat">{$t('al.tg.chat')}</label>
            <input id="tg-chat" type="text" autocomplete="off" bind:value={f.tg.chat_id} placeholder="-1001234567890" />
            <p class="muted xs">{$t('al.tg.help')}</p>
            <button type="button" class="btn sm" onclick={() => test('telegram')} disabled={testing !== '' || !(has('telegram', 'bot_token') || sec.tg_token)}>{testing === 'telegram' ? $t('al.testing') : $t('al.test')}</button>
          </fieldset>
          <!-- Discord -->
          <fieldset class="ch">
            <legend><label class="sw"><input type="checkbox" bind:checked={f.dc.enabled} /> {$t('al.ch.discord')}</label></legend>
            <label for="dc-hook">{$t('al.dc.hook')}</label>
            <input id="dc-hook" type="password" autocomplete="off" spellcheck="false" bind:value={sec.dc_hook}
              placeholder={has('discord', 'webhook_url') ? $t('al.secret_set') : 'https://discord.com/api/webhooks/…'} />
            {#if has('discord', 'webhook_url')}<button type="button" class="link" onclick={() => save(['discord.webhook_url'])}>{$t('al.clear')}</button>{/if}
            <p class="muted xs">{$t('al.dc.help')}</p>
            <button type="button" class="btn sm" onclick={() => test('discord')} disabled={testing !== '' || !(has('discord', 'webhook_url') || sec.dc_hook)}>{testing === 'discord' ? $t('al.testing') : $t('al.test')}</button>
          </fieldset>
          <!-- Email -->
          <fieldset class="ch">
            <legend><label class="sw"><input type="checkbox" bind:checked={f.em.enabled} /> {$t('al.ch.email')}</label></legend>
            <div class="two">
              <div><label for="em-host">{$t('al.em.host')}</label><input id="em-host" type="text" autocomplete="off" bind:value={f.em.host} placeholder="smtp.contoh.go.id" /></div>
              <div><label for="em-port">{$t('al.em.port')}</label><input id="em-port" type="number" min="1" max="65535" bind:value={f.em.port} /></div>
            </div>
            <label for="em-sec">{$t('al.em.security')}</label>
            <select id="em-sec" bind:value={f.em.security}><option value="starttls">STARTTLS (587)</option><option value="ssl">SSL/TLS (465)</option><option value="none">{$t('al.em.none')}</option></select>
            <div class="two">
              <div><label for="em-user">{$t('al.em.user')}</label><input id="em-user" type="text" autocomplete="off" bind:value={f.em.username} /></div>
              <div><label for="em-pass">{$t('al.em.pass')}</label><input id="em-pass" type="password" autocomplete="new-password" bind:value={sec.em_pass}
                placeholder={has('email', 'password') ? $t('al.secret_set') : ''} /></div>
            </div>
            {#if has('email', 'password')}<button type="button" class="link" onclick={() => save(['email.password'])}>{$t('al.clear')}</button>{/if}
            <label for="em-from">{$t('al.em.from')}</label><input id="em-from" type="text" autocomplete="off" bind:value={f.em.sender} placeholder="monishield@contoh.go.id" />
            <label for="em-to">{$t('al.em.to')}</label><input id="em-to" type="text" autocomplete="off" bind:value={f.em.to} placeholder="tim@contoh.go.id, ketua@contoh.go.id" />
            <button type="button" class="btn sm" onclick={() => test('email')} disabled={testing !== '' || !f.em.host}>{testing === 'email' ? $t('al.testing') : $t('al.test')}</button>
          </fieldset>
        </div>

        <fieldset class="ev">
          <legend>{$t('al.events')}</legend>
          {#each v.events_all as e}
            <label class="sw"><input type="checkbox" bind:checked={f.events[e]} /> <span><b>{$t(`al.ev.${e}`)}</b> <span class="muted xs">{$t(`al.ev.${e}.d`)}</span></span></label>
          {/each}
        </fieldset>

        <div class="opts">
          <div><label for="al-lang">{$t('al.lang')}</label>
            <select id="al-lang" bind:value={f.lang}><option value="id">Bahasa Indonesia</option><option value="en">English</option></select></div>
          <div class="grow"><label for="al-url">{$t('al.url')}</label><input id="al-url" type="text" autocomplete="off" bind:value={f.dashboard_url} /></div>
          <div><label for="al-hour">{$t('al.hour')}</label><input id="al-hour" type="number" min="0" max="23" bind:value={f.missing_hour} /></div>
        </div>
        <p class="muted xs">{$t('al.privacy')}</p>
        {#if err}<p class="err" role="alert">{err}</p>{/if}
        <div class="acts"><button class="btn primary" type="submit" disabled={busy}>{busy ? $t('action.saving') : $t('action.save')}</button></div>
      </form>
    </section>

    <DataTable title={$t('al.history')} rows={v.history} limit={30} columns={[
      { key: 'at', label: $t('col.time'), fmt: (r) => tWIB(utcToWib(r.at), $lang), cls: () => 'nowrap' },
      { key: 'channel', label: $t('al.col.channel'), fmt: (r) => $t(`al.ch.${r.channel}`) },
      { key: 'event', label: $t('al.col.event'), fmt: (r) => (r.event === 'test' ? $t('al.test') : $t(`al.ev.${r.event}`)) },
      { key: 'summary', label: $t('al.col.summary'), fmt: (r) => r.summary || '', minw: 220 },
      { key: 'ok', label: $t('col.status'), custom: true },
    ]}>
      {#snippet cell(r)}<SeverityTag level={r.ok ? 'ok' : 3} text={r.ok ? $t('al.ok') : $t('al.fail')} />{#if r.error}<div class="muted xs">{r.error}</div>{/if}{/snippet}
    </DataTable>
  </div>
{/if}

<style>
  header { margin-bottom: 6px; }
  h2 { font-size: 1rem; font-weight: 600; color: var(--heading); }
  .small { font-size: 0.8125rem; } .xs { font-size: 0.75rem; margin-top: 4px; }
  .chs { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 300px), 1fr)); gap: 14px; margin-top: 14px; }
  fieldset { border: 1px solid var(--line); border-radius: 14px; padding: 12px 14px 14px; display: flex; flex-direction: column; gap: 4px; min-width: 0; margin: 0; }
  legend { padding: 0 6px; font-weight: 600; }
  label { font-size: 0.8125rem; color: var(--kpi-label); margin-top: 6px; }
  .sw { display: flex; align-items: center; gap: 8px; color: var(--fg); font-size: 0.875rem; margin-top: 4px; }
  .sw input { width: auto; min-height: 0; }
  input:not([type='checkbox']), select { min-height: var(--touch); border-radius: 12px; width: 100%; }
  .two { display: grid; grid-template-columns: minmax(0, 2fr) minmax(0, 1fr); gap: 10px; }
  .two > div { display: flex; flex-direction: column; min-width: 0; }
  .ch .btn { margin-top: 10px; align-self: flex-start; }
  .btn.sm { min-height: 34px; padding: 0.3rem 0.9rem; font-size: 0.8125rem; }
  .link { align-self: flex-start; background: none; border: 0; color: var(--err); font-size: 0.75rem; cursor: pointer; padding: 2px 0; }
  .ev { margin-top: 14px; gap: 6px; }
  .opts { display: flex; gap: 12px; flex-wrap: wrap; margin-top: 14px; }
  .opts > div { display: flex; flex-direction: column; min-width: 140px; }
  .opts .grow { flex: 1 1 260px; }
  .err { color: var(--err); font-size: 0.875rem; margin-top: 10px; }
  .acts { margin-top: 14px; } .acts .btn { min-height: var(--touch); }
  @media (max-width: 420px) { .two { grid-template-columns: minmax(0, 1fr); } }
</style>
