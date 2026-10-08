<!-- Root Cause (DRD §3.5, inv. §2.5): "Ringkasan akar masalah" (up to 5 items), 4 charts, 3 tables.
     New (B07): "Refresh token kedaluwarsa: N" below the JWT age chart. DNS upstream from configuration (old: hard-coded).
     One request: GET /api/folders/{folder}/rootcause. -->
<script>
  import { lang, t } from '../i18n.js';
  import { api } from '../api.js';
  import { num, sysName, cut } from '../format.js';
  import ChartCard from '../lib/ChartCard.svelte';
  import DataTable from '../lib/DataTable.svelte';
  import Note from '../lib/Note.svelte';
  import Summary from '../lib/Summary.svelte';
  import Skeleton from '../lib/Skeleton.svelte';
  import ErrorState from '../lib/ErrorState.svelte';

  let { folder, dnsUpstream = '', reloadKey = 0, onready = null } = $props();
  let data = $state.raw(null), busy = $state(false), error = $state(null);
  let seq = 0;
  async function load() {
    const my = ++seq;
    busy = true; error = null; onready?.(false);
    try {
      const j = await api.get(`/api/folders/${encodeURIComponent(folder)}/rootcause`);
      if (my === seq) data = j;
    } catch (e) {
      if (my === seq) error = e;
    } finally {
      if (my === seq) { busy = false; onready?.(true); }
    }
  }
  $effect(() => { void [folder, reloadKey]; if (folder) load(); });

  const BUCKETS = ['< 5 Menit', '5–60 Menit', '1–24 Jam', '1–7 Hari', '> 7 Hari'];
  const bucketKey = (b) => `jwt.b${BUCKETS.indexOf(b)}`;
  // DNS timeout impact per domain (old: DNS_IMPACT); others "Resolusi domain eksternal"
  const IMPACT = [[/backup|s3\./i, 'rc.impact.backup'], [/pg-|postgres|\.local\.?$/i, 'rc.impact.db'], [/rancher|longhorn/i, 'rc.impact.rancher']];
  const impact = (d) => (IMPACT.find(([r]) => r.test(d)) || [0, 'rc.impact.external'])[1];
  const pct0 = (a, b) => (b ? `${num((a / b) * 100, $lang, 0)}%` : '-');

  const summary = $derived.by(() => {
    if (!data) return [];
    const T = data.tables, out = [];
    const c = T.c401?.rows?.[0];
    if (c) out.push([{ b: $t('rc.s.c401.b') }, { t: $t('rc.s.c401.t1', { ip: c.client.ip }) }, { code: c.endpoint },
                     { t: $t('rc.s.c401.t2', { n: num(c.n, $lang), peak: c.peak_per_min }) }]);
    if (data.jwt_total) out.push([{ b: $t('rc.s.jwt.b', { n: num(data.jwt_total, $lang) }) }, { t: $t('rc.s.jwt.t', { pct: pct0(data.jwt_over_1h, data.jwt_total) }) }]);
    if (data.pdf.fail) out.push([{ b: $t('rc.s.pdf.b', { n: num(data.pdf.fail, $lang) }) }, { t: $t('rc.s.pdf.t1') }, { code: 'Jasper template path : null' },
                                 { t: $t('rc.s.pdf.t2', { n: num(data.pdf.templates_failed, $lang) }) }]);
    if (data.dns_total) {
      const doms = (T.dns?.rows || []).filter((d) => IMPACT.some(([r]) => r.test(d.domain))).slice(0, 3).map((d) => d.domain);
      const parts = [{ b: $t('rc.s.dns.b', { n: num(data.dns_total, $lang) }) }, { t: $t('rc.s.dns.t', { dns: dnsUpstream }) }];
      if (doms.length) { parts.push({ t: $t('rc.s.dns.incl') }); doms.forEach((d, i) => { if (i) parts.push({ t: ', ' }); parts.push({ code: d }); }); }
      parts.push({ t: '.' });
      out.push(parts);
    }
    if (data.upstream_error_kinds.length)
      out.push([{ b: $t('rc.s.uperr.b', { n: num(data.upstream_errors_total, $lang) }) }, { t: $t('rc.s.uperr.t', { kind: data.upstream_error_kinds[0][0] }) }]);
    return out;
  });
  const jwtSvcs = $derived(Object.keys(data?.jwt || {}));
  const refresh = $derived(Object.values(data?.refresh_expired || {}).reduce((a, b) => a + b, 0));
</script>

{#if error && !data}
  <ErrorState {error} onretry={load} />
{:else if !data}
  <Skeleton kpis={0} charts={4} />
{:else}
  {@const T = data.tables}
  <div class="content" class:dim={busy}>
    {#if summary.length}
      <Summary title={$t('rc.summary')} items={summary} />
    {:else}
      <Note>{$t('rc.none')}</Note>
    {/if}
    <div class="grid">
      {#if T.c401?.total}
        {@const top = T.c401.rows.slice(0, 10)}
        <ChartCard title={$t('rc.c401_chart')} type="bar" labels={top.map((r) => cut(`${r.client.ip} ${r.endpoint}`, 48))}
          datasets={[{ label: '401', data: top.map((r) => r.n), color: '--err' }]}
          tooltipTitle={(i) => [`${top[i].client.ip} ${top[i].endpoint}`, ...(top[i].client.org ? [top[i].client.org] : [])]}
          options={{ indexAxis: 'y', plugins: { legend: { display: false } } }} />
      {/if}
      {#if data.jwt_total}
        <ChartCard title={$t('rc.jwt_chart')} type="bar" labels={BUCKETS.map((b) => $t(bucketKey(b)))}
          datasets={jwtSvcs.map((s, i) => ({ label: sysName(s), data: BUCKETS.map((b) => data.jwt[s][b] || 0), color: `--c${i + 1}` }))}
          options={{ scales: { x: { stacked: true }, y: { stacked: true } } }}>
          {#snippet footer()}
            <span class="refresh">{$t('rc.refresh_expired', { n: num(refresh, $lang) })}{#if Object.keys(data.refresh_expired).length > 1}{' '}({Object.entries(data.refresh_expired).map(([s, n]) => `${sysName(s)} ${num(n, $lang)}`).join(', ')}){/if}</span>
          {/snippet}
        </ChartCard>
      {/if}
      {#if T['pdf-templates']?.total}
        {@const top = T['pdf-templates'].rows.slice(0, 12)}
        <ChartCard title={$t('rc.pdf_chart')} type="bar" labels={top.map((r) => cut(r.template, 40))}
          datasets={[{ label: $t('rc.ok'), data: top.map((r) => r.ok), color: '--ok' }, { label: $t('rc.fail'), data: top.map((r) => r.fail), color: '--err' }]}
          tooltipTitle={(i) => top[i].template}
          options={{ indexAxis: 'y', scales: { x: { stacked: true }, y: { stacked: true } } }} />
      {/if}
      {#if data.upstream_error_kinds.length}
        <ChartCard title={$t('rc.uperr_chart')} type="bar" labels={data.upstream_error_kinds.map((k) => cut(k[0], 48))}
          datasets={[{ label: $t('rc.events'), data: data.upstream_error_kinds.map((k) => k[1]), color: '--err' }]}
          tooltipTitle={(i) => data.upstream_error_kinds[i][0]}
          options={{ indexAxis: 'y', plugins: { legend: { display: false } } }} />
      {/if}

      {#if T.c401?.total}
        <DataTable title={$t('rc.c401_table')} {folder} table="c401" initial={T.c401} columns={[
          { key: 'client', label: 'IP', type: 'ip', sort: true },
          { key: 'endpoint', label: $t('col.endpoint'), type: 'code', sort: true, minw: 220 },
          { key: 'n', label: $t('rc.col.n401'), type: 'num', cls: () => 'ERROR', sort: true },
          { key: 'peak_per_min', label: $t('rc.col.peak'), type: 'num', sort: true },
          { key: 'first', label: $t('col.time'), type: 'range', to: 'last', cls: () => 'nowrap', sort: true },
        ]} />
      {/if}
      {#if T['pdf-templates']?.total}
        <DataTable wide={false} title={$t('rc.pdf_table')} {folder} table="pdf-templates" initial={T['pdf-templates']} columns={[
          { key: 'template', label: $t('rc.col.template'), type: 'code', sort: true },
          { key: 'ok', label: $t('rc.ok'), type: 'num', sort: true },
          { key: 'fail', label: $t('rc.col.fail_null'), type: 'num', cls: (r) => (r.fail ? 'ERROR' : ''), sort: true },
        ]} />
      {/if}
      {#if T.dns?.total}
        <DataTable wide={false} title={$t('rc.dns_table')} {folder} table="dns" initial={T.dns} columns={[
          { key: 'domain', label: $t('col.domain'), type: 'code', sort: true },
          { key: 'n', label: $t('table.count'), type: 'num', sort: true },
          { key: 'impact', label: $t('rc.col.impact'), fmt: (r) => $t(impact(r.domain)) },
        ]} />
      {/if}
    </div>
  </div>
{/if}

<style>
  .content { transition: opacity 0.15s; }
  .content.dim { opacity: 0.6; }
  .refresh { font-weight: 500; }
</style>
