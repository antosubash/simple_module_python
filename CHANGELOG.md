# Changelog

All notable changes to this project are documented in this file. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project adheres to [Semantic Versioning](https://semver.org/) post-1.0.

> **Coverage note.** Between 0.0.1 and 0.0.27 this file carried no per-version
> sections, and several already-released fixes sat under `[Unreleased]` long
> after shipping — which led a downstream app to conclude a fix it depended on
> was still unreleased (GH issue #253). Those entries have been moved to the
> release they actually shipped in, verified with `git tag --contains`.
> Versions not listed below still have no entry; consult the commit log.

## [Unreleased]

### Added
- Every `smpy new` scaffold now ships Docker assets by default: a multi-stage
  `docker/host.Dockerfile` (uv + Node builder that runs `gen-pages` before the
  Vite build, slim non-root runtime that applies migrations on start), a
  `docker-compose.yml` matched to the `--db` choice (`app` on a SQLite named
  volume, or `postgres` + `app` — migration histories are dialect-frozen at
  autogenerate time, so containers run the same DB the migrations were
  generated against), plus `redis`/`worker`/`beat` reusing the app image when
  `background_tasks` is selected, a `.dockerignore`, and `make docker-up` /
  `docker-build` / `docker-down` targets. Previously Docker files only
  appeared with `background_tasks`, and their frontend stage couldn't build
  real apps (no `gen-pages` step). The separate `worker.Dockerfile` is gone;
  worker/beat run the same image with a celery command. `smpy new` also
  generates real `SM_USERS_*_TOKEN_SECRET` values into `.env.example` so the
  production-mode containers pass `UsersSettings` boot validation.

### Fixed
- `smpy gen-pages` now emits module stylesheet `@import` lines as **absolute
  paths** instead of `#module/<pkg>` alias specifiers. The alias only resolved
  if the host's `vite.config.ts` defined a matching `resolve.alias` — but that
  file is scaffold output, written into an app once and then owned and edited
  there, so it is versioned independently of these Python packages. Upgrading
  `simple_module_*` 0.0.26 → 0.0.27 therefore broke `vite build` in every app
  scaffolded earlier, failing with `Can't resolve '#module/<pkg>/styles.css'` —
  naming a specifier that appears nowhere in the app's own sources.

  `modules.generated.css` is now self-contained: it resolves under any
  `vite.config.ts`, with no alias configured at all, exactly as the `@source`
  lines in the same file already did. **No host action is required** — upgrade
  and re-run `gen-pages`. The scaffold template still defines the
  `#module/<pkg>` alias for hand-written imports, but nothing generated depends
  on it any more (GH issue #253).

## [0.0.27] — 2026-08-06

### Known issue
- Fixed in the `[Unreleased]` entry above. `gen-pages` emitted
  `@import "#module/<pkg>/…"` into `modules.generated.css`, which resolves only
  in hosts scaffolded at 0.0.27 or later; apps scaffolded earlier fail
  `vite build` after a Python-only upgrade. Either upgrade past this release,
  or add the alias to `host/client_app/vite.config.ts` by hand — build
  `{ find: '#module/' + package_name, replacement: package }` from each entry
  in `client_app/modules.assets.json` and pass the list as `resolve.alias`
  (GH issue #253).

## [0.0.16] — 2026-05-25

### Fixed
- The `users` module's post-login redirect (`login_redirect_url`) no longer
  hard-codes a `/` fallback when the Dashboard module isn't installed — `/`
  404s on apps without a root route (e.g. `smpy_gis`, `--preset minimal`). It
  now redirects to the first sibling module that exposes view routes, falling
  back to `/` only as an absolute last resort. Operator-set overrides are
  always preserved (GH issue #173).

## [0.0.15] — 2026-05-21

### Fixed
- The `moduleBareImportResolver` Vite plugin no longer short-circuits on
  `fsRoot`/`projectRoot` containment, so workspace-member modules at
  `modules/<name>/<pkg>/pages/` get the same workspace-root re-resolution as
  wheel-installed modules. In an npm-workspaces layout the workspace root *is*
  the resolver root, so the previous early-return excluded the very modules
  that need it. Cross-package bare imports (`maplibre-gl`, `pmtiles`, peer
  deps) now resolve in both wheel and workspace install modes (GH issue #156).
- The framework repo (Vite 8) seeds
  `optimizeDeps.rolldownOptions.resolve.modules` with the workspace
  `node_modules/` as a NODE_PATH-style fallback for the dep scanner
  (GH issue #155).

## [0.0.13] — 2026-05-15

### Fixed
- Vite's dev-mode dependency pre-bundling now resolves cross-package bare
  imports (e.g. `maplibre-gl`, `pmtiles`) from module pages whose importers sit
  outside the host's `client_app/`. The scaffold template (Vite 6) seeds
  `optimizeDeps.esbuildOptions.nodePaths` with the workspace `node_modules/`
  as a NODE_PATH-style fallback for the dep scanner (GH issue #152).

## [0.0.1] — 2026-04-21

Initial public release. All 12 Python packages publish to PyPI and all 3 JS packages publish to npm under the `@simple-module-py` scope.

### Python packages (PyPI)

- `simple_module_core`
- `simple_module_db`
- `simple_module_hosting`
- `simple_module_test`
- `simple_module_auth`
- `simple_module_background_tasks`
- `simple_module_dashboard`
- `simple_module_feature_flags`
- `simple_module_file_storage`
- `simple_module_permissions`
- `simple_module_settings`
- `simple_module_users`

### npm packages

- `@simple-module-py/ui`
- `@simple-module-py/i18n`
- `@simple-module-py/tsconfig`

### Added

- `smpy new <app>` CLI generator (shipped via the `simple_module_cli` PyPI distribution) scaffolding a working app with `users + dashboard + permissions` pre-wired.
- PyPI Trusted Publishing workflow (`.github/workflows/release.yml`) for zero-secret releases.
- npm Trusted Publishing for all three JS packages.

[Unreleased]: https://github.com/antosubash/simple_module_python/compare/v0.0.27...HEAD
[0.0.27]: https://github.com/antosubash/simple_module_python/compare/v0.0.26...v0.0.27
[0.0.16]: https://github.com/antosubash/simple_module_python/compare/v0.0.15...v0.0.16
[0.0.15]: https://github.com/antosubash/simple_module_python/compare/v0.0.14...v0.0.15
[0.0.13]: https://github.com/antosubash/simple_module_python/compare/v0.0.12...v0.0.13
[0.0.1]: https://github.com/antosubash/simple_module_python/releases/tag/v0.0.1
