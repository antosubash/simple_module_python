# Framework Package Layout Implementation Plan

> Reference spec: [`docs/superpowers/specs/2026-11-22-framework-layout-design.md`](../specs/2026-11-22-framework-layout-design.md)

Sequential 7-PR stack (moves and import rewrites only; zero behavioral changes). Each PR branches from its shipped predecessor, verifies fresh-interpreter imports + full `/ship --skip-browser`, and remains open for review.

---

### Task 0 (PR 0): Spec, Ratchet & Expiry Scan (`feat/framework-layout-spec` → `main`)
- **Worktree:** `/home/anto/Repos/smpy-fw0-layout-spec`
- **Files:**
  - `docs/superpowers/specs/2026-11-22-framework-layout-design.md`
  - `docs/superpowers/plans/2026-11-22-framework-layout.md`
  - `docs/framework-layout.md`
  - `docs/.vitepress/config.ts`
  - `AGENTS.md`
  - `framework/testing/simple_module_test/layout.py` (shared AST shim recognizer + `is_shim_package` / `is_docstring_only_init` / `only_bytecode`)
  - `framework/testing/tests/test_testing_module_layout.py` (boundary tests for shared layout/shim helpers)
  - `host/tests/test_framework_layout.py` (starts with `LEGACY_FLAT = {"inertia", "cli", "core", "db", "hosting", "testing"}` + `tmp_path` rule self-tests)
  - `host/tests/test_deprecation_expiry.py` (scan both `modules/` and `framework/` for `_layout_shims()`)
- **Done check:** `uv run ruff format docs/` + `/ship --skip-browser` (`make gen && make lint && PYTEST_WORKERS=4 make test-py && CHOKIDAR_USEPOLLING=1 make test-js && make ci-docs-build && make ci-doctor`) + remote GitHub CI green (`shipped` + `/ship passed on <sha>`).

### Task 1 (PR 1): `framework/inertia` (`refactor/framework-inertia-layout` → `feat/framework-layout-spec`)
- **Worktree:** `/home/anto/Repos/smpy-fw1-inertia`
- **Moves:** `simple_module_inertia/{protocol,rendering,assets}/` (`16` source files -> subpackages, keeping `__init__.py` + `py.typed` at root; `response.py` zero-dependency `DeprecationWarning` + `sys.modules` alias shim registered via `deprecate("simple_module_inertia.response", remove_in="0.0.52", use="simple_module_inertia.protocol.response")` in `_register_all()` of `host/tests/test_deprecation_expiry.py`).
- **Tests & Docs:** Move all `23` tests under `framework/inertia/tests/` into `tests/{protocol,rendering,assets}/`; rewrite all in-repo imports/mocks and backticked doc paths; drop `"inertia"` from `LEGACY_FLAT`; mark `inertia` migrated in `docs/framework-layout.md`.
- **Done check:** Fresh-interpreter imports across all moved modules + shim, `/ship --skip-browser --no-rebase` incl. `make ci-build-packages`, `shipped` + `/ship passed on <sha>`.

### Task 2 (PR 2): `framework/cli` (`refactor/framework-cli-layout` → `refactor/framework-inertia-layout`)
- **Worktree:** `/home/anto/Repos/smpy-fw2-cli`
- **Moves:** `simple_module_cli/{commands,scaffold,sources,updates,tooling,migrations}/` (`44` files moved; keep `cli.py`, `migration_recipes/`, `templates/`, `skills` at root; zero `core` dep).
- **Tests & Docs:** Update `Makefile` (`test_module_css_build.py` path), `test_no_framework_deps.py`, `test_build_packaging.py`; move all `83` tests into matching `tests/<area>/`; update doc paths; drop `"cli"` from `LEGACY_FLAT`; update `docs/framework-layout.md`.
- **Done check:** Fresh-interpreter imports, `/ship --skip-browser --no-rebase` incl. `make ci-css-build` & `make ci-build-packages`, `shipped` + `/ship passed on <sha>`.

### Task 3 (PR 3): `framework/core` (`refactor/framework-core-layout` → `refactor/framework-cli-layout`)
- **Worktree:** `/home/anto/Repos/smpy-fw3-core`
- **Moves:** `simple_module_core/{modules,access,eventing,settings,web,localization,mailer,runtime,diagnostics,migrations}/` (keep `tenant_events.py`, `user_events.py`, `__main__.py` at root for outbox wire names; keep `diagnostics/__init__.py` facade; replace `migration_support/` with `migrations/support.py` + `migration_support/__init__.py` shim).
- **Shims & Tests:** Add `remove_in="0.0.52"` `deprecated_module` alias shims for externally imported paths; update `test_deprecation_expiry.py` `_auth_providers` path & `test_no_framework_deps.py` parity path; move all `79` tests into `tests/<area>/`; drop `"core"` from `LEGACY_FLAT`; update `docs/framework-layout.md`.
- **Done check:** Fresh-interpreter imports, `test_durable_wire_names.py`, `test_deprecation_expiry.py`, `/ship --skip-browser --no-rebase` incl. `make ci-build-packages`.

### Task 4 (PR 4): `framework/db` (`refactor/framework-db-layout` → `refactor/framework-core-layout`)
- **Worktree:** `/home/anto/Repos/smpy-fw4-db`
- **Moves:** `simple_module_db/{engine,models,scoping,auditing,schema,queries}/` (`tenant_cleanup` explicitly passes `name="simple_module_db.tenant_cleanup.delete_tenant_settings"` on `subscribe_durable`).
- **Shims & Tests:** Add `remove_in="0.0.52"` alias shims for externally imported paths; keep `tests/` root `conftest.py` and shared `_*_models.py`/`_*_support.py`; move all `78` tests into `tests/<area>/`; drop `"db"` from `LEGACY_FLAT`; update `docs/framework-layout.md`.
- **Done check:** Fresh-interpreter imports, `test_durable_wire_names.py`, `/ship --skip-browser --no-rebase` incl. `make ci-build-packages`.

### Task 5 (PR 5): `framework/hosting` (`refactor/framework-hosting-layout` → `refactor/framework-db-layout`)
- **Worktree:** `/home/anto/Repos/smpy-fw5-hosting`
- **Moves:** `simple_module_hosting/{boot,config,pipeline,rate_limit,auth,error_handling,frontend,i18n,observability,locking}/` (keep `host_cli.py`, `__main__.py`, `admin_overview/`, `setup_wizard/`, `locales/`, `ui_locales/` at root).
- **Shims & Tests:** Add `remove_in="0.0.52"` alias shims for externally imported paths (including `_error_handlers`, `_preapp_config`, `_secret_key`, `_csp_dynamic`, `_body_limit`); move all `177` tests into `tests/<area>/` + `tests/{admin_overview,setup_wizard}/` keeping root helpers & `tests-js/`; drop `"hosting"` from `LEGACY_FLAT`; update `docs/framework-layout.md`.
- **Done check:** Fresh-interpreter imports, `/ship --skip-browser --no-rebase` incl. `make ci-css-build` & `make ci-build-packages`.

### Task 6 (PR 6): `framework/testing` (`refactor/framework-testing-layout` → `refactor/framework-hosting-layout`)
- **Worktree:** `/home/anto/Repos/smpy-fw6-testing`
- **Moves:** `simple_module_test/{app,db,web,fakes}/` (keep `__init__.py`, `py.typed`, `plugin.py` at root).
- **Shims & Tests:** Add `remove_in="0.0.52"` alias shims for externally imported paths (including `_schema.py`); move all `14` tests into `tests/<area>/`; delete `LEGACY_FLAT` cleanly from `host/tests/test_framework_layout.py`; mark all 6 packages complete in `docs/framework-layout.md`.
- **Done check:** Fresh-interpreter imports, `/ship --skip-browser --no-rebase` incl. `make ci-docs-build` & `make ci-build-packages`.
