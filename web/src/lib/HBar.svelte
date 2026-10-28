<!-- Top-N horizontal bars (DRD §4.2): labels truncated to 48 characters (28 on narrow screens), full text in the tooltip;
     for IPs, the tooltip shows the owner on the second line (old). onpick(i): bar click (e.g. scroll to the IP row). -->
<script>
  import ChartCard from './ChartCard.svelte';
  import { cut } from '../format.js';
  import { onMount } from 'svelte';

  /** rows: [{label, value, org?}] */
  let { title, rows = [], color = '--accent', valueLabel = null, fmtV = null, wide = false, info = null, onpick = null } = $props();
  let narrow = $state(false);
  onMount(() => {
    const mq = matchMedia('(max-width: 900px)');
    narrow = mq.matches;
    const f = (e) => (narrow = e.matches);
    mq.addEventListener('change', f);
    return () => mq.removeEventListener('change', f);
  });
  const labels = $derived(rows.map((r) => cut(r.label, narrow ? 28 : 48)));
  const datasets = $derived([{ label: valueLabel, data: rows.map((r) => r.value), color }]);
  const options = $derived({
    indexAxis: 'y',
    plugins: { legend: { display: false } },
    ...(onpick ? { onClick: (e, els) => els[0] && onpick(els[0].index) } : {}),
  });
</script>

<ChartCard {title} type="bar" {labels} {datasets} {wide} {fmtV} {info} {valueLabel} {options}
  tooltipTitle={(i) => (rows[i].org ? [String(rows[i].label), rows[i].org] : String(rows[i].label))} />
