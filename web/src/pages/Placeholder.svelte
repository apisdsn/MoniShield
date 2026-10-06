<!-- Pengganti halaman data sampai halaman sebenarnya dibangun (Tahap 13–20), sekaligus SATU HALAMAN CONTOH yang
     memakai semua komponen bersama dengan data nyata folder terpilih: KPI + perubahan, chart batang/garis/donat,
     batang horizontal, peringatan, catatan, tabel statis (kartu baris di ponsel), tabel server (filter, urut,
     lanjutan), sel IP, tag bahaya, kode status, keadaan memuat/kosong/gagal. Satu permintaan halaman (overview). -->
<script>
  import { lang, t } from '../i18n.js';
  import { api } from '../api.js';
  import { num, delta, titleCase, bytes, dLabel } from '../format.js';
  import Kpi from '../lib/Kpi.svelte';
  import ChartCard from '../lib/ChartCard.svelte';
  import HBar from '../lib/HBar.svelte';
  import DataTable from '../lib/DataTable.svelte';
  import Alert from '../lib/Alert.svelte';
  import Note from '../lib/Note.svelte';
  import Skeleton from '../lib/Skeleton.svelte';
  import ErrorState from '../lib/ErrorState.svelte';

  let { tab, folder, summary, reloadKey = 0, onready = null } = $props();

  const STAGE = { overview: 13, layanan: 13, peta: 20, tren: 14, keamanan: 15, 'akar-masalah': 16, ketersediaan: 16, pod: 17, bisnis: 17, pelacakan: 17 };
  const NG = 'nginx-ingress-controller';

  let page = $state(null), busy = $state(false), error = $state(null);
  let seq = 0;
  async function load() {
    const my = ++seq;
    busy = true; error = null;
    onready?.(false);
    try {
      const j = await api.get(`/api/folders/${encodeURIComponent(folder)}/overview`);
      if (my === seq) page = j;
    } catch (e) {
      if (my === seq) error = e;
    } finally {
      if (my === seq) { busy = false; onready?.(true); }
    }
  }
  $effect(() => { void [folder, reloadKey]; if (tab !== 'tren' && folder) load(); });

  const svc = $derived(summary?.services || []);
  const total = (k, list = svc) => list.reduce((a, s) => a + (s[k] || 0), 0);
  const prevTotal = (k) => (svc.some((s) => s.prev) ? svc.reduce((a, s) => a + (s.prev?.[k] || 0), 0) : null);
  const comparable = $derived(svc.length > 0 && svc.every((s) => !s.lines || (s.prev && s.prev.lines >= 0.5 * s.lines)));
  const d = (k, good = false) => (summary?.prev_folder ? delta(total(k), prevTotal(k), summary.prev_folder, $lang, { good, comparable }) : null);
  const hasNginx = $derived(svc.some((s) => s.service === NG && s.lines));
  const errSeries = $derived(Object.entries(page?.err_by_hour || {}));
  const hours = $derived([...new Set(errSeries.flatMap(([, pts]) => pts.map((p) => p[0])))].sort());
  const statusRows = $derived((summary?.files || []).reduce((m, f) => ((m[f.status] = (m[f.status] || 0) + 1), m), {}));
</script>

<Note>
  {$t('placeholder.note', { page: tab === 'layanan' ? $t('tab.layanan') : $t(`tab.${tab}`), stage: STAGE[tab] ?? '–' })}
  {#if tab !== 'tren'}{' '}{$t('placeholder.sample')}{/if}
</Note>

{#if tab === 'tren'}
  <!-- Tren tidak bergantung folder (DRD §3.3); halaman contoh memakai data per folder, jadi tidak ditampilkan di sini. -->
{:else if error && !page}
  <ErrorState {error} onretry={load} />
{:else if !page}
  <Skeleton kpis={6} charts={2} />
{:else}
  <div class="content" class:dim={busy}>
    <div class="kpis">
      <Kpi label={$t('kpi.lines')} value={total('lines')} delta={d('lines', true)} />
      <Kpi label={$t('kpi.error')} value={total('err')} tone="err" delta={d('err')} info={$t('kpi.error_info', { http: num(total('err_http'), $lang), log: num(total('err_log'), $lang) })} />
      <Kpi label={$t('kpi.warning')} value={total('warn')} tone="warn" delta={d('warn')} />
      <Kpi label={$t('kpi.files')} value={(summary?.files || []).length} />
      <Kpi label={$t('kpi.files_empty')} value={(summary?.files || []).filter((f) => !f.lines).length} tone="muted" />
      <Kpi label={$t('kpi.http')} value={hasNginx ? svc.find((s) => s.service === NG).requests : null} missing={$t('kpi.no_nginx')} />
    </div>

    {#if summary?.attack_ip_count}
      <Alert title={$t('placeholder.findings')}>
        <li>{$t('placeholder.finding_attack', { n: num(summary.attack_ip_count, $lang), date: dLabel(folder, $lang) })}</li>
      </Alert>
    {/if}

    <div class="grid">
      <ChartCard title={$t('placeholder.lines_per_service')} type="bar" labels={svc.map((s) => titleCase(s.service))}
        datasets={[{ label: $t('kpi.lines'), data: svc.map((s) => s.lines), colors: svc.map((_, i) => `--c${(i % 10) + 1}`) }]} />
      <ChartCard title={$t('placeholder.file_status')} type="doughnut" labels={Object.keys(statusRows).map((k) => $t(`file.${k}`))}
        datasets={[{ data: Object.values(statusRows) }]} />
      <ChartCard title={$t('placeholder.err_per_hour')} type="line" timeAxis wide labels={hours}
        datasets={errSeries.map(([s, pts], i) => { const m = Object.fromEntries(pts); return { label: titleCase(s), data: hours.map((h) => m[h] || 0), color: `--c${(i % 10) + 1}` }; })} />
      <HBar title={$t('placeholder.err_per_service')} rows={svc.filter((s) => s.err).map((s) => ({ label: s.service, value: s.err }))} color="--err" valueLabel={$t('kpi.error')} />

      <DataTable title={$t('placeholder.files')} rows={summary?.files || []} limit={10} bar="lines" columns={[
        { key: 'pod', label: $t('col.pod') },
        { key: 'service', label: $t('col.service'), fmt: (r) => titleCase(r.service) },
        { key: 'ns', label: $t('col.ns'), fmt: (r) => r.ns || '–' },
        { key: 'lines', label: $t('col.lines'), type: 'num', sort: true },
        { key: 'err', label: $t('kpi.error'), type: 'num', sort: true },
        { key: 'warn', label: $t('kpi.warning'), type: 'num', sort: true },
        { key: 'size_bytes', label: $t('col.size'), type: 'bytes', sort: true },
        { key: 'status', label: $t('col.status'), fmt: (r) => $t(`file.${r.status}`) },
      ]} />

      <DataTable title={$t('placeholder.messages')} {folder} table="messages" initial={page.tables.messages} columns={[
        { key: 'level', label: $t('col.level'), cls: (r) => r.level },
        { key: 'msg_key', label: $t('col.message'), detail: (r) => r.sample },
        { key: 'service', label: $t('col.service'), fmt: (r) => titleCase(r.service) },
        { key: 'n', label: $t('table.count'), type: 'num', sort: true },
      ]} />

      {#if hasNginx}
        <DataTable title={$t('placeholder.attack_urls')} {folder} table="attack-urls" limit={10} columns={[
          { key: 'category', label: $t('col.category'), type: 'sev', sev: (r) => ({ level: r.severity, text: r.category }) },
          { key: 'method_path', label: $t('col.url'), type: 'code', clip: true },
          { key: 'hits', label: $t('col.hits'), type: 'num', sort: true },
          { key: 'top_ip', label: $t('col.source_ip'), type: 'ip', more: (r) => r.ip_count - 1 },
          { key: 'status_counts', label: $t('col.status'), type: 'statuses' },
          { key: 'first', label: $t('col.time'), type: 'range', to: 'last', sort: true },
        ]} />
      {/if}
    </div>
    <p class="muted foot">{$t('placeholder.size_note', { size: bytes((summary?.files || []).reduce((a, f) => a + (f.size_bytes || 0), 0), $lang) })}</p>
  </div>
{/if}

<style>
  .content { transition: opacity 0.15s; }
  .content.dim { opacity: 0.6; }
  .foot { font-size: 0.75rem; margin-top: 18px; }
  :global(.note) + .content, :global(.note) { margin-bottom: 18px; }
</style>
