<!-- One line chart of the Servers page: a title, the current value on the right, a legend row (always there, so every card has the same
     structure and height), up to four lines and a one-line caption. The colours come from
     the theme tokens at draw time; a theme or language change redraws without fetching. The pointer plugin of scale.js keeps the
     tooltips right under the page zoom. Text alternative: the aria-label (title, current value, highest value). -->
<script>
  import { onDestroy } from 'svelte';
  import { Chart, registerables } from 'chart.js';
  import { lang, t } from '../i18n.js';
  import { theme } from '../theme.js';
  import { chartZoomFix } from '../scale.js';

  Chart.register(...registerables);

  /** datasets: [{label, data, color: token ('--accent', '--c2'), dashed?}]; the legend row shows them when there is more than one; labels: axis texts; tips: tooltip titles (same length). */
  let { title, now = '', labels = [], tips = [], datasets = [], fmt = (v) => String(v), max = null, caption = '', tickFmt = null } = $props();
  const Y_WIDTH = 76;      // every chart has the same y-axis width, so the plot areas of the six charts share their left and right edges and their time ticks

  let canvas = $state();
  let chart;
  const points = $derived(datasets.reduce((n, d) => n + d.data.filter((v) => v !== null).length, 0));
  const peak = $derived(Math.max(0, ...datasets.flatMap((d) => d.data.filter((v) => v !== null))));
  const summary = $derived(`${title}. ${now ? `${$t('sv.chart.now')}: ${now}. ` : ''}${points ? `${$t('sv.chart.peak')}: ${fmt(peak)}.` : $t('sv.chart.none')}`);

  function draw() {
    if (!canvas) return;
    chart?.destroy();
    const cs = getComputedStyle(document.documentElement);
    const v = (name) => cs.getPropertyValue(name).trim();
    const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
    chart = new Chart(canvas, {
      type: 'line',
      data: {
        labels,
        datasets: datasets.map((d) => ({ label: d.label, data: [...d.data], borderColor: v(d.color), backgroundColor: v(d.color), borderWidth: 2, tension: 0.25, pointRadius: 0,
          pointHoverRadius: 4, spanGaps: false, borderDash: d.dashed ? [5, 4] : [], fill: false })),
      },
      plugins: [chartZoomFix, { id: 'area', afterLayout: (c) => { c.canvas.dataset.left = Math.round(c.chartArea.left); c.canvas.dataset.width = Math.round(c.chartArea.right - c.chartArea.left); } }],
      options: {
        responsive: true, maintainAspectRatio: false, animation: reduce ? false : undefined, locale: $lang === 'en' ? 'en-US' : 'id-ID',
        layout: { padding: { right: 14 } },      // room for the last time label
        interaction: { mode: 'index', intersect: false },
        color: v('--muted'), borderColor: v('--grid'), font: { family: 'Outfit, system-ui, sans-serif' },
        scales: {
          x: { grid: { color: v('--grid') }, ticks: { color: v('--muted'), maxRotation: 0, autoSkip: true, autoSkipPadding: 14, maxTicksLimit: 7 } },
          y: { grid: { color: v('--grid') }, beginAtZero: true, afterFit: (scale) => { scale.width = Y_WIDTH; }, ...(max ? { suggestedMax: max } : {}), ticks: { color: v('--muted'), maxTicksLimit: 5, callback: (x) => (tickFmt || fmt)(x) } },
        },
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: v('--tooltip-bg'), borderColor: v('--tooltip-line'), borderWidth: 1, padding: 10, titleColor: '#e2ecf3', bodyColor: '#e2ecf3',
            callbacks: { title: (it) => tips[it[0].dataIndex] ?? '', label: (c) => `${c.dataset.label}: ${c.parsed.y === null ? '–' : fmt(c.parsed.y)}` },
          },
        },
      },
    });
  }

  $effect(() => {
    void [labels, tips, datasets, max, $lang, $theme, canvas];
    if (points) draw();
    else { chart?.destroy(); chart = null; }
  });
  onDestroy(() => chart?.destroy());
</script>

<section class="card" aria-label={title}>
  <header>
    <h2>{title}</h2>
    {#if now}<span class="now">{now}</span>{/if}
  </header>
  <ul class="legend">
    {#if datasets.length > 1}{#each datasets as d}<li><i class="sw" class:dashed={d.dashed} style:--sw="var({d.color})"></i>{d.label}</li>{/each}{/if}
  </ul>
  {#if points}
    <div class="chart" role="img" aria-label={summary}><canvas bind:this={canvas} aria-hidden="true"></canvas></div>
  {:else}
    <p class="none muted">{$t('sv.chart.none')}</p>
  {/if}
  <p class="capt muted" title={caption}>{caption}</p>
</section>

<style>
  header { display: flex; justify-content: space-between; align-items: baseline; gap: 8px; }
  h2 { font-size: 0.9375rem; font-weight: 600; color: var(--heading); text-transform: none; }
  .now { font-family: var(--mono); font-size: 0.875rem; color: var(--fg); white-space: nowrap; }
  /* min-width 0: the canvas has a fixed pixel width until Chart.js resizes it, and must not hold the grid track wider */
  .card { min-width: 0; display: flex; flex-direction: column; }
  header { min-height: 24px; }
  .legend { display: flex; flex-wrap: nowrap; justify-content: flex-end; gap: 4px 14px; list-style: none; margin: 4px 0 0; padding: 0; height: 20px; overflow: hidden; font-size: 0.75rem; color: var(--muted); }
  .legend li { display: inline-flex; align-items: center; gap: 6px; white-space: nowrap; }
  .sw { display: inline-block; width: 18px; height: 0; border-top: 2px solid var(--sw); }
  .sw.dashed { border-top-style: dashed; }
  .chart { position: relative; height: 180px; margin-top: 4px; min-width: 0; overflow: hidden; }
  .none { display: grid; place-items: center; height: 180px; margin: 4px 0 0; font-size: 0.875rem; }
  .capt { margin: 8px 0 0; font-size: 0.75rem; line-height: 1.25rem; height: 1.25rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
</style>
