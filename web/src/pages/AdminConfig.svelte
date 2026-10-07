<!-- Konfigurasi (permintaan pemilik 2026-10-07: "satu halaman untuk semua kredensial"), hanya admin. Satu tempat untuk:
     kredensial AWS S3 + wilayah, folder induk S3 otomatis, kunci MaxMind GeoLite2, notifikasi (Telegram/Discord/email),
     pengecualian daftar blokir, dan status kunci yang hanya bisa diisi lewat .env. API: /api/admin/config (monishield/
     settings.py), /api/admin/import/watch, /api/admin/alerts. Rahasia tidak pernah dikirim balik oleh server: kolomnya
     tampil "sudah diisi"; dibiarkan kosong saat menyimpan = tidak diubah; "Hapus isian layar" = kembali ke nilai .env.
     Isian layar langsung berlaku tanpa mulai ulang server. -->
<script>
  import { onMount, tick } from 'svelte';
  import { lang, t } from '../i18n.js';
  import { api } from '../api.js';
  import { build, route } from '../state.js';
  import { errText } from '../srv.js';
  import { toast } from '../lib/Toast.svelte';
  import Skeleton from '../lib/Skeleton.svelte';
  import ErrorState from '../lib/ErrorState.svelte';
  import SeverityTag from '../lib/SeverityTag.svelte';
  import AdminAlerts from './AdminAlerts.svelte';

  let { focus = '' } = $props();
  const SECTIONS = ['aws', 'watch', 'maxmind', 'notif', 'blocklist', 'server'];

  let v = $state.raw(null), imp = $state.raw(null), error = $state(null);
  // isian per kelompok; kolom rahasia selalu mulai kosong (kosong = tidak diubah)
  let aws = $state({ ak: '', sk: '', st: '', region: '' });
  let mm = $state({ id: '', key: '' });
  let bl = $state({ ex: '', org: '' });
  let wf = $state({ url: '', minutes: 60 });
  let busy = $state(''), msg = $state({});   // msg[kelompok] = {ok, text}

  function fill(r) {
    v = r;
    aws = { ak: '', sk: '', st: '', region: r.aws.import_region.value || '' };
    mm = { id: '', key: '' };
    bl = { ex: (r.blocklist.blocklist_exclude.value || '').split(',').map((x) => x.trim()).filter(Boolean).join('\n'), org: r.blocklist.blocklist_exclude_org.value || '' };
  }
  async function loadImp() {
    try {
      imp = await api.get('/api/admin/import');
      if (imp.watch) wf = { url: imp.watch.url || '', minutes: imp.watch.minutes || 60 };
    } catch { imp = null; }
  }
  async function load() {
    try { fill(await api.get('/api/admin/config')); error = null; } catch (e) { error = e; }
    await loadImp();
  }
  let ready = $state(false);
  onMount(async () => { await load(); ready = true; });
  // #/admin/notifikasi -> langsung ke bagian itu (juga saat berpindah dari #/admin/konfigurasi tanpa memuat ulang halaman)
  $effect(() => { if (ready && focus) tick().then(() => jump(focus)); });
  function jump(id) {
    const el = document.getElementById(`cf-${id}`);
    if (el) { el.scrollIntoView({ behavior: 'smooth', block: 'start' }); el.focus({ preventScroll: true }); }
  }

  async function save(group, body, ok = 'cf.saved') {
    busy = group; msg = { ...msg, [group]: null };
    try { fill(await api.put('/api/admin/config', body)); toast($t(ok)); await loadImp(); return true; }
    catch (e) { msg = { ...msg, [group]: { ok: false, text: $errText(e) } }; return false; }
    finally { busy = ''; }
  }
  const awsBody = () => ({ aws_access_key_id: aws.ak.trim(), aws_secret_access_key: aws.sk.trim(), aws_session_token: aws.st.trim(), import_region: aws.region.trim() });
  const mmBody = () => ({ maxmind_account_id: mm.id.trim(), maxmind_license_key: mm.key.trim() });
  const typed = (g) => (g === 'aws' ? aws.ak || aws.sk || aws.st || aws.region.trim() !== (v.aws.import_region.value || '') : mm.id || mm.key);

  async function test(kind) {
    if (typed(kind) && !(await save(kind, kind === 'aws' ? awsBody() : mmBody()))) return;   // uji memakai setelan TERSIMPAN
    busy = `${kind}-test`; msg = { ...msg, [kind]: null };
    try {
      const r = await api.post('/api/admin/config/test', { kind });
      msg = { ...msg, [kind]: { ok: true, text: kind === 'aws' ? $t('cf.aws.test_ok', { target: r.target }) : $t('cf.mm.test_ok') } };
    } catch (e) { msg = { ...msg, [kind]: { ok: false, text: $errText(e) } }; }
    finally { busy = ''; }
  }

  async function saveWatch(enabled) {
    busy = 'watch'; msg = { ...msg, watch: null };
    try {
      await api.put('/api/admin/import/watch', { url: wf.url.trim(), minutes: Number(wf.minutes), enabled });
      toast(enabled ? $t('imp.w.saved') : $t('imp.w.disabled'));
      window.dispatchEvent(new Event('monishield:watch-changed'));
      await loadImp();
    } catch (e) { msg = { ...msg, watch: { ok: false, text: $errText(e) } }; }
    finally { busy = ''; }
  }

  const src = (it) => $t(it.source === 'layar' ? 'cf.src.screen' : it.source === 'env' ? 'cf.src.env' : 'cf.src.none');
  const anyScreen = (g) => Object.values(v[g]).some((it) => it.source === 'layar');
  const keys = (g) => Object.keys(v[g]);
  const ENV = { jwt_secret: 'S4_JWT_SECRET', job_token: 'S4_JOB_TOKEN', auth_database_url: 'S4_AUTH_DATABASE_URL', admin_password: 'S4_ADMIN_PASSWORD' };
  const ingestLink = $derived(build({ ...$route, tab: 'admin/ingest', service: null, q: null }));
  const awsReady = $derived(v && v.aws.aws_access_key_id.set && v.aws.aws_secret_access_key.set);
  const mmReady = $derived(v && v.maxmind.maxmind_account_id.set && v.maxmind.maxmind_license_key.set);
  const minLabel = (m) => (m < 60 ? $t('imp.w.min', { n: m }) : $t('imp.w.hour', { n: m / 60 }));
</script>

{#snippet srcTag(it)}<span class="src" class:screen={it.source === 'layar'} class:none={!it.source}>{src(it)}</span>{/snippet}
{#snippet result(g)}
  {#if msg[g]}<p class={msg[g].ok ? 'okmsg' : 'err'} role={msg[g].ok ? 'status' : 'alert'}>{msg[g].ok ? '✓ ' : ''}{msg[g].text}</p>{/if}
{/snippet}

{#if error && !v}
  <ErrorState {error} onretry={load} />
{:else if !v}
  <Skeleton kpis={0} charts={2} />
{:else}
  <div class="page">
    <section class="card intro" aria-label={$t('cf.title')}>
      <p class="muted small">{$t('cf.intro')}</p>
      <nav class="chips" aria-label={$t('cf.nav')}>
        {#each SECTIONS as s}<button type="button" class="chip" onclick={() => jump(s)}>{$t(`cf.s.${s}`)}</button>{/each}
      </nav>
    </section>

    <!-- 1. AWS S3 -->
    <section class="card" id="cf-aws" tabindex="-1" aria-labelledby="cf-aws-h">
      <header>
        <h2 id="cf-aws-h">{$t('cf.s.aws')}</h2>
        <SeverityTag level={awsReady ? 'ok' : 3} text={awsReady ? $t('cf.ready') : $t('cf.not_ready')} />
      </header>
      <p class="muted small">{$t('cf.aws.intro')}</p>
      <form onsubmit={(e) => { e.preventDefault(); save('aws', awsBody()); }} novalidate>
        <div class="fields">
          <div>
            <label for="cf-ak">{$t('imp.c.ak')} {@render srcTag(v.aws.aws_access_key_id)}</label>
            <input id="cf-ak" type="text" autocomplete="off" spellcheck="false" bind:value={aws.ak}
              placeholder={v.aws.aws_access_key_id.set ? `${v.aws.aws_access_key_id.masked} — ${$t('cf.keep')}` : 'AKIA…'} />
          </div>
          <div>
            <label for="cf-sk">{$t('imp.c.sk')} {@render srcTag(v.aws.aws_secret_access_key)}</label>
            <input id="cf-sk" type="password" autocomplete="new-password" spellcheck="false" bind:value={aws.sk}
              placeholder={v.aws.aws_secret_access_key.set ? $t('al.secret_set') : ''} />
          </div>
          <div>
            <label for="cf-st">{$t('imp.c.st')} {@render srcTag(v.aws.aws_session_token)}</label>
            <input id="cf-st" type="password" autocomplete="new-password" spellcheck="false" bind:value={aws.st}
              placeholder={v.aws.aws_session_token.set ? $t('al.secret_set') : $t('cf.optional')} />
          </div>
          <div>
            <label for="cf-region">{$t('cf.aws.region')} {@render srcTag(v.aws.import_region)}</label>
            <input id="cf-region" type="text" autocomplete="off" spellcheck="false" bind:value={aws.region} placeholder="ap-southeast-3" />
          </div>
        </div>
        <p class="muted xs">{$t('cf.aws.buckets')}
          {#if Object.keys(v.server.import_buckets).length}
            {#each Object.entries(v.server.import_buckets) as [b, ps]}{#each ps as p}<code>s3://{b}/{p}</code>{' '}{/each}{/each}
          {:else}<b>{$t('cf.aws.no_buckets')}</b>{/if}
        </p>
        {@render result('aws')}
        <div class="acts">
          <button class="btn primary" type="submit" disabled={busy !== ''}>{busy === 'aws' ? $t('action.saving') : $t('action.save')}</button>
          <button class="btn" type="button" onclick={() => test('aws')} disabled={busy !== '' || !(awsReady || (aws.ak && aws.sk))}>{busy === 'aws-test' ? $t('al.testing') : $t('cf.test')}</button>
          {#if anyScreen('aws')}<button class="btn ghost" type="button" disabled={busy !== ''} onclick={() => save('aws', { clear: keys('aws') }, 'cf.cleared')}>{$t('cf.clear')}</button>{/if}
        </div>
      </form>
    </section>

    <!-- 2. Folder S3 otomatis -->
    <section class="card" id="cf-watch" tabindex="-1" aria-labelledby="cf-watch-h">
      <header>
        <h2 id="cf-watch-h">{$t('cf.s.watch')}</h2>
        {#if imp?.watch}<SeverityTag level={imp.watch.enabled ? 'ok' : 1} text={imp.watch.enabled ? $t('cf.on') : $t('cf.off')} />{/if}
      </header>
      <p class="muted small">{$t('imp.w.intro')}</p>
      {#if !imp}
        <p class="muted small">{$t('state.loading')}</p>
      {:else if !imp.enabled}
        <p class="warnline small">{$t('cf.aws.no_buckets')}</p>
      {:else}
        <form class="wform" onsubmit={(e) => { e.preventDefault(); saveWatch(true); }} novalidate>
          <div class="grow">
            <label for="cf-wurl">{$t('imp.w.url')}</label>
            <input id="cf-wurl" type="text" autocomplete="off" spellcheck="false" bind:value={wf.url}
              placeholder={imp.allowed[0]?.replace('<YYYY-MM-DD>/', '') || 's3://nama-bucket/k8s-logs/'} />
          </div>
          <div>
            <label for="cf-wmin">{$t('imp.w.every')}</label>
            <select id="cf-wmin" bind:value={wf.minutes}>
              {#each imp.watch?.minute_options || [60] as m}<option value={m}>{minLabel(m)}</option>{/each}
            </select>
          </div>
          <div class="acts inline">
            <button class="btn primary" type="submit" disabled={busy !== '' || !wf.url.trim()}>{imp.watch?.enabled ? $t('imp.w.save') : $t('imp.w.enable')}</button>
            {#if imp.watch?.enabled}<button class="btn" type="button" disabled={busy !== ''} onclick={() => saveWatch(false)}>{$t('imp.w.disable')}</button>{/if}
          </div>
        </form>
        {@render result('watch')}
        {#if imp.watch?.problem}<p class="err small">{imp.watch.problem}</p>{/if}
        {#if imp.watch?.enabled && !imp.credentials.available}<p class="warnline small">{$t('cf.watch.no_cred')}</p>{/if}
      {/if}
      <p class="muted xs"><a href={ingestLink}>{$t('cf.watch.more')}</a></p>
    </section>

    <!-- 3. MaxMind -->
    <section class="card" id="cf-maxmind" tabindex="-1" aria-labelledby="cf-mm-h">
      <header>
        <h2 id="cf-mm-h">{$t('cf.s.maxmind')}</h2>
        <SeverityTag level={mmReady ? 'ok' : 1} text={mmReady ? $t('cf.ready') : $t('cf.not_ready')} />
      </header>
      <p class="muted small">{$t('cf.mm.intro')}</p>
      <form onsubmit={(e) => { e.preventDefault(); save('maxmind', mmBody()); }} novalidate>
        <div class="fields">
          <div>
            <label for="cf-mmid">{$t('cf.mm.id')} {@render srcTag(v.maxmind.maxmind_account_id)}</label>
            <input id="cf-mmid" type="text" inputmode="numeric" autocomplete="off" spellcheck="false" bind:value={mm.id}
              placeholder={v.maxmind.maxmind_account_id.set ? `${v.maxmind.maxmind_account_id.masked} — ${$t('cf.keep')}` : '123456'} />
          </div>
          <div>
            <label for="cf-mmkey">{$t('cf.mm.key')} {@render srcTag(v.maxmind.maxmind_license_key)}</label>
            <input id="cf-mmkey" type="password" autocomplete="new-password" spellcheck="false" bind:value={mm.key}
              placeholder={v.maxmind.maxmind_license_key.set ? $t('al.secret_set') : ''} />
          </div>
        </div>
        <p class="muted xs">{$t('cf.mm.help')}</p>
        {@render result('maxmind')}
        <div class="acts">
          <button class="btn primary" type="submit" disabled={busy !== ''}>{busy === 'maxmind' ? $t('action.saving') : $t('action.save')}</button>
          <button class="btn" type="button" onclick={() => test('maxmind')} disabled={busy !== '' || !(mmReady || (mm.id && mm.key))}>{busy === 'maxmind-test' ? $t('al.testing') : $t('cf.test')}</button>
          {#if anyScreen('maxmind')}<button class="btn ghost" type="button" disabled={busy !== ''} onclick={() => save('maxmind', { clear: keys('maxmind') }, 'cf.cleared')}>{$t('cf.clear')}</button>{/if}
        </div>
      </form>
    </section>

    <!-- 4. Notifikasi -->
    <div id="cf-notif" tabindex="-1" class="anchor"><AdminAlerts /></div>

    <!-- 5. Daftar blokir -->
    <section class="card" id="cf-blocklist" tabindex="-1" aria-labelledby="cf-bl-h">
      <header><h2 id="cf-bl-h">{$t('cf.s.blocklist')}</h2></header>
      <p class="muted small">{$t('cf.bl.intro')}</p>
      <form onsubmit={(e) => { e.preventDefault(); save('blocklist', { blocklist_exclude: bl.ex.split(/[\s,]+/).filter(Boolean).join(', '), blocklist_exclude_org: bl.org.trim() }); }} novalidate>
        <div class="fields">
          <div>
            <label for="cf-blex">{$t('cf.bl.ex')} {@render srcTag(v.blocklist.blocklist_exclude)}</label>
            <textarea id="cf-blex" rows="4" spellcheck="false" bind:value={bl.ex} placeholder={'36.66.1.0/24\n198.51.100.7'}></textarea>
          </div>
          <div>
            <label for="cf-blorg">{$t('cf.bl.org')} {@render srcTag(v.blocklist.blocklist_exclude_org)}</label>
            <input id="cf-blorg" type="text" autocomplete="off" spellcheck="false" bind:value={bl.org} placeholder="OMBUDSMAN|KOMINFO" />
            <p class="muted xs">{$t('cf.bl.org_help')}</p>
          </div>
        </div>
        {@render result('blocklist')}
        <div class="acts">
          <button class="btn primary" type="submit" disabled={busy !== ''}>{busy === 'blocklist' ? $t('action.saving') : $t('action.save')}</button>
          {#if anyScreen('blocklist')}<button class="btn ghost" type="button" disabled={busy !== ''} onclick={() => save('blocklist', { clear: keys('blocklist') }, 'cf.cleared')}>{$t('cf.clear')}</button>{/if}
        </div>
      </form>
    </section>

    <!-- 6. Hanya .env -->
    <section class="card" id="cf-server" tabindex="-1" aria-labelledby="cf-sv-h">
      <header><h2 id="cf-sv-h">{$t('cf.s.server')}</h2></header>
      <p class="muted small">{$t('cf.sv.intro')}</p>
      <ul class="env">
        {#each Object.entries(ENV) as [k, name]}
          <li><code>{name}</code><span class="muted xs">{$t(`cf.sv.${k}`)}</span>
            <SeverityTag level={v.server[k] ? 'ok' : k === 'jwt_secret' ? 3 : 1} text={v.server[k] ? $t('cf.sv.set') : $t('cf.sv.empty')} /></li>
        {/each}
        <li><code>S4_IMPORT_BUCKETS</code><span class="muted xs">{$t('cf.sv.import_buckets')}</span>
          <SeverityTag level={Object.keys(v.server.import_buckets).length ? 'ok' : 1} text={Object.keys(v.server.import_buckets).length ? $t('cf.sv.set') : $t('cf.sv.empty')} /></li>
      </ul>
    </section>
  </div>
{/if}

<style>
  .page { display: flex; flex-direction: column; gap: 16px; }
  .card { scroll-margin-top: 80px; }
  .card:focus, .anchor:focus { outline: none; }
  .anchor { scroll-margin-top: 80px; }
  header { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-bottom: 6px; flex-wrap: wrap; }
  h2 { font-size: 1rem; font-weight: 600; color: var(--heading); }
  .small { font-size: 0.8125rem; } .xs { font-size: 0.75rem; margin-top: 6px; }
  .chips { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; }
  .intro .small { margin: 0; }
  .chip { border: 1px solid var(--line); background: transparent; color: var(--fg); border-radius: 999px; padding: 0.35rem 0.85rem; font-size: 0.8125rem; cursor: pointer; min-height: 34px; }
  .chip:hover { border-color: var(--accent); color: var(--accent); }
  .fields { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 260px), 1fr)); gap: 10px 16px; margin-top: 12px; }
  .fields > div { display: flex; flex-direction: column; justify-content: flex-end; min-width: 0; }   /* kolom sebaris tetap rata walau label terlipat */
  label { font-size: 0.8125rem; color: var(--kpi-label); margin-bottom: 4px; display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
  input, select, textarea { min-height: var(--touch); border-radius: 12px; width: 100%; }
  textarea { font-family: var(--mono, ui-monospace, monospace); font-size: 0.8125rem; padding: 8px 10px; resize: vertical; }
  .src { font-size: 0.6875rem; padding: 1px 8px; border-radius: 999px; border: 1px solid var(--line); color: var(--kpi-label); }
  .src.screen { border-color: var(--accent); color: var(--accent); }
  .src.none { border-style: dashed; }
  code { font-size: 0.75rem; word-break: break-all; }
  .acts { display: flex; gap: 10px; flex-wrap: wrap; margin-top: 12px; }
  .acts .btn { min-height: var(--touch); }
  .btn.ghost { background: none; border-color: transparent; color: var(--err); }
  .wform { display: flex; gap: 12px; flex-wrap: wrap; align-items: flex-end; margin-top: 12px; }
  .wform > div { display: flex; flex-direction: column; min-width: 140px; }
  .wform .grow { flex: 1 1 320px; }
  .acts.inline { margin-top: 0; flex-wrap: nowrap; }
  .err { color: var(--err); font-size: 0.875rem; margin-top: 10px; }
  .okmsg { color: var(--ok-text); font-size: 0.875rem; margin-top: 10px; }
  .warnline { color: var(--warn); margin-top: 8px; }
  .env { list-style: none; padding: 0; margin: 10px 0 0; display: flex; flex-direction: column; gap: 8px; }
  .env li { display: grid; grid-template-columns: minmax(170px, max-content) minmax(0, 1fr) max-content; gap: 10px; align-items: center; border-top: 1px solid var(--line); padding-top: 8px; }
  .env li .xs { margin-top: 0; }
  @media (max-width: 560px) { .env li { grid-template-columns: minmax(0, 1fr) max-content; } .env li .xs { grid-column: 1 / -1; grid-row: 2; } }
</style>
