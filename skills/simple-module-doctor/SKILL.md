---
name: simple-module-doctor
description: Use when interpreting a simple_module_python diagnostic code (SM001–SM021) printed at boot or by the diagnostics runner — what the code means, whether it's blocking, and the concrete fix. Triggers on any "SMnnn" code in logs, "InvalidModuleError", "module silently doesn't load", or "production failed boot".
---

# simple_module_python: diagnostics

`make doctor` runs `python -m simple_module_core`: it discovers modules **strictly**, runs the diagnostics, prints findings to stderr (`✓ No module diagnostics issues found` when clean), and exits `1` if any ERROR-level finding was reported.

The same diagnostics also run at host boot, but **only in development** (`SM_ENVIRONMENT == development`) — they print to the boot logs and `raise SystemExit` if there's any ERROR. **In production the diagnostics pass is skipped**; what protects prod is that module *discovery* runs strictly (any bad entry point — broken import, missing `meta`, non-`ModuleBase` class — raises and fails the boot). So "errors fail prod boot" is true for discovery-level breakage (surfaced as **SM001**), not for the per-finding checks below, which you'll catch via `make doctor` / dev boot before you ever deploy.

You can also call `run_diagnostics(...)` from `simple_module_core` programmatically (e.g. in a CI job) to surface issues without booting the full app — pass `migration_state=` / `module_tables=` / `migrated_tables=` to additionally get **SM010/SM011** (the migration checks below), and `i18n_supported_locales=` / `i18n_default_locale=` to get the locale checks.

## Code reference

| Code | Level | What it means | Fix |
|---|---|---|---|
| **SM001** | ERROR | Module class is missing its `meta = ModuleMeta(...)` class attribute, or (under strict discovery) the entry point failed to load — broken import, missing `meta`, or a class that isn't a `ModuleBase` subclass | Add a valid `meta` class attribute on the `ModuleBase` subclass / fix the entry point. This is the one code that fails *production* boot (via strict discovery) |
| **SM003** | WARNING | A `pages/<Name>.tsx` exists but no `inertia.render("<Module>/<Name>", ...)` references it | Either delete the orphan file or wire up the render call |
| **SM004** | WARNING | `inertia.render("<Module>/<Name>", ...)` is called but no matching `.tsx` exists | Fix the render-key typo or create the page file |
| **SM007** | INFO | Module overrides no `register_*` hooks at all — likely scaffolded but empty | Either implement at least one hook or delete the module if unused |
| **SM008** | ERROR | Two modules declare the same `ModuleMeta.name`, or two names collide once lowercased as table prefixes in the shared schema (one finding per collision, from either the duplicate-name or the schema-conflict check) | Rename one module's `meta.name` |
| **SM009** | ERROR | A `framework/*` package directly imports from a plugin module (`modules/*`) | Move the symbol *up* into `simple_module_core` / `simple_module_hosting`, or invert the dependency via the event bus / a registry |
| **SM010** | ERROR | Live DB revision is behind the migration head | Run `make migrate` before booting; in CI, ensure migrations are part of the deploy step. *Note:* only emitted when a caller passes `migration_state=` to `run_diagnostics` — `make doctor` and dev boot do **not** check this. The live boot enforces it separately: `check_migrations()` raises a plain `RuntimeError` (not an SM code) in dev and prod if the DB is behind head |
| **SM011** | WARNING | A module declares a SQLModel table that has no entry in migration history | Run `make migration msg="..."` and apply. *Note:* only emitted when `module_tables=`/`migrated_tables=` are passed to `run_diagnostics`; not surfaced by `make doctor` or boot |
| **SM012** | WARNING (dev only) | `register_settings` is overridden but nothing was added to `app.state.<module_lower>` | Either store the module's settings dataclass on `app.state.<module_lower>` or remove the empty override |
| **SM013** | WARNING | A locale file declared in `locale_dirs()` is missing for one of the supported locales | Create the file (even if empty) or trim `SM_I18N_SUPPORTED_LOCALES` |
| **SM014** | WARNING | A non-default locale is missing keys present in the default locale | Add the missing keys, or accept that a fallback to default applies |
| **SM015** | WARNING | A non-default locale has keys *not* present in the default | Remove dead keys from the non-default file or add them to default |
| **SM016** | ERROR | A locale JSON file is invalid or contains non-string leaves | Fix the JSON; only string leaves are allowed (interpolation is `{name}` placeholders) |
| **SM017** | WARNING | A module ships `.tsx` pages but is missing `package.json` / `tsconfig.json` | Add the JS workspace files so the host's frontend toolchain can resolve module imports |
| **SM018** | WARNING | An Inertia page calls `router.{post,patch,put,delete}()` targeting `/api/*` | Point the call at a view endpoint that returns `RedirectResponse(..., status_code=303)`, or use plain `fetch()` for the JSON endpoint; Inertia's client expects an Inertia response, not JSON |
| **SM019** | WARNING | A module registers view routes (non-empty `view_prefix` + overrides `register_routes`) but overrides neither `register_menu_items` nor `register_permissions` — its pages exist with no sidebar entry and no role-editor visibility | Add `register_menu_items()` (sidebar) or `register_permissions()` (role editor), or clear `view_prefix` if the module is API-only |
| **SM020** | ERROR | More than one auth provider module is installed | Install exactly one auth provider (e.g. `users` OR `keycloak`, not both) |
| **SM021** | WARNING | No auth provider module is installed | Install an auth provider module (e.g. `simple-module-users` or `simple-module-keycloak`) |

`SM002`, `SM005`, `SM006` don't exist in the implementation — they're reserved/retired and never emitted. `SM012` is the one code that doesn't come from the core diagnostics runner: it's raised from the hosting layer (`check_settings_registration`, after Phase 4 settings registration) and so is only ever seen at **dev boot**, not via `make doctor`.

Each finding prints across one to three lines, formatted as `<glyph> <CODE> [<LEVEL>] <module_name>: <message>`, with the glyph `✗` (error) / `⚠` (warning) / `ℹ` (info) — e.g. `✗ SM009 [ERROR] users: Framework package '...' directly imports from module package '...'`. A `↳ <file>` line and a `↳ Suggestion: <text>` line follow when present. The run ends with `Results: N error(s), N warning(s), N info`.

Warnings are load-bearing: the framework only emits one when something concrete *will* break under a specific condition (locale switch, schema downgrade, deploy ordering). They don't fail the prod boot — that's exactly why they're easy to ignore until the condition hits in production and becomes the next on-call page. If you're suppressing warnings in CI to make it green, you're trading the CI signal for that later runtime break.

## Related skills

- **simple-module-creating** — fixing SM001/SM007/SM008/SM017/SM019/SM020/SM021
- **simple-module-database** + **simple-module-migrations** — fixing SM010/SM011
- **simple-module-inertia-pages** — fixing SM003/SM004/SM018
- **simple-module-locales** — fixing SM013/SM014/SM015/SM016
- **simple-module-conventions** — fixing SM009/SM012
