<!-- IP profile (Stage 24 item 4): #/ip/<ip>?folder=… — opened from an IP cell in any table or from the global search.
     One request: GET /api/folders/{folder}/ips/{ip}. Contents: owner & location (offline database), 8 KPIs for this folder,
     accounts tried, the IP's trail across all folders (links to its profile in that folder), and all ingress requests in this
     folder (max. 1,000) with category + CRS rule. ?cari= (requestId from the search) fills the request table filter. -->
<script>
  import { lang, t, countryName } from '../i18n.js';
  import { api } from '../api.js';
  import { num, dLabel } from '../format.js';
  import { route, build } from '../state.js';
  import Kpi from '../lib/Kpi.svelte';
  import DataTable from '../lib/DataTable.svelte';
  import SeverityTag from '../lib/SeverityTag.svelte';
  import StatusCode from '../lib/StatusCode.svelte';
  import Note from '../lib/Note.svelte';
  import Skeleton from '../lib/Skeleton.svelte';
  import ErrorState from '../lib/ErrorState.svelte';
  import EmptyState from '../lib/EmptyState.svelte';

  let { folder, ip, reloadKey = 0, onready = null } = $props();
  let data = $state.raw(null), busy = $state(false), error = $state(null);
  let seq = 0;
  async function load() {
    const my = ++seq;
    busy = true; error = null; onready?.(false);
    try {
      const j = await api.get(`/api/folders/${encodeURIComponent(folder)}/ips/${encodeURIComponent(ip)}`);
      if (my === seq) data = j;
    } catch (e) { if (my === seq) { error = e; data = null; } }
    finally { if (my === seq) { busy = false; onready?.(true); } }
  }
  $effect(() => { void [folder, ip, reloadKey]; if (folder && ip) load(); });

  const search = $derived($route.q ? { text: $route.q, seq: $route.q, scroll: true } : null);
  const cat = (c) => { if (!c) return ''; if (data.scheme !== 'crs') return $t(`cat.${c.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '')}`);
    const [id, fam] = c.split('/'); return `${$t(`capec.${id}`)}${fam ? ` · ${$t(`fam.${fam.replace(/-/g, '_')}`)}` : ''}`; };
  const where = $derived(data?.info ? [data.info.city, data.info.region, data.info.country ? $countryName(data.info.country) : null].filter(Boolean)
    .filter((x, i, a) => a.indexOf(x) === i).join(', ') : '');
</script>

{#if error?.status === 404}
  <EmptyState title={$t('ipp.not_found', { ip })} text={$t('ipp.not_found_text')} />
{:else if error && !data}
  <ErrorState {error} onretry={load} />
{:else if !data}
  <Skeleton kpis={8} charts={1} />
{:else}
  {@const k = data.kpi}
  <div class="content" class:dim={busy}>
    <p class="who">
      {#if data.info?.org}<span><b>AS{data.info.asn}</b> · {data.info.org}</span>{/if}
      {#if where}<span>{where}</span>{/if}
      {#if data.info?.private}<SeverityTag level={1} text={$t('ip.private')} />{/if}
      {#if /OMBUDSMAN/i.test(data.info?.org || '')}<SeverityTag level="ok" text={$t('ip.ombudsman')} />{/if}
      {#if k.first}<span class="muted">{$t('ipp.period', { a: k.first, b: k.last })}</span>{/if}
    </p>
    <div class="kpis four">
      <Kpi icon="pulse" label={$t('ipp.kpi.requests')} value={k.requests} />
      <Kpi icon="alert" label="4xx" value={k.n4xx} tone={k.n4xx ? 'warn' : null} />
      <Kpi icon="alert" label="5xx" value={k.n5xx} tone={k.n5xx ? 'err' : null} />
      <Kpi icon="shield" label={$t('ipp.kpi.attacks')} value={k.attacks} tone={k.attacks ? 'err' : null} />
      <Kpi icon="lines" label={$t('ipp.kpi.endpoints')} value={k.endpoints} />
      <Kpi icon="user" label={$t('ipp.kpi.uas')} value={k.user_agents} />
      <Kpi icon="key" label={$t('ipp.kpi.login_fail')} value={k.login_fail} tone={k.login_fail ? 'warn' : null} />
      <Kpi icon="users" label={$t('ipp.kpi.login_ok')} value={k.login_ok} />
    </div>
    {#if data.accounts.length}
      <Note>{$t('ipp.accounts', { n: num(data.accounts.length, $lang) })} {data.accounts.join(', ')}</Note>
    {/if}

    <div class="grid">
      <DataTable title={$t('ipp.folders')} rows={data.folders} limit={30} wide={false} columns={[
        { key: 'folder', label: $t('ipp.col.folder'), custom: true, sort: true },
        { key: 'requests', label: $t('ipp.kpi.requests'), type: 'num', sort: true },
        { key: 'attacks', label: $t('ipp.kpi.attacks'), type: 'num', sort: true },
        { key: 'login_fail', label: $t('ipp.kpi.login_fail'), type: 'num', sort: true },
        { key: 'login_ok', label: $t('ipp.kpi.login_ok'), type: 'num', sort: true },
        { key: 'traced', label: $t('ipp.col.traced'), type: 'num', sort: true },
      ]}>
        {#snippet cell(r)}{#if r.folder === folder}<b>{dLabel(r.folder, $lang)}</b>{:else}<a href={build({ tab: 'ip', service: ip, folder: r.folder })}>{dLabel(r.folder, $lang)}</a>{/if}{/snippet}
      </DataTable>

      <DataTable title={$t('ipp.requests')} rows={data.requests} limit={50} maxHeight={640} {search} columns={[
        { key: 'time', label: $t('col.time'), cls: () => 'nowrap', sort: true },
        { key: 'path', label: $t('col.url'), custom: true, minw: 320 },
        { key: 'status', label: $t('col.status'), type: 'num', custom: true, sort: true },
        { key: 'category', label: $t('col.category'), custom: true, minw: 160 },
        { key: 'upstream', label: $t('sec.col.upstream'), cls: () => 'nowrap sys small' },
        { key: 'ua', label: 'User-Agent', clip: true, minw: 200 },
        { key: 'request_id', label: 'requestId', cls: () => 'mono small' },
      ]}>
        {#snippet cell(r, c)}
          {#if c.key === 'path'}<code class="pth"><b>{r.method}</b> {r.path}</code>
          {:else if c.key === 'status'}<StatusCode counts={{ [r.status]: 1 }} />
          {:else if r.category}
            <SeverityTag level={r.severity || 1} text={cat(r.category)} />
            {#if r.rules.length}<div class="small muted">{#each r.rules as id}<div title={data.rule_msgs[id] || ''}>{id} · {data.rule_msgs[id] || ''}</div>{/each}</div>{/if}
          {/if}
        {/snippet}
      </DataTable>
    </div>
    {#if data.truncated}<Note>{$t('ipp.truncated', { n: num(k.requests, $lang) })}</Note>{/if}
    <p class="muted foot">{$t('ipp.privacy')}</p>
  </div>
{/if}

<style>
  .content { transition: opacity 0.15s; }
  .content.dim { opacity: 0.6; }
  .who { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 16px; margin: 0 0 14px; font-size: 0.8125rem; }
  .who b { font-family: var(--mono); font-weight: 600; }
  .pth { font-size: 0.75rem; overflow-wrap: anywhere; white-space: normal; }
  .small { font-size: 0.75rem; }
  .foot { font-size: 0.75rem; margin-top: 14px; }
</style>
