<!-- Batang horizontal top-N (DRD §4.2): label dipotong 48 karakter (28 di layar sempit), teks lengkap di tooltip;
     untuk IP, tooltip menampilkan pemilik di baris kedua (lama). onpick(i): klik batang (mis. gulir ke baris IP). -->
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
