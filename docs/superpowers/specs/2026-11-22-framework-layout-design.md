# Framework Package Layout Design (`framework/*`)

- **Date:** 2026-11-22
- **Status:** Approved
- **Scope:** All six framework packages under `framework/{inertia,cli,core,db,hosting,testing}` (`simple_module_{inertia,cli,core,db,hosting,test}`) and their test suites.

## 1. Goal & Scope

Bring all six packages under `framework/` (`320` flat root `.py` files and `454` flat `tests/test_*.py` files) onto a domain-area layout matching the conventions already used by `modules/` (`docs/module-layout.md`, `host/tests/test_module_layout.py`).

### In scope
- Author `docs/framework-layout.md`, wire it into VitePress navigation and `AGENTS.md`.
- Add `host/tests/test_framework_layout.py` with a `LEGACY_FLAT` ratchet shrinking per PR until dropped in PR 6.
- Extend `host/tests/test_deprecation_expiry.py` (`_layout_shims()`) to discover `sys.modules` layout alias shims under `framework/` alongside `modules/`.
- Reorganize source packages and `tests/` for all 6 framework packages (`inertia`, `cli`, `core`, `db`, `hosting`, `testing`), rewrite in-repo imports, `mock.patch` / `monkeypatch` targets, and backticked doc paths, and leave deprecated alias shims at externally imported old paths.

### Out of scope
- Changing runtime behavior or refactoring logic inside moved modules (moves and import rewrites only).
- Editing downstream `smpy_modules` (kept green via 2-release compatibility shims).
- Moving `modules/*`, `host/`, or `packages/*`.

## 2. Approach & Stack Order

Each package moves in its own PR (after PR 0 introduces the spec and ratchet) in strict dependency order so every PR diff isolates one package and higher layers adopt settled lower-layer paths without cross-PR conflicts:

```text
main
 └─ PR 0: docs/framework-layout.md + test_framework_layout.py ratchet + expiry scan
     └─ PR 1: framework/inertia  (16 src,  23 tests — leaf, 0 framework deps)
         └─ PR 2: framework/cli      (46 src,  83 tests — leaf, 0 framework deps)
             └─ PR 3: framework/core     (71 src,  79 tests — leaf, 0 framework deps)
                 └─ PR 4: framework/db       (56 src,  78 tests — depends on core)
                     └─ PR 5: framework/hosting  (109 src, 177 tests — depends on core, db, inertia)
                         └─ PR 6: framework/testing  (22 src,  14 tests — depends on core, db, hosting, inertia; drops LEGACY_FLAT)
```

### Alternatives rejected
- **Six independent PRs off `main`:** `hosting` and `testing` import dozens of `core` and `db` submodules; independent branches would conflict on imports and couldn't enforce `test_framework_layout.py` until PR 0 landed.
- **Single mega-PR across all six packages:** Too large to review or isolate regressions across 774 moved files.

## 3. Target Layout Contract

1. **Package root (`framework/<proj>/simple_module_<pkg>/`):** Only `__init__.py` (preserving top-level public exports), `py.typed`, optional `__main__.py`, declared entry-point / resource / wire-name roots, named domain subpackages (`AREAS`), and active deprecated alias shims.
2. **Area initializers:** Every area subpackage carries a docstring-only `__init__.py` (except `simple_module_core/diagnostics/__init__.py`, an explicit public facade kept intentionally). Private helpers keep a leading underscore inside the area they serve. Declared area names must not collide with any existing root `.py` module stem (including active shims).
3. **Tests (`framework/<proj>/tests/`):** Mirror package areas (`tests/<area>/test_*.py`, or nested feature folders inside large areas). No flat `tests/test_*.py`, no `tests/**/__init__.py`. Root `conftest.py` and shared `_*_support.py` / `_*_models.py` helpers remain at `tests/` root (`pyproject.toml` `pythonpath` unchanged). `framework/hosting/tests-js/` remains unchanged.
4. **Compatibility shims:** Old submodule paths imported outside their owning package (verified across `modules/`, `host/`, and `smpy_modules`) keep a `sys.modules` alias shim with `remove_in="0.0.52"` (two releases ahead of `0.0.50`).

## 4. Target Subpackage Maps

### PR 1 — `framework/inertia` (`simple_module_inertia`, 16 `.py`, 23 tests)
- **Root:** `__init__.py`, `py.typed`, plus `response.py` shim (`DeprecationWarning` + `sys.modules` alias, registered via `deprecate(...)` in `_register_all()` of `host/tests/test_deprecation_expiry.py` to keep 0 `core` dependency).
- **Areas:**
  - `protocol/`: `config`, `request`, `response`, `errors`, `validation`, `middleware`
  - `rendering/`: `inertia`, `page`, `props`, `resolve`, `_json_snapshot`, `deps`
  - `assets/`: `head`, `manifest`, `templating`

### PR 2 — `framework/cli` (`simple_module_cli`, 46 `.py`, 83 tests)
- **Root:** `__init__.py`, `py.typed`, `cli.py` (`smpy` / `simple-module`), `migration_recipes/`, `templates/`, `skills` symlink.
- **Areas:**
  - `commands/`: `new`, `add_cmd`, `dev_cmd`, `docker_cmd`, `gen_cmd`, `migrations_cmd`, `module_cmd`, `openapi_cmd`, `skills_cmd`, `update_cmd`, `plugins`
  - `scaffold/`: `app_project`, `scaffolding`, `wizard`, `recipes`, `docker_assets`, `framework_repo`, `case`, `_templating`, `_env`, `_local_env`, `_app_project_manifests`, `_lint_tooling`
  - `sources/`: `catalog`, `git_source`, `git_versions`, `pypi`, `pins`, `requirements`, `pyproject_edit`, `uv_workspace`, `_add_install`, `_add_sources`, `_version_check`, `_project_cli_check`
  - `updates/`: `package_update`, `package_update_deps`, `package_update_git`, `package_update_npm`
  - `tooling/`: `openapi_types`, `_generation_cache`, `_module_build`, `_module_host`
  - `migrations/`: `_migration_support` (keeps byte-parity test with `simple_module_core`)

### PR 3 — `framework/core` (`simple_module_core`, 71 `.py`, 79 tests)
- **Root:** `__init__.py`, `__main__.py`, `py.typed`, `tenant_events.py`, `user_events.py` (wire-name invariant for durable outbox classes in `host/tests/test_durable_wire_names.py`).
- **Areas:**
  - `modules/`: `module`, `module_meta`, `discovery`, `services`, `app_state`, `versioning`, `_auth_providers`, `_entry_point_errors`, `_module_conventions`, `_module_ordering`, `_request_hooks`
  - `access/`: `permissions`, `permission_catalogue`, `permission_denied`, `_permission_grants`, `principals`, `principal_permissions`, `resources`, `tenancy`, `file_access`, `user_directory`, `role_directory`, `activity_feed`
  - `eventing/`: `events`, `durable_events`, `invalidation`, `invalidation_refresh`, `_invalidation_message`
  - `settings/`: `settings_base`, `module_settings`, `settings_hydrate`, `stored_settings`, `secret_fields`, `dotenv`, `environments`
  - `web/`: `admin_surface`, `menu`, `public_routes`, `body_limits`, `cors`, `csp`, `rate_limit`, `path_rules`, `redirect_safety`, `design_packs`, `setup_steps`, `spa_mount`, `audit_links`, `feature_flags`, `health`
  - `localization/`: `i18n`, `i18n_overrides`, `_i18n_flatten`, `_i18n_translator`
  - `mailer/`: `mail`, `_mail_headers`
  - `runtime/`: `correlation`, `crypto`, `datetimes`, `deprecation`, `exceptions`, `leases`, `_lease_memory`, `singleflight`
  - `diagnostics/`: existing `diagnostics/_*.py` + `_data_doctor`, `_migration_doctor` (keeps `__init__.py` facade)
  - `migrations/`: `data_compatibility`, `support` (replaces `migration_support/__init__.py`, with `migration_support` shim)

### PR 4 — `framework/db` (`simple_module_db`, 56 `.py`, 78 tests)
- **Root:** `__init__.py`, `py.typed`
- **Areas:**
  - `engine/`: `session`, `transaction`, `independent`, `callbacks`, `deps`, `provider`, `engine_options`, `admission`, `writes`, `query_stats`, `leases`
  - `models/`: `base`, `mixins`, `types`, `model_registry`, `listeners`, `extensions`
  - `scoping/`: `scopes`, `tenancy`, `tenant_cleanup` (pins `subscribe_durable(..., name="simple_module_db.tenant_cleanup.delete_tenant_settings")`), `query_filter`, `core_scope`, `scope_predicates`, `flush_guard`, `insert_guard`, `insert_scope`, `bulk_guard`, `_builtin_scopes`, `_core_joins`, `_core_walk`, `_engine_policies`, `_entity_selectables`, `_outer_joins`, `_persisted_owner`, `_scope_writes`, `_secondary_scope`
  - `auditing/`: `audit`, `audit_redaction`, `audit_sinks`, `bulk_audit`, `bulk_audit_targets`, `_bulk_audit_records`, `_bulk_pk_update`
  - `schema/`: `migrations`, `migration_portability`, `migration_state`, `data_compatibility`, `_migration_render`, `_sqlite_index_compare`
  - `queries/`: `pagination`, `search`, `stored_settings`, `principals`, `resource_policy`, `user_directory_sql`

### PR 5 — `framework/hosting` (`simple_module_hosting`, 109 `.py`, 177 tests)
- **Root:** `__init__.py`, `__main__.py`, `py.typed`, `host_cli.py`, `admin_overview/`, `setup_wizard/`, `locales/`, `ui_locales/`.
- **Areas:**
  - `boot/`: `app_builder`, `host`, `_app_boot`, `_lifespan`, `_deferred_startup`, `_hydrate_step`, `_dev_boot`, `_boot_checks`, `_table_coverage`, `_phase_helpers`, `_registrations`, `_module_routes`, `_fallback_routes`, `_process_services`, `_project_root`, `data_compatibility`, `migrations`, `migrations_env`, `db_options`, `health`, `_db_health`, `_openapi`
  - `config/`: `settings`, `host_settings`, `bootstrap_settings`, `_host_settings_support`, `_host_services`, `_preapp_config`, `_settings_registration`, `_api_version`, `_secret_key`, `_stored_identity`, `installation`
  - `pipeline/`: `middleware`, `middleware_config`, `_middleware_pipeline`, `_security_headers`, `_csp_dynamic`, `_cors`, `_body_limit`, `_forwarded_host`, `_insecure_transport`, `_request_guard_responses`, `_request_policy`, `_server_timing`, `maintenance`, `setup_gate`, `session`, `_tenant`, `tenancy`, `path_matching`, `_route_guard`, `_route_paths`, `_route_access`, `public_access`, `public_urls`, `redirects`
  - `rate_limit/`: `rate_limit_deps`, `_rate_limit`, `_rate_limit_keys`, `_rate_limit_store`
  - `auth/`: `auth_policy`, `csrf`, `permissions`, `resource_deps`, `token_guard`, `_anonymous`
  - `error_handling/`: `errors`, `_error_handlers`, `_error_negotiation`, `_error_page`
  - `frontend/`: `assets`, `_asset_sources`, `manifest`, `page_globs`, `admin_surfaces`, `frontend_extensions`, `module_tsconfig`, `_generated_files`, `static_files`, `_spa_mount`, `_favicon`, `inertia_deps`, `inertia_utils`, `shared_props`, `_inertia_setup`, `_inertia_shared`, `pagination`
  - `i18n/`: `i18n_deps`, `i18n_manifest`, `i18n_middleware`, `i18n_routes`, `_i18n_build`, `_i18n_json`, `_i18n_modules`, `_i18n_target`
  - `observability/`: `logging`, `log_sinks`, `_observability`, `sentry`, `sentry_scrub`, `sentry_scrub_text`
  - `locking/`: `leases`, `_lease_redis`, `_lease_redis_close`, `_lease_redis_scripts`

### PR 6 — `framework/testing` (`simple_module_test`, 22 `.py`, 14 tests)
- **Root:** `__init__.py`, `py.typed`, `plugin.py` (`pytest11` entry point).
- **Areas:**
  - `app/`: `app_factory`, `fixtures`, `process_state`, `routes`, `_dotenv`, `waiting`, `layout`
  - `db/`: `database`, `_schema`, `_compile_cache`, `_sqlite_template`, `redis_server`
  - `web/`: `inertia`, `inertia_page`, `session_cookie`, `setup_wizard`, `tenant_client`
  - `fakes/`: `fake_events`, `mail`, `oidc_issuer`

## 5. Verification & Risks
- Fresh-interpreter import verification (`python -c "import <pkg>.<mod>"`) for every moved module and every compatibility shim.
- Pin tests: `host/tests/test_framework_layout.py`, `host/tests/test_deprecation_expiry.py`, `host/tests/test_durable_wire_names.py`, `framework/cli/tests/.../test_no_framework_deps.py`, `framework/hosting/tests/.../test_middleware_order.py`.
- Full `/ship --skip-browser` gate on every PR: `make gen`, `make lint` (including `check_doc_paths.py`, `check_file_size.py`, `ty`, `ruff`, `biome`, `tsc`), `PYTEST_WORKERS=4 make test-py`, `CHOKIDAR_USEPOLLING=1 make test-js`, `make ci-doctor`, and `make ci-build-packages` (plus `make ci-css-build` on CLI/hosting and `make ci-docs-build` on PR 0/6).
- Because `.github/workflows/pr.yml` and `postgres-tests.yml` filter `pull_request.branches: [main]`, remote GitHub Actions CI runs automatically on PR 0 (`main`) and runs on PRs 1–6 once each predecessor merges / retargets to `main`.
