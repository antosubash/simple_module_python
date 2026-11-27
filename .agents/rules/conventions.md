---
trigger: model_decision
description: Coding conventions, frontend TypeScript/i18n/UI rules, error handling, styling, and API contract conventions for simple_module_python.
---

## Conventions

- **SQLModel everywhere**: tables are `SQLModel, table=True`; DTOs are plain
  `SQLModel` subclasses. No Pydantic `BaseModel`, no SQLAlchemy
  `DeclarativeBase`/`Mapped[...]` in module code.
- **No magic strings in non-test Python** (`scripts/check_hardcoded_strings.py`):
  `RequiresPermission(...)`, `registry.map_role(...)`, `registry.add_group(...)`
  items and `depends_on=[...]` entries use named constants from `core/constants.py`
  or `PermissionCatalogue` members. Attach the catalogue to `ModuleBase.permissions`
  for default registration; custom hooks extend it via `super()`. Literal module
  `inertia.render("MetaName/Page")` keys are allowed when the checker verifies the
  owning module name and existing TSX page (nested pages supported, tests excluded).
  Existing `PAGE_*` constants remain supported; new aliases are unnecessary.
- **300-line cap** on `.py`/`.ts`/`.tsx`, tests included, untracked files
  included (`scripts/check_file_size.py`). Exempt: shadcn components under
  `packages/ui/src/components/ui/**`, generated i18n files,
  `host/migrations/versions/**`. Split by responsibility; don't squeeze.
- **Configuration lives in the DB, not `.env`.** Operators normally set only
  `SM_DATABASE_URL`, `SM_REDIS_URL` and `SM_USERS_BOOTSTRAP_*`;
  `SM_ENVIRONMENT`/`SM_DEBUG`/`SM_VITE_DEV_URL` describe the process. Do not
  add new configuration as env vars. Host settings: precedence
  **env → DB → default**, and env must keep winning. `host/main.py` uses
  `build_host_app()` from `simple_module_hosting.boot.host`, which calls
  `merge_host_settings()`, not `Settings()`: `create_app` reads some fields
  before the lifespan opens the DB, and every such field is marked
  restart-required (`test_build_time_settings_marked.py`). `SM_SECRET_KEY` is
  optional: unset generates and stores a key; an explicit value wins and is never
  copied into the DB. A pre-app read failure is not a fresh install: outside
  development it refuses to boot (`HostSettingsUnavailableError` /
  `SecretKeyUnavailableError`); only a missing settings table falls back to
  defaults. Stored values parse through `simple_module_core.settings.stored_settings`; an
  invalid row is dropped with a WARNING. Module settings are a
  `DbBackedSettings` subclass registered in `register_settings` through
  `simple_module_core.settings.module_settings.register_module_settings(app, package,
  SettingsCls, services_factory)`, which mounts the services object on
  `app.state.<package>` (`SM012`); this works with the `settings` plugin
  disabled. The exceptions that read env are secrets and process wiring
  (`SM_BG_TASKS_*`, `SM_KEYCLOAK_*`, `SM_USERS_*_TOKEN_SECRET`).
  `docs/framework/settings.md`, `docs/reference/env-vars.md`.
- **Framework must not import plugins** (`SM009`): nothing under `framework/`
  imports from `modules/`; the framework exposes registries and callbacks
  instead. A module may import the modules it lists in `depends_on` directly.
- **Deprecations carry a removal release.** A compat shim uses
  `simple_module_core.runtime.deprecation` (`deprecated`, `deprecated_module`, `deprecate`)
  with `remove_in`, and is added to `host/tests/test_deprecation_expiry.py`, which
  fails once the framework version reaches it. No undated "back-compat" shims.
  `docs/framework/deprecations.md`.
- **Background tasks**: `tasks.py` with `@shared_task(name="<module>.<task>")`;
  heavy imports (`torch`, `cv2`, …) inside the task body (`SM028`). Enqueue from
  a transaction with `background_tasks.enqueue_after_commit(db, task, …)`, never
  `.delay()`. Long tasks call `heartbeat()`. `docs/modules/background_tasks.md`.
- **Mail**: build a `MailMessage` and send through `simple_module_core.mailer.mail`
  (`current_mail_sender()` in request code, `await resolve_mail_sender(db)` in
  durable handlers). Without the `mail` module the sender only logs. Tests use
  the `captured_mail` fixture.
- **Audit links / design packs**: build links with
  `AuditLink.for_model(Model, url_template=…, …)` (a table-name `entity_type`
  silently never matches); `register_design_packs` slugs must match
  `^[a-z0-9][a-z0-9-]*$` and the host must still import the CSS.
- **i18n.** Ship `<package>/locales/<lang>.json`; the default `locale_dirs()` discovers
  it with the lowercase package name as namespace. Override only for custom paths
  or namespaces; `{"browse": {"title": "X"}}` becomes
  `<ns>.browse.title`; plurals use CLDR suffixes (`_one`, `_other`). Menu items
  set `label_key`/`group_key` beside `label`/`group` (an unresolved key falls
  back to the literal, silently); group headers use `ui.nav_groups.*`.
  **No user-visible string literals in `.tsx`**: JSX text,
  `title`/`placeholder`/`aria-label`-style attributes, `toast.*()`/`confirm()`
  arguments and ternary branches all go through `t(keys.<ns>.…)` from
  `@simple-module-py/i18n`. Exempt: text inside `<code>`/`<pre>`/`<kbd>`/
  `<samp>`/`<var>`, a line marked `// i18n-exempt: <reason>` (or the line
  above), or `i18n-exempt-file: <reason>` within the first 800 characters.
  Strings passed through variables or config objects are not seen, so still
  translate them. Zod schemas with translated messages, and the non-hook `t` in
  helpers, are built inside the function, never at module scope.
  `docs/framework/i18n.md`.
- **Pages call the API through the typed client** (`packages/ui/src/lib/api.ts`,
  built from each module's `pages/api.generated.ts`), not raw `fetch()`
  (`scripts/check_no_raw_fetch.py`); a call that cannot use it is marked
  `// raw-fetch-ok: <reason>`.
- **No fixed sleeps in tests**: poll with `simple_module_test.wait_for`, or mark
  `# intentional-sleep: <reason>` (`scripts/check_test_sleeps.py`).
- **JS tests** go in `modules/<m>/tests-js/*.test.ts(x)`, `packages/**` or
  `host/client_app/**`; Vitest collects nothing else. Biome (single quotes,
  2 spaces, width 100) lints `host/client_app`, `packages`, module `pages/`, `ui/`
  and legacy `components/` dirs. `smpy host typecheck` uses host-generated module
  configs unless an authored `tsconfig.json` overrides them. Packages retain their
  own configs. Ordinary modules need neither frontend config file. CI typecheck
  rejects uninstalled workspace modules with frontend sources; frontend builds
  use `--installed-only` to allow intentional exclusions.
- **`ty` rules.** SQLModel false positives (`unresolved-attribute`,
  `unsupported-operator`, `unknown-argument`, `no-matching-overload`) are
  ignored globally in `pyproject.toml`; don't re-enable them.
  `invalid-argument-type` and `invalid-assignment` are **on** for shipped code
  and ignored only for tests. Fix what they report; for a genuine third-party
  false positive add `# ty: ignore[<rule>]` on that line. Never write
  `# type: ignore[<mypy-code>]`: ty matches the bracket against its own rule
  names, so it suppresses nothing.
