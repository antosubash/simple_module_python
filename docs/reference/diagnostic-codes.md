# Diagnostic codes

`make doctor` runs a set of static checks over installed modules. Same checks run at app boot; errors fail boot in production (`SM_ENVIRONMENT` ≠ `development`/`test`/`testing`).

## Levels

- **ERROR** — fails boot in production; exits non-zero from `make doctor`.
- **WARNING** — printed to stdout; does not fail boot. Fix before shipping.
- **INFO** — informational; safe to ignore but useful signal.

## The codes

| Code | Level | Trigger | Fix |
|---|---|---|---|
| `SM001` | ERROR | Module subclass has no `meta` attribute, or `meta` is not a `ModuleMeta`. | Declare `meta = ModuleMeta(name=..., version=..., ...)` on the class. |
| `SM003` | WARNING | `pages/<name>.tsx` exists but no `inertia.render()` call in any module references the corresponding page key. | Remove the orphan file, or add the matching `inertia.render("<Module>/<name>", ...)` in `views.py`. |
| `SM004` | WARNING | An `inertia.render("<Module>/<name>")` call exists but no matching `.tsx` file is shipped. | Create `pages/<name>.tsx`, or correct the render key. |
| `SM007` | INFO | Module overrides zero `register_*` hooks and has no `on_startup`/`on_shutdown`. | Delete the module if it's vestigial; otherwise ignore. |
| `SM008` | ERROR | Two modules declare the same `ModuleMeta.name`. Schema / prefix collision. | Rename one. Remember: name is used as Postgres schema, SQLite table prefix, Inertia namespace. |
| `SM009` | ERROR | A file under `framework/*` imports from any package under `modules/*`. | Invert the dependency: have the module register a callback into the framework (see `principal_serializer` pattern). |
| `SM010` | ERROR | DB `alembic_version` is behind the migration head. | Run `make migrate`. In dev this prints a warning; in production it's a hard failure before serving. |
| `SM011` | WARNING | A module's model declares a table that doesn't appear in any Alembic migration. | Run `make migration msg="..."`, review, `make migrate`. |
| `SM012` | WARNING | Module overrides `register_settings` but does not assign to `app.state.<module_lower>`. Dev-only. | Either remove the override or move your state assignment into it. |
| `SM013` | WARNING | Supported locale has no corresponding file in some module's `locales/`. | Add `modules/<name>/<name>/locales/<locale>.json`, or drop the locale from `SM_I18N_SUPPORTED_LOCALES`. |
| `SM014` | WARNING | Non-default locale is missing keys present in the default (untranslated). | Translate the missing keys. |
| `SM015` | WARNING | Non-default locale has keys not in the default (stale / orphan translation). | Remove the stale keys, or add them to the default file if they really belong. |
| `SM016` | ERROR | Locale JSON is invalid or contains non-string leaves. | Fix the JSON; keys must flatten to strings only. |
| `SM017` | WARNING | Module ships `.tsx` pages but has no `package.json` / `tsconfig.json`. Vite can't resolve type imports. | Run `make new-module` on a dummy name and copy the generated config, or scaffold by hand. |
| `SM018` | WARNING | An Inertia `router.post/patch/put/delete()` call in a page targets a JSON `/api/*` endpoint, which would return raw JSON and be rejected by Inertia. | Point the call at a view endpoint that returns `inertia.render(...)` or a redirect; or use plain `fetch()` if you really want a JSON response. |
| `SM019` | WARNING | Module declares a non-empty `view_prefix` and overrides `register_routes` but registers neither menu items nor permissions — admins can't reach the pages from the sidebar or grant access from the role editor. | Add `register_menu_items` for a sidebar entry, or `register_permissions` to surface the module in the role editor (sub-pages of another module typically just register permissions). |

## Running diagnostics

```bash
make doctor
```

Sample output:

```text
running diagnostics …

WARNING SM003  modules/orders/orders/pages/Unused.tsx: no inertia.render("Orders/Unused") call found
WARNING SM013  locale "es" missing file for module "orders" (expected modules/orders/orders/locales/es.json)
ERROR   SM010  DB revision 3a1b2c3d4e5f is behind migration head 9f8e7d6c5b4a — run `make migrate`

1 error, 2 warnings
```

Exits non-zero when any ERROR is present. Non-zero on warnings is opt-in with `-Werror` (there isn't a flag yet — but CI treats warnings as informational).

## When diagnostics fire

| Context | What runs |
|---|---|
| `make doctor` | Full suite. Exits non-zero on any ERROR. |
| App boot in development | Full suite, results logged. Doesn't abort. |
| App boot in production | Full suite. ERRORS abort boot before serving. |
| CI (PR check) | `make doctor` as part of the aggregate `pr-checks` job. |

Treat `make doctor` as the "ready to ship" checklist. A green run + green `make lint && make test` is the floor for pushing to `main`.

## Adding a new diagnostic

If you think a rule deserves a code, open a design doc in `docs/plans/` first — existing codes are stable contracts (downstream tooling can grep for them). Use the next free number in the `SM0XX` range and:

1. Add the check to `simple_module_core.diagnostics`.
2. Wire it into `build_diagnostics_pass()` so it runs from both `make doctor` and app boot.
3. Update this page with the row.
4. Add a test case under `tests/framework/core/diagnostics/`.
