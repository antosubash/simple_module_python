// What the installed Python modules contribute to the frontend build.
//
// Split out of vite.config.ts, which is already at the repo's 300-line cap.
// Everything here is derived from the two files `smpy gen-pages` writes:
// `modules.manifest.json` (name -> absolute pages/ dir) and the richer
// `modules.assets.json`. Both are absent until gen-pages has run, which is a
// normal state — a fresh checkout resolves to an empty index rather than an
// error.
import fs from 'node:fs';
import path from 'node:path';

type ModuleAsset = { package_name: string; package: string; npm_name?: string | null };

export type Alias = { find: string; replacement: string };

export type ModuleAssetIndex = {
  /** Package dirs Vite must be allowed to read outside the workspace root. */
  fsAllow: string[];
  /** Glob per module pages/ dir, for optimizeDeps.entries. */
  optimizeEntries: string[];
  /** Each module's package.json — its deps declare what its pages may import. */
  pkgJsonPaths: string[];
  /** `<pagesDir><sep>` prefixes, for cheaply testing "is this importer a module page?". */
  pagesPrefixes: string[];
  /** `#module/<pkg>` and `<npm_name>` aliases. */
  aliases: Alias[];
  /** npm names owned by modules — these resolve to source, so never pre-bundle them. */
  npmNames: Set<string>;
};

function readJson<T>(file: string, fallback: T): T {
  try {
    return JSON.parse(fs.readFileSync(file, 'utf-8')) as T;
  } catch {
    return fallback;
  }
}

export function loadModuleAssets(clientAppDir: string): ModuleAssetIndex {
  const fsAllow: string[] = [];
  const optimizeEntries: string[] = [];
  const pkgJsonPaths: string[] = [];
  const pagesPrefixes: string[] = [];
  const aliases: Alias[] = [];
  const npmNames = new Set<string>();

  // Each manifest entry points at an absolute pages/ dir — typically inside a
  // pip-installed wheel under .venv/.../site-packages/. Two install modes put
  // package.json in different places: wheels embed it next to the Python
  // package (one level up from pages/, force-included by Hatch), while
  // editable/workspace installs leave it at the source-tree module root (two
  // levels up). We accept either.
  const manifest = readJson<Record<string, string>>(
    path.resolve(clientAppDir, 'modules.manifest.json'),
    {},
  );
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

  // modules.assets.json rather than the manifest: the manifest is keyed off
  // `pages/`, so a module shipping only CSS never appears in it.
  //
  // The `#module/<pkg>` alias is convenience only — `modules.generated.css`
  // imports module stylesheets by absolute path and resolves with no alias
  // configured at all. Emitting an alias there made a generated file depend on
  // this hand-owned config, and since vite.config.ts is scaffolded once and
  // then owned by the app, a Python-only version bump broke every host
  // scaffolded earlier (GH issue #253).
  //
  // The `<npm_name>` alias is load-bearing: it is what lets one module import
  // another's TS/TSX by package name. It aims at the module's *Python package*
  // dir, because a wheel ships `site-packages/foo/**` and nothing above it —
  // the source-tree module root is not a target both layouts have. Both
  // layouts need it: a wheel module is never in node_modules, and npm symlinks
  // a workspace member onto the module root, one level too high.
  // See docs/module-authoring.md § Importing another module's TS/TSX.
  //
  // Both kinds work in CSS as well as JS: `@tailwindcss/vite` builds its CSS
  // import resolver with `createResolver({ ...config.resolve, ... })`, so
  // `resolve.alias` governs `@import` too — verified against 4.2.4.
  const assets = readJson<Record<string, ModuleAsset>>(
    path.resolve(clientAppDir, 'modules.assets.json'),
    {},
  );
  for (const entry of Object.values(assets)) {
    aliases.push({ find: `#module/${entry.package_name}`, replacement: entry.package });
    if (entry.npm_name) {
      aliases.push({ find: entry.npm_name, replacement: entry.package });
      npmNames.add(entry.npm_name);
    }
    if (!fsAllow.includes(entry.package)) fsAllow.push(entry.package);
  }

  // Stable, longest-first. Vite matches a string `find` on exact equality or a
  // `/`-bounded prefix, so `#module/gis` could not swallow `#module/gis_extra`
  // in any order — this is determinism, not a correctness fix.
  aliases.sort((a, b) => b.find.length - a.find.length);

  return { fsAllow, optimizeEntries, pkgJsonPaths, pagesPrefixes, aliases, npmNames };
}
