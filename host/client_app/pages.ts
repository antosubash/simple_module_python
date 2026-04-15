/**
 * Inertia page resolver.
 *
 * Module pages are discovered via a generated file (modules.generated.ts)
 * emitted by the Python host at boot. Each installed module contributes an
 * import.meta.glob() call with an absolute path, so pages shipped inside
 * pip-installed module wheels resolve correctly.
 *
 * Host-level pages live in host/client_app/pages/{PageName}.tsx and are
 * registered under just "{PageName}" (e.g. "Error").
 *
 * Vite code-splits each page into its own chunk; HMR edits land instantly.
 */

import { moduleGlobs } from './modules.generated';

type PageModule = { default: React.ComponentType<Record<string, unknown>> };
type PageLoader = () => Promise<PageModule>;

const hostPages = import.meta.glob<PageModule>('./pages/*.tsx');

const pages: Record<string, PageLoader> = {};

for (const [moduleName, globEntries] of Object.entries(moduleGlobs)) {
  for (const [filePath, loader] of Object.entries(globEntries)) {
    // e.g., "/.../products/pages/Browse.tsx" -> pageName = "Browse"
    const match = filePath.match(/\/pages\/(.+)\.tsx$/);
    if (match) {
      pages[`${moduleName}/${match[1]}`] = loader;
    }
  }
}

for (const [filePath, loader] of Object.entries(hostPages)) {
  // e.g., "./pages/Error.tsx" -> "Error"
  const match = filePath.match(/\.\/pages\/(\w+)\.tsx$/);
  if (match) {
    pages[match[1]] = loader;
  }
}

export async function resolvePage(
  name: string,
): Promise<React.ComponentType<Record<string, unknown>>> {
  const loader = pages[name];
  if (!loader) {
    throw new Error(`Page "${name}" not found. Available pages: ${Object.keys(pages).join(', ')}`);
  }
  const module = await loader();
  return module.default;
}
