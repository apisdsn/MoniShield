// Flow animation on the map (owner request 2026-10-07: "garis peta diberi animasi gerak agar kelihatan ke arah IP tujuan",
// i.e. animate the map lines so the direction to the target IP is visible; Kafka realtime preparation). Glowing particles
// travel along the arcs from the origin location to the server dot, with a fading tail; every particle that arrives
// triggers a ripple at the server dot.
//
// Two particle sources:
//   ambient  historical data (one folder): each arc spawns particles periodically, more often the more requests it
//            has (square root, so small locations stay visible).
//   pulse()  one real event (e.g. a Kafka message forwarded to the browser): a particle on that location's arc, or a temporary
//            arc when the location is not on the map yet. `live` mode turns off ambient so only real events
//            move. Other code only needs to send the window event `monishield:map-pulse` {lat, lon, n}.
//
// Cheap: only two small GeoJSON sources updated ±30 times/second (max. MAX particles); stops by itself when the map
// is not visible, the tab is hidden, or paused. Direction is readable without motion too: base arcs get a faint -> bright gradient.

const MAX = 320;          // maximum active particles
const FPS_MS = 33;        // ±30 fps
const TAIL = 0.14;        // tail length (fraction of the arc)
const RIPPLE_MS = 1100;

export function rgba(color, a) {
  const m = /^#?([0-9a-f]{6})$/i.exec((color || '').trim());
  if (!m) return color;
  const n = parseInt(m[1], 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${a})`;
}

/** Quadratic arc (same as the map's arc lines): control point above the midpoint. */
export function arcOf(x0, y0, x1, y1) {
  return { x0, y0, x1, y1, cx: (x0 + x1) / 2, cy: (y0 + y1) / 2 + Math.hypot(x1 - x0, y1 - y0) / 4 };
}
const at = (a, s) => { const u = 1 - s; return [u * u * a.x0 + 2 * u * s * a.cx + s * s * a.x1, u * u * a.y0 + 2 * u * s * a.cy + s * s * a.y1]; };
const durOf = (a) => Math.min(3200, Math.max(900, 800 + Math.hypot(a.x1 - a.x0, a.y1 - a.y0) * 45));
const FC = (features) => ({ type: 'FeatureCollection', features });

export const flowSources = () => ({
  'flow-tail': { type: 'geojson', data: FC([]), lineMetrics: true },
  'flow-head': { type: 'geojson', data: FC([]) },
  'flow-ripple': { type: 'geojson', data: FC([]) },
});

export const flowLayers = (accent, server) => [
  { id: 'flow-tail', type: 'line', source: 'flow-tail', layout: { 'line-cap': 'round' },
    paint: { 'line-width': ['get', 'w'], 'line-gradient': tailGradient(accent) } },
  { id: 'flow-glow', type: 'circle', source: 'flow-head',   // glow around the particle head
    paint: { 'circle-radius': ['*', ['get', 'r'], 2.8], 'circle-color': accent, 'circle-blur': 1, 'circle-opacity': 0.3 } },
  { id: 'flow-head', type: 'circle', source: 'flow-head',
    paint: { 'circle-radius': ['get', 'r'], 'circle-color': accent, 'circle-blur': 0.35, 'circle-opacity': 0.95 } },
  { id: 'flow-ripple', type: 'circle', source: 'flow-ripple',
    paint: { 'circle-radius': ['get', 'r'], 'circle-color': 'rgba(0,0,0,0)', 'circle-stroke-color': server, 'circle-stroke-width': 1.5,
      'circle-stroke-opacity': ['get', 'op'] } },
];
export const tailGradient = (accent) => ['interpolate', ['linear'], ['line-progress'], 0, rgba(accent, 0), 1, rgba(accent, 0.9)];
export const arcGradient = (accent) => ['interpolate', ['linear'], ['line-progress'], 0, rgba(accent, 0.25), 1, accent];

export class FlowAnimator {
  /** map: maplibre Map that has loaded flowSources/flowLayers; box: map element (for visibility detection). */
  constructor(map, box) {
    this.map = map; this.arcs = []; this.parts = []; this.ripples = []; this.server = null;
    this.on = true; this.live = false; this.visible = true; this.raf = 0; this.last = 0; this.cleared = true;
    this.io = new IntersectionObserver(([e]) => { this.visible = e.isIntersecting; this._kick(); });
    this.io.observe(box);
    this._onVis = () => this._kick();
    document.addEventListener('visibilitychange', this._onVis);
  }

  /** pts: [{lon, lat, requests}], server: {lon, lat} — ambient arcs rebuilt (travelling particles dropped). */
  setData(pts, server) {
    this.server = server && Number.isFinite(server.lon) ? server : null;
    const max = Math.max(1, ...pts.map((p) => p.requests || 0));
    const now = performance.now();
    this.arcs = this.server ? pts.map((p) => {
      const a = arcOf(p.lon, p.lat, this.server.lon, this.server.lat);
      const share = Math.sqrt((p.requests || 0) / max);
      a.every = 3800 - 3200 * share;            // ms between particles: 0.6 s (largest) .. 3.8 s (smallest)
      a.w = 1.5 + 2.5 * share;
      a.next = now + Math.random() * a.every;  // not in sync
      return a;
    }) : [];
    this.parts = []; this.ripples = [];
    this._kick();
  }

  setPlaying(on) { this.on = on; if (!on) this._clear(); this._kick(); }
  setLive(live) { this.live = live; this._kick(); }

  /** One real event from (lat, lon) toward the server; n = request count (max. 5 particles, staggered). */
  pulse({ lat, lon, n = 1, w = 2.5 }) {
    if (!this.server || !Number.isFinite(lat) || !Number.isFinite(lon)) return false;
    let a = this.arcs.find((x) => Math.abs(x.x0 - lon) < 0.05 && Math.abs(x.y0 - lat) < 0.05);
    if (!a) { a = arcOf(lon, lat, this.server.lon, this.server.lat); a.w = w; }
    const now = performance.now();
    for (let k = 0; k < Math.min(5, Math.max(1, n)); k++) this._spawn(a, now + k * 140);
    this._kick();
    return true;
  }

  destroy() {
    cancelAnimationFrame(this.raf); this.raf = 0;
    this.io.disconnect();
    document.removeEventListener('visibilitychange', this._onVis);
  }

  // ------------------------------------------------------------------ internals
  _spawn(a, t0) {
    if (this.parts.length >= MAX) return;
    this.parts.push({ a, t0, dur: durOf(a) });
  }
  _active() { return this.on && this.visible && !document.hidden && (this.parts.length || this.ripples.length || (!this.live && this.arcs.length)); }
  _kick() {
    if (this.raf || !this._active()) return;
    this.raf = requestAnimationFrame((t) => this._frame(t));
  }
  _clear() {
    if (this.cleared) return;
    for (const id of ['flow-tail', 'flow-head', 'flow-ripple']) this.map.getSource(id)?.setData(FC([]));
    this.cleared = true;
  }
  _frame(now) {
    this.raf = 0;
    if (!this._active()) return;
    if (now - this.last >= FPS_MS) {
      this.last = now;
      if (!this.live) for (const a of this.arcs) if (now >= a.next) { this._spawn(a, now); a.next = now + a.every * (0.8 + Math.random() * 0.4); }
      const tails = [], heads = [], keep = [];
      for (const p of this.parts) {
        if (now < p.t0) { keep.push(p); continue; }
        const s = (now - p.t0) / p.dur;
        if (s >= 1) { if (this.ripples.length < 8) this.ripples.push(now); continue; }
        keep.push(p);
        const e = s * s * (3 - 2 * s);          // slow at the start/end
        const s0 = Math.max(0, e - TAIL);
        tails.push({ type: 'Feature', properties: { w: p.a.w }, geometry: { type: 'LineString', coordinates: [0, 0.25, 0.5, 0.75, 1].map((k) => at(p.a, s0 + (e - s0) * k)) } });
        heads.push({ type: 'Feature', properties: { r: 1.6 + p.a.w * 0.7 }, geometry: { type: 'Point', coordinates: at(p.a, e) } });
      }
      this.parts = keep;
      this.ripples = this.ripples.filter((t0) => now - t0 < RIPPLE_MS);
      const rip = this.server ? this.ripples.map((t0) => {
        const k = (now - t0) / RIPPLE_MS;
        return { type: 'Feature', properties: { r: 7 + 16 * k, op: 0.7 * (1 - k) }, geometry: { type: 'Point', coordinates: [this.server.lon, this.server.lat] } };
      }) : [];
      this.map.getSource('flow-tail')?.setData(FC(tails));
      this.map.getSource('flow-head')?.setData(FC(heads));
      this.map.getSource('flow-ripple')?.setData(FC(rip));
      this.cleared = false;
    }
    this._kick();
  }
}
