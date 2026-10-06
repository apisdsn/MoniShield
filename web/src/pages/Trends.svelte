<!-- Tren (DRD §3.3, inv. §2.3): perbandingan antar folder, tidak bergantung pemilih folder (dinonaktifkan di header).
     Pemilih rentang 14 / 30 / 90 / semua folder terakhir (U4; bawaan 30, ASUMSI Q4), diingat per browser.
     6 chart + 2 tabel; tabel selalu menggulir mendatar dengan kolom Layanan terkunci dan folder terbaru di kanan.
     Satu permintaan: GET /api/trends?last=… -->
<script>
  import { lang, t } from '../i18n.js';
  import { api } from '../api.js';
  import { num, dLabel, sysName } from '../format.js';
  import { load as loadPref, save as savePref } from '../store.js';
  import ChartCard from '../lib/ChartCard.svelte';
  import Skeleton from '../lib/Skeleton.svelte';
  import ErrorState from '../lib/ErrorState.svelte';
  import SeverityTag from '../lib/SeverityTag.svelte';

  let { reloadKey = 0, onready = null } = $props();
  const RANGES = ['14', '30', '90', 'all'];
  const BIZ = ['Laporan Dibuat', 'Registrasi Laporan', 'File Diunggah', 'Email Terkirim', 'OTP Diminta'];   // kunci dari API (data lama)

  let range = $state(RANGES.includes(loadPref('trendRange', '30')) ? loadPref('trendRange', '30') : '30');
  // $state.raw: data dibaca saja; array-nya diserahkan ke Chart.js, yang menambah properti internal ke array (proksi $state menolaknya)
  let data = $state.raw(null), busy = $state(false), error = $state(null);
  let seq = 0;

  async function load() {
    const my = ++seq;
    busy = true; error = null; onready?.(false);
    try {
      const j = await api.get(`/api/trends?last=${range}`);
      if (my === seq) data = j;
    } catch (e) {
      if (my === seq) error = e;
    } finally {
      if (my === seq) { busy = false; onready?.(true); }
    }
  }
  $effect(() => { void [range, reloadKey]; savePref('trendRange', range); load(); });

  const labels = $derived((data?.folders || []).map((f) => dLabel(f, $lang)));
  const bySvc = (k) => (data?.services || []).map((s, i) => ({ label: sysName(s), data: data[k][s].map((v) => v ?? 0), color: `--c${(i % 10) + 1}` }));
  const slug = (k) => k.toLowerCase().replace(/ /g, '_');   // kunci kamus metrik bisnis (label, diterjemahkan; DRD §6.3)
  const stack = { scales: { x: { stacked: true }, y: { stacked: true } } };

  // tabel mulai dari ujung kanan: folder terbaru terlihat (DRD §3.3); diulang tiap data berganti
  function scrollEnd(node, _key) {
    const go = () => requestAnimationFrame(() => (node.scrollLeft = node.scrollWidth));
    go();
    return { update: go };
  }

  // perubahan error vs folder sebelumnya: hanya bila error kemarin > 0 dan baris kemarin ≥ 50 % hari ini (lama)
  function change(s, i) {
    if (i === 0) return null;
    const c = data.err[s][i], p = data.err[s][i - 1], cl = data.lines[s][i], pl = data.lines[s][i - 1];
    if (c === null || p === null || !p || pl < 0.5 * cl) return null;
    const up = c > p;
    return { up, text: `${up ? '▲' : '▼'} ${Math.abs(((c - p) / p) * 100).toFixed(0)}%` };
  }
</script>

<p class="muted intro">{$t('tr.note')}</p>
<div class="bar">
  <label for="tr-range">{$t('tr.range')}</label>
  <select id="tr-range" bind:value={range}>
    {#each RANGES as r}<option value={r}>{r === 'all' ? $t('tr.range_all') : $t('tr.range_n', { n: r })}</option>{/each}
  </select>
  {#if data}<span class="muted">{$t('tr.n_folders', { n: num(data.folders.length, $lang) })}</span>{/if}
</div>

{#if error && !data}
  <ErrorState {error} onretry={load} />
{:else if !data}
  <Skeleton kpis={0} charts={6} />
{:else}
  <div class="grid content" class:dim={busy}>
    <ChartCard title={$t('tr.err')} type="bar" {labels} datasets={bySvc('err')} options={stack} />
    <ChartCard title={$t('tr.warn')} type="bar" {labels} datasets={bySvc('warn')} options={stack} />
    <ChartCard title={$t('tr.http')} type="bar" {labels} datasets={[
      { label: $t('svc.total'), data: data.http.total, color: '--accent' },
      { label: '4xx', data: data.http.n4xx, color: '--warn' }, { label: '5xx', data: data.http.n5xx, color: '--err' }]} />
    <ChartCard title={$t('tr.security')} type="bar" {labels} datasets={[
      { label: $t('tr.attack_requests'), data: data.security.attack_requests, color: '--err' },
      { label: $t('tr.login_fail'), data: data.security.login_fail, color: '--warn' },
      { label: $t('tr.resets'), data: data.security.resets, color: '--violet' }]} />
    <ChartCard title={$t('tr.business')} type="bar" {labels}
      datasets={BIZ.map((k, i) => ({ label: $t(`biz.${slug(k)}`), data: data.business[k], color: `--c${i + 1}` }))} />
    <ChartCard title={$t('tr.lines')} type="bar" {labels} datasets={bySvc('lines')} options={stack} />

    {#each [['err', $t('tr.err_table')], ['lines', $t('tr.completeness')]] as [kind, title]}
      <section class="card wide" aria-label={title}>
        <header><h2>{title}</h2></header>
        <div class="scroll tt" use:scrollEnd={data} tabindex="0" role="region" aria-label={title}>
          <table>
            <caption class="sr-only">{title}</caption>
            <thead><tr><th scope="col" class="first">{$t('col.service')}</th>{#each labels as l}<th scope="col" class="n">{l}</th>{/each}</tr></thead>
            <tbody>
              {#each data.services as s}
                <tr>
                  <th scope="row" class="first nowrap">{sysName(s)}</th>
                  {#each data.folders as f, i}
                    {@const ln = data.lines[s][i]}
                    {#if kind === 'err'}
                      {@const c = change(s, i)}
                      <td class="n" class:muted={ln === null}>{ln === null ? '–' : num(data.err[s][i], $lang)}{#if c}<div class="chg" class:up={c.up}>{c.text}</div>{/if}</td>
                    {:else}
                      {@const st = data.file_status[s][i]}
                      <td class="n" class:muted={ln === null || !ln}>
                        {#if ln === null}{$t('tr.absent')}
                        {:else if !ln}{st === 'rusak' ? $t('file.rusak') : $t('file.kosong')}
                        {:else}{num(ln, $lang)}{#if st === 'rusak'}<div><SeverityTag level={2} text={$t('file.rusak')} /></div>{/if}{/if}
                      </td>
                    {/if}
                  {/each}
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
      </section>
    {/each}
  </div>
{/if}

<style>
  .intro { margin: 0 0 12px; font-size: 0.8125rem; max-width: 900px; }
  .bar { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin-bottom: 16px; font-size: 0.8125rem; }
  .bar label { color: var(--kpi-label); }
  .content { transition: opacity 0.15s; }
  .content.dim { opacity: 0.6; }
  .tt { max-height: 560px; border-radius: var(--r-box); }
  table { border-collapse: separate; border-spacing: 0; font-size: 0.8125rem; min-width: 100%; }
  th, td { padding: 9px 12px; border-bottom: 1px solid var(--row-line); text-align: left; vertical-align: top; }
  thead th {
    position: sticky; top: 0; z-index: 2; background: var(--th-bg); color: var(--th-fg);
    font-size: 0.6875rem; font-weight: 600; letter-spacing: 0.07em; text-transform: uppercase; white-space: nowrap;
  }
  .first { position: sticky; left: 0; z-index: 1; background: var(--card); font-weight: 500; color: var(--fg); box-shadow: 1px 0 0 var(--line); }
  thead .first { z-index: 3; background: var(--th-bg); }
  .n { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
  tr:hover td, tr:hover th.first { background: var(--row-hover); }
  .chg { font-size: 0.6875rem; color: var(--ok-text); }
  .chg.up { color: var(--err); }
  .muted { color: var(--muted); }
</style>
