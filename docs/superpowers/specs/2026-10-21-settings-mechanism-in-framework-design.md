# Settings mechanism moves into the framework (#500)

Approved 2026-10-21.

## Problem

`simple_module_hosting` cannot boot without the `settings` plugin, yet reaches it
only through `importlib.import_module("settings.…")` strings and raw SQL with
hard-coded column names (`_hydrate_step.py`, `_lifespan.py`,
`_settings_registration.py`, `_preapp_config.py`, `_secret_key.py`). SM009 sees
none of it. Option 2 (import `settings` statically) is impossible: the
`settings` package already depends on `simple_module_hosting`.

## Design

Move the mechanism down; keep the admin UI and the write path in `settings`.

| What | From `modules/settings/settings/` | To |
|---|---|---|
| `register_module_settings` + `ModuleSettingsRegistry` | `registration.py`, `module_registry.py` | `simple_module_core/module_settings.py` |
| Secret-field masking (pure pydantic) | `_secrets.py` | `simple_module_core/secret_fields.py` |
| Hydration (env → DB → default), `RELATED_FIELDS_CTX`, `build_settings`, field helpers | `hydrate.py` | `simple_module_core/settings_hydrate.py`; DB reads through `OverrideSource` Protocol (`async get_overrides(package) -> dict[str, tuple[str, str]]`) |
| `Setting` model, table/column/scope constants, read-only override queries (`store.py:31-63`), `get_overrides_sync`, `hydrate_settings_sync` | `models.py`, `store.py`, `constants.py` | `simple_module_db/stored_settings.py` (split if >300 lines) |

- The module-settings registry is created lazily on `app.state` by the framework,
  so registration no longer requires the `settings` module to have registered
  first, and works with `settings` disabled.
- Stays in `settings`: `SettingService`, the write half of `SettingsStore`
  (still satisfies `OverrideSource`), `reload`/`SettingsReloaded`, `contracts`,
  `known_keys`, admin endpoints/pages/CLI. `SettingsServices.module_registry` is
  the framework registry object.
- Framework call sites (`_lifespan`, `_hydrate_step`, `_settings_registration`)
  import statically. `_preapp_config` and `_secret_key` take table/column names
  from `simple_module_db.stored_settings` and build SQL with
  `sqlalchemy.table()/column()`, not f-strings.
- Table: `settings_setting` unchanged (same name, columns, constraints,
  `create_module_base("settings")` metadata name). No migration.
  `build_module_metadata` and `simple_module_test/_schema.py` import
  `simple_module_db.stored_settings` explicitly so the table is collected
  without the plugin. `alembic check` (Postgres round trip) proves no drift.
- Back-compat: `settings.registration`, `settings.module_registry`,
  `settings.hydrate`, `settings.models`, `settings._secrets`, and the moved names
  in `settings.store`/`settings.constants` re-export the same objects (never a
  second `Setting` class). `registration`, `module_registry`, `hydrate` emit a
  module-level `DeprecationWarning`; removal no earlier than 0.1.0. In-repo code
  uses the new paths.
- SM009 (`diagnostics/_coupling.py`): also flag `importlib.import_module`,
  `import_module`, `__import__`, `importlib.util.find_spec` calls whose literal
  first argument (or `name=`) has a plugin package as its top segment; ERROR.
- Same PR: the 7 modules using `importlib` to reach `register_module_settings`
  import it statically from core; the `make new-module` templates use
  `DbBackedSettings` + `register_module_settings`.

## Not in scope

Missing `depends_on` targets still only warn (#501). Write path, contracts and
reload stay in the plugin (no new package, no new PyPI name).

## Risks

- `_secret_key` treats a missing table as a fresh install; safe only because the
  framework now always owns the table metadata.
- `app_builder.py` is near the 300-line cap: no new lines there.
- Out-of-tree hosts without `settings` will see autogenerate emit
  `settings_setting` (CHANGELOG).
