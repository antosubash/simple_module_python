---
name: simple-module-doctor
description: Use when interpreting a simple_module_python diagnostic code (SM001–SM018) printed at boot or by the diagnostics runner — what the code means, whether it's blocking, and the concrete fix. Triggers on any "SMnnn" code in logs, "InvalidModuleError", "module silently doesn't load", or "production failed boot".
---

# simple_module_python: diagnostics

Diagnostics run automatically at host boot. **In development**, warnings and errors land in the boot logs and the host keeps running. **In production** (`SM_ENVIRONMENT != development`), errors fail the boot — by design, because a module silently dropping out in prod is worse than a crash.

You can also call `run_diagnostics(...)` from `simple_module_core` programmatically (e.g. in a CI job) to surface issues without booting the full app.

## Code reference

| Code | Level | What it means | Fix |
|---|---|---|---|
| **SM001** | ERROR | Module class is missing `meta = ModuleMeta(...)` or it's malformed | Add a valid `meta` class attribute on the `ModuleBase` subclass |
| **SM003** | WARNING | A `pages/<Name>.tsx` exists but no `inertia.render("<Module>/<Name>", ...)` references it | Either delete the orphan file or wire up the render call |
| **SM004** | WARNING | `inertia.render("<Module>/<Name>", ...)` is called but no matching `.tsx` exists | Fix the render-key typo or create the page file |
| **SM007** | INFO | Module overrides no `register_*` hooks at all — likely scaffolded but empty | Either implement at least one hook or delete the module if unused |
| **SM008** | ERROR | Two modules declare the same `ModuleMeta.name` (Postgres-schema / SQLite-prefix collision) | Rename one module's `meta.name` |
| **SM009** | ERROR | A `framework/*` package directly imports from a plugin module (`modules/*`) | Move the symbol *up* into `simple_module_core` / `simple_module_hosting`, or invert the dependency via the event bus / a registry |
| **SM010** | ERROR | Live DB revision is behind the migration head | Run `alembic upgrade head` before booting; in CI, ensure migrations are part of the deploy step |
| **SM011** | WARNING | A module declares a SQLModel table that has no entry in migration history | Run `alembic revision --autogenerate -m "..."` and apply |
| **SM012** | WARNING (dev only) | `register_settings` is overridden but nothing was added to `app.state.<module_lower>` | Either store the module's settings dataclass on `app.state.<module_lower>` or remove the empty override |
| **SM013** | WARNING | A locale file declared in `locale_dirs()` is missing for one of the supported locales | Create the file (even if empty) or trim `SM_I18N_SUPPORTED_LOCALES` |
| **SM014** | WARNING | A non-default locale is missing keys present in the default locale | Add the missing keys, or accept that a fallback to default applies |
| **SM015** | WARNING | A non-default locale has keys *not* present in the default | Remove dead keys from the non-default file or add them to default |
| **SM016** | ERROR | A locale JSON file is invalid or contains non-string leaves | Fix the JSON; only string leaves are allowed (interpolation is `{name}` placeholders) |
| **SM017** | WARNING | A module ships `.tsx` pages but is missing `package.json` / `tsconfig.json` | Add the JS workspace files so the host's frontend toolchain can resolve module imports |
| **SM018** | WARNING | An Inertia page calls `router.{post,patch,put,delete}()` targeting `/api/*` | Use plain `fetch()` for JSON endpoints; Inertia's client expects an Inertia response, not JSON |

Codes `SM002`, `SM005`, `SM006` are reserved/retired — don't try to look them up. Output format is one line per finding, e.g. `[SM009] ERROR: <subject>`.

Warnings are load-bearing: the framework only emits one when something concrete *will* break under a specific condition (locale switch, schema downgrade, deploy ordering). Ignored long enough they become the next on-call page. If you're suppressing warnings in CI to make it green, you're trading the CI signal for a production-boot failure later.

## Related skills

- **simple-module-creating** — fixing SM001/SM007/SM008
- **simple-module-database** + **simple-module-migrations** — fixing SM010/SM011
- **simple-module-inertia-pages** — fixing SM003/SM004/SM018
- **simple-module-conventions** — fixing SM009/SM012 and locale codes
