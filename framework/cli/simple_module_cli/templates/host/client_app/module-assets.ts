// What the installed Python modules contribute to the frontend build.
//
// Split out of vite.config.ts to keep each file under the 300-line cap and to
// give this one job a name. Everything here is derived from the two files
// `smpy gen-pages` writes: `modules.manifest.json` (name -> absolute pages/
// dir) and the richer `modules.assets.json`. Both are absent until gen-pages
// has run, which is a normal state — a fresh checkout resolves to empty.
import fs from 'node:fs';
import path from 'node:path';

export type Alias = { find: string; replacement: string };

export type ModuleAssetIndex = {
  fsAllow: string[];
  optimizeEntries: string[];
  pkgJsonPaths: string[];
  /** `<dir><sep>` prefixes for module-owned TSX (pages/ and components/). */
  pagesPrefixes: string[];
  aliases: Alias[];
  npmNames: Set<string>;
};

export function loadModuleAssets(clientAppDir: string): ModuleAssetIndex {
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
  const manifestPath = path.resolve(clientAppDir, 'modules.manifest.json');
  const fsAllow: string[] = [];
  const optimizeEntries: string[] = [];
  const pkgJsonPaths: string[] = [];
  const pagesPrefixes: string[] = [];
  if (fs.existsSync(manifestPath)) {
    const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf-8')) as Record<string, string>;
    for (const pagesDir of Object.values(manifest)) {
      const pkgDir = path.dirname(pagesDir);
      fsAllow.push(pkgDir);
      optimizeEntries.push(path.join(pagesDir, '**/*.tsx'));
      pagesPrefixes.push(pagesDir + path.sep);
      for (const candidate of [
        path.join(pkgDir, 'package.json'),
        path.join(path.dirname(pkgDir), 'package.json'),
      ]) {
        if (fs.existsSync(candidate)) {
          pkgJsonPaths.push(candidate);
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
  type ModuleAsset = {
    package_name: string;
    package: string;
    npm_name?: string | null;
    // Wheel modules ship widgets here; the pages-keyed manifest never sees them.
    components?: string | null;
  };
  const aliases: { find: string; replacement: string }[] = [];
  const npmNames = new Set<string>();
  const assetsPath = path.resolve(clientAppDir, 'modules.assets.json');
  let assets: Record<string, ModuleAsset> = {};
  try {
    assets = JSON.parse(fs.readFileSync(assetsPath, 'utf-8'));
  } catch {
    // Absent until `smpy gen-pages` runs — proceed with no aliases.
  }
  for (const entry of Object.values(assets)) {
    aliases.push({ find: `#module/${entry.package_name}`, replacement: entry.package });
    if (entry.npm_name) {
      aliases.push({ find: entry.npm_name, replacement: entry.package });
      npmNames.add(entry.npm_name);
    }
    if (!fsAllow.includes(entry.package)) fsAllow.push(entry.package);
    // Without this the bare-specifier fallback below skips widgets, and a
    // component's `@simple-module-py/ui` import fails to resolve.
    if (entry.components) {
      const prefix = entry.components + path.sep;
      if (!pagesPrefixes.includes(prefix)) pagesPrefixes.push(prefix);
      optimizeEntries.push(path.join(entry.components, '**/*.tsx'));
    }
  }
  // Keep the alias list in a stable, longest-first order. Vite matches a string
  // `find` on exact equality or a `/`-bounded prefix, so `#module/gis` could not
  // swallow `#module/gis_extra` in any order — this is just determinism, not a
  // correctness fix.
  aliases.sort((a, b) => b.find.length - a.find.length);
  return { fsAllow, optimizeEntries, pkgJsonPaths, pagesPrefixes, aliases, npmNames };
}
