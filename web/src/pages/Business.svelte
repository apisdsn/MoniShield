<!-- Bisnis (DRD §3.8, inv. §2.8): 11 KPI (perubahan vs folder sebelumnya untuk metrik simpel-loop), catatan, 5 chart,
     2 tabel. Satu permintaan: GET /api/folders/{folder}/business. Berubah dari lama (U16): KPI yang lognya tidak ada
     di folder ini tampil "–" dengan keterangan, bukan 0 (simpel-loop: aktivitas; report: PDF; appsmanager: login). -->
<script>
  import { lang, t } from '../i18n.js';
  import { api } from '../api.js';
  import { num, delta } from '../format.js';
  import Kpi from '../lib/Kpi.svelte';
  import ChartCard from '../lib/ChartCard.svelte';
  import HBar from '../lib/HBar.svelte';
  import DataTable from '../lib/DataTable.svelte';
  import Note from '../lib/Note.svelte';
  import Skeleton from '../lib/Skeleton.svelte';
  import ErrorState from '../lib/ErrorState.svelte';

  const SL = 'om-be-simpel-loop', AM = 'om-be-appsmanager', RP = 'om-be-report';
  let { folder, summary, reloadKey = 0, onready = null } = $props();
  let data = $state.raw(null), busy = $state(false), error = $state(null);
  let seq = 0;
  async function load() {
    const my = ++seq;
    busy = true; error = null; onready?.(false);
    try {
      const j = await api.get(`/api/folders/${encodeURIComponent(folder)}/business`);
      if (my === seq) data = j;
    } catch (e) {
      if (my === seq) error = e;
    } finally {
      if (my === seq) { busy = false; onready?.(true); }
    }
  }
  $effect(() => { void [folder, reloadKey]; if (folder) load(); });

  // label metrik bisnis dari kamus (kunci biz.<slug>); metrik baru yang belum ada di kamus tampil apa adanya
  const bizLabel = (k) => { const key = `biz.${k.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '')}`; const s = $t(key); return s === key ? k : s; };
  const has = (s) => !!data?.sources?.includes(s);
  // perubahan hanya bila log simpel-loop folder sebelumnya sebanding (≥ 50 % baris hari ini; lama: comparable)
  const slRow = $derived(summary?.folder === folder ? summary.services.find((s) => s.service === SL) : null);
  const cmp = $derived(!!(slRow?.lines && slRow.prev && slRow.prev.lines >= 0.5 * slRow.lines));
  const B = (k) => (has(SL) ? data.biz[k] || 0 : null);
  const d = (k) => (has(SL) && data.biz_prev && data.prev_folder
    ? delta(data.biz[k] || 0, data.biz_prev[k] || 0, data.prev_folder, $lang, { good: true, comparable: cmp }) : null);
  const bizRows = $derived(Object.entries(data?.biz || {}).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])));
  const act = $derived(data?.tables.activity || { total: 0, rows: [] });
  const pdfT = $derived(data?.tables['pdf-templates'] || { total: 0, rows: [] });
  const pdfTop = $derived([...pdfT.rows].sort((a, b) => b.ok + b.fail - a.ok - a.fail).slice(0, 12));
</script>

{#if error && !data}
  <ErrorState {error} onretry={load} />
{:else if !data}
  <Skeleton kpis={11} charts={4} />
{:else}
  {@const miss = (s) => $t('bz.no_log', { svc: s })}
  <div class="content" class:dim={busy}>
    <div class="kpis">
      <Kpi icon="file" label={bizLabel('Laporan Dibuat')} value={B('Laporan Dibuat')} delta={d('Laporan Dibuat')} missing={miss(SL)} />
      <Kpi icon="file" label={bizLabel('Registrasi Laporan')} value={B('Registrasi Laporan')} delta={d('Registrasi Laporan')} missing={miss(SL)} />
      <Kpi icon="key" label={bizLabel('OTP Diminta')} value={B('OTP Diminta')} delta={d('OTP Diminta')} missing={miss(SL)} />
      <Kpi icon="key" label={bizLabel('OTP Terverifikasi')} value={B('OTP Terverifikasi')} tone="ok" delta={d('OTP Terverifikasi')} missing={miss(SL)} />
      <Kpi icon="download" label={bizLabel('File Diunggah')} value={B('File Diunggah')} delta={d('File Diunggah')} missing={miss(SL)} />
      <Kpi icon="alert" label={$t('bz.kpi.upload_rejected')} value={has(SL) ? B('Upload Ditolak (Terlalu Besar)') + B('Upload Ditolak (Tipe File)') : null} tone="warn"
        info={$t('bz.kpi.upload_rejected_info')} missing={miss(SL)} />
      <Kpi icon="route" label={bizLabel('Email Terkirim')} value={B('Email Terkirim')} tone="ok" delta={d('Email Terkirim')} missing={miss(SL)} />
      <Kpi icon="file" label={$t('bz.kpi.pdf_ok')} value={has(RP) ? data.pdf.ok : null} tone="ok" missing={miss(RP)} />
      <Kpi icon="file" label={$t('bz.kpi.pdf_fail')} value={has(RP) ? data.pdf.fail : null} tone={data.pdf.fail ? 'err' : 'ok'} missing={miss(RP)} />
      <Kpi icon="user" label={$t('bz.kpi.login_ok')} value={has(AM) ? data.login.ok : null} missing={miss(AM)} />
      <Kpi icon="users" label={$t('bz.kpi.login_users')} value={has(AM) ? data.login.users : null} missing={miss(AM)} />
    </div>
    <Note>{$t('bz.note')}</Note>
    <div class="grid">
      {#if bizRows.length}
        <HBar title={$t('bz.summary_chart')} rows={bizRows.map(([k, n]) => ({ label: bizLabel(k), value: n }))} color="--accent" valueLabel={$t('table.count')} />
      {/if}
      {#if data.mail.length}
        <HBar title={$t('bz.mail_chart')} rows={data.mail.map(([k, n]) => ({ label: k, value: n }))} color="--ok" valueLabel="Email" />
      {/if}
      {#if act.total}
        <HBar title={$t('bz.act_chart')} rows={act.rows.slice(0, 12).map((r) => ({ label: r.key, value: r.n }))} color="--c2" valueLabel={$t('table.count')} />
      {/if}
      {#if data.login_ok_by_hour.length}
        <ChartCard title={$t('bz.login_hour')} type="line" timeAxis labels={data.login_ok_by_hour.map((h) => h[0])}
          datasets={[{ label: $t('bz.kpi.login_ok'), data: data.login_ok_by_hour.map((h) => h[1]), color: '--ok' }]} />
      {/if}
      {#if pdfT.total}
        <HBar title={$t('bz.pdf_chart')} rows={pdfTop.map((r) => ({ label: r.template, value: r.ok + r.fail }))} color="--accent" valueLabel="PDF" />
      {/if}
      {#if act.total}
        <DataTable wide={false} title={$t('bz.t.activity')} {folder} table="activity" initial={act} bar="n" columns={[
          { key: 'key', label: $t('col.endpoint'), type: 'code', sort: true },
          { key: 'n', label: $t('table.count'), type: 'num', sort: true },
        ]} />
      {/if}
      {#if pdfT.total}
        <DataTable wide={false} title={$t('bz.t.pdf')} {folder} table="pdf-templates" initial={pdfT} columns={[
          { key: 'template', label: $t('rc.col.template'), type: 'code', sort: true },
          { key: 'ok', label: $t('rc.ok'), type: 'num', sort: true },
          { key: 'fail', label: $t('rc.fail'), type: 'num', cls: (r) => (r.fail ? 'ERROR' : ''), sort: true },
        ]} />
      {/if}
    </div>
  </div>
{/if}

<style>
  .content { transition: opacity 0.15s; }
  .content.dim { opacity: 0.6; }
  .content :global(.note) { margin-bottom: 18px; }
</style>
