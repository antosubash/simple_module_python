# Changelog

All notable changes to this project are documented in this file. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project adheres to [Semantic Versioning](https://semver.org/) post-1.0.

## [Unreleased]

### Fixed
- Vite's dev-mode dependency pre-bundling now resolves cross-package bare
  imports (e.g. `maplibre-gl`, `pmtiles`) from module pages whose importers sit
  outside the host's `client_app/` — including wheel-installed modules and
  workspace modules shipping their own JS deps. The scaffold template (Vite 6)
  seeds `optimizeDeps.esbuildOptions.nodePaths` and the framework repo (Vite 8)
  seeds `optimizeDeps.rolldownOptions.resolve.modules` with the workspace
  `node_modules/` as a NODE_PATH-style fallback for the dep scanner (GH issue #152).

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

[Unreleased]: https://github.com/antosubash/simple_module_python/compare/v0.0.1...HEAD
[0.0.1]: https://github.com/antosubash/simple_module_python/releases/tag/v0.0.1
