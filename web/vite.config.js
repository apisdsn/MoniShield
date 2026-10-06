// Bangun: `npm run build` -> web/dist (disajikan FastAPI di "/"). Jalan pengembangan: `npm run dev` dengan server
// v2 di 127.0.0.1:8000; /api dan /map diteruskan ke sana sehingga cookie sesi tetap satu asal.
import { defineConfig } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';

const api = 'http://127.0.0.1:8000';

// Pesan galat runtime Svelte memuat tautan dokumentasi https://svelte.dev/e/<kode>. Tidak pernah diambil, tetapi
// hasil build harus bebas alamat pihak ketiga (DRD §7.2, A4; diperiksa Tahap 12): kodenya tetap, tautannya dibuang.
const noExternalLinks = {
  name: 'simpel4-no-external-links',
  renderChunk: (code) => ({ code: code.replaceAll('https://svelte.dev/e/', 'svelte/e/'), map: null }),
};

export default defineConfig({
  plugins: [svelte(), noExternalLinks],
  build: { outDir: 'dist', emptyOutDir: true, chunkSizeWarningLimit: 600, sourcemap: false },
  server: { proxy: { '/api': api, '/map': api } },
});
