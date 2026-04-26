# Changelog

All notable changes to this project are documented in this file. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project adheres to [Semantic Versioning](https://semver.org/) post-1.0.

## [Unreleased]

## [0.0.1] — 2026-04-21

Initial public release. All 14 Python packages publish to PyPI and all 3 JS packages publish to npm under the `@simple-module-py` scope.

### Python packages (PyPI)

- `simple_module_core`
- `simple_module_db`
- `simple_module_hosting`
- `simple_module_testing`
- `simple_module_auth`
- `simple_module_background_tasks`
- `simple_module_dashboard`
- `simple_module_datasets`
- `simple_module_feature_flags`
- `simple_module_file_storage`
- `simple_module_permissions`
- `simple_module_products`
- `simple_module_settings`
- `simple_module_users`

### npm packages

- `@simple-module-py/ui`
- `@simple-module-py/i18n`
- `@simple-module-py/tsconfig`

### Added

- `sm new <app>` CLI generator (shipped via the `simple-module-cli` PyPI distribution) scaffolding a working app with `users + dashboard + permissions` pre-wired.
- PyPI Trusted Publishing workflow (`.github/workflows/release.yml`) for zero-secret releases.
- npm Trusted Publishing for all three JS packages.

[Unreleased]: https://github.com/antosubash/simple_module_python/compare/v0.0.1...HEAD
[0.0.1]: https://github.com/antosubash/simple_module_python/releases/tag/v0.0.1
