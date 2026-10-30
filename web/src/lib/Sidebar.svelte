<!-- Navigation (DRD §1.1, §2.1, §9.4, §12 style): Analysis group (9 tabs, old order) and Services (those in the selected
     folder, file order), each item with an icon. Badges: Security "N IP", services = error count; with hidden text
     for screen readers. Footer: time zone card + ingest status. Same for admin and user.
     On narrow screens shown as a drawer (App.svelte). On wide screens it can be collapsed into an icon rail (owner request
     2026-10-07; button next to the logo, choice stored per browser): labels via `title`, badges become dots.
     Owner request 2026-10-08: a third group, Configuration (admins), whose items open pop-ups (lib/ConfigDialogs.svelte),
     and every group (Analysis, Services, Configuration) folds open/closed with an animation; the choice is kept per
     browser. In the icon rail the groups are always open (their headings are only separators).
     Redesign 2026-10-27: the Services group lists every service (error badges; "!" for a corrupt file) with a search box
     when there are more than six (owner: "just make it the services", no problems-only list). -->
<script>
  import { lang, t } from '../i18n.js';
  import { num, sysName } from '../format.js';
  import { TABS, build } from '../state.js';
  import { APP_NAME } from '../brand.js';
  import Logo from './Logo.svelte';
  import Icon from './Icon.svelte';
  import { CONFIG, configOpen, openConfig } from './ConfigDialogs.svelte';
  let { route, summary = null, ingest = null, onpick = null, collapsed = false, ontoggle = null, admin = false } = $props();

  // open/closed groups, per browser (wrapped: storage can be missing or blocked)
  const KEY = 'nav-groups';
  let open = $state(read());
  function read() {
    try { return { analysis: true, services: true, config: true, ...JSON.parse(localStorage.getItem(KEY) || '{}') }; }
    catch { return { analysis: true, services: true, config: true }; }
  }
  function fold(g) {
    open = { ...open, [g]: !open[g] };
    try { localStorage.setItem(KEY, JSON.stringify(open)); } catch { /* not kept */ }
  }
  const isOpen = (g) => collapsed || open[g];

  // services: all of them; the search box narrows the list (the icon rail always shows all)
  let q = $state('');
  const all = $derived(summary?.services || []);
  const shownSvc = $derived.by(() => {
    const term = collapsed ? '' : q.trim().toLowerCase();
    return term ? all.filter((s) => s.service.toLowerCase().includes(term)) : all;
  });
  const tip = (s) => (collapsed ? s : undefined);

  const ICON = { overview: 'overview', 'command-center': 'globe', trends: 'trend', security: 'shield', 'root-causes': 'search',
                 availability: 'pulse', pods: 'box', business: 'briefcase', tracing: 'route', 'raw-logs': 'terminal' };
  const ingestTone = $derived(ingest?.running ? 'accent' : ingest?.last_status === 'ok' ? 'ok' : ingest?.last_status ? 'err' : '');

  const href = (patch) => build({ ...route, ...patch, q: null, ...(patch.tab !== 'service' ? { service: null } : {}) });
  const active = (tab, service = null) => (route.tab === tab && (tab !== 'service' || route.service === service) ? 'page' : undefined);
</script>

<div class="logo" class:c={collapsed}>
  <Logo size={32} glow /><span class="name">{APP_NAME}</span>
  {#if ontoggle}
    <button class="tog" onclick={ontoggle} aria-expanded={!collapsed} aria-controls="side"
      aria-label={$t(collapsed ? 'nav.expand' : 'nav.collapse')} title={$t(collapsed ? 'nav.expand' : 'nav.collapse')}>
      <Icon name={collapsed ? 'side-open' : 'side-close'} />
    </button>
  {/if}
</div>
<nav aria-label={$t('nav.label')} class:c={collapsed}>
  {@render head('analysis', 'nav-analisis', $t('nav.analysis'))}
  <div class="fold" class:shut={!isOpen('analysis')} id="grp-analysis" inert={!isOpen('analysis') || undefined}><div class="in">
  <ul aria-labelledby="nav-analisis">
    {#each TABS as tab}
      <li>
        <a href={href({ tab })} aria-current={active(tab)} onclick={onpick} title={tip($t(`tab.${tab}`))}>
          <Icon name={ICON[tab]} /><span class="lbl">{$t(`tab.${tab}`)}</span>
          {#if tab === 'security' && summary?.attack_ip_count}
            <span class="b" aria-hidden="true">{num(summary.attack_ip_count, $lang)} IP</span><span class="pip" aria-hidden="true"></span>
            <span class="sr-only">{$t('nav.badge_attack', { n: num(summary.attack_ip_count, $lang) })}</span>
          {/if}
        </a>
      </li>
    {/each}
  </ul>
  </div></div>
  {#if summary?.services?.length}
    {@render head('services', 'nav-services', $t('nav.services'))}
    <div class="fold" class:shut={!isOpen('services')} id="grp-services" inert={!isOpen('services') || undefined}><div class="in">
    {#if !collapsed && all.length > 6}
      <label class="sr-only" for="svc-q">{$t('nav.svc_search')}</label>
      <input id="svc-q" class="q" type="search" placeholder="{$t('nav.svc_search')}…" bind:value={q} />
    {/if}
    <ul aria-labelledby="nav-services">
      {#each shownSvc as s}
        <li>
          <a href={href({ tab: 'service', service: s.service })} aria-current={active('service', s.service)} onclick={onpick} title={tip(sysName(s.service))}>
            <Icon name="server" /><span class="lbl sys">{sysName(s.service)}</span>
            {#if s.err}
              <span class="b" aria-hidden="true">{num(s.err, $lang)}</span><span class="pip" aria-hidden="true"></span>
              <span class="sr-only">{$t('nav.badge_err', { n: num(s.err, $lang) })}</span>
            {:else if s.files_corrupt}
              <span class="b warn" aria-hidden="true">!</span><span class="sr-only">{$t('ov.badge_corrupt')}</span>
            {/if}
          </a>
        </li>
      {/each}
    </ul>
    </div></div>
  {/if}
  {#if admin}
    {@render head('config', 'nav-config', $t('nav.config'))}
    <div class="fold" class:shut={!isOpen('config')} id="grp-config" inert={!isOpen('config') || undefined}><div class="in">
    <ul aria-labelledby="nav-config">
      {#each CONFIG as c}
        <li>
          <button type="button" class="item" aria-haspopup="dialog" aria-current={$configOpen === c.id ? 'true' : undefined}
            onclick={() => { onpick?.(); openConfig(c.id); }} title={tip($t(`nav.cfg.${c.id}`))}>
            <Icon name={c.icon} /><span class="lbl">{$t(`nav.cfg.${c.id}`)}</span>
          </button>
        </li>
      {/each}
    </ul>
    </div></div>
  {/if}
</nav>

{#snippet head(g, id, label)}
  <h2 class="grp" {id}>
    <button type="button" class="gbtn" aria-expanded={isOpen(g)} aria-controls="grp-{g}" disabled={collapsed} onclick={() => fold(g)}>
      <span>{label}</span><span class="chev" class:up={isOpen(g)}><Icon name="chevron" size={14} /></span>
    </button>
  </h2>
{/snippet}
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
  nav { display: flex; flex-direction: column; overflow-y: auto; flex: 1; scrollbar-width: thin; scrollbar-color: var(--scroll-thumb) transparent; }
  ul { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 2px; }
  .grp { font-size: 0.6875rem; font-weight: 500; letter-spacing: 0.08em; color: var(--muted); margin: 10px 0 2px; text-transform: uppercase; }
  .gbtn {
    width: 100%; display: flex; align-items: center; justify-content: space-between; gap: 8px; padding: 6px 10px; min-height: 30px;
    background: none; border: 0; border-radius: 8px; color: inherit; font: inherit; letter-spacing: inherit; text-transform: inherit; cursor: pointer;
  }
  .gbtn:hover:not(:disabled) { color: var(--fg); background: var(--nav-hover); }
  .gbtn:disabled { cursor: default; }
  .chev { display: grid; transition: transform 0.25s ease; transform: rotate(-90deg); }
  .chev.up { transform: rotate(0deg); }
  /* fold: the row height animates between 0fr and 1fr (no fixed heights), the content fades along */
  .fold { display: grid; grid-template-rows: 1fr; transition: grid-template-rows 0.28s ease, opacity 0.28s ease; }
  .fold.shut { grid-template-rows: 0fr; opacity: 0; }
  .fold > .in { overflow: hidden; min-height: 0; }
  @media (prefers-reduced-motion: reduce) { .fold, .chev { transition: none; } }
  .item { background: none; font: inherit; cursor: pointer; text-align: left; text-transform: none !important; }
  a, .item {
    font-size: 0.84375rem; display: flex; align-items: center; gap: 10px; width: 100%; text-decoration: none;
    color: var(--nav-fg); padding: 8px 10px; border-radius: 10px; min-height: 38px; text-transform: capitalize;
    border: 1px solid transparent; transition: background 0.15s, color 0.15s;
  }
  a :global(svg), .item :global(svg) { color: var(--muted); }
  a:hover, .item:hover { background: var(--nav-hover); color: var(--fg); }
  a[aria-current='page'], .item[aria-current='true'] { background: var(--seg-on); border-color: color-mix(in srgb, var(--accent) 22%, transparent); color: var(--accent-text); }
  a[aria-current='page'] :global(svg), .item[aria-current='true'] :global(svg) { color: var(--accent-text); }
  .lbl { min-width: 0; overflow-wrap: anywhere; }
  .q { width: 100%; box-sizing: border-box; min-height: 36px; margin: 2px 0 6px; padding: 6px 12px; border-radius: 10px; font-size: 0.8125rem; }
  /* the group folds with overflow: hidden, so the focus ring is drawn inside the field instead of around it */
  nav :focus-visible { outline-offset: -2px; }   /* links and buttons inside the folding groups: ring drawn inside, never clipped */
  .q:focus-visible { outline: none; border-color: var(--focus); box-shadow: inset 0 0 0 1px var(--focus); }
  .b.warn { color: var(--sev2-fg); background: color-mix(in srgb, var(--warn) 14%, transparent); }
  .b { margin-left: auto; font-size: 0.6875rem; color: var(--badge-fg); background: var(--badge-bg); padding: 1px 7px; border-radius: 999px; white-space: nowrap; text-transform: none; }
  .foot {
    border: 1px solid var(--card-border); background: var(--card-bg); border-radius: 14px; padding: 10px 12px;
    display: flex; flex-direction: column; gap: 6px; font-size: 0.75rem;
  }
  .row { display: flex; align-items: center; gap: 8px; color: var(--muted); }
  .tz { text-transform: capitalize; }
  @media (max-width: 900px) {
    a, .item { min-height: var(--touch); }
    .tog { display: none; }   /* narrow screen: drawer with ☰ in the page header, not collapsed */
  }
  /* icon rail (wide screens only; width --side-w-c in theme.css) */
  @media (min-width: 901px) {
    .logo.c { flex-direction: column; padding: 2px 0 6px; gap: 12px; }
    .logo.c .name, nav.c .lbl, nav.c .b, .foot.c .tz { display: none; }
    nav.c .grp { height: 1px; margin: 12px 8px; background: var(--line); overflow: hidden; color: transparent; }
    nav.c .gbtn { display: none; }
    nav.c a, nav.c .item { justify-content: center; padding: 8px 0; position: relative; }
    nav.c .pip { display: block; position: absolute; top: 7px; right: 10px; width: 7px; height: 7px; border-radius: 50%; background: var(--err); box-shadow: 0 0 0 2px var(--side-bg); }
    .foot.c { align-items: center; padding: 10px 0; }
  }
</style>
