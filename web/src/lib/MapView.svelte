<!-- Peta asal request (DRD §7) dengan MapLibre GL. Tanpa permintaan ke domain luar: daratan/batas dari /map/*.geojson
     (dibuat ingest), label dari /map/labels.json, huruf Noto Sans dari /fonts (dibundel). 13 lapisan §7.3; preset
     Indonesia/Dunia (fit bounds); titik per lokasi + pengelompokan < 40 px sampai zoom 7 (lingkaran kelompok
     tanpa angka, keputusan pemilik 2026-10-06; angka di tooltip dan di label 6 lokasi terbesar); busur per lokasi; titik
     server; tooltip bergaya chart dengan "Lihat di tabel"; gerakan kooperatif (Ctrl + roda, dua jari); keyboard
     (panah, +/−, 0, Esc); atribusi selalu terlihat; ganti tema/bahasa/data tanpa kehilangan posisi.
     MapLibre dimuat terpisah (import dinamis) agar halaman lain tidak ikut membawanya. -->
<script module>
  let labelsP = null;   // labels.json dipakai bersama semua peta di halaman
  const loadLabels = () => (labelsP ||= fetch('/map/labels.json').then((r) => (r.ok ? r.json() : { c: [], p: [], k: [] })).catch(() => ({ c: [], p: [], k: [] })));
  export const PRESETS = { id: [[94, -12], [142, 8]], world: [[-168, -60], [168, 80]] };
</script>

<script>
  import { onMount, tick } from 'svelte';
  import { lang, t, countryName } from '../i18n.js';
  import { theme } from '../theme.js';
  import { num } from '../format.js';

  /** points: [{lat, lon, city, region, cc, ips, requests, modules: {modul: n}}] (urut naik); server: {ip, lat, lon, city, cc} */
  let { points = [], server = null, preset = $bindable('id'), onpick = null, label = '', compact = false, tall = false } = $props();   // tall: setinggi layar (Command Center)
  let box = $state(), wrap = $state(), map = null, ml = null, ready = $state(false), failed = $state(false);
  let tip = $state(null), full = $state(false);   // tip: {x, y, kind, ...}

  const css = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
  const place = (p, l) => [p.city, p.region, $countryName(p.cc)].filter(Boolean).filter((x, i, a) => a.indexOf(x) === i).join(', ') || (l === 'en' ? 'Unknown' : 'Tidak diketahui');
  const shortName = (p) => p.city || p.region || $countryName(p.cc) || '?';

  // ---------------------------------------------------------------- data -> GeoJSON
  function features(pts) {
    const max = Math.max(1, ...pts.map((p) => p.requests));
    const byRank = [...pts].sort((a, b) => b.requests - a.requests);
    const rank = new Map(byRank.map((p, i) => [p, i + 1]));
    const loc = pts.map((p, i) => ({ type: 'Feature', id: i + 1, geometry: { type: 'Point', coordinates: [p.lon, p.lat] },
      properties: { i, requests: p.requests, ips: p.ips, rank: rank.get(p), name: shortName(p), sub: `${num(p.ips, $lang)} IP · ${num(p.requests, $lang)} req` } }));
    const arcs = server ? pts.map((p) => {
      const [x0, y0, x1, y1] = [p.lon, p.lat, server.lon, server.lat];
      const cx = (x0 + x1) / 2, cy = (y0 + y1) / 2 + Math.hypot(x1 - x0, y1 - y0) / 4;   // lengkung lama: kontrol di atas titik tengah
      const line = Array.from({ length: 25 }, (_, k) => { const s = k / 24, u = 1 - s; return [u * u * x0 + 2 * u * s * cx + s * s * x1, u * u * y0 + 2 * u * s * cy + s * s * y1]; });
      return { type: 'Feature', geometry: { type: 'LineString', coordinates: line },
        properties: { w: 1 + (3 * p.requests) / max, op: p.requests < max * 0.01 ? 0.25 : 0.45 } };
    }) : [];
    return { loc: { type: 'FeatureCollection', features: loc }, top: { type: 'FeatureCollection', features: loc.filter((f) => f.properties.rank <= 6) },
      arcs: { type: 'FeatureCollection', features: arcs }, max };
  }
  const srvFC = () => ({ type: 'FeatureCollection', features: server ? [{ type: 'Feature', geometry: { type: 'Point', coordinates: [server.lon, server.lat] },
    properties: { name: `${$t('map.server')}\n${server.ip}` } }] : [] });
  function labelFC(L) {
    const P = (x, y, props) => ({ type: 'Feature', geometry: { type: 'Point', coordinates: [x, y] }, properties: props });
    return {
      c: { type: 'FeatureCollection', features: L.c.map(([id, en, x, y, r]) => P(x, y, { id: id.toUpperCase(), en: en.toUpperCase(), r })) },
      p: { type: 'FeatureCollection', features: L.p.map(([n, x, y]) => P(x, y, { n })) },
      k: { type: 'FeatureCollection', features: L.k.map(([n, x, y]) => P(x, y, { n })) },
    };
  }

  // ---------------------------------------------------------------- gaya
  function colors() {
    return { sea: css('--card2'), land: css('--land'), coast: css('--coast'), accent: css('--accent'), server: css('--c10'), fg: css('--fg'), muted: css('--muted'),
      halo: css('--card2') };
  }
  function style(L, d, c, l) {
    const font = ['Noto Sans Regular'], bold = ['Noto Sans Bold'];
    const o = location.origin;
    return {
      version: 8, glyphs: `${o}/fonts/{fontstack}/{range}.pbf`,   // huruf dibundel (DRD §7.2); tanpa sprite
      sources: {
        land: { type: 'geojson', data: `${o}/map/land.geojson` },
        borders: { type: 'geojson', data: `${o}/map/borders-country.geojson` },
        prov: { type: 'geojson', data: `${o}/map/borders-province-id.geojson` },
        arcs: { type: 'geojson', data: d.arcs },
        loc: { type: 'geojson', data: d.loc, cluster: true, clusterRadius: 40, clusterMaxZoom: 7,
          clusterProperties: { requests: ['+', ['get', 'requests']], ips: ['+', ['get', 'ips']] } },
        top: { type: 'geojson', data: d.top },
        srv: { type: 'geojson', data: srvFC() },
        lc: { type: 'geojson', data: L.c }, lp: { type: 'geojson', data: L.p }, lk: { type: 'geojson', data: L.k },
      },
      layers: [
        { id: 'sea', type: 'background', paint: { 'background-color': c.sea } },
        { id: 'land', type: 'fill', source: 'land', paint: { 'fill-color': c.land } },
        { id: 'coast', type: 'line', source: 'land', paint: { 'line-color': c.coast, 'line-width': 0.5 } },
        { id: 'borders', type: 'line', source: 'borders', paint: { 'line-color': c.coast, 'line-width': 0.75 } },
        { id: 'prov', type: 'line', source: 'prov', minzoom: 4, paint: { 'line-color': c.coast, 'line-width': 0.5, 'line-dasharray': [3, 2] } },
        { id: 'arcs', type: 'line', source: 'arcs', layout: { 'line-cap': 'round' }, paint: { 'line-color': c.accent, 'line-width': ['get', 'w'], 'line-opacity': ['get', 'op'] } },
        { id: 'clusters', type: 'circle', source: 'loc', filter: ['has', 'point_count'],
          paint: { 'circle-color': c.accent, 'circle-opacity': 0.28, 'circle-stroke-color': c.accent, 'circle-stroke-width': 2, 'circle-stroke-opacity': 0.9,
            'circle-radius': ['interpolate', ['linear'], ['sqrt', ['get', 'requests']], 0, 12, Math.sqrt(Math.max(d.max * 4, 1)), 22] } },
        { id: 'points', type: 'circle', source: 'loc', filter: ['!', ['has', 'point_count']],
          layout: { 'circle-sort-key': ['get', 'requests'] },   // terbesar paling atas (lama)
          paint: { 'circle-radius': 5, 'circle-color': c.accent, 'circle-stroke-color': c.accent, 'circle-stroke-width': 2, 'circle-stroke-opacity': 0.45 } },
        { id: 'server', type: 'circle', source: 'srv', paint: { 'circle-radius': 7, 'circle-color': c.server, 'circle-stroke-color': c.halo, 'circle-stroke-width': 2 } },
        // label: urutan bawah -> atas = prioritas rendah -> tinggi (kabupaten < provinsi < negara < lokasi IP < server)
        { id: 'lbl-kab', type: 'symbol', source: 'lk', minzoom: 7,
          layout: { 'text-field': ['get', 'n'], 'text-font': font, 'text-size': 10, 'text-padding': 4 },
          paint: { 'text-color': c.muted, 'text-halo-color': c.halo, 'text-halo-width': 1.2 } },
        { id: 'lbl-prov', type: 'symbol', source: 'lp', minzoom: 4,
          layout: { 'text-field': ['get', 'n'], 'text-font': font, 'text-size': 11, 'text-padding': 4, 'text-max-width': 8 },
          paint: { 'text-color': c.muted, 'text-halo-color': c.halo, 'text-halo-width': 1.2 } },
        { id: 'lbl-country-small', type: 'symbol', source: 'lc', minzoom: 3, filter: ['>', ['get', 'r'], 2],
          layout: { 'text-field': ['get', l === 'en' ? 'en' : 'id'], 'text-font': bold, 'text-size': 10, 'text-letter-spacing': 0.15, 'text-max-width': 7 },
          paint: { 'text-color': c.muted, 'text-halo-color': c.halo, 'text-halo-width': 1, 'text-opacity': 0.85 } },
        { id: 'lbl-country', type: 'symbol', source: 'lc', filter: ['<=', ['get', 'r'], 2],
          layout: { 'text-field': ['get', l === 'en' ? 'en' : 'id'], 'text-font': bold, 'text-size': 11, 'text-letter-spacing': 0.18, 'text-max-width': 7 },
          paint: { 'text-color': c.muted, 'text-halo-color': c.halo, 'text-halo-width': 1, 'text-opacity': 0.9 } },
        { id: 'lbl-loc', type: 'symbol', source: 'loc', filter: ['all', ['!', ['has', 'point_count']], ['>', ['get', 'rank'], 6]],
          layout: { 'text-field': ['get', 'name'], 'text-font': font, 'text-size': 11, 'text-anchor': 'left', 'text-offset': [0.9, 0], 'text-optional': true,
            'symbol-sort-key': ['-', ['get', 'requests']] },
          paint: { 'text-color': c.fg, 'text-halo-color': c.halo, 'text-halo-width': 1.4 } },
        { id: 'lbl-top', type: 'symbol', source: 'top',   // 6 lokasi terbesar selalu berlabel (lama)
          // 6 terbesar: ditempatkan paling dulu (lapisan teratas) dan boleh pindah sisi; tidak menimpa label lain (§7.3)
          // nama tebal + baris kecil "N IP · N req" (gaya label lama; diminta pemilik 2026-10-06)
          layout: { 'text-field': ['format', ['get', 'name'], { 'text-font': ['literal', bold] }, '\n', {}, ['get', 'sub'], { 'font-scale': 0.85, 'text-font': ['literal', ['Noto Sans Regular']] }],
            'text-font': bold, 'text-size': 12, 'text-line-height': 1.25,
            'text-variable-anchor': ['left', 'right', 'top', 'bottom', 'top-left', 'bottom-left', 'top-right', 'bottom-right'], 'text-radial-offset': 0.9,
            'text-justify': 'auto', 'text-padding': 3, 'symbol-sort-key': ['-', ['get', 'requests']] },
          paint: { 'text-color': c.fg, 'text-halo-color': c.halo, 'text-halo-width': 1.6 } },
        { id: 'lbl-srv', type: 'symbol', source: 'srv',
          layout: { 'text-field': ['get', 'name'], 'text-font': bold, 'text-size': 11, 'text-anchor': 'right', 'text-justify': 'right', 'text-offset': [-1, 0],
            'text-allow-overlap': true },   // selalu tampil, dan label lain menghindarinya
          paint: { 'text-color': c.server, 'text-halo-color': c.halo, 'text-halo-width': 1.6 } },
      ],
    };
  }

  // ---------------------------------------------------------------- teks antarmuka MapLibre (dua bahasa)
  const uiText = (l) => ({
    'CooperativeGesturesHandler.WindowsHelpText': l === 'en' ? 'Hold Ctrl and scroll to zoom the map' : 'Tahan Ctrl lalu gulir untuk memperbesar peta',
    'CooperativeGesturesHandler.MacHelpText': l === 'en' ? 'Hold ⌘ and scroll to zoom the map' : 'Tahan ⌘ lalu gulir untuk memperbesar peta',
    'CooperativeGesturesHandler.MobileHelpText': l === 'en' ? 'Use two fingers to move the map' : 'Gunakan dua jari untuk menggeser peta',
    'Map.Title': label,
  });

  onMount(() => {
    let alive = true, offTheme, offLang;
    (async () => {
      try {
        const [mod, L] = await Promise.all([import('maplibre-gl'), loadLabels(), import('maplibre-gl/dist/maplibre-gl.css')]);
        if (!alive) return;
        ml = mod.default;
        const l = $lang, LF = labelFC(L);
        const d = features(points);
        map = new ml.Map({
          container: box, style: style(LF, d, colors(), l), bounds: PRESETS[preset], fitBoundsOptions: { padding: 12 },
          maxZoom: 10, minZoom: 0.5, renderWorldCopies: false, dragRotate: false, pitchWithRotate: false, touchPitch: false,
          cooperativeGestures: true, attributionControl: false, locale: uiText(l), maxPitch: 0,
          canvasContextAttributes: { preserveDrawingBuffer: tall },   // Command Center: kanvas ikut tercetak di ringkasan PDF (Tahap 24)
        });
        box.__map = map;   // dibaca alat uji (tools/uji_tahap20.cjs): posisi, zoom, fitur yang tergambar
        map.touchZoomRotate.disableRotation();
        map.keyboard.disableRotation();
        map.getCanvas().setAttribute('aria-label', label);
        map.on('load', () => { ready = true; });
        map.on('error', (e) => { if (/WebGL/i.test(String(e?.error?.message))) failed = true; });
        map.on('movestart', () => (tip = null));
        for (const id of ['points', 'clusters', 'server']) {
          map.on('mouseenter', id, () => (map.getCanvas().style.cursor = 'pointer'));
          map.on('mouseleave', id, () => { map.getCanvas().style.cursor = ''; if (!tip?.sticky) tip = null; });
          map.on('mousemove', id, (e) => show(id, e.features[0], e.point, false));
          map.on('click', id, (e) => { e.preventDefault(); clickOn(id, e.features[0], e.point); });
        }
        map.on('click', (e) => { if (!e.defaultPrevented) tip = null; });
        // tema & bahasa: ubah cat/teks di tempat (posisi dan zoom tetap)
        let firstT = true, firstL = true;
        offTheme = theme.subscribe(() => { if (firstT) return (firstT = false); tick().then(repaint); });
        offLang = lang.subscribe((nl) => { if (firstL) return (firstL = false); relabel(nl); });
      } catch (e) { failed = true; }
    })();
    return () => { alive = false; offTheme?.(); offLang?.(); map?.remove(); map = null; };
  });

  // data berganti (mis. pilih modul): ganti isi sumber; kamera tidak disentuh
  $effect(() => {
    const d = features(points);
    void server;
    if (!ready || !map) return;
    map.getSource('loc')?.setData(d.loc); map.getSource('top')?.setData(d.top); map.getSource('arcs')?.setData(d.arcs); map.getSource('srv')?.setData(srvFC());
    map.setPaintProperty('clusters', 'circle-radius', ['interpolate', ['linear'], ['sqrt', ['get', 'requests']], 0, 12, Math.sqrt(Math.max(d.max * 4, 1)), 22]);
    tip = null;
  });
  // preset dari tombol Indonesia | Dunia
  let lastPreset = null;
  $effect(() => { const p = preset; if (ready && map && lastPreset !== null && p !== lastPreset) fit(); lastPreset = p; });
  const fit = () => map?.fitBounds(PRESETS[preset], { padding: 12, duration: 400 });

  function repaint() {
    if (!map) return;
    const c = colors();
    const set = (id, k, v) => map.getLayer(id) && map.setPaintProperty(id, k, v);
    set('sea', 'background-color', c.sea); set('land', 'fill-color', c.land); set('coast', 'line-color', c.coast); set('borders', 'line-color', c.coast);
    set('prov', 'line-color', c.coast); set('arcs', 'line-color', c.accent); set('clusters', 'circle-color', c.accent); set('clusters', 'circle-stroke-color', c.accent);
    set('points', 'circle-color', c.accent); set('points', 'circle-stroke-color', c.accent); set('server', 'circle-color', c.server); set('server', 'circle-stroke-color', c.halo);
    for (const id of ['lbl-kab', 'lbl-prov', 'lbl-country-small', 'lbl-country']) { set(id, 'text-color', c.muted); set(id, 'text-halo-color', c.halo); }
    for (const id of ['lbl-loc', 'lbl-top']) { set(id, 'text-color', c.fg); set(id, 'text-halo-color', c.halo); }
    set('lbl-srv', 'text-color', c.server); set('lbl-srv', 'text-halo-color', c.halo);
  }
  function relabel(l) {
    if (!map) return;
    for (const id of ['lbl-country', 'lbl-country-small']) map.getLayer(id) && map.setLayoutProperty(id, 'text-field', ['get', l === 'en' ? 'en' : 'id']);
    // teks gerakan kooperatif dibaca MapLibre saat diaktifkan: tulis ulang lalu aktifkan lagi (map._locale = kamus UI MapLibre)
    Object.assign(map._locale, uiText(l));
    map.cooperativeGestures.disable(); map.cooperativeGestures.enable();
    map.getCanvas().setAttribute('aria-label', label);
    const d = features(points); map.getSource('loc')?.setData(d.loc); map.getSource('top')?.setData(d.top);   // "N IP · N req" dan nama negara mengikuti bahasa
    tip = null;
  }

  // ---------------------------------------------------------------- tooltip
  async function show(kind, f, pt, sticky) {
    if (tip?.sticky && !sticky) return;
    if (kind === 'server') return (tip = { kind, x: pt.x, y: pt.y, sticky });
    if (kind === 'points') return (tip = { kind, x: pt.x, y: pt.y, p: points[f.properties.i], sticky });
    const src = map.getSource('loc');
    const leaves = await src.getClusterLeaves(f.properties.cluster_id, 10000, 0);
    const ps = leaves.map((x) => points[x.properties.i]).filter(Boolean).sort((a, b) => b.requests - a.requests);
    tip = { kind, x: pt.x, y: pt.y, sticky, n: ps.length, ips: ps.reduce((a, p) => a + p.ips, 0), req: ps.reduce((a, p) => a + p.requests, 0), top: ps.slice(0, 3) };
  }
  async function clickOn(kind, f, pt) {
    if (kind === 'clusters') {
      const z = await map.getSource('loc').getClusterExpansionZoom(f.properties.cluster_id);
      map.easeTo({ center: f.geometry.coordinates, zoom: Math.min(z, 10) });
      return;
    }
    show(kind, f, pt, true);
  }
  function onkey(e) {
    if (e.key === 'Escape') { tip = null; }
    else if (e.key === '0') { e.preventDefault(); fit(); }
  }
  const zoom = (d) => map?.easeTo({ zoom: map.getZoom() + d, duration: 250 });
  async function toggleFull() { full = !full; await tick(); map?.resize(); if (!full) wrap?.scrollIntoView({ block: 'nearest' }); }
  const mods = (p) => Object.entries(p.modules || {}).sort((a, b) => b[1] - a[1]);
</script>

<svelte:window onkeydown={(e) => full && e.key === 'Escape' && toggleFull()} />

<div class="mapwrap" class:compact class:tall class:full bind:this={wrap}>
  <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
  <div class="map" bind:this={box} role="application" aria-label={label} onkeydown={onkey}></div>
  {#if failed}<p class="fail muted">{$t('map.no_webgl')}</p>{/if}
  <div class="ctl">
    <button type="button" class="mb" aria-label={$t('map.zoom_in')} title={$t('map.zoom_in')} onclick={() => zoom(1)}>+</button>
    <button type="button" class="mb" aria-label={$t('map.zoom_out')} title={$t('map.zoom_out')} onclick={() => zoom(-1)}>−</button>
    <button type="button" class="mb" aria-label={$t('map.reset')} title={$t('map.reset')} onclick={fit}>⤢</button>
    <button type="button" class="mb fs" aria-pressed={full} aria-label={$t(full ? 'map.exit_full' : 'map.full')} title={$t(full ? 'map.exit_full' : 'map.full')} onclick={toggleFull}>{full ? '×' : '⛶'}</button>
  </div>
  {#if tip}
    <div class="tip" class:flipx={tip.x > (wrap?.clientWidth ?? 0) - 340} class:flipy={tip.y > (wrap?.clientHeight ?? 0) - 170}
      role="dialog" aria-label={$t('map.details')} style="left:{tip.x}px;top:{tip.y}px">
      {#if tip.kind === 'server'}
        <b>{$t('map.server')}</b> <code>{server.ip}</code><div class="muted">{server.city}, {server.cc}</div>
      {:else if tip.kind === 'points'}
        <b>{place(tip.p, $lang)}</b>
        <div>{$t('map.tip_line', { ips: num(tip.p.ips, $lang), n: num(tip.p.requests, $lang) })}</div>
        {#each mods(tip.p) as [m, n], i}<div class="mod"><span class="sys">{i === 0 ? '→ ' : '  '}{m}</span> ({num(n, $lang)})</div>{/each}
        {#if onpick}<button type="button" class="btn accent sm" onclick={() => { onpick(tip.p.city || tip.p.region || $countryName(tip.p.cc)); tip = null; }}>{$t('map.see_table')}</button>{/if}
      {:else}
        <b>{$t('map.cluster_line', { n: num(tip.n, $lang), ips: num(tip.ips, $lang), req: num(tip.req, $lang) })}</b>
        {#each tip.top as p}<div class="mod">{shortName(p)} ({num(p.requests, $lang)})</div>{/each}
        <div class="muted">{$t('map.cluster_hint')}</div>
      {/if}
    </div>
  {/if}
  <div class="attr">{$t('map.attr_pre')} <a href="https://www.maxmind.com" target="_blank" rel="noreferrer">MaxMind</a> · <a href="https://www.geonames.org" target="_blank" rel="noreferrer">GeoNames</a> · Natural Earth</div>
</div>

<style>
  .mapwrap { position: relative; width: 100%; aspect-ratio: 2.4 / 1; border-radius: 12px; overflow: hidden; border: 1px solid var(--line); background: var(--card2); }
  .map { position: absolute; inset: 0; }
  .map :global(canvas:focus-visible) { outline: 2px solid var(--focus); outline-offset: -2px; }
  .ctl { position: absolute; top: 10px; right: 10px; display: flex; flex-direction: column; gap: 6px; z-index: 2; }
  .mb {
    width: 34px; height: 34px; border-radius: 10px; border: 1px solid var(--line-strong); background: var(--card); color: var(--fg);
    font-size: 1.05rem; cursor: pointer; display: grid; place-items: center; box-shadow: var(--glow);
  }
  .mb:hover { background: var(--nav-hover); }
  .fs { display: none; }
  .attr {
    position: absolute; right: 0; bottom: 0; z-index: 2; font-size: 0.6875rem; padding: 3px 8px; border-top-left-radius: 8px;
    background: color-mix(in srgb, var(--card) 88%, transparent); color: var(--muted);
  }
  .attr a { color: inherit; }
  .tip {
    position: absolute; z-index: 3; transform: translate(12px, 12px); max-width: min(320px, calc(100% - 24px)); pointer-events: auto;
    background: var(--tooltip-bg); color: #e2ecf3; border: 1px solid var(--tooltip-line); border-radius: 12px; padding: 10px 12px;
    font-size: 0.8125rem; line-height: 1.45; box-shadow: var(--glow);
  }
  .tip.flipx { transform: translate(calc(-100% - 12px), 12px); }
  .tip.flipy { transform: translate(12px, calc(-100% - 12px)); }
  .tip.flipx.flipy { transform: translate(calc(-100% - 12px), calc(-100% - 12px)); }
  .tip .muted { color: #9fb0bf; }
  .tip code { color: #e2ecf3; }
  .mod { white-space: pre; font-size: 0.75rem; }
  .sm { min-height: 32px; margin-top: 8px; padding: 0.3rem 0.8rem; font-size: 0.75rem; }
  .fail { position: absolute; inset: 0; display: grid; place-items: center; padding: 16px; text-align: center; font-size: 0.875rem; }
  .compact { aspect-ratio: 2.4 / 1; }
  .mapwrap.tall { aspect-ratio: auto; height: calc(100vh - 300px); height: calc(100dvh - 300px); min-height: 440px; }
  .mapwrap :global(.maplibregl-cooperative-gesture-screen) { font-family: inherit; font-size: 1rem; background: rgba(0, 0, 0, 0.45); }
  @media (max-width: 900px) {
    .mapwrap { aspect-ratio: 4 / 3; min-height: 300px; }
    .mapwrap.tall { aspect-ratio: auto; height: calc(100dvh - 220px); min-height: 360px; }
    .mb { width: 44px; height: 44px; }
    .fs { display: grid; }
    .mapwrap.full { position: fixed; inset: 0; z-index: 80; aspect-ratio: auto; border-radius: 0; min-height: 0; }
  }
</style>
