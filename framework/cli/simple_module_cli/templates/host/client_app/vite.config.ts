import fs from 'node:fs';
import path from 'node:path';
import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

// File-system serve root — the directory that holds `node_modules`. In flat
// mode that's the host root; in workspace mode npm hoists `node_modules` to
// the workspace root one level higher, so we walk up to find it.
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
// dev server can read files outside the host root, and in
// optimizeDeps.entries so its dependency scanner discovers bare imports
// from wheel-installed pages and pre-bundles them.
const manifestPath = path.resolve(__dirname, 'modules.manifest.json');
const moduleFsAllow: string[] = [];
const moduleOptimizeEntries: string[] = [];
if (fs.existsSync(manifestPath)) {
  const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf-8')) as Record<string, string>;
  for (const pagesDir of Object.values(manifest)) {
    moduleFsAllow.push(path.dirname(pagesDir));
    moduleOptimizeEntries.push(path.join(pagesDir, '**/*.tsx'));
  }
}

// CJS-only deps like `clsx`, `tailwind-merge`, `class-variance-authority`
// expose named exports only after esbuild's CJS→ESM transform. Vite's
// optimizer would normally pre-bundle them on first import, but the
// scanner sometimes misses bare imports inside wheel-installed pages
// because their importer paths sit outside the project root. Walking
// host/client_app/package.json + every dep's package.json one level
// deep and force-including the result keeps the named-import contract
// for everything pulled in transitively by `@simple-module-py/ui` etc.
function findPackageJSON(name: string): string | null {
  let dir = __dirname;
  while (true) {
    const candidate = path.join(dir, 'node_modules', name, 'package.json');
    if (fs.existsSync(candidate)) return candidate;
    const parent = path.dirname(dir);
    if (parent === dir) return null;
    dir = parent;
  }
}

function hasTopLevelEntry(pkgJsonPath: string): boolean {
  let pkg: { main?: string; module?: string; exports?: unknown };
  try {
    pkg = JSON.parse(fs.readFileSync(pkgJsonPath, 'utf-8'));
  } catch {
    return false;
  }
  if (pkg.main || pkg.module) return true;
  const exp = pkg.exports;
  if (typeof exp === 'string') return true;
  if (exp && typeof exp === 'object') return '.' in exp;
  return false;
}

function collectOptimizeIncludes(): string[] {
  const seeded = [
    'react',
    'react-dom',
    'react-dom/client',
    'react/jsx-runtime',
    'react/jsx-dev-runtime',
    '@inertiajs/react',
    'use-sync-external-store',
    'use-sync-external-store/shim',
    'use-sync-external-store/shim/with-selector',
  ];
  const includes = new Set<string>(seeded);
  const visited = new Set<string>();
  const queue: string[] = [path.join(__dirname, 'package.json')];
  while (queue.length > 0) {
    const pkgJsonPath = queue.shift();
    if (!pkgJsonPath || visited.has(pkgJsonPath)) continue;
    visited.add(pkgJsonPath);
    let pkg: { dependencies?: Record<string, string> };
    try {
      pkg = JSON.parse(fs.readFileSync(pkgJsonPath, 'utf-8'));
    } catch {
      continue;
    }
    for (const name of Object.keys(pkg.dependencies ?? {})) {
      if (name.startsWith('@types/')) continue;
      const nested = findPackageJSON(name);
      if (!nested) continue;
      // Skip packages that ship only sub-paths (`@babel/runtime`); vite
      // refuses to pre-bundle them and bare imports against them resolve
      // naturally through Node's normal module-walk anyway.
      if (hasTopLevelEntry(nested)) {
        includes.add(name);
      }
      queue.push(nested);
    }
  }
  return [...includes];
}

export default defineConfig({
  plugins: [react(), tailwindcss()],
  root: __dirname,
  // Force every importer (host pages, workspace modules, wheel-installed
  // modules) to resolve to one React copy. Without this, plugin-react's
  // Fast Refresh preamble check fires in a realm where its global was
  // never set ("can't detect preamble").
  resolve: {
    dedupe: [
      'react',
      'react-dom',
      'react/jsx-runtime',
      'react/jsx-dev-runtime',
      '@inertiajs/react',
      '@simple-module-py/ui',
      '@simple-module-py/i18n',
    ],
  },
  optimizeDeps: {
    entries: ['main.tsx', 'pages/**/*.tsx', ...moduleOptimizeEntries],
    include: collectOptimizeIncludes(),
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
