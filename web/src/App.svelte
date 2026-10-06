<!-- Kerangka aplikasi (DRD §2, §6, §8, §9): masuk/ganti sandi wajib -> dashboard. Sidebar + baris alat lekat + isi.
     Data dashboard tidak dimuat sebelum masuk (DRD §6.9). Halaman data dipasang per tab; sampai Tahap 13–20 semuanya
     memakai Placeholder (halaman contoh komponen). -->
<script>
  import { onMount, tick } from 'svelte';
  import { get } from 'svelte/store';
  import { lang, t } from './i18n.js';
  import { api, session, offline, lastActivity, retryNow, onReconnect } from './api.js';
  import { route, go, build, ADMIN } from './state.js';
  import { dLabel, logRange, num, titleCase } from './format.js';
  import Sidebar from './lib/Sidebar.svelte';
  import Header from './lib/Header.svelte';
  import EmptyState from './lib/EmptyState.svelte';
  import ErrorState from './lib/ErrorState.svelte';
  import Toast, { toast } from './lib/Toast.svelte';
  import Note from './lib/Note.svelte';
  import Login from './pages/Login.svelte';
  import ChangePassword from './pages/ChangePassword.svelte';
  import Placeholder from './pages/Placeholder.svelte';

  // ASUMSI (DRD §6.6 "praktis kosong"): folder dengan < 1.000 baris log diberi pita kuning (jumlah file rusak ikut
  // disebut). File rusak saja tidak cukup: folder penuh pun sering punya 1–3 file berbaris rusak.
  const SPARSE_LINES = 1000;

  let screen = $state('boot');          // boot | login | force-password | app
  let me = $state(null), meta = $state(null), summary = $state(null);
  let bootError = $state(null), expired = $state(false);
  let reloadKey = $state(0), pageReady = $state(true), announce = $state('');
  let drawer = $state(false), menuBtn = $state(), h1 = $state();
  let lastFolder = null;

  // ---------------------------------------------------------------- masuk
  async function boot() {
    bootError = null;
    try {
      me = await api.get('/api/me');
    } catch (e) {
      if (e.status === 401) { screen = 'login'; return; }
      bootError = e; return;
    }
    if (me.must_change_password) { screen = 'force-password'; return; }
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
    else loadMeta().then(() => meta && (screen = 'app'));   // kembali ke alamat yang tadi diminta: alamat tidak diubah
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
    if (lastTab && key !== lastTab) { window.scrollTo({ top: 0 }); tick().then(() => h1?.focus()); drawer = false; }
    lastTab = key;
  });

  function reload() {
    if (screen !== 'app') return;
    loadMeta();
    reloadKey++;
  }
  function setFolder(f) { go({ folder: f }); }

  // ---------------------------------------------------------------- judul
  const title = $derived.by(() => {
    const r = $route;
    if (r.tab === 'overview') return $t('title.overview');
    if (r.tab === 'layanan') return titleCase(r.service || '');
    if (r.tab === 'sandi') return $t('pw.title');
    if (r.tab === 'admin/user') return $t('menu.users');
    if (r.tab === 'admin/ingest') return $t('menu.ingest');
    return $t(`tab.${r.tab}`);
  });
  const subtitle = $derived.by(() => {
    if (!isDataTab || !folder) return '';
    if ($route.tab === 'tren') return $t('sub.trends');
    const parts = [$t('sub.folder', { date: dLabel(folder, $lang) })];
    const rng = logRange(folderInfo?.range_start, folderInfo?.range_end, $lang);
    if (rng) parts.push($t('sub.contains', { range: rng }));
    if (summary?.folder === folder) parts.push($t('sub.services', { n: summary.services.length }));
    return parts.join(' · ');
  });
  $effect(() => { document.title = screen === 'app' ? `${title} · SIMPEL4 Log` : 'SIMPEL4 Log'; });
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
  <aside id="side" class="side" class:open={drawer} aria-label={$t('nav.label')}>
    <Sidebar route={{ ...$route, folder }} {summary} onpick={() => (drawer = false)} />
  </aside>
  {#if drawer}<button class="backdrop" aria-label={$t('nav.close')} onclick={closeDrawer}></button>{/if}

  <div class="wrap" inert={drawer || undefined}>
    <Header {me} route={{ ...$route, folder }} {folders} {folder} folderDisabled={$route.tab === 'tren' || !isDataTab}
      onfolder={setFolder} onreload={reload} onlogout={logout} onmenu={openDrawer} drawerOpen={drawer} bind:menuBtn />

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
      <div class="head">
        <h1 bind:this={h1} tabindex="-1">{title}</h1>
        {#if subtitle}<p class="sub">{subtitle}</p>{/if}
      </div>
      <p class="sr-only" aria-live="polite">{announce}</p>

      {#if sparse}
        <div class="band warn" role="note">
          <span>{$t('band.sparse', { n: num(folderInfo.lines, $lang), m: num(folderInfo.files_corrupt, $lang) })}</span>
          <a href={build({ ...$route, tab: 'pod', service: null, folder })}>{$t('band.to_pods')}</a>
        </div>
      {/if}

      {#if $route.tab === 'sandi'}
        <ChangePassword ondone={() => history.back()} oncancel={() => history.back()} />
      {:else if isAdminTab && me.role !== 'admin'}
        <EmptyState title={$t('state.no_access')} text={$t('state.no_access_text')}>
          <a class="btn" href={build({ tab: 'overview', service: null, folder, module: null })}>{$t('action.to_overview')}</a>
        </EmptyState>
      {:else if isAdminTab}
        <Note>{$t('placeholder.admin', { stage: 18 })}</Note>
      {:else if !folders.length}
        <EmptyState title={$t('state.no_data')} text={me.role === 'admin' ? '' : $t('state.no_data_user')}>
          {#if me.role === 'admin'}<a class="btn primary" href={build({ tab: 'admin/ingest', service: null })}>{$t('menu.ingest')}</a>{/if}
        </EmptyState>
      {:else}
        {#key $route.tab + '/' + ($route.service || '')}
          <Placeholder tab={$route.tab} {folder} {summary} {reloadKey} {onready} />
        {/key}
      {/if}
    </main>
  </div>
{/if}
<Toast />

<style>
  .skip {
    position: absolute; left: 12px; top: -60px; z-index: 100; padding: 10px 16px; border-radius: 999px;
    background: var(--accent); color: #04201c; font-weight: 600; text-decoration: none;
  }
  .skip:focus { top: 12px; }
  .side {
    position: fixed; inset: 0 auto 0 0; width: var(--side-w); background: var(--side-bg); border-right: 1px solid var(--line);
    display: flex; flex-direction: column; padding: 18px 12px; gap: 14px; z-index: 30;
  }
  .wrap { margin-left: var(--side-w); padding: 0 34px 40px; max-width: calc(1560px + var(--side-w)); }
  .head { margin: 14px 0 22px; }
  h1 {
    font-size: 2.375rem; font-weight: 600; letter-spacing: -0.01em; line-height: 1.1; text-transform: capitalize;
    background: var(--title-grad); -webkit-background-clip: text; background-clip: text; color: transparent;
    width: fit-content; max-width: 100%; overflow-wrap: anywhere;
  }
  .sub { margin: 6px 0 0; color: var(--muted); font-size: 0.875rem; }
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

  @media (max-width: 900px) {
    .side {
      width: min(300px, 86vw); transform: translateX(-100%); visibility: hidden; transition: transform 0.15s, visibility 0.15s;
      box-shadow: var(--glow); overflow-y: auto;
    }
    .side.open { transform: none; visibility: visible; transition: transform 0.15s, visibility 0s; }   /* terlihat seketika agar bisa difokus */
    .backdrop { display: block; position: fixed; inset: 0; z-index: 25; background: rgba(0, 0, 0, 0.45); border: 0; }
    .wrap { margin-left: 0; padding: 0 16px 32px; }
    h1 { font-size: 1.75rem; }
    .head { margin: 8px 0 16px; }
  }
</style>
