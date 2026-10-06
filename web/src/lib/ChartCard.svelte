<!-- Kartu chart (DRD §4.2): judul kiri, aksi kanan, kanvas 280 px. Warna dari token (§5.4), dibaca saat digambar;
     ganti tema/bahasa = gambar ulang tanpa mengambil data. Alternatif teks: aria-label (judul + ringkasan) dan
     "Lihat sebagai tabel" (U9). Sumbu waktu tanpa pengulangan tanggal bila semua titik satu tanggal (U10).
     0 titik -> kartu tidak dirender (lama). -->
<script module>
  import { Chart, registerables } from 'chart.js';
  Chart.register(...registerables);

  // Angka persentase terbesar di tengah donat (lama: centerText)
  const centerText = {
    id: 'centerText',
    afterDraw(c) {
      if (c.config.type !== 'doughnut') return;
      const ds = c.data.datasets[0].data, tot = ds.reduce((a, b) => a + b, 0);
      if (!tot) return;
      const i = ds.indexOf(Math.max(...ds)), { ctx } = c, m = c.getDatasetMeta(0).data[0];
      if (!m) return;
      const cs = getComputedStyle(document.documentElement);
      ctx.save();
      ctx.textAlign = 'center';
      ctx.fillStyle = cs.getPropertyValue('--accent').trim();
      ctx.font = '600 26px Outfit, system-ui';
      ctx.fillText(Math.round((ds[i] / tot) * 100) + '%', m.x, m.y + 2);
      ctx.fillStyle = cs.getPropertyValue('--muted').trim();
      ctx.font = '500 12px Outfit, system-ui';
      const lb = String(c.data.labels[i]);
      ctx.fillText(lb.length > 22 ? lb.slice(0, 21) + '…' : lb, m.x, m.y + 22);
      ctx.restore();
    },
  };
  const PAL = ['--c1', '--c2', '--c3', '--c4', '--c5', '--c6', '--c7', '--c8', '--c9', '--c10'];
</script>

<script>
  import { onDestroy } from 'svelte';
  import { lang, t } from '../i18n.js';
  import { theme } from '../theme.js';
  import { num, dLabel, tWIB } from '../format.js';
  import InfoTip from './InfoTip.svelte';

  /**
   * datasets: [{label, data, color?: token ('--err' / '--c2'), colors?: [token per titik]}]
   * timeAxis: label 'YYYY-MM-DD HH' (jam WIB dari API). fmtV: format nilai (sumbu + tooltip).
   * tooltipTitle(i): baris judul tooltip (mis. IP + pemilik). options: digabung ke opsi Chart.js.
   */
  let { title, type = 'bar', labels = [], datasets = [], wide = false, timeAxis = false, fmtV = null, tooltipTitle = null,
        options = {}, info = null, valueLabel = null, actions = null, chip = null } = $props();

  let canvas = $state();
  let asTable = $state(false);
  let chart;

  const points = $derived(datasets.reduce((n, d) => n + (d.data?.length || 0), 0));
  const oneDay = $derived(timeAxis && labels.length > 0 && labels.every((l) => String(l).slice(0, 10) === String(labels[0]).slice(0, 10)));
  const shownLabels = $derived(
    timeAxis ? labels.map((l) => (oneDay ? tWIB(l, $lang).split(' ').pop() : tWIB(l, $lang))) : labels.map(String),
  );
  const fv = (v) => (fmtV ? fmtV(v, $lang) : num(v, $lang));
  const total = $derived(datasets.reduce((a, d) => a + (d.data || []).reduce((x, y) => x + (+y || 0), 0), 0));
  const summary = $derived.by(() => {
    if (!points) return title;
    let best = null;
    datasets.forEach((d) => (d.data || []).forEach((v, i) => { if (best === null || v > best.v) best = { v, i, d }; }));
    const lbl = shownLabels[best.i] + (datasets.length > 1 ? ` (${best.d.label})` : '');
    return `${title}. ${$t('chart.summary', { label: lbl, value: fv(best.v), total: fv(total) })}`;
  });

  function draw() {
    if (!canvas) return;
    chart?.destroy();
    const cs = getComputedStyle(document.documentElement);
    const v = (name) => cs.getPropertyValue(name).trim();
    const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
    const ds = datasets.map((d, k) => {
      const c = v(d.color || PAL[k % PAL.length]);
      const base = { label: d.label, data: d.data };
      if (type === 'line') {
        return { ...base, fill: true, tension: 0.42, pointRadius: 0, pointHoverRadius: 5, borderWidth: 2, borderColor: c,
          backgroundColor: (ctx) => {
            const a = ctx.chart.chartArea;
            if (!a) return c + '33';
            const g = ctx.chart.ctx.createLinearGradient(0, a.top, 0, a.bottom);
            g.addColorStop(0, c + '66'); g.addColorStop(1, c + '00');
            return g;
          } };
      }
      const per = d.colors ? d.colors.map((x) => v(x)) : type === 'doughnut' ? d.data.map((_, i) => v(PAL[i % PAL.length])) : c;
      if (type === 'doughnut') return { ...base, backgroundColor: per, borderWidth: 0, hoverOffset: 6 };
      return { ...base, backgroundColor: per, borderRadius: 6, borderSkipped: false, maxBarThickness: 34 };
    });
    const horizontal = options.indexAxis === 'y';
    chart = new Chart(canvas, {
      type,
      data: { labels: shownLabels, datasets: ds },
      plugins: [centerText],
      options: {
        responsive: true, maintainAspectRatio: false, animation: reduce ? false : undefined, locale: $lang === 'en' ? 'en-US' : 'id-ID',
        interaction: { mode: 'index', intersect: false },
        color: v('--muted'), borderColor: v('--grid'),
        font: { family: 'Outfit, system-ui, sans-serif' },
        ...(type === 'doughnut' ? { cutout: '74%' } : {}),
        scales: type === 'doughnut' ? {} : {
          x: { grid: { color: v('--grid') }, ticks: { color: v('--muted'), maxRotation: 0, autoSkip: true, autoSkipPadding: 12,
               ...(horizontal && fmtV ? { callback: (x) => fv(x) } : {}) } },
          y: { grid: { color: v('--grid') }, ticks: { color: v('--muted'), ...(!horizontal && fmtV ? { callback: (x) => fv(x) } : {}) },
               ...(horizontal ? {} : { beginAtZero: true }) },
          ...(options.scales || {}),
        },
        plugins: {
          legend: { display: datasets.length > 1 || type === 'doughnut', labels: { color: v('--muted'), usePointStyle: true, pointStyle: 'circle', boxWidth: 8 } },
          tooltip: {
            backgroundColor: v('--tooltip-bg'), borderColor: v('--tooltip-line'), borderWidth: 1, padding: 10,
            titleColor: '#e2ecf3', bodyColor: '#e2ecf3',
            callbacks: {
              ...(tooltipTitle ? { title: (it) => tooltipTitle(it[0].dataIndex) } : timeAxis ? { title: (it) => tWIB(labels[it[0].dataIndex], $lang) } : {}),
              label: (c) => `${c.dataset.label ? c.dataset.label + ': ' : ''}${fv(type === 'doughnut' ? c.raw : horizontal ? c.parsed.x : c.parsed.y)}`,
            },
          },
          ...(options.plugins || {}),
        },
        ...Object.fromEntries(Object.entries(options).filter(([k]) => !['scales', 'plugins'].includes(k))),
      },
    });
  }

  // gambar ulang saat data, bahasa, atau tema berubah (warna dibaca ulang dari token)
  $effect(() => {
    void [labels, datasets, $lang, $theme, canvas, asTable];
    if (points && !asTable) draw();
    else { chart?.destroy(); chart = null; }
  });
  onDestroy(() => chart?.destroy());
</script>

{#if points}
  <section class="card" class:wide aria-label={title}>
    <header>
      <h2>{title}{#if info}<InfoTip text={info} />{/if}</h2>
      <div class="acts">
        {#if chip}<span class="chip">{chip}</span>{/if}
        {#if actions}{@render actions()}{/if}
        <button class="btn sm" aria-pressed={asTable} onclick={() => (asTable = !asTable)}>{asTable ? $t('chart.as_chart') : $t('chart.as_table')}</button>
      </div>
    </header>
    {#if asTable}
      <div class="scroll tbl">
        <table>
          <caption class="sr-only">{title}</caption>
          <thead><tr><th scope="col">{timeAxis ? $t('chart.time') : $t('chart.label')}</th>
            {#each datasets as d}<th scope="col" class="n">{d.label || valueLabel || $t('table.count')}</th>{/each}</tr></thead>
          <tbody>
            {#each labels as l, i}<tr><td>{timeAxis ? tWIB(l, $lang) : String(l)}</td>{#each datasets as d}<td class="n">{fv(d.data[i])}</td>{/each}</tr>{/each}
          </tbody>
        </table>
      </div>
      {#if oneDay}<p class="day muted">{dLabel(String(labels[0]).slice(0, 10), $lang)}</p>{/if}
    {:else}
      <div class="chart" role="img" aria-label={summary}><canvas bind:this={canvas} aria-hidden="true"></canvas></div>
      {#if oneDay}<p class="day muted">{dLabel(String(labels[0]).slice(0, 10), $lang)} · WIB</p>{/if}
    {/if}
  </section>
{/if}

<style>
  .chart { position: relative; height: 280px; }
  .acts { display: flex; gap: 8px; align-items: center; }
  .btn.sm { min-height: 2rem; padding: 0.2rem 0.75rem; font-size: 0.75rem; }
  @media (max-width: 900px) { .btn.sm { min-height: var(--touch); } }
  h2 { display: flex; align-items: center; }
  .day { margin: 6px 0 0; font-size: 0.75rem; text-align: center; }
  .tbl { max-height: 280px; }
  table { width: 100%; border-collapse: collapse; font-size: 0.8125rem; }
  th, td { text-align: left; padding: 6px 10px; border-bottom: 1px solid var(--row-line); }
  th { color: var(--th-fg); background: var(--th-bg); position: sticky; top: 0; font-size: 0.75rem; }
  .n { text-align: right; font-variant-numeric: tabular-nums; }
</style>
