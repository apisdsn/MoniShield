<!-- Navigasi (DRD §1.1, §2.1, §9.4, gaya §12): grup Analisis (9 tab, urutan lama) dan Layanan (yang ada di folder
     terpilih, urutan file), tiap butir berikon. Lencana: Keamanan "N IP", layanan = jumlah error; punya teks
     tersembunyi untuk pembaca layar. Kaki: kartu zona waktu + status ingest. Sama untuk admin dan user.
     Di layar sempit tampil sebagai laci (App.svelte). -->
<script>
  import { lang, t } from '../i18n.js';
  import { num, sysName } from '../format.js';
  import { TABS, build } from '../state.js';
  import { APP_NAME, APP_MARK } from '../brand.js';
  import Icon from './Icon.svelte';
  let { route, summary = null, ingest = null, onpick = null } = $props();

  const ICON = { overview: 'overview', peta: 'globe', tren: 'trend', keamanan: 'shield', 'akar-masalah': 'search',
                 ketersediaan: 'pulse', pod: 'box', bisnis: 'briefcase', pelacakan: 'route' };
  const ingestTone = $derived(ingest?.running ? 'accent' : ingest?.last_status === 'ok' ? 'ok' : ingest?.last_status ? 'err' : '');

  const href = (patch) => build({ ...route, ...patch, q: null, ...(patch.tab !== 'layanan' ? { service: null } : {}) });
  const active = (tab, service = null) => (route.tab === tab && (tab !== 'layanan' || route.service === service) ? 'page' : undefined);
</script>

<div class="logo"><i aria-hidden="true">{APP_MARK}</i><span>{APP_NAME}</span></div>
<nav aria-label={$t('nav.label')}>
  <h2 class="grp" id="nav-analisis">{$t('nav.analysis')}</h2>
  <ul aria-labelledby="nav-analisis">
    {#each TABS as tab}
      <li>
        <a href={href({ tab })} aria-current={active(tab)} onclick={onpick}>
          <Icon name={ICON[tab]} /><span class="lbl">{$t(`tab.${tab}`)}</span>
          {#if tab === 'keamanan' && summary?.attack_ip_count}
            <span class="b" aria-hidden="true">{num(summary.attack_ip_count, $lang)} IP</span>
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
          <a href={href({ tab: 'layanan', service: s.service })} aria-current={active('layanan', s.service)} onclick={onpick}>
            <Icon name="server" /><span class="lbl sys">{sysName(s.service)}</span>
            {#if s.err}
              <span class="b" aria-hidden="true">{num(s.err, $lang)}</span>
              <span class="sr-only">{$t('nav.badge_err', { n: num(s.err, $lang) })}</span>
            {/if}
          </a>
        </li>
      {/each}
    </ul>
  {/if}
</nav>
<div class="foot">
  <div class="row"><Icon name="clock" size={16} /><span class="tz">{$t('ui.all_wib')}</span></div>
  {#if ingest}
    <div class="row muted"><span class="dot {ingestTone}" aria-hidden="true"></span>{ingest.running ? $t('ingest.running') : $t(`ingest.${ingest.last_status || 'none'}`)}</div>
  {/if}
</div>

<style>
  .logo { display: flex; align-items: center; gap: 10px; padding: 2px 6px 6px; font-weight: 600; font-size: 1rem; }
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
  @media (max-width: 900px) { a { min-height: var(--touch); } }
</style>
