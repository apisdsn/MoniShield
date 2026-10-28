<!-- MoniShield logo (shield + letter M), a single source for the login page, left navigation, and narrow-screen header
     (owner request 2026-10-07: "logo navbar samakan seperti logo di halaman login" — make the navbar logo match the login logo). Same as favicon.svg. -->
<script>
  let { size = 32, glow = false } = $props();
</script>

<svg class="logo" class:glow viewBox="0 0 32 32" width={size} height={size} aria-hidden="true" focusable="false">
  <path class="s" d="M16 2l12 4.5v8.2c0 7.3-5 13.4-12 15.3C9 28.1 4 22 4 14.7V6.5z" />
  <path class="m" d="M10 21V11l6 6 6-6v10" />
</svg>

<style>
  .logo { flex: none; display: block; }
  .glow { filter: drop-shadow(0 0 12px color-mix(in srgb, var(--accent) 35%, transparent)); }
  .s { fill: var(--accent); }
  .m { fill: none; stroke: var(--brand-fg); stroke-width: 2.6; stroke-linecap: round; stroke-linejoin: round; }
</style>
