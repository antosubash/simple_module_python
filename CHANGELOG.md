# Changelog

All notable changes to this project are documented in this file. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project adheres to [Semantic Versioning](https://semver.org/) post-1.0.

## [Unreleased]

## [0.0.1] — 2026-04-21

Initial public release. All 14 Python packages publish to PyPI and all 3 JS packages publish to npm under the `@simple-module-py` scope.

### Python packages (PyPI)

- `simple-module-core`
- `simple-module-db`
- `simple-module-hosting`
- `simple-module-testing`
- `simple-module-auth`
- `simple-module-background-tasks`
- `simple-module-dashboard`
- `simple-module-datasets`
- `simple-module-feature-flags`
- `simple-module-file-storage`
- `simple-module-permissions`
- `simple-module-products`
- `simple-module-settings`
- `simple-module-users`

### npm packages

- `@simple-module-py/ui`
- `@simple-module-py/i18n`
- `@simple-module-py/tsconfig`

### Added

- `simple-module new <app>` / `sm new <app>` CLI generator scaffolding a working app with `users + dashboard + permissions` pre-wired.
- PyPI Trusted Publishing workflow (`.github/workflows/release.yml`) for zero-secret releases.
- npm Trusted Publishing for all three JS packages.

[Unreleased]: https://github.com/antosubash/simple_module_python/compare/v0.0.1...HEAD
[0.0.1]: https://github.com/antosubash/simple_module_python/releases/tag/v0.0.1
