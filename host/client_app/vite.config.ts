import fs from 'node:fs';
import path from 'node:path';
import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react-swc';
import { visualizer } from 'rollup-plugin-visualizer';
import { defineConfig } from 'vite';
import tsconfigPaths from 'vite-tsconfig-paths';

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
const moduleTsconfigs: string[] = [];
let manifest: Record<string, string> = {};
try {
  manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf-8'));
} catch {
  // Manifest absent (sm gen-pages hasn't run yet) — proceed with empty set.
}
for (const pagesDir of Object.values(manifest)) {
  // Pages live at <moduleRoot>/<pkg>/pages/*.tsx — climb two levels to the
  // module root where its tsconfig.json and package.json live.
  const moduleRoot = path.dirname(path.dirname(pagesDir));
  moduleFsAllow.push(path.dirname(pagesDir));
  try {
    fs.statSync(path.join(moduleRoot, 'tsconfig.json'));
    moduleTsconfigs.push(path.join(moduleRoot, 'tsconfig.json'));
  } catch {
    // Module has no tsconfig (e.g. backend-only) — skip.
  }
}

export default defineConfig({
  // `tsconfigPaths` makes Vite honor each package's tsconfig `paths` at
  // import-resolution time. Each package's `@/*` maps to its own local root,
  // so there's no global `@` alias here — the plugin picks the right tsconfig
  // per importing file.
  plugins: [
    tsconfigPaths({
      projects: [
        path.resolve(__dirname, 'tsconfig.json'),
        path.resolve(projectRoot, 'packages/ui/tsconfig.json'),
        ...moduleTsconfigs,
      ],
    }),
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
