<!-- Kartu 2–19 halaman layanan (DRD §3.10, inv. §2.10), dipakai juga bagian "Traffic HTTP seluruh sistem" di
     Overview (tanpa kartu pesan: withMsgs=false). Kartu yang datanya kosong tidak dirender (lama): API hanya
     mengirim tabel yang berisi; chart dengan 0 titik tidak digambar ChartCard. Peta (kartu 1) ada di lib/ServiceMap (terlipat).
     data = respons GET /api/folders/{folder}/services/{service}. Top 10 chart = 10 baris pertama tabel terkait,
     yang urutannya sama dengan urutan lama. -->
<script>
  import { lang, t } from '../i18n.js';
  import { num, dur } from '../format.js';
  import ChartCard from './ChartCard.svelte';
  import HBar from './HBar.svelte';
  import DataTable from './DataTable.svelte';
  import MessagesTable from './MessagesTable.svelte';

  let { data, folder, withMsgs = true, search = null } = $props();   // search: filter tabel endpoint dari pencarian global (Tahap 24)

  const svc = $derived(data.service);
  const T = $derived(data.tables || {});
  const dns = $derived(svc === 'coredns');
  const SL = 'om-be-simpel-loop';
  const params = $derived({ service: svc });
  const top = (k, n = 10) => (T[k]?.rows || []).slice(0, n);
  const STATUS = { 2: '--ok', 3: '--neutral', 4: '--warn', 5: '--err' };
  const LVL = { ERROR: '--err', WARN: '--warn', INFO: '--accent', PERFORMANCE: '--ok', DEBUG: '--muted', EXC: '--err' };
  const statusTok = (c) => STATUS[String(c)[0]] || '--neutral';
  const pctS = (a, b, d = 1) => (b ? `${num((a / b) * 100, $lang, d)}%` : '-');
  const fs = (x) => (x === null || x === undefined ? '–' : dur(x, $lang));   // detik -> 850 ms / 2,35 dtk
  const hourTitle = $derived(
    $t('svc.hour') + (data.corr ? ' – ' + $t('svc.hour_corr', { pct: pctS(data.corr.matched, data.corr.total) }) : ''));
</script>

<!-- 2 aktivitas per jam: Total & Error -->
<ChartCard title={hourTitle} type="line" timeAxis wide labels={data.hour.map((h) => h[0])}
  info={['nginx-ingress-controller', 'om-fe-inhouse'].includes(svc) ? $t('svc.hour_err_info') : null}
  datasets={[{ label: $t('svc.total'), data: data.hour.map((h) => h[1]), color: '--accent' },
             { label: $t('kpi.error'), data: data.hour.map((h) => h[2]), color: '--violet' }]} />
<!-- 3 status code (sumbu logaritmik) -->
<ChartCard title={$t('svc.status')} type="bar" labels={data.status.map((s) => s[0])}
  datasets={[{ label: $t('table.count'), data: data.status.map((s) => s[1]), colors: data.status.map((s) => statusTok(s[0])) }]}
  options={{ scales: { y: { type: 'logarithmic', min: 0.5, ticks: { callback: (v) => (Number.isInteger(Math.log10(v)) ? num(v, $lang) : '') } } }, plugins: { legend: { display: false } } }} />
<!-- 4 traffic per upstream (donat) -->
<ChartCard title={$t('svc.upstream')} type="doughnut" labels={data.upstreams.map((u) => u[0])}
  datasets={[{ data: data.upstreams.map((u) => u[1]) }]} options={{ plugins: { legend: { position: 'right' } } }} />
<!-- 5 distribusi level (donat); warna level tetap, lainnya palet mulai seri 5 (lama) -->
<ChartCard title={$t('svc.levels')} type="doughnut" labels={data.levels.map((l) => l[0])}
  info={svc === SL ? $t('svc.levels_info') : null}
  datasets={[{ data: data.levels.map((l) => l[1]), colors: data.levels.map((l, i) => LVL[l[0]] || `--c${((i + 4) % 10) + 1}`) }]}
  options={{ plugins: { legend: { position: 'right' } } }} />
<!-- 6 top 10 endpoint / domain -->
<HBar title={dns ? $t('svc.top_domains') : $t('svc.top_endpoints')} rows={top('endpoints').map((r) => ({ label: r.key, value: r.n }))}
  color="--accent" valueLabel={$t('table.count')} />
<!-- 7 top 10 endpoint 4xx/5xx -->
{#if T['endpoint-errors']}
  <ChartCard title={$t('svc.top_errors')} type="bar" labels={top('endpoint-errors').map((r) => `${r.status} ${r.key}`.slice(0, 48))}
    datasets={[{ label: $t('table.count'), data: top('endpoint-errors').map((r) => r.n), colors: top('endpoint-errors').map((r) => statusTok(r.status)) }]}
    tooltipTitle={(i) => `${top('endpoint-errors')[i].status} ${top('endpoint-errors')[i].key}`}
    options={{ indexAxis: 'y', plugins: { legend: { display: false } } }} />
{/if}
<!-- 8 top 10 IP klien (tooltip: pemilik jaringan) -->
<HBar title={$t('svc.top_ips')} rows={top('ips').map((r) => ({ label: r.ip.ip, value: r.n, org: r.ip.org }))} color="--violet" valueLabel={$t('table.count')} />
<!-- 9 top 10 pesan -->
{#if withMsgs && T.messages}
  <ChartCard title={$t('svc.top_msgs')} type="bar" labels={top('messages').map((r) => r.msg_key.slice(0, 48))}
    datasets={[{ label: $t('table.count'), data: top('messages').map((r) => r.n), colors: top('messages').map((r) => (r.msg_key.startsWith('WARN') ? '--warn' : '--err')) }]}
    tooltipTitle={(i) => top('messages')[i].msg_key} options={{ indexAxis: 'y', plugins: { legend: { display: false } } }} />
{/if}
<!-- 10 top endpoint / domain gagal resolve -->
{#if T.endpoints}
  <DataTable wide={false} title={dns ? $t('svc.domains') : $t('svc.endpoints')} {folder} table="endpoints" {params} initial={T.endpoints} {search} bar="n"
    columns={[{ key: 'key', label: dns ? $t('col.domain') : $t('col.endpoint'), sort: true }, { key: 'n', label: $t('table.count'), type: 'num', sort: true }]} />
{/if}
<!-- 11 endpoint dengan status 4xx/5xx -->
{#if T['endpoint-errors']}
  <DataTable wide={false} title={$t('svc.errors')} {folder} table="endpoint-errors" {params} initial={T['endpoint-errors']} bar="n"
    columns={[{ key: 'key', label: $t('col.status_endpoint'), status: 'status', sort: true }, { key: 'n', label: $t('table.count'), type: 'num', sort: true }]} />
{/if}
<!-- 12, 13 chart kinerja; 14, 15 tabel kinerja -->
{#if T['endpoint-perf']}
  <HBar title={$t('svc.p95_chart')} rows={top('endpoint-perf').map((r) => ({ label: r.key, value: r.p95 }))} color="--warn" valueLabel="P95" fmtV={(v) => fs(v)} />
{/if}
{#if T['endpoint-error-rate']}
  <HBar title={$t('svc.err_rate_chart')} rows={top('endpoint-error-rate').map((r) => ({ label: r.key, value: +(r.error_rate * 100).toFixed(2) }))}
    color="--err" valueLabel={$t('col.error_rate')} fmtV={(v) => `${num(v, $lang)}%`} />
{/if}
{#if T['endpoint-perf']}
  <DataTable title={$t('svc.perf')} {folder} table="endpoint-perf" {params} initial={T['endpoint-perf']} maxHeight={560} columns={[
    { key: 'key', label: $t('col.endpoint'), type: 'code', sort: true },
    { key: 'requests', label: $t('col.requests'), type: 'num', sort: true },
    { key: 'p50', label: 'P50', type: 'num', fmt: (r) => fs(r.p50), sort: true },
    { key: 'p95', label: 'P95', type: 'num', fmt: (r) => fs(r.p95), cls: (r) => (r.p95 >= 1 ? 'WARN' : ''), sort: true },
    { key: 'p99', label: 'P99', type: 'num', fmt: (r) => fs(r.p99), cls: (r) => (r.p99 >= 5 ? 'ERROR' : ''), sort: true },
    { key: 'max', label: $t('col.max'), type: 'num', fmt: (r) => fs(r.max), sort: true },
    { key: 'error_rate', label: $t('col.error_rate'), type: 'num', fmt: (r) => pctS(r.n4xx + r.n5xx, r.requests), cls: (r) => (r.n5xx ? 'ERROR' : r.n4xx ? 'WARN' : ''), sort: true },
  ]} />
{/if}
{#if T['endpoint-error-rate']}
  <DataTable title={$t('svc.err_rate')} {folder} table="endpoint-error-rate" {params} initial={T['endpoint-error-rate']} maxHeight={560} columns={[
    { key: 'key', label: $t('col.endpoint'), type: 'code', sort: true },
    { key: 'requests', label: $t('col.requests'), type: 'num', sort: true },
    { key: 'n4xx', label: '4xx', type: 'num', cls: () => 'WARN', sort: true },
    { key: 'n5xx', label: '5xx', type: 'num', cls: (r) => (r.n5xx ? 'ERROR' : ''), sort: true },
    { key: 'error_rate', label: $t('col.error_rate'), type: 'num', fmt: (r) => pctS(r.n4xx + r.n5xx, r.requests), cls: () => 'ERROR', sort: true },
  ]} />
{/if}
<!-- 16 request lambat ≥ 1 dtk -->
{#if T.slow}
  <DataTable wide={false} title={$t('svc.slow')} {folder} table="slow" {params} initial={T.slow} columns={[
    { key: 'key', label: $t('col.request'), status: 'status' },
    { key: 'duration_ms', label: $t('col.response_time'), type: 'num', fmt: (r) => fs(r.duration_ms / 1000), sort: true },
  ]} />
{/if}
<!-- 17 top IP klien, 18 top user-agent -->
{#if T.ips}
  <DataTable wide={false} title={$t('svc.ips')} {folder} table="ips" {params} initial={T.ips} bar="n"
    columns={[{ key: 'ip', label: 'IP', type: 'ip', sort: true }, { key: 'n', label: $t('table.count'), type: 'num', sort: true }]} />
{/if}
{#if T['user-agents']}
  <DataTable wide={false} title={$t('svc.ua')} {folder} table="user-agents" {params} initial={T['user-agents']} bar="n"
    columns={[{ key: 'ua', label: 'User-Agent', clip: true, sort: true }, { key: 'n', label: $t('table.count'), type: 'num', sort: true }]} />
{/if}
<!-- 19 pesan error / warning (dikelompokkan) -->
{#if withMsgs && T.messages}
  <MessagesTable title={$t('svc.messages')} {folder} service={svc} initial={T.messages} />
{/if}
