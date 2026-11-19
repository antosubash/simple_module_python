import path from 'node:path';
import { simpleModule } from '@simple-module-py/vite-plugin';
import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import { visualizer } from 'rollup-plugin-visualizer';
import { defineConfig } from 'vite';
import { compressAssets } from './compress-assets.ts';
import { viteDevServer } from './vite.dev-url.ts';

const { origin: devUrl, port: devPort } = viteDevServer();
const analyzeBundle = process.env.ANALYZE === '1';

export { findNodeModulesRoot } from '@simple-module-py/vite-plugin';

// Chunks smaller than this get merged into their importer. See build.rollupOptions.
const MIN_CHUNK_BYTES = 20_000;

export default defineConfig(({ command }) => ({
  // Built chunks record their lazy-import dependencies as base-relative paths
  // ("assets/Browse-x.js"), and Vite's __vitePreload helper prefixes them with
  // `base`. The host serves the build under /static/dist/, so the default base
  // of "/" made every preload request /assets/... — which the SPA fallback
  // answered with HTML, producing a 404 plus a MIME-type console error on
  // every lazy page load. The page still worked, because the *actual* dynamic
  // import uses a relative "./" specifier; only the preloads were wasted.
  //
  // Build only: in dev the host points <script> straight at
  // ${SM_VITE_DEV_URL}/main.tsx, and a base here would move the dev server's
  // served paths out from under it.
  base: command === 'build' ? '/static/dist/' : '/',
  plugins: [
    ...simpleModule({ root: import.meta.dirname }),
    react(),
    tailwindcss(),
    compressAssets(),
    ...(analyzeBundle
      ? [
          visualizer({
            filename: path.resolve(import.meta.dirname, '../static/dist/stats.html'),
            template: 'sunburst',
            gzipSize: true,
            brotliSize: true,
          }),
        ]
      : []),
  ],
  root: import.meta.dirname,
  // The supervisor resolves dotenv once; standalone launches and builds use Vite's loader.
  envDir: command === 'serve' && process.env.SM_DEV_SUPERVISED === '1' ? false : undefined,
  build: {
    outDir: '../static/dist',
    manifest: true,
    rollupOptions: {
      input: path.resolve(import.meta.dirname, 'main.tsx'),
      output: {
        // Default splitting produced 40 chunks under 2 KB holding 32 KB
        // between them — 40 HTTP requests for a rounding error of code. The
        // server speaks HTTP/1.1, so the browser opens ~6 connections and
        // those 40 requests cost ~7 serial round trips; at 40 ms latency
        // that is ~280 ms of pure waiting before first paint.
        //
        // Merging anything below this threshold into its importer trades a
        // little duplicated code for far fewer round trips. Keep it well
        // under the size of a real page chunk so route-level code splitting
        // still works and pages stay lazily loaded.
        //
        // Vite 8 bundles with Rolldown, so this is `advancedChunks` rather
        // than Rollup's `experimentalMinChunkSize` (which type-errors here —
        // the option does not exist on Rolldown's OutputOptions). Rolldown
        // ignores minSize unless groups are declared.
        //
        // React is split from the rest of vendor deliberately: it changes only
        // on a dependency bump, so a normal deploy leaves it cached while the
        // app chunks re-download.
        advancedChunks: {
          minSize: MIN_CHUNK_BYTES,
          groups: [
            {
              name: 'react-vendor',
              test: /node_modules\/(react|react-dom|scheduler)\//,
              priority: 100,
            },
            { name: 'vendor', test: /node_modules\//, priority: 50 },
            {
              name: 'ui',
              test: /packages\/ui\/src\//,
              priority: 10,
              minShareCount: 2,
            },
          ],
        },
      },
    },
  },
  server: {
    // smpy dev supplies the same URL to Vite and the API.
    port: devPort,
    strictPort: true,
    origin: devUrl,
  },
}));
