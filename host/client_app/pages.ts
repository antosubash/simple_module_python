/**
 * Auto-discover all module pages via Vite's import.meta.glob.
 *
 * Convention: modules/{name}/src/sm_{name}/pages/{PageName}.tsx
 * Inertia component name: "{ModuleName}/{PageName}"
 *
 * Vite code-splits each page into its own chunk automatically.
 * HMR works instantly — just edit any .tsx file.
 */

type PageModule = { default: React.ComponentType<Record<string, unknown>> };
type PageLoader = () => Promise<PageModule>;

const pageModules = import.meta.glob<PageModule>('../../modules/*/src/*/pages/*.tsx');

const pages: Record<string, PageLoader> = {};

for (const [filePath, loader] of Object.entries(pageModules)) {
  // Extract module name and page name from file path
  // e.g., "../../modules/products/src/sm_products/pages/Browse.tsx"
  //   -> moduleName = "Products", pageName = "Browse"
  const match = filePath.match(/modules\/(\w+)\/src\/\w+\/pages\/(\w+)\.tsx$/);
  if (match) {
    const moduleName = match[1].charAt(0).toUpperCase() + match[1].slice(1);
    const pageName = match[2];
    pages[`${moduleName}/${pageName}`] = loader;
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
