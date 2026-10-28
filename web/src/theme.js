// Dark/light theme (DRD §6.4). Dark by default, does not follow the system preference (ASSUMPTION D2). Chart colors are read
// from CSS tokens at draw time, so a theme change = redraw without fetching data again.
import { writable } from 'svelte/store';
import { load, save } from './store.js';

export const theme = writable(load('theme', 'dark') === 'light' ? 'light' : 'dark');
theme.subscribe((v) => {
  save('theme', v);
  if (typeof document !== 'undefined') document.documentElement.dataset.theme = v;
});

/** Current CSS token value, e.g. css('--accent'). */
export const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
