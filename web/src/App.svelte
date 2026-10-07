<!-- Kerangka aplikasi (DRD §2, §6, §8, §9): masuk/ganti sandi wajib -> dashboard. Sidebar + baris alat lekat + isi.
     Data dashboard tidak dimuat sebelum masuk (DRD §6.9). Halaman data dipasang per tab (pages/*.svelte). -->
<script>
  import { onMount, tick, untrack } from 'svelte';
  import { get } from 'svelte/store';
  import { lang, t } from './i18n.js';
  import { api, session, offline, lastActivity, retryNow, onReconnect } from './api.js';
  import { route, go, build, ADMIN } from './state.js';
  import { dLabel, logRange, num, sysName, tWIB } from './format.js';
  import { APP_NAME } from './brand.js';
  import { load, save } from './store.js';
  import Sidebar from './lib/Sidebar.svelte';
  import Header from './lib/Header.svelte';
  import EmptyState from './lib/EmptyState.svelte';
  import ErrorState from './lib/ErrorState.svelte';
  import Toast, { toast } from './lib/Toast.svelte';
  import Login from './pages/Login.svelte';
  import ChangePassword from './pages/ChangePassword.svelte';
  import Pods from './pages/Pods.svelte';
  import Business from './pages/Business.svelte';
  import Tracing from './pages/Tracing.svelte';
  import CommandCenter from './pages/CommandCenter.svelte';
  import IpProfile from './pages/IpProfile.svelte';
  import AdminUsers from './pages/AdminUsers.svelte';
  import AdminIngest from './pages/AdminIngest.svelte';
  import AdminConfig from './pages/AdminConfig.svelte';
  import Overview from './pages/Overview.svelte';
  import Service from './pages/Service.svelte';
  import Trends from './pages/Trends.svelte';
  import Security from './pages/Security.svelte';
  import RootCause from './pages/RootCause.svelte';
  import Availability from './pages/Availability.svelte';

  // ASUMSI (DRD §6.6 "praktis kosong"): folder dengan < 1.000 baris log diberi pita kuning (jumlah file rusak ikut
  // disebut). File rusak saja tidak cukup: folder penuh pun sering punya 1–3 file berbaris rusak.
  const SPARSE_LINES = 1000;

  let screen = $state('boot');          // boot | login | force-password | app
  let me = $state(null), meta = $state(null), summary = $state(null);
  let bootError = $state(null), expired = $state(false);
  let reloadKey = $state(0), pageReady = $state(true), announce = $state('');
  let drawer = $state(false), menuBtn = $state(), h1 = $state();
  let collapsed = $state(load('side', 'open') === 'collapsed');   // navigasi kiri diciutkan (layar lebar), per browser
  function toggleSide() { collapsed = !collapsed; save('side', collapsed ? 'collapsed' : 'open'); }   // h1 = judul halaman di Header (fokus saat pindah tab)
  let lastFolder = null;

  // ---------------------------------------------------------------- masuk
  // /api/docs (Swagger) mengarahkan ke sini dengan ?next=/api/docs bila belum masuk: sesudah masuk (dan ganti sandi
  // awal) kembali ke sana. Hanya alamat dalam daftar ini yang diikuti (bukan pengalihan terbuka).
  const NEXT = ['/api/docs'];
  function goNext() {
    const n = new URLSearchParams(location.search).get('next');
    if (!NEXT.includes(n)) return false;
    location.replace(n); return true;
  }
  async function boot() {
    bootError = null;
    try {
      me = await api.get('/api/me');
    } catch (e) {
      if (e.status === 401) { screen = 'login'; return; }
      bootError = e; return;
    }
    if (me.must_change_password) { screen = 'force-password'; return; }
    if (goNext()) return;
    await loadMeta();
    if (meta) screen = 'app';
  }
  async function loadMeta() {
    try { meta = await api.get('/api/meta'); bootError = null; }
    catch (e) { if (e.status !== 401) bootError = e; }
  }
  function onlogin(u) {
    me = u; expired = false;
    if (u.must_change_password) screen = 'force-password';
    else if (!goNext()) loadMeta().then(() => meta && (screen = 'app'));   // kembali ke alamat yang tadi diminta: alamat tidak diubah
  }
  // peran/nama bisa diubah admin kapan saja: dibaca ulang tiap pindah tab dan muat ulang ("pada permintaan berikutnya")
  async function refreshMe() {
    try {
      const u = await api.get('/api/me');
      if (u.role !== me?.role || u.display_name !== me?.display_name) me = u;
      if (u.must_change_password) screen = 'force-password';
    } catch { /* 401 -> sesi habis ditangani api.js */ }
  }
  function clear() { me = null; meta = null; summary = null; lastFolder = null; }
  async function logout() {
    try { await api.post('/api/auth/logout'); } catch { /* sesi mungkin sudah habis */ }
    clear(); expired = false; screen = 'login';
  }
  onMount(() => {
    boot();
    const off1 = session.subscribe((s) => {
      if (s !== 'expired') return;
      clear(); expired = true; screen = 'login'; session.set('ok');
    });
    const off2 = onReconnect(() => reload());
    return () => { off1(); off2(); };
  });

  // ---------------------------------------------------------------- folder dan tab
  const folders = $derived(meta?.folders || []);
  const folder = $derived(folders.some((f) => f.folder === $route.folder) ? $route.folder : folders[0]?.folder ?? null);
  const folderInfo = $derived(folders.find((f) => f.folder === folder) || null);
  const isAdminTab = $derived(ADMIN.includes($route.tab));
  const isDataTab = $derived(!isAdminTab && $route.tab !== 'sandi');

  // folder di alamat tidak ada -> folder terbaru + pemberitahuan (DRD §1.3); tanpa folder -> folder terbaru di alamat
  $effect(() => {
    if (screen !== 'app' || !folder || $route.folder === folder) return;
    if ($route.folder) toast(get(t)('folder.not_found', { date: $route.folder }));
    go({ folder }, { replace: true });
  });

  // ringkasan folder: sidebar (layanan, lencana) dan subjudul. Daftar lama tetap tampil sampai yang baru tiba (§6.5).
  let sumSeq = 0;
  async function loadSummary(f) {
    const my = ++sumSeq;
    try {
      const s = await api.get(`/api/folders/${encodeURIComponent(f)}`);
      if (my === sumSeq) summary = s;
    } catch (e) {
      if (my === sumSeq && e.status === 404) reload();   // folder hilang (dilupakan admin): ambil daftar baru
    }
  }
  $effect(() => {
    void reloadKey;
    if (screen === 'app' && folder) loadSummary(folder);
  });
  // tab layanan yang tidak ada di folder terpilih -> Overview (lama)
  $effect(() => {
    if (screen === 'app' && summary?.folder === folder && $route.tab === 'layanan' && !summary.services.some((s) => s.service === $route.service))
      go({ tab: 'overview' }, { replace: true });
  });
  // ganti folder: posisi gulir ke atas (DRD §6.1)
  $effect(() => {
    if (folder && lastFolder && folder !== lastFolder) window.scrollTo({ top: 0 });
    lastFolder = folder;
  });
  // pindah tab: gulir ke atas, fokus ke judul (DRD §6.8)
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
  // tombol Sinkronkan (admin): setelah ingest, muat ulang daftar folder + halaman; ada folder baru -> pindah ke yang terbaru
  async function onsynced() {
    const before = new Set(folders.map((f) => f.folder));
    await loadMeta(); refreshMe(); reloadKey++;
    const baru = (meta?.folders || []).map((f) => f.folder).filter((f) => !before.has(f)).sort();
    if (baru.length) go({ folder: baru[baru.length - 1] });
  }

  // ---------------------------------------------------------------- judul
  const title = $derived.by(() => {
    const r = $route;
    if (r.tab === 'overview') return $t('title.overview');
    if (r.tab === 'layanan') return sysName(r.service);
    if (r.tab === 'ip') return $t('ipp.title', { ip: r.service });
    if (r.tab === 'sandi') return $t('pw.title');
    if (r.tab === 'admin/user') return $t('menu.users');
    if (r.tab === 'admin/ingest') return $t('menu.ingest');
    if (r.tab === 'admin/konfigurasi' || r.tab === 'admin/notifikasi') return $t('menu.config');
    return $t(`tab.${r.tab}`);
  });
  // baris kesegaran data di bawah kepala (U2 + pengganti "streaming · last event" referensi selama Kafka ditunda)
  const subtitle = $derived.by(() => {
    if (!isDataTab || !folder) return '';
    if ($route.tab === 'tren') return $t('sub.trends', { n: num(folders.length, $lang) });
    const parts = [$t('sub.folder', { date: dLabel(folder, $lang) })];
    const rng = logRange(folderInfo?.range_start, folderInfo?.range_end, $lang);
    if (rng) parts.push($t('sub.contains', { range: rng }));
    if (folderInfo?.derived_at) parts.push($t('sub.derived', { time: tWIB(folderInfo.derived_at, $lang) }));
    return parts.join(' · ');
  });
  // baris status ringkas di bawah judul (gaya referensi DRD §12): jumlah layanan, error, warning, IP serangan
  const status = $derived.by(() => {
    if (!isDataTab || $route.tab === 'tren' || summary?.folder !== folder) return [];
    const sv = $route.tab === 'layanan' ? summary.services.filter((x) => x.service === $route.service) : summary.services;
    const sum = (k) => sv.reduce((a, x) => a + (x[k] || 0), 0);
    const out = [];
    if ($route.tab !== 'layanan') out.push({ tone: 'accent', n: num(summary.services.length, $lang), text: $t('status.services') });
    else out.push({ tone: 'accent', n: num(sum('lines'), $lang), text: $t('status.lines') });
    out.push({ tone: sum('err') ? 'err' : 'ok', n: num(sum('err'), $lang), text: $t('status.errors') });
    out.push({ tone: sum('warn') ? 'warn' : 'ok', n: num(sum('warn'), $lang), text: $t('status.warnings') });
    if ($route.tab !== 'layanan' && summary.attack_ip_count) out.push({ tone: 'err', n: num(summary.attack_ip_count, $lang), text: $t('status.attack_ips') });
    return out;
  });
  const suffix = $derived(isDataTab && folder && $route.tab !== 'tren' ? dLabel(folder, $lang) : '');
  $effect(() => { document.title = screen === 'app' ? `${title} · ${APP_NAME}` : APP_NAME; });
  const sparse = $derived(isDataTab && $route.tab !== 'tren' && folderInfo && folderInfo.lines < SPARSE_LINES);

  // ---------------------------------------------------------------- sesi menganggur (DRD §6.9)
  let now = $state(Date.now());
  onMount(() => { const id = setInterval(() => (now = Date.now()), 15000); return () => clearInterval(id); });
  // server mencatat aktivitas paling sering semenit sekali: hitung mundur dengan cadangan 1 menit
  const idleLeft = $derived(me?.session_idle_minutes ? $lastActivity + (me.session_idle_minutes - 1) * 60000 - now : Infinity);
  async function stay() { try { await api.get('/api/me'); now = Date.now(); } catch { /* 401 -> sesi habis */ } }

  // ---------------------------------------------------------------- keyboard (DRD §9.3)
  function onkey(e) {
    if (screen !== 'app' || e.ctrlKey || e.metaKey || e.altKey) return;
    const el = e.target;
    if (el.closest?.('input, select, textarea, [contenteditable="true"]')) return;
    const i = folders.findIndex((f) => f.folder === folder);
    if (e.key === '[' && i >= 0 && i < folders.length - 1 && $route.tab !== 'tren') { e.preventDefault(); setFolder(folders[i + 1].folder); }
    else if (e.key === ']' && i > 0 && $route.tab !== 'tren') { e.preventDefault(); setFolder(folders[i - 1].folder); }
    else if (e.key === '/') { const q = document.querySelector('main [data-filter]'); if (q) { e.preventDefault(); q.focus(); } }
    else if (e.key === 'Escape' && drawer) closeDrawer();
  }
  async function closeDrawer() {
    drawer = false;
    await tick();          // isi lain baru lepas dari inert setelah render: baru fokus bisa kembali ke ☰
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

{#if screen === 'boot'}
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
    <Sidebar route={{ ...$route, folder }} {summary} ingest={meta?.ingest} onpick={() => (drawer = false)} {collapsed} ontoggle={toggleSide} />
  </aside>
  {#if drawer}<button class="backdrop" aria-label={$t('nav.close')} onclick={closeDrawer}></button>{/if}

  <div class="wrap" class:collapsed inert={drawer || undefined}>
    <Header {me} route={{ ...$route, folder }} {folders} {folder} folderDisabled={$route.tab === 'tren' || !isDataTab}
      onfolder={setFolder} onreload={reload} {onsynced} onlogout={logout} onmenu={openDrawer} drawerOpen={drawer} bind:menuBtn
      {title} sysTitle={$route.tab === 'layanan'} {suffix} {status} bind:titleEl={h1} />
    {#if subtitle}<p class="sub"><span class="dot ok" aria-hidden="true"></span>{subtitle}</p>{/if}

    {#if $offline}
      <div class="band err" role="alert">
        <span>{$t('band.offline')}{$offline.auto ? ` ${$t('band.offline_auto')}` : ''}</span>
        {#if !$offline.auto}<button class="btn" onclick={retryNow}>{$t('action.retry')}</button>{/if}
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

      {#if sparse}
        <div class="band warn" role="note">
          <span>{$t('band.sparse', { n: num(folderInfo.lines, $lang), m: num(folderInfo.files_corrupt, $lang) })}</span>
          <a href={build({ ...$route, tab: 'pod', service: null, folder, q: null })}>{$t('band.to_pods')}</a>
        </div>
      {/if}

      {#if $route.tab === 'sandi'}
        <ChangePassword ondone={() => history.back()} oncancel={() => history.back()} />
      {:else if isAdminTab && me.role !== 'admin'}
        <EmptyState title={$t('state.no_access')} text={$t('state.no_access_text')}>
          <a class="btn" href={build({ tab: 'overview', service: null, folder, module: null })}>{$t('action.to_overview')}</a>
        </EmptyState>
      {:else if $route.tab === 'admin/user'}
        <AdminUsers {me} onme={refreshMe} />
      {:else if $route.tab === 'admin/ingest'}
        <AdminIngest onfinished={reload} />
      {:else if $route.tab === 'admin/konfigurasi' || $route.tab === 'admin/notifikasi'}
        <!-- #/admin/notifikasi (alamat lama) = halaman Konfigurasi, langsung ke bagian notifikasi -->
        <AdminConfig focus={$route.tab === 'admin/notifikasi' ? 'notif' : ''} />
      {:else if !folders.length}
        <EmptyState title={$t('state.no_data')} text={me.role === 'admin' ? '' : $t('state.no_data_user')}>
          {#if me.role === 'admin'}<a class="btn primary" href={build({ tab: 'admin/ingest', service: null })}>{$t('menu.ingest')}</a>{/if}
        </EmptyState>
      {:else}
        {#key $route.tab + '/' + ($route.service || '')}
          {#if $route.tab === 'overview'}
            <Overview {folder} {summary} {reloadKey} {onready} />
          {:else if $route.tab === 'keamanan'}
            <Security {folder} hosts={meta?.hosts || {}} {reloadKey} {onready} />
          {:else if $route.tab === 'akar-masalah'}
            <RootCause {folder} dnsUpstream={meta?.dns_upstream || ''} {reloadKey} {onready} />
          {:else if $route.tab === 'ketersediaan'}
            <Availability {folder} {reloadKey} {onready} />
          {:else if $route.tab === 'tren'}
            <Trends {reloadKey} {onready} />
          {:else if $route.tab === 'peta'}
            <CommandCenter {folder} server={meta?.server} {reloadKey} {onready} />
          {:else if $route.tab === 'pod'}
            <Pods {folder} {summary} {reloadKey} {onready} />
          {:else if $route.tab === 'bisnis'}
            <Business {folder} {summary} {reloadKey} {onready} />
          {:else if $route.tab === 'pelacakan'}
            <Tracing {folder} hosts={meta?.hosts || {}} {reloadKey} {onready} />
          {:else if $route.tab === 'ip'}
            <IpProfile {folder} ip={$route.service} {reloadKey} {onready} />
          {:else if $route.tab === 'layanan'}
            <Service {folder} service={$route.service} server={meta?.server} {reloadKey} {onready} />
          {/if}
        {/key}
      {/if}
    </main>
  </div>
{/if}
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
    .side.open { transform: none; visibility: visible; transition: transform 0.15s, visibility 0s; }   /* terlihat seketika agar bisa difokus */
    .backdrop { display: block; position: fixed; inset: 0; z-index: 25; background: rgba(0, 0, 0, 0.45); border: 0; }
    .wrap { margin-left: 0; padding: 0 16px 32px; }
    .sub { text-align: left; margin: -4px 0 14px; }
  }
</style>
