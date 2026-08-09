import fs from 'node:fs';
import path from 'node:path';
import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import { visualizer } from 'rollup-plugin-visualizer';
import { defineConfig, type Plugin } from 'vite';
import { compressAssets } from './compress-assets.ts';
import { loadModuleAssets } from './module-assets.ts';

const projectRoot = path.resolve(import.meta.dirname, '../..');

// ANALYZE=1 npm run build emits host/static/dist/stats.html — a sunburst of
// every chunk and its constituent modules. Open it to chase bundle bloat.
const analyzeBundle = process.env.ANALYZE === '1';

// Everything the installed modules contribute to this build — fs.allow entries,
// dep-scan globs, package.json paths, and the `#module/<pkg>` + npm-name
// aliases. See ./module-assets.ts for why each exists.
const {
  fsAllow: moduleFsAllow,
  optimizeEntries: moduleOptimizeEntries,
  pkgJsonPaths: modulePkgJsonPaths,
  pagesPrefixes: modulePagesPrefixes,
  aliases: moduleAliases,
  npmNames: moduleNpmNames,
} = loadModuleAssets(import.meta.dirname);

// Gather every bare specifier a module's pages might import. We include
// both `dependencies` (deps the module ships its own copy of) and
// `peerDependencies` (deps the host is expected to provide, e.g.
// `@inertiajs/react`, `@simple-module-py/ui`) so the dep scanner pre-
// bundles all of them. Without pre-bundling, the resolver would have to
// walk from each importer at request time, which is the failure mode
// described in https://github.com/antosubash/simple_module_python/issues/152.
function collectModuleDecls(): string[] {
  const decls = new Set<string>();
  for (const pkgJsonPath of modulePkgJsonPaths) {
    let pkg: { dependencies?: Record<string, string>; peerDependencies?: Record<string, string> };
    try {
      pkg = JSON.parse(fs.readFileSync(pkgJsonPath, 'utf-8'));
    } catch {
      continue;
    }
    for (const block of [pkg.dependencies, pkg.peerDependencies]) {
      for (const dep of Object.keys(block ?? {})) {
        if (dep.startsWith('@types/')) continue;
        // A sibling module declared as a dep/peer dep is not a node_modules
        // package — it is aliased to a source directory above. Pre-bundling
        // it would point the optimizer at raw .tsx with no entry point.
        if (moduleNpmNames.has(dep)) continue;
        decls.add(dep);
      }
    }
  }
  return [...decls];
}

// Cross-package bare imports from module pages (`maplibre-gl`, `pmtiles`,
// `@inertiajs/react`, …) live in the workspace-root node_modules after
// `npm install`. But Vite's resolver walks up from the importer looking
// for node_modules and doesn't always reach <repo>/node_modules — true for
// wheel installs under `.venv/.../site-packages/<pkg>/pages/` (outside the
// project root) AND for workspace-member modules at `modules/<name>/<pkg>/
// pages/` whose upward walk hits intermediate dirs without node_modules
// before reaching the hoisted workspace root. Resolution fails with:
// "Failed to resolve import … Does the file exist?".
//
// This plugin recovers by retrying any unresolved bare import from a
// module-pages importer as if the importer lived at the workspace root,
// which puts <repo>/node_modules back on the resolver's path. Combined
// with `optimizeDeps.include` (declared module deps + peer deps),
// dev/scan/build all converge on the host's hoisted copy.
function moduleBareImportResolver(): Plugin {
  return {
    name: 'simple-module:resolve-module-bare-imports',
    enforce: 'pre',
    async resolveId(source, importer) {
      if (!importer) return null;
      if (
        source.startsWith('.') ||
        source.startsWith('/') ||
        source.startsWith('\0') ||
        source.startsWith('virtual:')
      ) {
        return null;
      }
      const importerPath = importer.split('?')[0];
      if (!modulePagesPrefixes.some((prefix) => importerPath.startsWith(prefix))) {
        return null;
      }
      const resolved = await this.resolve(source, fakeWorkspaceImporter, {
        skipSelf: true,
      });
      return resolved ?? null;
    },
  };
}

const moduleDecls = collectModuleDecls();
const fakeWorkspaceImporter = path.join(projectRoot, 'package.json');

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
    moduleBareImportResolver(),
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
  // Vite 8 resolves tsconfig `paths` natively from this app's tsconfig.json.
  // The only live alias in the repo is `@simple-module-py/ui/*`, which the host
  // tsconfig maps to `../../packages/ui/src/*` — that resolves identically
  // regardless of which file does the importing, so we no longer need to
  // feed Vite the per-module tsconfigs.
  resolve: {
    tsconfigPaths: true,
    // `#module/<pkg>` -> that module's package directory. Optional sugar for
    // hand-written imports; modules.generated.css does not rely on it.
    alias: moduleAliases,
    // Force every importer (host, workspace module, wheel-installed module)
    // to resolve to one React copy — without it, plugin-react's Fast
    // Refresh preamble check fires in a realm where its global was never
    // set ("can't detect preamble").
    dedupe: ['react', 'react-dom', 'react/jsx-runtime', 'react/jsx-dev-runtime'],
  },
  optimizeDeps: {
    entries: ['main.tsx', 'pages/**/*.tsx', ...moduleOptimizeEntries],
    include: [
      'react',
      'react-dom',
      'react-dom/client',
      'react/jsx-runtime',
      'react/jsx-dev-runtime',
      ...moduleDecls,
    ],
    // Add the hoisted workspace node_modules to Rolldown's resolve search
    // so the dev-mode scan resolves bare specifiers from module pages
    // whose importer paths sit outside host/client_app (e.g.
    // `modules/<name>/pages/*.tsx` shipping their own JS deps). Rolldown's
    // default `modules: ['node_modules']` walks upward from the importer,
    // which doesn't always reach the workspace root; adding the absolute
    // path provides a NODE_PATH-style fallback. See GitHub issue #152.
    rolldownOptions: {
      resolve: {
        modules: ['node_modules', path.join(projectRoot, 'node_modules')],
      },
    },
  },
  root: import.meta.dirname,
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
    // If you override SM_VITE_PORT, set the backend's SM_VITE_DEV_URL to the
    // same port — the backend uses it for the dev <script src> and the CSP
    // script-src/connect-src, so a mismatch breaks asset loading + HMR.
    port: Number(process.env.SM_VITE_PORT) || 5050,
    strictPort: true,
    origin: `http://localhost:${Number(process.env.SM_VITE_PORT) || 5050}`,
    fs: {
      allow: [projectRoot, ...moduleFsAllow],
    },
  },
}));
