<!-- One line chart of the Servers page: a title, the current value on the right, up to two lines and a caption. The colours come from
     the theme tokens at draw time; a theme or language change redraws without fetching. The pointer plugin of scale.js keeps the
     tooltips right under the page zoom. Text alternative: the aria-label (title, current value, highest value). -->
<script>
  import { onDestroy } from 'svelte';
  import { Chart, registerables } from 'chart.js';
  import { lang, t } from '../i18n.js';
  import { theme } from '../theme.js';
  import { chartZoomFix } from '../scale.js';

  Chart.register(...registerables);

  /** datasets: [{label, data, color: token ('--accent', '--c2'), dashed?}]; labels: axis texts; tips: tooltip titles (same length). */
  let { title, now = '', labels = [], tips = [], datasets = [], fmt = (v) => String(v), max = null, caption = '' } = $props();

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
      plugins: [chartZoomFix],
      options: {
        responsive: true, maintainAspectRatio: false, animation: reduce ? false : undefined, locale: $lang === 'en' ? 'en-US' : 'id-ID',
        interaction: { mode: 'index', intersect: false },
        color: v('--muted'), borderColor: v('--grid'), font: { family: 'Outfit, system-ui, sans-serif' },
        scales: {
          x: { grid: { color: v('--grid') }, ticks: { color: v('--muted'), maxRotation: 0, autoSkip: true, autoSkipPadding: 14, maxTicksLimit: 7 } },
          y: { grid: { color: v('--grid') }, beginAtZero: true, ...(max ? { suggestedMax: max } : {}), ticks: { color: v('--muted'), maxTicksLimit: 5, callback: (x) => fmt(x) } },
        },
        plugins: {
          legend: { display: datasets.length > 1, labels: { color: v('--muted'), usePointStyle: true, pointStyle: 'line', boxWidth: 24 } },
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
  {#if points}
    <div class="chart" role="img" aria-label={summary}><canvas bind:this={canvas} aria-hidden="true"></canvas></div>
  {:else}
    <p class="none muted">{$t('sv.chart.none')}</p>
  {/if}
  {#if caption}<p class="capt muted">{caption}</p>{/if}
</section>

<style>
  header { display: flex; justify-content: space-between; align-items: baseline; gap: 8px; }
  h2 { font-size: 0.9375rem; font-weight: 600; color: var(--heading); text-transform: none; }
  .now { font-family: var(--mono); font-size: 0.875rem; color: var(--fg); white-space: nowrap; }
  .chart { position: relative; height: 180px; margin-top: 8px; }
  .none { display: grid; place-items: center; height: 180px; margin: 8px 0 0; font-size: 0.875rem; }
  .capt { margin: 8px 0 0; font-size: 0.75rem; }
</style>
