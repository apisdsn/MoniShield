<!-- Overview (DRD §3.1, inv. §2.1). Sumber (TRD §5.3): /overview (periode, error per jam per layanan, 25 pesan
     teratas), ringkasan folder dari App (/api/folders/{f}: KPI, layanan, file), dan /services/nginx-ingress-controller
     untuk bagian "Traffic HTTP seluruh sistem" (kartu layanan nginx tanpa peta dan tanpa kartu pesan). Dua
     permintaan halaman berjalan bersamaan dan tampil bersama (U31). -->
<script>
  import { untrack } from 'svelte';
  import { lang, t } from '../i18n.js';
  import { api } from '../api.js';
  import { num, delta, sysName, tWIB } from '../format.js';
  import Kpi from '../lib/Kpi.svelte';
  import ChartCard from '../lib/ChartCard.svelte';
  import DataTable from '../lib/DataTable.svelte';
  import MessagesTable from '../lib/MessagesTable.svelte';
  import ServiceCards from '../lib/ServiceCards.svelte';
  import Skeleton from '../lib/Skeleton.svelte';
  import ErrorState from '../lib/ErrorState.svelte';

  let { folder, summary, reloadKey = 0, onready = null } = $props();
  const NG = 'nginx-ingress-controller';

  // view = potret data yang sedang tampil; saat ganti folder isi lama tetap terlihat (diredupkan) sampai yang baru tiba
  let view = $state(null), busy = $state(false), error = $state(null);
  let seq = 0, loadedKey = '';
  const current = $derived(summary?.folder === folder ? summary : null);

  async function load(sum) {
    const my = ++seq;
    busy = true; error = null; onready?.(false);
    const f = encodeURIComponent(sum.folder);
    const hasNg = sum.services.some((s) => s.service === NG && s.lines);
    try {
      const [o, n] = await Promise.all([api.get(`/api/folders/${f}/overview`), hasNg ? api.get(`/api/folders/${f}/services/${NG}`) : null]);
      if (my === seq) view = { folder: sum.folder, summary: sum, page: o, nginx: n };
    } catch (e) {
      if (my === seq) error = e;
    } finally {
      if (my === seq) { busy = false; onready?.(true); }
    }
  }
  // muat sekali per (folder, muat ulang), setelah ringkasan folder itu tiba (tahu ada nginx atau tidak)
  $effect(() => {
    const key = `${folder}|${reloadKey}`;
    if (!current || key === loadedKey) return;
    loadedKey = key;
    untrack(() => load(current));
  });

  const page = $derived(view?.page), nginx = $derived(view?.nginx), summ = $derived(view?.summary);
  const svc = $derived(summ?.services || []);
  const ngRow = $derived(svc.find((s) => s.service === NG && s.lines) || null);

  // perubahan vs folder sebelumnya hanya atas layanan yang sebanding (lama: comparable/dlt, inv. §2.0)
  const cmp = $derived(svc.filter((s) => s.lines && s.prev && s.prev.lines >= 0.5 * s.lines));
  const sum = (list, k) => list.reduce((a, s) => a + (s[k] || 0), 0);
  const d = (k, good = false) => summ?.prev_folder
    ? delta(sum(cmp, k), sum(cmp.map((s) => s.prev), k), summ.prev_folder, $lang, { good, comparable: cmp.length > 0 }) : null;
  const files = $derived(summ?.files || []);
  const nCorrupt = $derived(files.filter((f) => f.status === 'rusak').length);
  const rate = (n, dg) => `${num((n / ngRow.requests) * 100, $lang, dg)}%`;

  // error per jam per layanan: batang bertumpuk, jam gabungan semua layanan
  const errSeries = $derived(Object.entries(page?.err_by_hour || {}));
  const hours = $derived([...new Set(errSeries.flatMap(([, pts]) => pts.map((p) => p[0])))].sort());
</script>

{#if error && !view}
  <ErrorState {error} onretry={() => current && load(current)} />
{:else if !view}
  <Skeleton kpis={8} charts={3} />
{:else}
  {#if error}<ErrorState {error} onretry={() => current && load(current)} />{/if}
  <div class="content" class:dim={busy || view.folder !== folder}>
    {#if page.period?.start}
      <p class="period muted">{$t('ov.period')} <b>{tWIB(page.period.start + ':00', $lang)} – {tWIB(page.period.end + ':59', $lang)}</b></p>
    {/if}
    <div class="kpis">
      <Kpi icon="lines" label={$t('kpi.lines')} value={sum(svc, 'lines')} delta={d('lines', true)} />
      <Kpi icon="alert" label={$t('kpi.error')} value={sum(svc, 'err')} tone="err" delta={d('err')}
        info={$t('kpi.error_info', { http: num(sum(svc, 'err_http'), $lang), log: num(sum(svc, 'err_log'), $lang) })} />
      <Kpi icon="alert" label={$t('ov.warn_4xx')} value={sum(svc, 'warn')} tone="warn" delta={d('warn')} info={$t('ov.warn_4xx_info')} />
      {#if ngRow?.requests}
        <Kpi icon="pulse" label={$t('kpi.http')} value={ngRow.requests} />
        <Kpi icon="trend" label={$t('kpi.rate4xx')} value={rate(ngRow.n4xx, 1)} tone="warn" />
        <Kpi icon="trend" label={$t('kpi.rate5xx')} value={rate(ngRow.n5xx, 2)} tone="err" />
      {/if}
      <Kpi icon="server" label={$t('ov.services')} value={svc.length} />
      <Kpi icon="file" label={$t('kpi.files')} value={files.length} />
      <Kpi icon="file" label={$t('kpi.files_empty')} value={files.filter((f) => !f.size_bytes).length} tone="muted" />
      {#if nCorrupt}<Kpi icon="file" label={$t('ov.files_corrupt')} value={nCorrupt} tone="warn" />{/if}
    </div>

    <div class="grid">
      <ChartCard title={$t('ov.err_per_hour')} type="bar" timeAxis wide labels={hours} chip={$t('chip.hourly')}
        info={$t('svc.hour_err_info')}
        datasets={errSeries.map(([s, pts], i) => { const m = Object.fromEntries(pts); return { label: sysName(s), data: hours.map((h) => m[h] || 0), color: `--c${(i % 10) + 1}` }; })}
        options={{ scales: { x: { stacked: true }, y: { stacked: true } } }} />
      <ChartCard title={$t('ov.err_warn_per_service')} type="bar" labels={svc.map((s) => sysName(s.service))}
        datasets={[{ label: $t('kpi.error'), data: svc.map((s) => s.err), color: '--err' }, { label: 'Warn', data: svc.map((s) => s.warn), color: '--warn' }]}
        options={{ indexAxis: 'y' }} />
      <ChartCard title={$t('ov.lines_per_service')} type="bar" labels={svc.map((s) => sysName(s.service))}
        datasets={[{ label: $t('col.lines'), data: svc.map((s) => s.lines), color: '--accent' }]}
        options={{ indexAxis: 'y', plugins: { legend: { display: false } } }} />
      <DataTable wide={false} title={$t('ov.service_summary')} rows={svc} limit={50} columns={[
        { key: 'service', label: $t('col.service'), fmt: (r) => sysName(r.service), cls: () => 'nowrap', sort: true },
        { key: 'lines', label: $t('col.lines'), type: 'num', sort: true },
        { key: 'err', label: $t('kpi.error'), type: 'num', sort: true },
        { key: 'warn', label: 'Warn', type: 'num', sort: true },
        { key: 'files', label: $t('col.pod'), type: 'num', sort: true },
      ]} />
      <DataTable wide={false} title={$t('kpi.files')} rows={files} limit={50} columns={[
        { key: 'pod', label: $t('col.pod'), fmt: (r) => `${sysName(r.service)} / ${sysName(r.pod)}`, sort: true },
        { key: 'lines', label: $t('col.lines'), type: 'num', sort: true },
        { key: 'size_bytes', label: $t('col.size'), type: 'num', fmt: (r) => `${num(r.size_bytes / 1048576, $lang, 2)} MB`, sort: true },
      ]} />
      <MessagesTable title={$t('ov.top_msgs')} folder={view.folder} initial={page.tables.messages} crossService chip={$t('chip.all_data')} />
    </div>

    {#if nginx?.available}
      <section class="traffic" aria-labelledby="traffic-h">
        <h2 id="traffic-h">{$t('ov.traffic')}</h2>
        <p class="muted">{$t('ov.traffic_note')}</p>
        <div class="grid"><ServiceCards data={nginx} folder={view.folder} withMsgs={false} /></div>
      </section>
    {/if}
  </div>
{/if}

<style>
  .content { transition: opacity 0.15s; }
  .content.dim { opacity: 0.6; }
  .period { margin: 0 0 14px; font-size: 0.8125rem; }
  .period b { color: var(--fg); font-weight: 600; }
  .traffic { margin-top: 26px; }
  .traffic h2 { font-size: 1rem; font-weight: 600; color: var(--heading); text-transform: capitalize; margin: 0 0 4px; }
  .traffic > p { margin: 0 0 14px; font-size: 0.75rem; }
</style>
