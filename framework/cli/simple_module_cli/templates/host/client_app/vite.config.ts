import fs from 'node:fs';
import { createRequire } from 'node:module';
import path from 'node:path';
import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import { defineConfig, type Plugin } from 'vite';

// Host project boundary — used by the resolver plugin below to decide
// whether an importer needs re-rooting. Always one level up from
// client_app/, regardless of layout.
const hostRoot = path.resolve(__dirname, '..');

// File-system serve root — the directory that holds `node_modules`. In flat
// mode that's `hostRoot`; in workspace mode npm hoists `node_modules` to the
// workspace root one level higher, so we walk up to find it.
function findNodeModulesRoot(start: string): string {
  let dir = start;
  while (dir !== path.dirname(dir)) {
    if (fs.existsSync(path.join(dir, 'node_modules'))) return dir;
    dir = path.dirname(dir);
  }
  return start;
}
const fsRoot = findNodeModulesRoot(__dirname);

// Load the module pages manifest written by the Python host at boot.
// Each entry points at an absolute pages/ directory — typically inside a
// pip-installed module wheel. Vite needs these in server.fs.allow so the
// dev server can read files outside the host root.
const manifestPath = path.resolve(__dirname, 'modules.manifest.json');
const moduleFsAllow: string[] = [];
if (fs.existsSync(manifestPath)) {
  const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf-8')) as Record<string, string>;
  for (const pagesDir of Object.values(manifest)) {
    moduleFsAllow.push(path.dirname(pagesDir));
  }
}

// Module .tsx files live in `.venv/.../site-packages/<mod>/pages/`. Vite's
// default resolver walks UP from the importing file looking for
// `node_modules/`, but the host's `node_modules/` is in `client_app/` — a
// sibling of the venv, not an ancestor. Bare imports from module pages
// (`@simple-module-py/ui`, `lucide-react`, …) therefore fail with
// "could not be resolved" even though the host has them installed.
//
// This plugin re-roots bare-import resolution at the host's node_modules
// when the importer lives outside the project. It runs `pre` so it beats
// vite's built-in resolver.
const hostRequire = createRequire(path.join(__dirname, 'package.json'));
const resolveCache = new Map<string, string | null>();

function resolveFromHost(): Plugin {
  return {
    name: 'resolve-module-imports-from-host',
    enforce: 'pre',
    resolveId(source, importer) {
      if (!importer) return null;
      if (source.startsWith('.') || source.startsWith('/')) return null;
      if (importer.startsWith(hostRoot + path.sep)) return null;
      let resolved = resolveCache.get(source);
      if (resolved === undefined) {
        try {
          resolved = hostRequire.resolve(source);
        } catch {
          resolved = null;
        }
        resolveCache.set(source, resolved);
      }
      return resolved;
    },
  };
}

export default defineConfig({
  plugins: [resolveFromHost(), react(), tailwindcss()],
  root: __dirname,
  // Force every importer to resolve to one React copy — without it,
  // plugin-react's Fast Refresh preamble check fires in a realm where its
  // global was never set ("can't detect preamble").
  resolve: {
    dedupe: ['react', 'react-dom', 'react/jsx-runtime', 'react/jsx-dev-runtime'],
  },
  // ``use-sync-external-store`` is the CJS shim recharts/react-redux pull
  // in; pre-bundling resolves its named export under ESM.
  optimizeDeps: {
    include: [
      'react',
      'react-dom',
      'react-dom/client',
      'react/jsx-runtime',
      'react/jsx-dev-runtime',
      'use-sync-external-store',
      'use-sync-external-store/shim',
      'use-sync-external-store/shim/with-selector',
    ],
  },
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
      allow: [fsRoot, ...moduleFsAllow],
    },
  },
});
