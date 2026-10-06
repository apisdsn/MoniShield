<!-- Navigasi (DRD §1.1, §2.1, §9.4): grup Analisis (9 tab, urutan lama) dan Layanan (yang ada di folder terpilih,
     urutan file). Lencana: Keamanan "N IP", layanan = jumlah error; punya teks tersembunyi untuk pembaca layar.
     Sama untuk admin dan user. Di layar sempit tampil sebagai laci (App.svelte). -->
<script>
  import { lang, t } from '../i18n.js';
  import { num, titleCase } from '../format.js';
  import { TABS, build } from '../state.js';
  import { APP_NAME } from '../brand.js';
  let { route, summary = null, onpick = null } = $props();

  const href = (patch) => build({ ...route, ...patch, ...(patch.tab !== 'layanan' ? { service: null } : {}) });
  const active = (tab, service = null) => (route.tab === tab && (tab !== 'layanan' || route.service === service) ? 'page' : undefined);
</script>

<div class="logo"><i aria-hidden="true">S4</i><span>{APP_NAME}</span></div>
<nav aria-label={$t('nav.label')}>
  <h2 class="grp" id="nav-analisis">{$t('nav.analysis')}</h2>
  <ul aria-labelledby="nav-analisis">
    {#each TABS as tab}
      <li>
        <a href={href({ tab })} aria-current={active(tab)} onclick={onpick}>
          <span class="dot" aria-hidden="true"></span><span class="lbl">{$t(`tab.${tab}`)}</span>
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
            <span class="dot" aria-hidden="true"></span><span class="lbl">{titleCase(s.service)}</span>
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
<p class="tz">{$t('ui.all_wib')}</p>

<style>
  .logo { display: flex; align-items: center; gap: 10px; padding: 0 6px; font-weight: 600; letter-spacing: 0.02em; }
  .logo i {
    width: 38px; height: 38px; border-radius: 12px; display: grid; place-items: center; font-style: normal; font-weight: 700;
    color: var(--accent-text); background: rgba(45, 212, 191, 0.08);
    box-shadow: inset 0 0 0 1px rgba(45, 212, 191, 0.2), 0 0 18px rgba(45, 212, 191, 0.15);
  }
  nav { display: flex; flex-direction: column; overflow-y: auto; flex: 1; scrollbar-width: thin; scrollbar-color: var(--scroll-thumb) transparent; }
  ul { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 2px; }
  .grp { font-size: 0.6875rem; font-weight: 400; letter-spacing: 0.08em; color: var(--muted); margin: 12px 10px 6px; text-transform: uppercase; }
  a {
    font-size: 0.84375rem; display: flex; align-items: center; gap: 10px; width: 100%; text-decoration: none;
    color: var(--nav-fg); padding: 9px 12px; border-radius: 12px; min-height: 40px; text-transform: capitalize;
    transition: background 0.15s, color 0.15s;
  }
  a:hover { background: var(--nav-hover); color: var(--fg); }
  .dot { width: 7px; height: 7px; border-radius: 50%; background: var(--nav-dot); flex: none; }
  a[aria-current='page'] {
    background: linear-gradient(90deg, rgba(45, 212, 191, 0.16), rgba(45, 212, 191, 0.02));
    color: var(--accent-text); box-shadow: inset 2px 0 0 var(--accent);
  }
  a[aria-current='page'] .dot { background: var(--accent); box-shadow: 0 0 10px var(--accent); }
  .lbl { min-width: 0; overflow-wrap: anywhere; }
  .b { margin-left: auto; font-size: 0.6875rem; color: var(--badge-fg); background: var(--badge-bg); padding: 1px 7px; border-radius: 999px; white-space: nowrap; text-transform: none; }
  .tz { font-size: 0.75rem; color: var(--muted); padding: 0 10px; margin: 0; text-transform: capitalize; }
  @media (max-width: 900px) { a { min-height: var(--touch); } }
</style>
