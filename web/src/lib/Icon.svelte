<!-- 24×24 line icons (reference style DRD §12), self-drawn and bundled: no CDN/icon library (A4).
     Decorative by default (aria-hidden); the text next to them carries the meaning. -->
<script module>
  const P = {
    overview: 'M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4zM14 14h6v6h-6z',
    globe: 'M12 3a9 9 0 1 0 0 18a9 9 0 1 0 0-18M3 12h18M12 3c2.5 2.6 3.8 5.6 3.8 9s-1.3 6.4-3.8 9c-2.5-2.6-3.8-5.6-3.8-9S9.5 5.6 12 3',
    trend: 'M3 17l6-6 4 4 8-8M15 7h6v6',
    shield: 'M12 3l7 3v5c0 4.5-3 8.3-7 10c-4-1.7-7-5.5-7-10V6z',
    search: 'M11 4a7 7 0 1 0 0 14a7 7 0 1 0 0-14M20 20l-4-4',
    pulse: 'M3 12h4l2-5 4 10 2-5h6',
    box: 'M12 3l8 4.5v9L12 21l-8-4.5v-9zM4 7.5l8 4.5 8-4.5M12 12v9',
    briefcase: 'M4 8h16v11H4zM9 8V5h6v3M4 13h16',
    route: 'M6 19a2 2 0 1 0 0-4a2 2 0 1 0 0 4M18 9a2 2 0 1 0 0-4a2 2 0 1 0 0 4M8 17h7a3 3 0 0 0 0-6H9a3 3 0 0 1 0-6h7',
    server: 'M4 4h16v6H4zM4 14h16v6H4zM8 7h.01M8 17h.01',
    file: 'M6 3h8l4 4v14H6zM14 3v4h4',
    alert: 'M12 4l9 16H3zM12 10v4M12 17h.01',
    lines: 'M4 6h16M4 12h16M4 18h10',
    clock: 'M12 3a9 9 0 1 0 0 18a9 9 0 1 0 0-18M12 7v5l3 2',
    user: 'M12 4a4 4 0 1 0 0 8a4 4 0 1 0 0-8M4 21c1.5-4 4.4-6 8-6s6.5 2 8 6',
    users: 'M9 5a3.5 3.5 0 1 0 0 7a3.5 3.5 0 1 0 0-7M2.5 20c1.2-3.4 3.5-5 6.5-5s5.3 1.6 6.5 5M16 5.5a3 3 0 0 1 0 6M18 14.5c1.7.6 2.9 2.4 3.5 5',
    download: 'M12 4v11M7 10l5 5 5-5M5 20h14',
    key: 'M8 15a4 4 0 1 1 3.5-6H21v3h-2v3h-3v-3h-4.5A4 4 0 0 1 8 15',
    logout: 'M14 4h5v16h-5M10 8l-4 4 4 4M6 12h10',
    sync: 'M3 7h6l2 2h10v10H3zM12 11.5v5M9.5 14l2.5 2.5 2.5-2.5',   // folder + incoming arrow: sync log folders
    refresh: 'M20 5v5h-5M4 19v-5h5M19 10a7.5 7.5 0 0 0-13.5-3M5 14a7.5 7.5 0 0 0 13.5 3',
    arrow: 'M5 12h14M13 6l6 6-6 6',
    dots: 'M5 12h.01M12 12h.01M19 12h.01',
    calendar: 'M4 6h16v14H4zM4 10h16M8 3v5M16 3v5',
    'side-close': 'M4 4h16v16H4zM9 4v16M16 9.5L13.5 12l2.5 2.5',   // left panel + arrow: collapse navigation
    'side-open': 'M4 4h16v16H4zM9 4v16M13.5 9.5L16 12l-2.5 2.5',
    sun: 'M12 8a4 4 0 1 0 0 8a4 4 0 1 0 0-8M12 2.5v2M12 19.5v2M4.6 4.6l1.4 1.4M18 18l1.4 1.4M2.5 12h2M19.5 12h2M4.6 19.4L6 18M18 6l1.4-1.4',
    moon: 'M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z',
    settings: 'M4 7h9M17 7h3M15 5v4M4 12h3M11 12h9M9 10v4M4 17h11M19 17h1M17 15v4',   // sliders: configuration
    code: 'M8 8l-4 4 4 4M16 8l4 4-4 4M13.5 5l-3 14',
    database: 'M12 3c4.4 0 8 1.3 8 3s-3.6 3-8 3s-8-1.3-8-3s3.6-3 8-3M4 6v12c0 1.7 3.6 3 8 3s8-1.3 8-3V6M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3',
  };
</script>

<script>
  let { name, size = 18, stroke = 1.75 } = $props();
</script>

<svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width={stroke}
  stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d={P[name] || P.dots} /></svg>

<style>
  svg { flex: none; display: block; }
</style>
