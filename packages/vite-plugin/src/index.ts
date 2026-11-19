import path from 'node:path';
import type { Plugin } from 'vite';
import { collectOptimizeIncludes, findNodeModulesRoot } from './dependencies.js';
import { i18nGenerated } from './i18n.js';
import { loadModuleAssets } from './module-assets.js';

export { findNodeModulesRoot } from './dependencies.js';
export { i18nGenerated } from './i18n.js';
export type { Alias, ModuleAssetIndex } from './module-assets.js';
export { loadModuleAssets } from './module-assets.js';

/** Shared module integration. The root is the app's client_app directory. */
export function simpleModule({ root }: { root: string }): Plugin[] {
  const fsRoot = findNodeModulesRoot(root);
  const assets = loadModuleAssets(root);
  return [
    i18nGenerated(),
    moduleBareImportResolver(assets.pagesPrefixes, path.join(fsRoot, 'package.json')),
    {
      name: 'simple-module:assets',
      config() {
        return {
          resolve: {
            tsconfigPaths: true,
            alias: assets.aliases,
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
            entries: ['main.tsx', 'pages/**/*.tsx', ...assets.optimizeEntries],
            include: collectOptimizeIncludes(root, fsRoot, assets.pkgJsonPaths, assets.npmNames),
            rolldownOptions: {
              resolve: { modules: ['node_modules', path.join(fsRoot, 'node_modules')] },
            },
          },
          server: { fs: { allow: [fsRoot, ...assets.fsAllow] } },
        };
      },
    },
  ];
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
function moduleBareImportResolver(
  modulePagesPrefixes: string[],
  fakeWorkspaceImporter: string,
): Plugin {
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
