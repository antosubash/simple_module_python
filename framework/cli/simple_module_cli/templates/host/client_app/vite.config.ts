import fs from 'node:fs';
import path from 'node:path';
import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import { type Plugin, defineConfig } from 'vite';
import { viteDevServer } from './vite.dev-url';

// Force every importer (host, workspace module, wheel-installed module)
// to resolve to one React copy + a single Inertia hook context. Without
// dedupe, plugin-react fires "can't detect preamble" and `usePage` from
// a wheel-loaded page lands in a different React realm than the host's.
const REACT_CORE_DEPS = [
  'react',
  'react-dom',
  'react/jsx-runtime',
  'react/jsx-dev-runtime',
  '@inertiajs/react',
] as const;

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

// Walks up from client_app to the directory holding the project .env itself —
// fsRoot tracks node_modules, which (in flat mode) is NOT where .env lives.
const { origin: devUrl, port: devPort } = viteDevServer(__dirname);

// Load the module pages manifest written by the Python host at boot.
// Each entry points at an absolute pages/ directory — typically inside a
// pip-installed module wheel. Vite needs these in server.fs.allow so the
// dev server can read files outside the host root, and in
// optimizeDeps.entries so its dependency scanner discovers bare imports
// from wheel-installed pages and pre-bundles them.
//
// We also collect each module's package.json — wheels embed it next to
// the Python package (one level up from pages/, force-included by Hatch),
// while editable/workspace installs leave it at the source-tree module
// root (two levels up). We accept either. The dep walk in
// `collectOptimizeIncludes` uses it to reach packages a module's pages
// import directly (`sonner`, `lucide-react`, `maplibre-gl`, …). Without
// this seed, Vite's pre-bundler never sees those bare specifiers and Node
// module resolution walks up from inside .venv/site-packages — never
// reaching host/client_app/node_modules.
const manifestPath = path.resolve(__dirname, 'modules.manifest.json');
const moduleFsAllow: string[] = [];
const moduleOptimizeEntries: string[] = [];
const modulePkgJsonPaths: string[] = [];
const modulePagesPrefixes: string[] = [];
if (fs.existsSync(manifestPath)) {
  const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf-8')) as Record<string, string>;
  for (const pagesDir of Object.values(manifest)) {
    const pkgDir = path.dirname(pagesDir);
    moduleFsAllow.push(pkgDir);
    moduleOptimizeEntries.push(path.join(pagesDir, '**/*.tsx'));
    modulePagesPrefixes.push(pagesDir + path.sep);
    for (const candidate of [
      path.join(pkgDir, 'package.json'),
      path.join(path.dirname(pkgDir), 'package.json'),
    ]) {
      if (fs.existsSync(candidate)) {
        modulePkgJsonPaths.push(candidate);
        break;
      }
    }
  }
}

// Three things come out of modules.assets.json.
//
// 1. `server.fs.allow` entries. The dev server must be allowed to read each
//    module's package dir. Read from modules.assets.json rather than
//    modules.manifest.json because the manifest is keyed off `pages/`, so a
//    module shipping only CSS never appears in it.
//
// 2. A convenience `#module/<pkg>` alias. This is NOT required by
//    `modules.generated.css` — that file imports module stylesheets by
//    absolute path, so it resolves with no alias configured at all. Emitting
//    an alias there made a generated file depend on this hand-owned config,
//    and since `vite.config.ts` is scaffolded once and then owned by the app,
//    a Python-only version bump broke every host scaffolded earlier
//    (GH issue #253). The alias stays because it costs nothing.
//
// 3. An `<npm_name>` alias per module, so one module can import another's
//    TS/TSX by package name. Aimed at the module's *Python package* dir —
//    a wheel ships `site-packages/foo/**` and nothing above it, so the
//    source-tree module root is not a target both layouts have. Needed in
//    both: a wheel module is never in node_modules, and npm symlinks a
//    workspace member onto the module root, one level too high.
//    See docs/module-authoring.md § Importing another module's TS/TSX.
//
// `@tailwindcss/vite` builds its CSS import resolver with
// `createResolver({ ...config.resolve, ... })`, so `resolve.alias` governs
// CSS `@import` as well as JS — verified against @tailwindcss/vite 4.2.4.
type ModuleAsset = { package_name: string; package: string; npm_name?: string | null };
const moduleAliases: { find: string; replacement: string }[] = [];
const moduleNpmNames = new Set<string>();
const assetsPath = path.resolve(__dirname, 'modules.assets.json');
let moduleAssets: Record<string, ModuleAsset> = {};
try {
  moduleAssets = JSON.parse(fs.readFileSync(assetsPath, 'utf-8'));
} catch {
  // Absent until `smpy gen-pages` runs — proceed with no aliases.
}
for (const entry of Object.values(moduleAssets)) {
  moduleAliases.push({ find: `#module/${entry.package_name}`, replacement: entry.package });
  if (entry.npm_name) {
    moduleAliases.push({ find: entry.npm_name, replacement: entry.package });
    moduleNpmNames.add(entry.npm_name);
  }
  if (!moduleFsAllow.includes(entry.package)) moduleFsAllow.push(entry.package);
}
// Keep the alias list in a stable, longest-first order. Vite matches a string
// `find` on exact equality or a `/`-bounded prefix, so `#module/gis` could not
// swallow `#module/gis_extra` in any order — this is just determinism, not a
// correctness fix.
moduleAliases.sort((a, b) => b.find.length - a.find.length);
const fakeWorkspaceImporter = path.join(fsRoot, 'package.json');

// CJS-only deps like `clsx`, `tailwind-merge`, `class-variance-authority`
// expose named exports only after esbuild's CJS→ESM transform. Vite's
// optimizer would normally pre-bundle them on first import, but the
// scanner sometimes misses bare imports inside wheel-installed pages
// because their importer paths sit outside the project root. Walking
// host/client_app/package.json + every dep's package.json one level
// deep and force-including the result keeps the named-import contract
// for everything pulled in transitively by `@simple-module-py/ui` etc.
type Pkg = {
  main?: string;
  module?: string;
  exports?: unknown;
  dependencies?: Record<string, string>;
  peerDependencies?: Record<string, string>;
};

const pkgCache = new Map<string, Pkg | null>();

function readPackageJSON(pkgJsonPath: string): Pkg | null {
  let pkg = pkgCache.get(pkgJsonPath);
  if (pkg !== undefined) return pkg;
  try {
    pkg = JSON.parse(fs.readFileSync(pkgJsonPath, 'utf-8')) as Pkg;
  } catch {
    pkg = null;
  }
  pkgCache.set(pkgJsonPath, pkg);
  return pkg;
}

function findPackageJSON(name: string): string | null {
  // npm hoists into `fsRoot/node_modules`; that's the only location worth
  // checking in workspace + flat layouts alike.
  const candidate = path.join(fsRoot, 'node_modules', name, 'package.json');
  return fs.existsSync(candidate) ? candidate : null;
}

function hasTopLevelEntry(pkg: Pkg): boolean {
  if (pkg.main || pkg.module) return true;
  const exp = pkg.exports;
  if (typeof exp === 'string') return true;
  if (exp && typeof exp === 'object') return '.' in exp;
  return false;
}

function collectOptimizeIncludes(): string[] {
  const includes = new Set<string>([
    ...REACT_CORE_DEPS,
    'react-dom/client',
    'use-sync-external-store',
    'use-sync-external-store/shim',
    'use-sync-external-store/shim/with-selector',
  ]);
  const visited = new Set<string>();
  const queue: string[] = [path.join(__dirname, 'package.json'), ...modulePkgJsonPaths];
  while (queue.length > 0) {
    const pkgJsonPath = queue.shift();
    if (!pkgJsonPath || visited.has(pkgJsonPath)) continue;
    visited.add(pkgJsonPath);
    const pkg = readPackageJSON(pkgJsonPath);
    if (!pkg) continue;
    // Walk both `dependencies` and `peerDependencies`: a module's pages
    // routinely import host-provided peer deps (`@inertiajs/react`,
    // `@simple-module-py/ui`, …) as bare specifiers and we need those
    // pre-bundled too, not just the deps the module ships its own copy of.
    for (const block of [pkg.dependencies, pkg.peerDependencies]) {
      for (const name of Object.keys(block ?? {})) {
        if (name.startsWith('@types/')) continue;
        // A sibling module declared as a dep/peer dep is not a node_modules
        // package — it is aliased to a source directory above. Pre-bundling
        // it would point the optimizer at raw .tsx with no entry point.
        if (moduleNpmNames.has(name)) continue;
        const nested = findPackageJSON(name);
        if (!nested) continue;
        const nestedPkg = readPackageJSON(nested);
        if (!nestedPkg) continue;
        // Skip packages that ship only sub-paths (`@babel/runtime`); vite
        // refuses to pre-bundle them and bare imports against them resolve
        // naturally through Node's normal module-walk anyway.
        if (hasTopLevelEntry(nestedPkg)) {
          includes.add(name);
        }
        queue.push(nested);
      }
    }
  }
  return [...includes];
}

// Cross-package bare imports from module pages (`maplibre-gl`, `pmtiles`,
// `@inertiajs/react`, …) live in fsRoot/node_modules after `npm install`.
// But Vite's resolver walks up from the importer looking for node_modules
// and doesn't always reach fsRoot/node_modules — true for wheel installs
// under `.venv/.../site-packages/<pkg>/pages/` (outside fsRoot) AND for
// workspace-member modules at `modules/<name>/<pkg>/pages/` whose upward
// walk hits intermediate dirs without node_modules before reaching the
// hoisted workspace root. Resolution fails with: "Failed to resolve import
// … Does the file exist?".
//
// This plugin recovers by retrying any unresolved bare import from a
// module-pages importer as if the importer lived at fsRoot, which puts
// fsRoot/node_modules back on the resolver's path. Combined with the
// `optimizeDeps.include` walk above (module deps + peer deps), dev,
// dep-scan, and production builds all converge on the host's hoisted copy.
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

export default defineConfig({
  plugins: [moduleBareImportResolver(), react(), tailwindcss()],
  root: __dirname,
  resolve: {
    // `#module/<pkg>` -> that module's package directory. Optional sugar for
    // hand-written imports; modules.generated.css does not rely on it.
    alias: moduleAliases,
    dedupe: [...REACT_CORE_DEPS, '@simple-module-py/ui', '@simple-module-py/i18n'],
  },
  optimizeDeps: {
    entries: ['main.tsx', 'pages/**/*.tsx', ...moduleOptimizeEntries],
    include: collectOptimizeIncludes(),
    // Vite's dep scanner runs esbuild against every entry above. When the
    // entry sits outside the workspace (a wheel-installed module's
    // pages/, or sometimes even a workspace module's pages/), esbuild's
    // upward node_modules walk from the importer does not always reach
    // the hoisted node_modules at fsRoot. Seeding it as NODE_PATH-style
    // fallback ensures bare specifiers like `maplibre-gl` resolve during
    // scan-imports. See GitHub issue #152.
    esbuildOptions: {
      nodePaths: [path.join(fsRoot, 'node_modules')],
    },
  },
  build: {
    outDir: '../static/dist',
    manifest: true,
    rollupOptions: {
      input: path.resolve(__dirname, 'main.tsx'),
    },
  },
  server: {
    port: devPort,
    strictPort: true,
    origin: devUrl,
    fs: {
      allow: [fsRoot, ...moduleFsAllow],
    },
  },
});
