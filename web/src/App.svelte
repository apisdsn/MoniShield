<!-- App shell (DRD §2, §6, §8, §9): login/forced password change -> dashboard. Sidebar + sticky toolbar + content.
     Dashboard data is not loaded before login (DRD §6.9). Data pages are mounted per tab (pages/*.svelte). -->
<script>
  import { onMount, tick, untrack } from 'svelte';
  import { get } from 'svelte/store';
  import { lang, t } from './i18n.js';
  import { api, session, offline, lastActivity, retryNow, onReconnect } from './api.js';
  import { route, go, build, parse, ADMIN } from './state.js';
  import { setSite } from './site.js';
  import { fLabel, logRange, num, sysName, tLocal, SPARSE_LINES } from './format.js';
  import { cmpNote } from './lib/compare.js';
  import { APP_NAME } from './brand.js';
  import { load, save } from './store.js';
  import Sidebar from './lib/Sidebar.svelte';
  import VolumeBand from './lib/VolumeBand.svelte';
  import Header from './lib/Header.svelte';
  import EmptyState from './lib/EmptyState.svelte';
  import ErrorState from './lib/ErrorState.svelte';
  import Toast, { toast } from './lib/Toast.svelte';
  import Login from './pages/Login.svelte';
  import Landing from './pages/Landing.svelte';
  import ChangePassword from './pages/ChangePassword.svelte';
  import AccountDialogs, { openAccount } from './lib/AccountDialogs.svelte';
  import ConfigDialogs, { openConfig } from './lib/ConfigDialogs.svelte';
  import Pods from './pages/Pods.svelte';
  import Business from './pages/Business.svelte';
  import Tracing from './pages/Tracing.svelte';
  import RawLogs from './pages/RawLogs.svelte';
  import CommandCenter from './pages/CommandCenter.svelte';
  import IpProfile from './pages/IpProfile.svelte';
  import AdminUsers from './pages/AdminUsers.svelte';
  import AdminIngest from './pages/AdminIngest.svelte';
  import Overview from './pages/Overview.svelte';
  import Service from './pages/Service.svelte';
  import Trends from './pages/Trends.svelte';
  import Security from './pages/Security.svelte';
  import RootCause from './pages/RootCause.svelte';
  import Availability from './pages/Availability.svelte';

  let screen = $state('boot');          // boot | home | login | force-password | app
  let me = $state(null), meta = $state(null), summary = $state(null);
  let bootError = $state(null), expired = $state(false);
  let reloadKey = $state(0), pageReady = $state(true), announce = $state('');
  let drawer = $state(false), menuBtn = $state(), h1 = $state();
  let collapsed = $state(load('side', 'open') === 'collapsed');   // left navigation collapsed (wide screen), per browser
  function toggleSide() { collapsed = !collapsed; save('side', collapsed ? 'collapsed' : 'open'); }   // h1 = page title in the Header (focused when switching tabs)
  let lastFolder = null;

  // ---------------------------------------------------------------- login
  // /api/docs (Swagger) redirects here with ?next=/api/docs when not logged in: after login (and the initial password
  // change) go back there. Only addresses in this list are followed (not an open redirect).
  const NEXT = ['/api/docs'];
  function goNext() {
    const n = new URLSearchParams(location.search).get('next');
    if (!NEXT.includes(n)) return false;
    location.replace(n); return true;
  }
  // signed out: the address becomes /login, with ?next= the page that was asked for (none for the Overview)
  function toLogin(keep = true) {
    if (location.pathname !== '/login') {
      const here = location.pathname + location.search, prev = new URLSearchParams(location.search).get('next');
      const next = prev || (keep && here !== '/' && here !== '/overview' ? here : null);
      history.replaceState(null, '', '/login' + (next ? '?next=' + encodeURIComponent(next) : ''));
    }
    screen = 'login';
  }
  // signed in: from /login to the page in ?next= (the route already points at it, state.js parse)
  function leaveLogin() {
    if (location.pathname !== '/login') return;
    const url = build(get(route));
    history.replaceState(null, '', url); route.set(parse(url));
  }
  async function boot() {
    bootError = null;
    if (get(route).tab === 'home') { screen = 'home'; return; }   // public home page: no sign-in, no data of the app
    try {
      me = await api.get('/api/me');
    } catch (e) {
      if (e.status === 401) { toLogin(); return; }
      bootError = e; return;
    }
    if (me.must_change_password) { screen = 'force-password'; return; }
    if (goNext()) return;
    leaveLogin();
    await loadMeta();
    if (meta) screen = 'app';
  }
  async function loadMeta() {
    try { meta = await api.get('/api/meta'); setSite(meta); bootError = null; }
    catch (e) { if (e.status !== 401) bootError = e; }
  }
  function onlogin(u) {
    me = u; expired = false;
    refreshMe();   // the sign-in answer has no email_pending (an address an admin entered, waiting for this user's code)
    if (u.must_change_password) screen = 'force-password';
    else if (!goNext()) { leaveLogin(); loadMeta().then(() => meta && (screen = 'app')); }   // return to the previously requested address: the address is not changed
  }
  // role/name can be changed by an admin at any time: re-read on every tab switch and reload ("on the next request")
  async function refreshMe() {
    try {
      const u = await api.get('/api/me');
      if (['role', 'display_name', 'email', 'email_pending'].some((k) => u[k] !== me?.[k])) me = { ...me, ...u };
      if (u.must_change_password) screen = 'force-password';
    } catch { /* 401 -> expired session handled by api.js */ }
  }
  function clear() { me = null; meta = null; summary = null; lastFolder = null; }
  async function logout() {
    try { await api.post('/api/auth/logout'); } catch { /* session may have expired already */ }
    clear(); expired = false; toLogin(false);
  }
  onMount(() => {
    boot();
    const off1 = session.subscribe((s) => {
      if (s !== 'expired') return;
      clear(); expired = true; toLogin(); session.set('ok');
    });
    const off2 = onReconnect(() => reload());
    return () => { off1(); off2(); };
  });

  // back/forward between the home page and the app (links between them reload the page: data-reload)
  $effect(() => {
    const home = $route.tab === 'home';
    if (home && screen !== 'home' && screen !== 'boot') untrack(() => { screen = 'home'; });
    else if (!home && screen === 'home') untrack(boot);
  });

  // ---------------------------------------------------------------- folders and tabs
  // the folder list of the data source in the address (S3 or Kafka); until the list of the new source arrives there is none
  const folders = $derived(meta && meta.source === $route.source ? meta.folders : []);
  $effect(() => { if (screen === 'app' && meta && meta.source !== $route.source) untrack(loadMeta); });   // source switched: its own folders
  function setSource(s) { go({ source: s, folder: null }); }
  const folder = $derived(folders.some((f) => f.folder === $route.folder) ? $route.folder : folders[0]?.folder ?? null);
  const folderInfo = $derived(folders.find((f) => f.folder === folder) || null);
  const isAdminTab = $derived(ADMIN.includes($route.tab));
  const isDataTab = $derived(!isAdminTab);
  // #/password and #/email (old Indonesian path): open the account pop-up over the Overview (lib/AccountDialogs.svelte)
  $effect(() => {
    if (screen !== 'app' || ($route.tab !== 'password' && $route.tab !== 'email')) return;
    openAccount($route.tab);
    go({ tab: 'overview', service: null, q: null }, { replace: true });
  });
  // #/admin/configuration and #/admin/notifications (old Indonesian addresses too): the matching configuration pop-up
  $effect(() => {
    if (screen !== 'app' || ($route.tab !== 'admin/configuration' && $route.tab !== 'admin/notifications')) return;
    if (me?.role === 'admin') openConfig($route.tab === 'admin/notifications' ? 'notif' : 'storage');
    go({ tab: 'overview', service: null, q: null }, { replace: true });
  });

  // folder in the address does not exist -> newest folder + notice (DRD §1.3); no folder -> newest folder in the address
  $effect(() => {
    if (screen !== 'app' || !folder || $route.folder === folder) return;
    if ($route.folder) toast(get(t)('folder.not_found', { date: fLabel($route.folder, get(lang)) }));
    go({ folder }, { replace: true });
  });

  // folder summary: sidebar (services, badges) and subtitle. The old list stays visible until the new one arrives (§6.5).
  let sumSeq = 0;
  async function loadSummary(f) {
    const my = ++sumSeq;
    try {
      const s = await api.get(`/api/folders/${encodeURIComponent(f)}`);
      if (my === sumSeq) summary = s;
    } catch (e) {
      if (my === sumSeq && e.status === 404) reload();   // folder gone (forgotten by an admin): fetch a new list
    }
  }
  $effect(() => {
    void reloadKey;
    if (screen === 'app' && folder) loadSummary(folder);
  });
  // service tab not present in the selected folder -> Overview (old)
  $effect(() => {
    if (screen === 'app' && summary?.folder === folder && $route.tab === 'service' && !summary.services.some((s) => s.service === $route.service))
      go({ tab: 'overview' }, { replace: true });
  });
  // folder change: scroll position to top (DRD §6.1)
  $effect(() => {
    if (folder && lastFolder && folder !== lastFolder) window.scrollTo({ top: 0 });
    lastFolder = folder;
  });
  // tab switch: scroll to top, focus the title (DRD §6.8)
  let lastTab = null;
  $effect(() => {
    const key = `${$route.tab}/${$route.service}`;
    if (screen !== 'app') return;
    if (lastTab && key !== lastTab) { window.scrollTo({ top: 0 }); tick().then(() => h1?.focus()); drawer = false; untrack(refreshMe); }
    lastTab = key;
  });

  function reload() {
    if (screen !== 'app') return;
    loadMeta(); refreshMe();
    reloadKey++;
  }
  function setFolder(f) { go({ folder: f }); }
  // Sync button (admin): after ingest, reload the folder list + page; a new folder exists -> switch to the newest
  async function onsynced() {
    const before = new Set(folders.map((f) => f.folder));
    await loadMeta(); refreshMe(); reloadKey++;
    const added = folders.map((f) => f.folder).filter((f) => !before.has(f)).sort();
    if (added.length) go({ folder: added[added.length - 1] });
  }

  // ---------------------------------------------------------------- title
  const title = $derived.by(() => {
    const r = $route;
    if (r.tab === 'overview') return $t('title.overview');
    if (r.tab === 'service') return sysName(r.service);
    if (r.tab === 'ip') return $t('ipp.title', { ip: r.service });
    if (r.tab === 'admin/users') return $t('menu.users');
    if (r.tab === 'admin/ingest') return $t('menu.ingest');
    return $t(`tab.${r.tab}`);
  });
  // Trends covers every folder: one line under the header says so
  const subtitle = $derived(isDataTab && folder && $route.tab === 'trends' ? $t('sub.trends', { n: num(folders.length, $lang) }) : '');
  // the date picker's tooltip: what the folder holds and when it was computed (redesign 2026-10-27: the date is shown once)
  const pickerInfo = $derived.by(() => {
    if (!folderInfo) return '';
    const parts = [];
    const rng = logRange(folderInfo.range_start, folderInfo.range_end, $lang);
    if (rng) parts.push($t('sub.contains', { range: rng }));
    if (folderInfo.derived_at) parts.push($t('sub.derived', { time: tLocal(folderInfo.derived_at, $lang) }));
    return parts.join(' · ');
  });
  // compact status line under the title (reference style DRD §12): number of services, errors, warnings, attack IPs
  const status = $derived.by(() => {
    if (!isDataTab || ['trends', 'overview'].includes($route.tab) || summary?.folder !== folder) return [];   // Overview: its status card
    const sv = $route.tab === 'service' ? summary.services.filter((x) => x.service === $route.service) : summary.services;
    const sum = (k) => sv.reduce((a, x) => a + (x[k] || 0), 0);
    const out = [];
    if ($route.tab !== 'service') out.push({ tone: 'accent', n: num(summary.services.length, $lang), text: $t('status.services') });
    else out.push({ tone: 'accent', n: num(sum('lines'), $lang), text: $t('status.lines') });
    out.push({ tone: sum('err') ? 'err' : 'ok', n: num(sum('err'), $lang), text: $t('status.errors') });
    out.push({ tone: sum('warn') ? 'warn' : 'ok', n: num(sum('warn'), $lang), text: $t('status.warnings') });
    if ($route.tab !== 'service' && summary.attack_ip_count) out.push({ tone: 'err', n: num(summary.attack_ip_count, $lang), text: $t('status.attack_ips') });
    return out;
  });
  $effect(() => { document.title = screen === 'app' ? `${title} · ${APP_NAME}` : APP_NAME; });
  // Overview shows both notes inside its status card
  const sparse = $derived(isDataTab && !['trends', 'overview'].includes($route.tab) && folderInfo && folderInfo.lines < SPARSE_LINES);
  const note = $derived(isDataTab && $route.tab !== 'overview' ? [...$cmpNote.values()][0] || '' : '');

  // ---------------------------------------------------------------- idle session (DRD §6.9)
  let now = $state(Date.now());
  onMount(() => { const id = setInterval(() => (now = Date.now()), 15000); return () => clearInterval(id); });
  // the server records activity at most once a minute: count down with a 1-minute margin
  const idleLeft = $derived(me?.session_idle_minutes ? $lastActivity + (me.session_idle_minutes - 1) * 60000 - now : Infinity);
  async function stay() { try { await api.get('/api/me'); now = Date.now(); } catch { /* 401 -> session expired */ } }

  // ---------------------------------------------------------------- keyboard (DRD §9.3)
  function onkey(e) {
    if (screen !== 'app' || e.ctrlKey || e.metaKey || e.altKey) return;
    const el = e.target;
    if (el.closest?.('input, select, textarea, [contenteditable="true"]')) return;
    const i = folders.findIndex((f) => f.folder === folder);
    if (e.key === '[' && i >= 0 && i < folders.length - 1 && $route.tab !== 'trends') { e.preventDefault(); setFolder(folders[i + 1].folder); }
    else if (e.key === ']' && i > 0 && $route.tab !== 'trends') { e.preventDefault(); setFolder(folders[i - 1].folder); }
    else if (e.key === '/') { const q = document.querySelector('main [data-filter]'); if (q) { e.preventDefault(); q.focus(); } }
    else if (e.key === 'Escape' && drawer) closeDrawer();
  }
  async function closeDrawer() {
    drawer = false;
    await tick();          // the rest of the content is released from inert only after render: only then can focus return to ☰
    menuBtn?.focus();
  }
  async function openDrawer() {
    drawer = !drawer;
    if (drawer) { await tick(); document.querySelector('#side a')?.focus(); }
  }
  function onready(ok) {
    pageReady = ok;
    announce = ok ? $t('state.done') : $t('state.loading');
  }
</script>

<svelte:window onkeydown={onkey} />

{#if screen === 'home'}
  <Landing />
{:else if screen === 'boot'}
  {#if bootError}
    <main id="main" class="center"><ErrorState error={bootError} onretry={boot} /></main>
  {/if}
{:else if screen === 'login'}
  <Login {expired} {onlogin} />
{:else if screen === 'force-password'}
  <ChangePassword forced ondone={() => onlogin({ ...me, must_change_password: false })} onlogout={logout} />
{:else}
  <a class="skip" href="#main" onclick={(e) => { e.preventDefault(); document.getElementById('main')?.focus(); }}>{$t('ui.skip')}</a>
  <aside id="side" class="side" class:open={drawer} class:collapsed aria-label={$t('nav.label')}>
    <Sidebar route={{ ...$route, folder }} {summary} ingest={meta?.ingest} onpick={() => (drawer = false)} {collapsed} ontoggle={toggleSide} admin={me?.role === 'admin'} />
  </aside>
  {#if drawer}<button class="backdrop" aria-label={$t('nav.close')} onclick={closeDrawer}></button>{/if}

  <div class="wrap" class:collapsed inert={drawer || undefined}>
    <Header {me} route={{ ...$route, folder }} {folders} {folder} folderDisabled={$route.tab === 'trends' || !isDataTab}
      sources={meta?.sources || []} source={$route.source} onsource={setSource} onfolder={setFolder} folderInfo={pickerInfo} onreload={reload} {onsynced} onlogout={logout} onmenu={openDrawer} drawerOpen={drawer} bind:menuBtn
      {title} sysTitle={$route.tab === 'service'} {status} bind:titleEl={h1} />
    {#if subtitle}<p class="sub"><span class="dot ok" aria-hidden="true"></span>{subtitle}</p>{/if}

    {#if $offline}
      <div class="band err" role="alert">
        <span>{$t('band.offline')}{$offline.auto ? ` ${$t('band.offline_auto')}` : ''}</span>
        {#if !$offline.auto}<button class="btn" onclick={retryNow}>{$t('action.retry')}</button>{/if}
      </div>
    {/if}
    {#if me?.email_pending}
      <div class="band info" role="status">
        <span>{$t('band.email_pending', { email: me.email_pending })}</span>
        <button class="btn" onclick={() => openAccount('email')}>{$t('band.email_confirm')}</button>
      </div>
    {/if}
    {#if idleLeft <= 5 * 60000}
      <div class="band info" role="status">
        <span>{$t('band.session_ending', { n: Math.max(1, Math.ceil(idleLeft / 60000)) })}</span>
        <button class="btn" onclick={stay}>{$t('band.stay')}</button>
      </div>
    {/if}

    <main id="main" tabindex="-1" aria-busy={!pageReady}>
      <p class="sr-only" aria-live="polite">{announce}</p>

      {#if note}<p class="cmpnote" role="note">{note}</p>{/if}
      {#if sparse}
        <div class="band warn" role="note">
          <span>{$t('band.sparse', { n: num(folderInfo.lines, $lang), m: num(folderInfo.files_corrupt, $lang) })}</span>
          <a href={build({ ...$route, tab: 'pods', service: null, folder, q: null })}>{$t('band.to_pods')}</a>
        </div>
      {/if}

      <!-- folder-wide totals: not on Trends (many days) nor on one service / one IP, whose own numbers would contradict them -->
      {#if isDataTab && folders.length && !['trends', 'service', 'ip'].includes($route.tab)}<VolumeBand {folders} {folder} {summary} />{/if}

      {#if isAdminTab && me.role !== 'admin'}
        <EmptyState title={$t('state.no_access')} text={$t('state.no_access_text')}>
          <a class="btn" href={build({ tab: 'overview', service: null, folder, module: null })}>{$t('action.to_overview')}</a>
        </EmptyState>
      {:else if $route.tab === 'admin/users'}
        <AdminUsers {me} onme={refreshMe} />
      {:else if $route.tab === 'admin/ingest'}
        <AdminIngest onfinished={reload} />
      {:else if !folders.length}
        <EmptyState title={$t('state.no_data')} text={me.role === 'admin' ? '' : $t('state.no_data_user')}>
          {#if me.role === 'admin'}<a class="btn primary" href={build({ tab: 'admin/ingest', service: null })}>{$t('menu.ingest')}</a>{/if}
        </EmptyState>
      {:else}
        {#key $route.tab + '/' + ($route.service || '')}
          {#if $route.tab === 'overview'}
            <Overview {folder} {summary} {reloadKey} {onready} />
          {:else if $route.tab === 'security'}
            <Security {folder} hosts={meta?.hosts || {}} {reloadKey} {onready} />
          {:else if $route.tab === 'root-causes'}
            <RootCause {folder} dnsUpstream={meta?.dns_upstream || ''} {reloadKey} {onready} />
          {:else if $route.tab === 'availability'}
            <Availability {folder} {reloadKey} {onready} />
          {:else if $route.tab === 'trends'}
            <Trends {reloadKey} {onready} />
          {:else if $route.tab === 'command-center'}
            <CommandCenter {folder} server={meta?.server} {reloadKey} {onready} />
          {:else if $route.tab === 'pods'}
            <Pods {folder} {summary} {reloadKey} {onready} />
          {:else if $route.tab === 'business'}
            <Business {folder} {summary} {reloadKey} {onready} />
          {:else if $route.tab === 'tracing'}
            <Tracing {folder} hosts={meta?.hosts || {}} {reloadKey} {onready} />
          {:else if $route.tab === 'raw-logs'}
            <RawLogs {folder} {summary} {onready} />
          {:else if $route.tab === 'ip'}
            <IpProfile {folder} ip={$route.service} {reloadKey} {onready} />
          {:else if $route.tab === 'service'}
            <Service {folder} service={$route.service} server={meta?.server} {reloadKey} {onready} />
          {/if}
        {/key}
      {/if}
    </main>
  </div>
{/if}
{#if screen === 'app'}<AccountDialogs onme={refreshMe} returnFocus={menuBtn} />{#if me?.role === 'admin'}<ConfigDialogs returnFocus={menuBtn} />{/if}{/if}
<Toast />

<style>
  .skip {
    position: absolute; left: 12px; top: -60px; z-index: 100; padding: 10px 16px; border-radius: 999px;
    background: var(--accent); color: var(--brand-fg); font-weight: 600; text-decoration: none;
  }
  .skip:focus { top: 12px; }
  .side {
    position: fixed; inset: 0 auto 0 0; width: var(--side-w); background: var(--side-bg); border-right: 1px solid var(--line);
    display: flex; flex-direction: column; padding: 18px 12px; gap: 14px; z-index: 30;
  }
  .wrap { margin-left: var(--side-w); padding: 0 28px 40px; max-width: calc(1560px + var(--side-w)); }
  .sub { margin: 0 4px 16px; color: var(--muted); font-size: 0.78rem; text-align: right; }
  main:focus { outline: none; }
  .cmpnote { margin: 0 0 12px; font-size: 0.8125rem; color: var(--muted); }
  .center { min-height: 100vh; display: grid; place-items: center; padding: 16px; }
  .band {
    display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap;
    padding: 10px 16px; border-radius: 14px; margin: 8px 0 14px; font-size: 0.875rem;
  }
  .band.err { background: color-mix(in srgb, var(--err) 16%, var(--card)); box-shadow: inset 3px 0 0 var(--err); }
  .band.info { background: color-mix(in srgb, var(--accent) 12%, var(--card)); box-shadow: inset 3px 0 0 var(--accent); }
  .band.warn { background: color-mix(in srgb, var(--warn) 14%, var(--card)); box-shadow: inset 3px 0 0 var(--warn); }
  .backdrop { display: none; }
  @media (min-width: 901px) {
    .side { transition: width 0.18s ease; }
    .side.collapsed { width: var(--side-w-c); padding-inline: 10px; }
    .wrap { transition: margin-left 0.18s ease; }
    .wrap.collapsed { margin-left: var(--side-w-c); max-width: calc(1560px + var(--side-w-c)); }
  }
  @media (prefers-reduced-motion: reduce) { .side, .wrap { transition: none !important; } }

  @media (max-width: 900px) {
    .side {
      width: min(300px, 86vw); transform: translateX(-100%); visibility: hidden; transition: transform 0.15s, visibility 0.15s;
      box-shadow: var(--glow); overflow-y: auto;
    }
    .side.open { transform: none; visibility: visible; transition: transform 0.15s, visibility 0s; }   /* visible immediately so it can be focused */
    .backdrop { display: block; position: fixed; inset: 0; z-index: 25; background: rgba(0, 0, 0, 0.45); border: 0; }
    .wrap { margin-left: 0; padding: 0 16px 32px; }
    .sub { text-align: left; margin: -4px 0 14px; }
  }
</style>
