// Gentle scale-up of the signed-in app on very wide screens (owner choice 2026-11-04): 1.0 up to 2200 CSS px of window
// width, then width / 2200, at most 1.6 (about 1.16 at 2560 px and 1.6 at 3840 px), so text is not tiny on 4K at 100 % OS scaling.
// Applied once as CSS `zoom` on <html> (--ui-scale holds the same number); the public pages and the sign-in screens stay at 1.
export const BASE_WIDTH = 2200, MAX_SCALE = 1.6;

export const scaleFor = (width) => Math.min(MAX_SCALE, Math.max(1, width / BASE_WIDTH));

/** Start following the window width; returns the function that stops it and puts the scale back to 1. */
export function followScale() {
  const root = document.documentElement;
  const apply = () => {
    const s = scaleFor(window.innerWidth);
    root.style.setProperty('--ui-scale', String(s));
    root.style.zoom = s > 1 ? String(s) : '';
  };
  apply();
  window.addEventListener('resize', apply);
  return () => {
    window.removeEventListener('resize', apply);
    root.style.removeProperty('--ui-scale');
    root.style.zoom = '';
  };
}

/** The zoom now applied to <html> (1 when none). */
export const uiZoom = () => parseFloat(document.documentElement.style.zoom) || 1;

/** Chart.js plugin: with CSS zoom on <html> the browser reports pointer offsets in screen pixels while the canvas is laid out in
 *  CSS pixels, so Chart.js would look for bars and tooltips in the wrong place. This recomputes the position from the
 *  canvas rectangle (screen pixels) and the chart size (CSS pixels). No effect at scale 1. */
export const chartZoomFix = {
  id: 'uiZoomFix',
  // Chart.js sizes the canvas from the container's getBoundingClientRect(), which is in screen pixels under zoom: the first
  // draw was zoom times too wide until the ResizeObserver corrected it. The container reports CSS pixels instead.
  beforeInit(chart) {
    const el = chart.canvas.parentNode;
    if (!el || el.__uiZoomRect) return;
    const rect = el.getBoundingClientRect.bind(el);
    el.getBoundingClientRect = () => { const r = rect(), z = uiZoom(); return z === 1 ? r : new DOMRect(r.x / z, r.y / z, r.width / z, r.height / z); };
    el.__uiZoomRect = true;
  },
  beforeEvent(chart, args) {
    if (uiZoom() === 1) return;
    const e = args.event, n = e.native, r = chart.canvas.getBoundingClientRect();
    if (!n || n.clientX === undefined || !r.width || !r.height) return;
    e.x = ((n.clientX - r.left) / r.width) * chart.width;
    e.y = ((n.clientY - r.top) / r.height) * chart.height;
  },
};
