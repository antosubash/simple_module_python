import fs from 'node:fs';
import path from 'node:path';

// Package managers may hoist the install above client_app, so walk up to find it.
export function findNodeModulesRoot(start: string): string {
  let dir = start;
  while (dir !== path.dirname(dir)) {
    // Vite creates node_modules/.vite even where npm hasn't installed anything.
    if (fs.existsSync(path.join(dir, 'node_modules', 'vite', 'package.json'))) return dir;
    dir = path.dirname(dir);
  }
  return start;
}
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

function readPackageJSON(pkgJsonPath: string, cache: Map<string, Pkg | null>): Pkg | null {
  let pkg = cache.get(pkgJsonPath);
  if (pkg !== undefined) return pkg;
  try {
    pkg = JSON.parse(fs.readFileSync(pkgJsonPath, 'utf-8')) as Pkg;
  } catch {
    pkg = null;
  }
  cache.set(pkgJsonPath, pkg);
  return pkg;
}

function findPackageJSON(name: string, fsRoot: string): string | null {
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

export function collectOptimizeIncludes(
  root: string,
  fsRoot: string,
  modulePkgJsonPaths: string[],
  moduleNpmNames: Set<string>,
): string[] {
  const includes = new Set<string>([
    'react',
    'react-dom',
    'react/jsx-runtime',
    'react/jsx-dev-runtime',
    '@inertiajs/react',
    'react-dom/client',
    'use-sync-external-store',
    'use-sync-external-store/shim',
    'use-sync-external-store/shim/with-selector',
  ]);
  const pkgCache = new Map<string, Pkg | null>();
  const visited = new Set<string>();
  const queue: string[] = [path.join(root, 'package.json'), ...modulePkgJsonPaths];
  while (queue.length > 0) {
    const pkgJsonPath = queue.shift();
    if (!pkgJsonPath || visited.has(pkgJsonPath)) continue;
    visited.add(pkgJsonPath);
    const pkg = readPackageJSON(pkgJsonPath, pkgCache);
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
        const nested = findPackageJSON(name, fsRoot);
        if (!nested) continue;
        const nestedPkg = readPackageJSON(nested, pkgCache);
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
