<!-- Configuration (owner request 2026-10-07: "satu halaman untuk semua kredensial" — one page for all credentials), admin only. One place for:
     AWS S3 credentials + region, automatic S3 parent folder, MaxMind GeoLite2 key, notifications (Telegram/Discord/email),
     blocklist exclusions, and the status of keys that can only be set via .env. API: /api/admin/config (monishield/
     settings.py), /api/admin/import/watch, /api/admin/alerts. Secrets are never sent back by the server: their fields
     show "sudah diisi"; left empty on save = unchanged; "Hapus dari .env" = line disabled (default).
     Every field is WRITTEN TO THE server's .env FILE (owner request 2026-10-07) and takes effect immediately without a restart. -->
<script>
  import { onMount, tick } from 'svelte';
  import { lang, t } from '../i18n.js';
  import { api } from '../api.js';
  import { build, route } from '../state.js';
  import { errText, srv } from '../srv.js';
  import { dLabel, tWIB, utcToWib } from '../format.js';
  import { toast } from '../lib/Toast.svelte';
  import Skeleton from '../lib/Skeleton.svelte';
  import ErrorState from '../lib/ErrorState.svelte';
  import SeverityTag from '../lib/SeverityTag.svelte';
  import AdminAlerts from './AdminAlerts.svelte';
  import KafkaCard from '../lib/KafkaCard.svelte';

  let { focus = '' } = $props();
  const SECTIONS = ['aws', 'watch', 'kafka', 'maxmind', 'notif', 'blocklist', 'retention', 'server'];

  let v = $state.raw(null), imp = $state.raw(null), error = $state(null);
  // fields per group; secret fields always start empty (empty = unchanged)
  let aws = $state({ ak: '', sk: '', st: '', region: '' });
  let mm = $state({ id: '', key: '' });
  let kf = $state({}), kcard = $state();
  let bl = $state({ ex: '', org: '' });
  let wf = $state({ url: '', minutes: 60 });
  let rt = $state({ days: 0, inbox: 0 }), rplan = $state.raw(null), rconfirm = $state(false);
  let busy = $state(''), msg = $state({});   // msg[group] = {ok, text}

  function fill(r) {
    v = r;
    aws = { ak: '', sk: '', st: '', region: r.aws.import_region.value || '' };
    mm = { id: '', key: '' };
    const k = r.kafka;
    kf = { enabled: k.kafka_enabled.value, brokers: k.kafka_brokers.value, topic: k.kafka_topic.value, group: k.kafka_group.value, security: k.kafka_security.value,
      mech: k.kafka_sasl_mechanism.value, user: k.kafka_username.value, pass: '', offset: k.kafka_offset_reset.value, minutes: k.kafka_ingest_minutes.value };
    rt = { days: r.retention.retention_days.value, inbox: r.retention.retention_inbox_days.value };
    bl = { ex: (r.blocklist.blocklist_exclude.value || '').split(',').map((x) => x.trim()).filter(Boolean).join('\n'), org: r.blocklist.blocklist_exclude_org.value || '' };
  }
  async function loadImp() {
    try {
      imp = await api.get('/api/admin/import');
      if (imp.watch) wf = { url: imp.watch.url || '', minutes: imp.watch.minutes || 60 };
    } catch { imp = null; }
  }
  async function loadRet() { try { rplan = await api.get('/api/admin/retention'); } catch { rplan = null; } }
  async function load() {
    try { fill(await api.get('/api/admin/config')); error = null; } catch (e) { error = e; }
    await Promise.all([loadImp(), loadRet()]);
  }
  async function saveRet() {
    if (await save('retention', { retention_days: String(rt.days || 0), retention_inbox_days: String(rt.inbox || 0) })) await loadRet();
  }
  async function runRet() {
    busy = 'retention-run'; msg = { ...msg, retention: null };
    try { rplan = await api.post('/api/admin/retention/run'); rconfirm = false; toast($t('cf.rt.done')); }
    catch (e) { msg = { ...msg, retention: { ok: false, text: $errText(e) } }; }
    finally { busy = ''; }
  }
  let ready = $state(false);
  onMount(async () => { await load(); ready = true; });
  // #/admin/notifikasi -> straight to that section (also when coming from #/admin/konfigurasi without reloading the page)
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
    if (typed(kind) && !(await save(kind, kind === 'aws' ? awsBody() : mmBody()))) return;   // the test uses the SAVED settings
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

  // value source: 'file' = .env, 'environment' = process environment variable (overrides .env), null = default / not set
  const src = (it) => $t(it.source === 'file' ? 'cf.src.screen' : it.source === 'environment' ? 'cf.src.env' : it.set || it.value ? 'cf.src.default' : 'cf.src.none');
  const anyScreen = (g) => Object.values(v[g]).some((it) => it.source === 'file' && (it.set || it.value));
  const keys = (g) => Object.keys(v[g]);
  const ENV = { jwt_secret: 'S4_JWT_SECRET', job_token: 'S4_JOB_TOKEN', auth_database_url: 'S4_AUTH_DATABASE_URL', admin_password: 'S4_ADMIN_PASSWORD' };
  const ingestLink = $derived(build({ ...$route, tab: 'admin/ingest', service: null, q: null }));
  const awsReady = $derived(v && v.aws.aws_access_key_id.set && v.aws.aws_secret_access_key.set);
  const kfBody = () => ({ kafka_enabled: kf.enabled, kafka_brokers: kf.brokers.trim(), kafka_topic: kf.topic.trim(), kafka_group: kf.group.trim(),
    kafka_security: kf.security, kafka_sasl_mechanism: kf.mech, kafka_username: kf.user.trim(), kafka_password: kf.pass, kafka_offset_reset: kf.offset,
    kafka_ingest_minutes: String(kf.minutes) });
  async function saveKafka() { if (await save('kafka', kfBody())) setTimeout(() => kcard?.load(), 1500); }
  const mmReady = $derived(v && v.maxmind.maxmind_account_id.set && v.maxmind.maxmind_license_key.set);
  const minLabel = (m) => (m < 60 ? $t('imp.w.min', { n: m }) : $t('imp.w.hour', { n: m / 60 }));
</script>

{#snippet srcTag(it)}<span class="src" class:screen={it.source === 'file'} class:warn={it.source === 'environment'} class:none={!it.source}
  title={$t('cf.env_hint', { name: it.env })}>{src(it)}</span>{/snippet}
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
      <p class="small file">{$t('cf.file.title')} <code>{v.file.path}</code>
        {#if v.file.writable}<SeverityTag level="ok" text={$t('cf.file.ok')} />{/if}</p>
      {#if !v.file.writable}<p class="warnline small" role="alert">{$t('cf.file.ro')}</p>{/if}
      {#if v.file.environment_override.length}<p class="warnline small">{$t('cf.file.override', { list: v.file.environment_override.join(', ') })}</p>{/if}
      {#if v.file.pending.length}<p class="warnline small">{$t('cf.file.pending', { list: v.file.pending.join(', ') })}</p>{/if}
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

    <!-- 2. Automatic S3 folder -->
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
        {#if imp.watch?.problem}<p class="err small">{$errText({ code: imp.watch.problem_code, message: imp.watch.problem })}</p>{/if}
        {#if imp.watch?.enabled && !imp.credentials.available}<p class="warnline small">{$t('cf.watch.no_cred')}</p>{/if}
      {/if}
      <p class="muted xs"><a href={ingestLink}>{$t('cf.watch.more')}</a></p>
    </section>

    <!-- 3. Kafka -->
    <section class="card" id="cf-kafka" tabindex="-1" aria-labelledby="cf-kf-h">
      <header>
        <h2 id="cf-kf-h">{$t('cf.s.kafka')}</h2>
        <SeverityTag level={v.kafka.kafka_brokers.value && v.kafka.kafka_topic.value && kf.enabled ? 'ok' : 1}
          text={v.kafka.kafka_brokers.value && v.kafka.kafka_topic.value ? (v.kafka.kafka_enabled.value ? $t('cf.on') : $t('cf.off')) : $t('cf.not_ready')} />
      </header>
      <p class="muted small">{$t('cf.kf.intro')}</p>
      <form onsubmit={(e) => { e.preventDefault(); saveKafka(); }} novalidate>
        <div class="fields">
          <div><label for="cf-kb">{$t('cf.kf.brokers')} {@render srcTag(v.kafka.kafka_brokers)}</label>
            <input id="cf-kb" type="text" autocomplete="off" spellcheck="false" bind:value={kf.brokers} placeholder="10.10.1.5:9092" /></div>
          <div><label for="cf-kt">{$t('cf.kf.topic')} {@render srcTag(v.kafka.kafka_topic)}</label>
            <input id="cf-kt" type="text" autocomplete="off" spellcheck="false" bind:value={kf.topic} placeholder="k8s-logs" /></div>
          <div><label for="cf-kg">{$t('cf.kf.group')} {@render srcTag(v.kafka.kafka_group)}</label>
            <input id="cf-kg" type="text" autocomplete="off" spellcheck="false" bind:value={kf.group} /></div>
          <div><label for="cf-ks">{$t('cf.kf.security')} {@render srcTag(v.kafka.kafka_security)}</label>
            <select id="cf-ks" bind:value={kf.security}>
              <option value="plaintext">{$t('cf.kf.sec.plaintext')}</option><option value="sasl_plaintext">SASL</option>
              <option value="sasl_ssl">SASL + TLS</option><option value="ssl">TLS</option>
            </select></div>
          {#if kf.security.startsWith('sasl')}
            <div><label for="cf-km">{$t('cf.kf.mech')} {@render srcTag(v.kafka.kafka_sasl_mechanism)}</label>
              <select id="cf-km" bind:value={kf.mech}><option>PLAIN</option><option>SCRAM-SHA-256</option><option>SCRAM-SHA-512</option></select></div>
            <div><label for="cf-ku">{$t('cf.kf.user')} {@render srcTag(v.kafka.kafka_username)}</label>
              <input id="cf-ku" type="text" autocomplete="off" spellcheck="false" bind:value={kf.user} /></div>
            <div><label for="cf-kp">{$t('cf.kf.pass')} {@render srcTag(v.kafka.kafka_password)}</label>
              <input id="cf-kp" type="password" autocomplete="new-password" bind:value={kf.pass} placeholder={v.kafka.kafka_password.set ? $t('al.secret_set') : ''} /></div>
          {/if}
          <div><label for="cf-ko">{$t('cf.kf.offset')} {@render srcTag(v.kafka.kafka_offset_reset)}</label>
            <select id="cf-ko" bind:value={kf.offset}><option value="earliest">{$t('cf.kf.earliest')}</option><option value="latest">{$t('cf.kf.latest')}</option></select></div>
          <div><label for="cf-ki">{$t('cf.kf.minutes')} {@render srcTag(v.kafka.kafka_ingest_minutes)}</label>
            <input id="cf-ki" type="number" min="1" max="1440" bind:value={kf.minutes} /></div>
        </div>
        <label class="sw"><input type="checkbox" bind:checked={kf.enabled} /> {$t('cf.kf.enabled')}</label>
        <p class="muted xs">{$t('cf.kf.rancher')}</p>
        {@render result('kafka')}
        <div class="acts">
          <button class="btn primary" type="submit" disabled={busy !== ''}>{busy === 'kafka' ? $t('action.saving') : $t('action.save')}</button>
        </div>
      </form>
      {#if v.kafka.kafka_brokers.value && v.kafka.kafka_topic.value}<KafkaCard compact bind:this={kcard} />{/if}
    </section>

    <!-- 4. MaxMind -->
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

    <!-- 4. Notifications -->
    <div id="cf-notif" tabindex="-1" class="anchor"><AdminAlerts /></div>

    <!-- 5. Blocklist -->
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

    <!-- 6. Data retention -->
    <section class="card" id="cf-retention" tabindex="-1" aria-labelledby="cf-rt-h">
      <header>
        <h2 id="cf-rt-h">{$t('cf.s.retention')}</h2>
        <SeverityTag level={v.retention.retention_days.value || v.retention.retention_inbox_days.value ? 'ok' : 1}
          text={v.retention.retention_days.value || v.retention.retention_inbox_days.value ? $t('cf.on') : $t('cf.off')} />
      </header>
      <p class="muted small">{$t('cf.rt.intro')}</p>
      <form onsubmit={(e) => { e.preventDefault(); saveRet(); }} novalidate>
        <div class="fields">
          <div>
            <label for="cf-rtd">{$t('cf.rt.days')} {@render srcTag(v.retention.retention_days)}</label>
            <input id="cf-rtd" type="number" min="0" max="3650" bind:value={rt.days} />
            <p class="muted xs">{$t('cf.rt.days_help')}</p>
          </div>
          <div>
            <label for="cf-rti">{$t('cf.rt.inbox')} {@render srcTag(v.retention.retention_inbox_days)}</label>
            <input id="cf-rti" type="number" min="0" max="3650" bind:value={rt.inbox} />
            <p class="muted xs">{$t('cf.rt.inbox_help')}</p>
          </div>
        </div>
        {#if rplan}
          <div class="plan small">
            <b>{$t('cf.rt.next')}</b>
            {#if !rplan.db.length && !rplan.inbox.length}<span class="muted">{$t('cf.rt.none')}</span>{/if}
            {#if rplan.db.length}<span>{$t('cf.rt.plan_db', { n: rplan.db.length, d: dLabel(rplan.cutoff_db, $lang) })}</span>{/if}
            {#if rplan.inbox.length}<span>{$t('cf.rt.plan_inbox', { n: rplan.inbox.length, d: dLabel(rplan.cutoff_inbox, $lang) })}</span>{/if}
            {#if rplan.last}<span class="muted xs">{$t('cf.rt.last', { at: tWIB(utcToWib(rplan.last.at), $lang), by: $srv(rplan.last.by), db: rplan.last.db.length, inbox: rplan.last.inbox.length })}</span>{/if}
          </div>
        {/if}
        {@render result('retention')}
        <div class="acts">
          <button class="btn primary" type="submit" disabled={busy !== ''}>{busy === 'retention' ? $t('action.saving') : $t('action.save')}</button>
          {#if rplan && (rplan.db.length || rplan.inbox.length)}
            {#if !rconfirm}
              <button class="btn" type="button" disabled={busy !== ''} onclick={() => (rconfirm = true)}>{$t('cf.rt.run')}</button>
            {:else}
              <span class="warnline small confirm">{$t('cf.rt.confirm_q')}</span>
              <button class="btn danger" type="button" disabled={busy !== ''} onclick={runRet}>{busy === 'retention-run' ? $t('state.loading') : $t('cf.rt.confirm')}</button>
              <button class="btn" type="button" disabled={busy !== ''} onclick={() => (rconfirm = false)}>{$t('action.cancel')}</button>
            {/if}
          {/if}
        </div>
      </form>
    </section>

    <!-- 7. .env only -->
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
  .fields > div { display: flex; flex-direction: column; justify-content: flex-end; min-width: 0; }   /* inline fields stay aligned even when the label wraps */
  label { font-size: 0.8125rem; color: var(--kpi-label); margin-bottom: 4px; display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
  input, select, textarea { min-height: var(--touch); border-radius: 12px; width: 100%; }
  textarea { font-family: var(--mono, ui-monospace, monospace); font-size: 0.8125rem; padding: 8px 10px; resize: vertical; }
  .src { font-size: 0.6875rem; padding: 1px 8px; border-radius: 999px; border: 1px solid var(--line); color: var(--kpi-label); }
  .src.screen { border-color: var(--accent); color: var(--accent); }
  .src.none { border-style: dashed; }
  .src.warn { border-color: var(--warn); color: var(--warn); }
  .file { margin-top: 8px; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
  code { font-size: 0.75rem; word-break: break-all; }
  .acts { display: flex; gap: 10px; flex-wrap: wrap; margin-top: 12px; }
  .acts .btn { min-height: var(--touch); }
  .btn.ghost { background: none; border-color: transparent; color: var(--err); }
  .wform { display: flex; gap: 12px; flex-wrap: wrap; align-items: flex-end; margin-top: 12px; }
  .wform > div { display: flex; flex-direction: column; min-width: 140px; }
  .wform .grow { flex: 1 1 320px; }
  .acts.inline { margin-top: 0; flex-wrap: nowrap; }
  .sw { display: flex; align-items: center; gap: 8px; color: var(--fg); font-size: 0.875rem; margin-top: 12px; }
  .sw input { width: auto; min-height: 0; }
  .err { color: var(--err); font-size: 0.875rem; margin-top: 10px; }
  .okmsg { color: var(--ok-text); font-size: 0.875rem; margin-top: 10px; }
  .warnline { color: var(--warn); margin-top: 8px; }
  .plan { display: flex; flex-direction: column; gap: 4px; margin-top: 12px; padding: 10px 12px; border: 1px solid var(--line); border-radius: 12px; }
  .plan .xs { margin-top: 2px; }
  .confirm { margin: 0; align-self: center; }
  .btn.danger { border-color: var(--err); color: var(--err); }
  .env { list-style: none; padding: 0; margin: 10px 0 0; display: flex; flex-direction: column; gap: 8px; }
  .env li { display: grid; grid-template-columns: minmax(170px, max-content) minmax(0, 1fr) max-content; gap: 10px; align-items: center; border-top: 1px solid var(--line); padding-top: 8px; }
  .env li .xs { margin-top: 0; }
  @media (max-width: 560px) { .env li { grid-template-columns: minmax(0, 1fr) max-content; } .env li .xs { grid-column: 1 / -1; grid-row: 2; } }
</style>
