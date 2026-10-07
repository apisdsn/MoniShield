<!-- Navigasi (DRD §1.1, §2.1, §9.4, gaya §12): grup Analisis (9 tab, urutan lama) dan Layanan (yang ada di folder
     terpilih, urutan file), tiap butir berikon. Lencana: Keamanan "N IP", layanan = jumlah error; punya teks
     tersembunyi untuk pembaca layar. Kaki: kartu zona waktu + status ingest. Sama untuk admin dan user.
     Di layar sempit tampil sebagai laci (App.svelte). Di layar lebar bisa diciutkan jadi lajur ikon (permintaan pemilik
     2026-10-07; tombol di samping logo, pilihan disimpan per browser): label lewat `title`, lencana jadi titik. -->
<script>
  import { lang, t } from '../i18n.js';
  import { num, sysName } from '../format.js';
  import { TABS, build } from '../state.js';
  import { APP_NAME, APP_MARK } from '../brand.js';
  import Icon from './Icon.svelte';
  let { route, summary = null, ingest = null, onpick = null, collapsed = false, ontoggle = null } = $props();
  const tip = (s) => (collapsed ? s : undefined);

  const ICON = { overview: 'overview', peta: 'globe', tren: 'trend', keamanan: 'shield', 'akar-masalah': 'search',
                 ketersediaan: 'pulse', pod: 'box', bisnis: 'briefcase', pelacakan: 'route' };
  const ingestTone = $derived(ingest?.running ? 'accent' : ingest?.last_status === 'ok' ? 'ok' : ingest?.last_status ? 'err' : '');

  const href = (patch) => build({ ...route, ...patch, q: null, ...(patch.tab !== 'layanan' ? { service: null } : {}) });
  const active = (tab, service = null) => (route.tab === tab && (tab !== 'layanan' || route.service === service) ? 'page' : undefined);
</script>

<div class="logo" class:c={collapsed}>
  <i aria-hidden="true">{APP_MARK}</i><span class="name">{APP_NAME}</span>
  {#if ontoggle}
    <button class="tog" onclick={ontoggle} aria-expanded={!collapsed} aria-controls="side"
      aria-label={$t(collapsed ? 'nav.expand' : 'nav.collapse')} title={$t(collapsed ? 'nav.expand' : 'nav.collapse')}>
      <Icon name={collapsed ? 'side-open' : 'side-close'} />
    </button>
  {/if}
</div>
<nav aria-label={$t('nav.label')} class:c={collapsed}>
  <h2 class="grp" id="nav-analisis">{$t('nav.analysis')}</h2>
  <ul aria-labelledby="nav-analisis">
    {#each TABS as tab}
      <li>
        <a href={href({ tab })} aria-current={active(tab)} onclick={onpick} title={tip($t(`tab.${tab}`))}>
          <Icon name={ICON[tab]} /><span class="lbl">{$t(`tab.${tab}`)}</span>
          {#if tab === 'keamanan' && summary?.attack_ip_count}
            <span class="b" aria-hidden="true">{num(summary.attack_ip_count, $lang)} IP</span><span class="pip" aria-hidden="true"></span>
            <span class="sr-only">{$t('nav.badge_attack', { n: num(summary.attack_ip_count, $lang) })}</span>
          {/if}
        </a>
      </li>
    {/each}
  </ul>
  {#if summary?.services?.length}
    <h2 class="grp" id="nav-layanan">{$t('nav.services')}</h2>
    <ul aria-labelledby="nav-layanan">
      {#each summary.services as s}
        <li>
          <a href={href({ tab: 'layanan', service: s.service })} aria-current={active('layanan', s.service)} onclick={onpick} title={tip(sysName(s.service))}>
            <Icon name="server" /><span class="lbl sys">{sysName(s.service)}</span>
            {#if s.err}
              <span class="b" aria-hidden="true">{num(s.err, $lang)}</span><span class="pip" aria-hidden="true"></span>
              <span class="sr-only">{$t('nav.badge_err', { n: num(s.err, $lang) })}</span>
            {/if}
          </a>
        </li>
      {/each}
    </ul>
  {/if}
</nav>
<div class="foot" class:c={collapsed}>
  <div class="row" title={tip($t('ui.all_wib'))}><Icon name="clock" size={16} /><span class="tz">{$t('ui.all_wib')}</span></div>
  {#if ingest}
    {@const st = ingest.running ? $t('ingest.running') : $t(`ingest.${ingest.last_status || 'none'}`)}
    <div class="row muted" title={tip(st)}><span class="dot {ingestTone}" aria-hidden="true"></span><span class="tz">{st}</span></div>
  {/if}
</div>

<style>
  .logo { display: flex; align-items: center; gap: 10px; padding: 2px 6px 6px; font-weight: 600; font-size: 1rem; }
  .name { flex: 1; min-width: 0; white-space: nowrap; }
  .tog {
    flex: none; width: 32px; height: 32px; display: grid; place-items: center; border-radius: 9px; cursor: pointer;
    background: transparent; border: 1px solid transparent; color: var(--muted); padding: 0;
  }
  .tog:hover { background: var(--nav-hover); color: var(--fg); border-color: var(--line); }
  .pip { display: none; }
  .logo i {
    width: 32px; height: 32px; border-radius: 9px; display: grid; place-items: center; font-style: normal; font-weight: 700;
    font-size: 0.8125rem; color: var(--brand-fg); background: var(--brand-bg); box-shadow: 0 0 18px rgba(45, 212, 191, 0.25);
  }
  nav { display: flex; flex-direction: column; overflow-y: auto; flex: 1; scrollbar-width: thin; scrollbar-color: var(--scroll-thumb) transparent; }
  ul { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 2px; }
  .grp { font-size: 0.6875rem; font-weight: 500; letter-spacing: 0.08em; color: var(--muted); margin: 14px 10px 6px; text-transform: uppercase; }
  a {
    font-size: 0.84375rem; display: flex; align-items: center; gap: 10px; width: 100%; text-decoration: none;
    color: var(--nav-fg); padding: 8px 10px; border-radius: 10px; min-height: 38px; text-transform: capitalize;
    border: 1px solid transparent; transition: background 0.15s, color 0.15s;
  }
  a :global(svg) { color: var(--muted); }
  a:hover { background: var(--nav-hover); color: var(--fg); }
  a[aria-current='page'] { background: rgba(45, 212, 191, 0.1); border-color: rgba(45, 212, 191, 0.18); color: var(--accent-text); }
  a[aria-current='page'] :global(svg) { color: var(--accent-text); }
  .lbl { min-width: 0; overflow-wrap: anywhere; }
  .b { margin-left: auto; font-size: 0.6875rem; color: var(--badge-fg); background: var(--badge-bg); padding: 1px 7px; border-radius: 999px; white-space: nowrap; text-transform: none; }
  .foot {
    border: 1px solid var(--card-border); background: var(--card-bg); border-radius: 14px; padding: 10px 12px;
    display: flex; flex-direction: column; gap: 6px; font-size: 0.75rem;
  }
  .row { display: flex; align-items: center; gap: 8px; color: var(--muted); }
  .tz { text-transform: capitalize; }
  @media (max-width: 900px) {
    a { min-height: var(--touch); }
    .tog { display: none; }   /* layar sempit: laci dengan ☰ di kepala halaman, tidak diciutkan */
  }
  /* lajur ikon (hanya layar lebar; lebar --side-w-c di theme.css) */
  @media (min-width: 901px) {
    .logo.c { flex-direction: column; padding: 2px 0 6px; gap: 12px; }
    .logo.c .name, nav.c .lbl, nav.c .b, .foot.c .tz { display: none; }
    nav.c .grp { height: 1px; margin: 12px 8px; background: var(--line); overflow: hidden; color: transparent; }
    nav.c a { justify-content: center; padding: 8px 0; position: relative; }
    nav.c .pip { display: block; position: absolute; top: 7px; right: 10px; width: 7px; height: 7px; border-radius: 50%; background: var(--err); box-shadow: 0 0 0 2px var(--side-bg); }
    .foot.c { align-items: center; padding: 10px 0; }
  }
</style>
