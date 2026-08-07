# Diagnostic codes

The framework runs a set of static checks over installed modules at app boot. The full structural/page/i18n suite runs in development (`SM_ENVIRONMENT=development`), prints to stderr, and aborts boot on any ERROR. In non-development environments (anything other than `development`) module discovery is **strict** — entry-point failures and missing/invalid `meta` (the SM001 class of problems) raise at boot — and the migration check (SM010) fails boot in every environment.

## Levels

- **ERROR** — fails boot in production. Always fix.
- **WARNING** — printed; doesn't fail boot. Fix before shipping.
- **INFO** — informational; safe to ignore but useful signal.

## The codes

| Code | Level | Trigger | Fix |
|---|---|---|---|
| `SM001` | ERROR | Module subclass has no `meta` attribute, or `meta` is not a `ModuleMeta`. | Declare `meta = ModuleMeta(name=..., version=..., ...)` on the class. |
| `SM003` | WARNING | `pages/<name>.tsx` exists but no `inertia.render()` call in any module references the corresponding page key. | Remove the orphan file, or add the matching `inertia.render("<Module>/<name>", ...)` in `views.py`. |
| `SM004` | WARNING | An `inertia.render("<Module>/<name>")` call exists but no matching `.tsx` file is shipped. | Create `pages/<name>.tsx`, or correct the render key. |
| `SM007` | INFO | Module overrides zero `register_*` hooks and has no `on_startup`/`on_shutdown`. | Delete the module if it's vestigial; otherwise ignore. |
| `SM008` | ERROR | Two modules declare the same `ModuleMeta.name`. Table-prefix collision. | Rename one. Remember: the name is the table-name prefix (all modules share one DB schema) and the Inertia namespace. |
| `SM009` | ERROR | A file under `framework/*` imports from any package under `modules/*`. | Invert the dependency: have the module register a callback into the framework (see `principal_serializer` pattern). |
| `SM010` | ERROR | DB `alembic_version` is behind the migration head. | Run `make migrate`. The lifespan migration check raises and aborts boot in every environment before serving. |
| `SM011` | WARNING | A module's model declares a table that doesn't appear in any Alembic migration. | Run `uv run alembic revision --autogenerate -m "..."`, review, `make migrate`. |
| `SM012` | WARNING | Module overrides `register_settings` but does not assign to `app.state.<module_lower>`. Dev-only. | Either remove the override or move your state assignment into it. |
| `SM013` | WARNING | Supported locale has no corresponding file in some module's `locales/`. | Add `modules/<name>/<name>/locales/<locale>.json`, or drop the locale from `SM_I18N_SUPPORTED_LOCALES`. |
| `SM014` | WARNING | Non-default locale is missing keys present in the default (untranslated). | Translate the missing keys. |
| `SM015` | WARNING | Non-default locale has keys not in the default (stale / orphan translation). | Remove the stale keys, or add them to the default file if they really belong. |
| `SM016` | ERROR | Locale JSON is invalid or contains non-string leaves. | Fix the JSON; keys must flatten to strings only. |
| `SM017` | WARNING | Module ships `.tsx` pages but has no `package.json` / `tsconfig.json`. Vite can't resolve type imports. | Run `smpy create-module` on a dummy name and copy the generated config, or scaffold by hand. |
| `SM018` | WARNING | An Inertia `router.post/patch/put/delete()` call in a page targets a JSON `/api/*` endpoint, which would return raw JSON and be rejected by Inertia. | Point the call at a view endpoint that returns `inertia.render(...)` or a redirect; or use plain `fetch()` if you really want a JSON response. |
| `SM019` | WARNING | Module declares a non-empty `view_prefix` and overrides `register_routes` but registers neither menu items nor permissions — admins can't reach the pages from the sidebar or grant access from the role editor. | Add `register_menu_items` for a sidebar entry, or `register_permissions` to surface the module in the role editor (sub-pages of another module typically just register permissions). |
| `SM020` | ERROR | More than one auth-provider module is installed (e.g. both `users` and `keycloak`). | Install exactly one auth provider. |
| `SM021` | WARNING | No auth-provider module is installed. | Install an auth provider (e.g. `simple-module-users` or `simple-module-keycloak`). |
| `SM022` | WARNING | A module's `styles.css` contains a top-level `@theme`, `@custom-variant` or `@utility` block. That file is imported into `layer(components)`, where those at-rules are inert. | Move the block to the module's `theme.css`, which is imported unlayered so its tokens actually register. |
| `SM023` | WARNING | A module's `theme.css` contains an unlayered plain rule (anything but an at-rule or a `:root`-style selector). Unlayered CSS outranks every Tailwind utility. | Move the rule to the module's `styles.css`, which is imported into `layer(components)` so utilities still win. |

`SM022`/`SM023` are the two halves of the same invariant: a module's optional [`theme.css` is imported unlayered and `styles.css` into `layer(components)`](/module-authoring#styling), and CSS put in the wrong one silently does nothing (or silently wins everything).

## When diagnostics fire

| Context | What runs |
|---|---|
| App boot in development | Full structural/page/i18n suite, results logged to stderr. ERRORS abort boot. |
| App boot in non-development | Strict module discovery (raises on SM001-class failures) + the migration check (SM010). The page/locale static suite is dev-only. |

Sample dev-mode output:

```text
running diagnostics …

WARNING SM003  modules/orders/orders/pages/Unused.tsx: no inertia.render("Orders/Unused") call found
WARNING SM013  locale "es" missing file for module "orders" (expected modules/orders/orders/locales/es.json)
ERROR   SM010  DB revision 3a1b2c3d4e5f is behind migration head 9f8e7d6c5b4a — run `make migrate`

1 error, 2 warnings
```

Treat a clean dev boot as the "ready to ship" gate. If you want to run the diagnostics manually without booting the app, the framework repo's `make doctor` target does exactly that — it's a contributor convenience and not part of the user-facing flow.

## Adding a new diagnostic

If you think a rule deserves a code, open a design doc in `docs/plans/` first — existing codes are stable contracts (downstream tooling can grep for them). Use the next free number in the `SM0XX` range and:

1. Add the check to `simple_module_core.diagnostics`.
2. Wire it into `run_diagnostics()` (or the relevant `*Diagnostics.run()` method) so it runs at app boot.
3. Update this page with the row.
4. Add a test case under `framework/core/tests/`.
