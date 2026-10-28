<!-- Business (DRD §3.8, inv. §2.8): 11 KPIs (change vs the previous folder for events-service metrics), notes, 5 charts,
     2 tables. One request: GET /api/folders/{folder}/business. Changed from the old one (U16): KPIs whose log is missing
     in this folder show "–" with an explanation, not 0 (events service: activity; report: PDF; auth: login). -->
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
  import { site } from '../site.js';

  const SL = $derived($site.roles.events), AM = $derived($site.roles.auth), RP = $derived($site.roles.report);
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

  // business metric labels from the dictionary (key biz.<slug>); new metrics not yet in the dictionary are shown as is
  const bizLabel = (k) => { const key = `biz.${k.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '')}`; const s = $t(key); return s === key ? k : s; };
  const has = (s) => !!data?.sources?.includes(s);
  // change only when the previous folder's events-service log is comparable (≥ 50 % of today's lines; old: comparable)
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
      <Kpi icon="file" label={bizLabel('reports_created')} value={B('reports_created')} delta={d('reports_created')} missing={miss(SL)} />
      <Kpi icon="file" label={bizLabel('report_registrations')} value={B('report_registrations')} delta={d('report_registrations')} missing={miss(SL)} />
      <Kpi icon="key" label={bizLabel('otp_requested')} value={B('otp_requested')} delta={d('otp_requested')} missing={miss(SL)} />
      <Kpi icon="key" label={bizLabel('otp_verified')} value={B('otp_verified')} tone="ok" delta={d('otp_verified')} missing={miss(SL)} />
      <Kpi icon="download" label={bizLabel('files_uploaded')} value={B('files_uploaded')} delta={d('files_uploaded')} missing={miss(SL)} />
      <Kpi icon="alert" label={$t('bz.kpi.upload_rejected')} value={has(SL) ? B('uploads_rejected_too_large') + B('uploads_rejected_file_type') : null} tone="warn"
        info={$t('bz.kpi.upload_rejected_info')} missing={miss(SL)} />
      <Kpi icon="route" label={bizLabel('emails_sent')} value={B('emails_sent')} tone="ok" delta={d('emails_sent')} missing={miss(SL)} />
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
