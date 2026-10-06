// Tema gelap/terang (DRD §6.4). Bawaan gelap, tidak mengikuti preferensi sistem (ASUMSI D2). Warna chart dibaca
// dari token CSS saat digambar, jadi ganti tema = gambar ulang tanpa mengambil data lagi.
import { writable } from 'svelte/store';
import { load, save } from './store.js';

export const theme = writable(load('theme', 'dark') === 'light' ? 'light' : 'dark');
theme.subscribe((v) => {
  save('theme', v);
  if (typeof document !== 'undefined') document.documentElement.dataset.theme = v;
});

/** Nilai token CSS saat ini, mis. css('--accent'). */
export const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
