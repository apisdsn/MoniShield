// Build: `npm run build` -> web/dist (served by FastAPI at "/"). Development: `npm run dev` with the v2 server
// at 127.0.0.1:8000; /api and /map are proxied there so the session cookie stays same-origin.
import { defineConfig } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';
import { copyFileSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';

const api = 'http://127.0.0.1:8000';

// Svelte runtime error messages contain documentation links https://svelte.dev/e/<code>; MapLibre contains its default
// logo/attribution links (unused: our own attribution, DRD §7.8) and one issue link in a warning text. Nothing is fetched,
// but the build output must be free of third-party addresses (DRD §7.2, A4): the code stays, the links are removed. The
// only ones left are the mandatory MaxMind and GeoNames attribution links (DRD §7.8, opened by the user).
const LINKS = [['https://svelte.dev/e/', 'svelte/e/'], ['https://maplibre.org/', 'maplibre.org/'],
               ['https://github.com/mapbox/mapbox-gl-js/issues/2907', 'mapbox-gl-js#2907']];
const noExternalLinks = {
  name: 'monishield-no-external-links',
  renderChunk: (code) => ({ code: LINKS.reduce((c, [a, b]) => c.replaceAll(a, b), code), map: null }),
};

// API documentation (/api/docs, owner request 2026-10-07): Swagger UI is served from our own server (CSP 'self', no
// CDN), copied from swagger-ui-dist into dist/swagger/ at build time. sourceMappingURL comments are removed (maps not copied).
const SWAGGER = 'node_modules/swagger-ui-dist/';
const swaggerAssets = {
  name: 'monishield-swagger-assets',
  closeBundle() {
    mkdirSync('dist/swagger', { recursive: true });
    for (const f of ['swagger-ui-bundle.js', 'swagger-ui.css']) {
      writeFileSync(`dist/swagger/${f}`, readFileSync(SWAGGER + f, 'utf8').replace(/\n?\/[*/]# sourceMappingURL=\S+( \*\/)?\s*$/, '\n'));
    }
    copyFileSync(SWAGGER + 'LICENSE', 'dist/swagger/LICENSE.txt');
  },
};

export default defineConfig({
  plugins: [svelte(), noExternalLinks, swaggerAssets],
  // chunkSizeWarningLimit: MapLibre ±1 MB, a separate chunk loaded only when the map is opened
  build: { outDir: 'dist', emptyOutDir: true, chunkSizeWarningLimit: 1100, sourcemap: false },
  server: { proxy: { '/api': api, '/map': api } },
});
