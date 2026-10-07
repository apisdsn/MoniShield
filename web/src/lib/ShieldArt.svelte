<!-- Ilustrasi perisai MoniShield (halaman login; permintaan pemilik 2026-10-07: jelas, tidak transparan). SVG dibundel
     (tanpa berkas/CDN luar), warna dari token tema sehingga tampil di tema gelap dan terang. Hiasan: aria-hidden. -->
<script>
  let { size = 260 } = $props();
  const id = `sa-${Math.random().toString(36).slice(2, 8)}`;
</script>

<svg class="art" width={size} height={Math.round(size * 1.15)} viewBox="0 0 260 300" aria-hidden="true" focusable="false">
  <defs>
    <linearGradient id="{id}-g" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" style="stop-color: var(--accent)" />
      <stop offset="1" style="stop-color: color-mix(in srgb, var(--accent) 55%, #052e2b)" />
    </linearGradient>
    <linearGradient id="{id}-i" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" style="stop-color: color-mix(in srgb, var(--card) 88%, var(--accent))" />
      <stop offset="1" style="stop-color: var(--card)" />
    </linearGradient>
  </defs>
  <!-- lingkar radar di belakang perisai -->
  <g class="rings" fill="none">
    <circle cx="130" cy="150" r="124" />
    <circle cx="130" cy="150" r="96" />
  </g>
  <g class="nodes">
    <circle cx="22" cy="104" r="5" /><circle cx="240" cy="86" r="5" /><circle cx="34" cy="226" r="4" /><circle cx="232" cy="214" r="6" />
    <path d="M22 104L58 118M240 86L204 104M34 226L66 208M232 214L198 200" />
  </g>
  <!-- perisai luar (gradien penuh) + dalam -->
  <path d="M130 22l92 34v64c0 62-39 115-92 136C77 235 38 182 38 120V56z" fill="url(#{id}-g)" />
  <path class="rim" d="M130 22l92 34v64c0 62-39 115-92 136C77 235 38 182 38 120V56z" fill="none" />
  <path d="M130 44l72 27v50c0 50-31 93-72 110C89 214 58 171 58 121V71z" fill="url(#{id}-i)" />
  <!-- garis denyut (pemantauan) -->
  <polyline class="pulse" points="70,140 98,140 110,112 124,170 138,124 150,150 160,140 190,140" />
  <circle class="dot" cx="190" cy="140" r="5" />
  <!-- huruf M -->
  <path class="m" d="M104 204v-30l26 22 26-22v30" />
</svg>

<style>
  .art { display: block; max-width: 100%; height: auto; filter: drop-shadow(0 12px 32px color-mix(in srgb, var(--accent) 35%, transparent)); }
  .rings circle { stroke: color-mix(in srgb, var(--accent) 45%, transparent); stroke-width: 1.5; stroke-dasharray: 4 6; }
  .nodes circle { fill: var(--accent); }
  .nodes path { stroke: color-mix(in srgb, var(--accent) 60%, transparent); stroke-width: 1.5; fill: none; }
  .rim { stroke: color-mix(in srgb, var(--accent) 70%, #ffffff); stroke-width: 2; }
  .pulse { fill: none; stroke: var(--accent); stroke-width: 6; stroke-linecap: round; stroke-linejoin: round; }
  .dot { fill: var(--accent); }
  .m { fill: none; stroke: var(--accent); stroke-width: 7; stroke-linecap: round; stroke-linejoin: round; }
</style>
