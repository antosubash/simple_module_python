import fs from 'node:fs';
import path from 'node:path';
import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import { visualizer } from 'rollup-plugin-visualizer';
import { defineConfig } from 'vite';

const projectRoot = path.resolve(__dirname, '../..');

// ANALYZE=1 npm run build emits host/static/dist/stats.html — a sunburst of
// every chunk and its constituent modules. Open it to chase bundle bloat.
const analyzeBundle = process.env.ANALYZE === '1';

// Load the module pages manifest written by the Python host at boot.
// Each entry points at an absolute pages/ directory — typically inside a
// pip-installed module wheel. Vite needs these in server.fs.allow so the
// dev server can read files outside the workspace root.
const manifestPath = path.resolve(__dirname, 'modules.manifest.json');
const moduleFsAllow: string[] = [];
let manifest: Record<string, string> = {};
try {
  manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf-8'));
} catch {
  // Manifest absent (smpy gen-pages hasn't run yet) — proceed with empty set.
}
for (const pagesDir of Object.values(manifest)) {
  moduleFsAllow.push(path.dirname(pagesDir));
}

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    ...(analyzeBundle
      ? [
          visualizer({
            filename: path.resolve(__dirname, '../static/dist/stats.html'),
            template: 'sunburst',
            gzipSize: true,
            brotliSize: true,
          }),
        ]
      : []),
  ],
  // Vite 8 resolves tsconfig `paths` natively from this app's tsconfig.json.
  // The only live alias in the repo is `@simple-module-py/ui/*`, which the host
  // tsconfig maps to `../../packages/ui/src/*` — that resolves identically
  // regardless of which file does the importing, so we no longer need to
  // feed Vite the per-module tsconfigs.
  resolve: {
    tsconfigPaths: true,
    // Force every importer (host, workspace module, wheel-installed module)
    // to resolve to one React copy — without it, plugin-react's Fast
    // Refresh preamble check fires in a realm where its global was never
    // set ("can't detect preamble").
    dedupe: ['react', 'react-dom', 'react/jsx-runtime', 'react/jsx-dev-runtime'],
  },
  optimizeDeps: {
    include: [
      'react',
      'react-dom',
      'react-dom/client',
      'react/jsx-runtime',
      'react/jsx-dev-runtime',
    ],
    // Seed NODE_PATH-style fallback so esbuild's scan-imports resolves
    // bare specifiers from module pages whose importer paths sit outside
    // host/client_app (e.g. `modules/<name>/pages/*.tsx` shipping their
    // own JS deps that live in the hoisted workspace node_modules).
    // See GitHub issue #152.
    esbuildOptions: {
      nodePaths: [path.join(projectRoot, 'node_modules')],
    },
  },
  root: __dirname,
  build: {
    outDir: '../static/dist',
    manifest: true,
    rollupOptions: {
      input: path.resolve(__dirname, 'main.tsx'),
    },
  },
  server: {
    port: 5050,
    strictPort: true,
    origin: 'http://localhost:5050',
    fs: {
      allow: [projectRoot, ...moduleFsAllow],
    },
  },
});
