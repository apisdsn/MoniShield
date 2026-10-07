// Bangun: `npm run build` -> web/dist (disajikan FastAPI di "/"). Jalan pengembangan: `npm run dev` dengan server
// v2 di 127.0.0.1:8000; /api dan /map diteruskan ke sana sehingga cookie sesi tetap satu asal.
import { defineConfig } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';

const api = 'http://127.0.0.1:8000';

// Pesan galat runtime Svelte memuat tautan dokumentasi https://svelte.dev/e/<kode>; MapLibre memuat tautan logo/atribusi
// bawaannya (tidak dipakai: atribusi sendiri, DRD §7.8) dan satu tautan isu di teks peringatan. Tidak ada yang diambil,
// tetapi hasil build harus bebas alamat pihak ketiga (DRD §7.2, A4): kodenya tetap, tautannya dibuang. Yang tersisa
// hanya tautan atribusi wajib MaxMind dan GeoNames (DRD §7.8, dibuka pengguna sendiri).
const LINKS = [['https://svelte.dev/e/', 'svelte/e/'], ['https://maplibre.org/', 'maplibre.org/'],
               ['https://github.com/mapbox/mapbox-gl-js/issues/2907', 'mapbox-gl-js#2907']];
const noExternalLinks = {
  name: 'monishield-no-external-links',
  renderChunk: (code) => ({ code: LINKS.reduce((c, [a, b]) => c.replaceAll(a, b), code), map: null }),
};

export default defineConfig({
  plugins: [svelte(), noExternalLinks],
  // chunkSizeWarningLimit: MapLibre ±1 MB, chunk terpisah yang dimuat hanya saat peta dibuka
  build: { outDir: 'dist', emptyOutDir: true, chunkSizeWarningLimit: 1100, sourcemap: false },
  server: { proxy: { '/api': api, '/map': api } },
});
