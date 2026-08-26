# Commands

Two surfaces drive day-to-day work:

1. **The `smpy` CLI** — installed globally with `uv tool install simple_module_cli`. Used to scaffold apps and modules and to bump dependency versions.
2. **The Makefile in your scaffolded app** — a thin wrapper around `uv` and `npm` for the inner dev loop (`dev`, `migrate`, `build`, `gen-pages`).

Past those, there's no hidden tooling — read the `Makefile` and pyproject.toml in your app directly when something surprises you.

## `smpy` CLI

```bash
smpy --help
```

### Scaffolders

| Command | What |
|---|---|
| `smpy new <name>` | Scaffold a new app at `./<name>`. Interactive by default; pass `--yes` for defaults, `--preset minimal\|standard\|full`, `--with mod1,mod2` for extras, `--db sqlite\|postgres`, `--tenancy`, `--flat` (no `modules/` dir). |
| `smpy create-module <name>` | Scaffold a publishable module package at `./simple_module_<name>` (or `--dest <path>`). |
| `smpy create-host <name>` | Scaffold just a host project (no sample module). Useful when you want a minimal shell that consumes published modules. |

### Installing modules

| Command | What |
|---|---|
| `smpy add <spec>` | Add a module dependency and wire it up. `<spec>` is a PyPI requirement, a `git+URL[@ref][#subdirectory=dir]`, or a local path. Writes `pyproject.toml`, then runs `uv sync` + `gen-pages` unless `--no-sync`. |
| `smpy update [name]` | Update git-sourced modules to their newest release tag. Omit the name to update every git-sourced module; `--dry-run` previews. |

`smpy add` handles a repo containing several modules: `--module a,b` picks specific dist names and `--all` takes every module it finds.

Modules from one repo move **in lockstep** — one repo, one ref. `smpy update` takes every module sourced from the same URL to the same new tag, which must be a `v*` semver tag satisfying every sibling's declared dependency range. Mixing tags from one source tree is how you end up with a module built against a sibling it was never shipped with. Branch-pinned sources re-lock to the newest SHA (dev mode), rev-pinned sources are left alone, and a plain PyPI name delegates to `uv lock --upgrade-package`.

Both take `--path` to point at a project root or `pyproject.toml` other than the cwd. `smpy add` takes `--yes` to fail rather than prompt, which is what you want in CI.

### Authoring a module

Run these from inside a module package directory:

| Command | What |
|---|---|
| `smpy module verify` | Build this module's frontend inside a throwaway scaffolded host — catches "works in the monorepo, breaks as a wheel" before you publish. |
| `smpy module build` | Bundle `<pkg>/assets_src/` into `<pkg>/static/dist/` for `static_mounts()`. |

Both cache the scratch host under `.smpy/verify-host`; pass `--fresh` to rebuild it from scratch.

### Maintenance

| Command | What |
|---|---|
| `smpy package-update` | Bump every `simple_module_*` dependency in `pyproject.toml` to the latest PyPI version. `--dry-run` previews the diff. |
| `smpy skills add\|list\|update` | Install or update the bundled agent skills under `.claude/skills/` for use with Claude Code. |

### Module-contributed plugins

When a module declares a `simple_module_cli.cli_plugins` entry point, the CLI mounts it as a `sm <name> ...` subgroup. The bundled modules contribute:

| Command | From | What |
|---|---|---|
| `smpy host gen-pages` | `simple_module_hosting` | Regenerate `client_app/modules.{manifest.json,generated.ts,generated.css}` from the installed modules. Run when you add or remove pages. |
| `smpy host sync-js-deps` | `simple_module_hosting` | Install JS deps declared by wheel-installed modules into `client_app/node_modules`. In-repo workspace modules don't need this. |
| `smpy settings import-from-env` | `simple_module_settings` | One-shot migration: read every `SM_<MODULE>_*` env var and seed it as a SYSTEM-scope row in the DB-backed settings store. Idempotent. |

`smpy users create-admin` is contributed by the `users` module as a `smpy users` subcommand:

```bash
uv run smpy users create-admin --email admin@example.com --password changeme
```

## Scaffolded-app Makefile

`smpy new` writes a slim Makefile to your app. The intent is *zero magic* — every target is one or two lines you could run by hand.

| Command | What |
|---|---|
| `make install` | `uv sync` + `cd client_app && npm install` + `make sync-js-deps`. Re-runs are safe. |
| `make dev` | `make gen-pages`, then `uvicorn main:app --reload` on `:8000` and `vite` on `:5050` in parallel. |
| `make migrate` | `uv run alembic upgrade head`. Idempotent. |
| `make build` | `cd client_app && npm run build`. Produces the production frontend bundle. |
| `make gen-pages` | Regenerate the page manifest. Auto-runs before `make dev`. Same effect as `smpy host gen-pages`. |
| `make sync-js-deps` | Install JS deps from wheel-installed modules. Same effect as `smpy host sync-js-deps`. |

If you included `background_tasks` in `smpy new`, the scaffold appends `worker`, `beat`, and `worker-docker` targets that wrap the Celery commands — read your `Makefile` to see the exact invocations.

## Routine ops without a target

The scaffolded Makefile intentionally doesn't wrap one-off things. Run them directly:

| Need | Command |
|---|---|
| New Alembic migration | `uv run alembic revision --autogenerate -m "..."` |
| Downgrade one revision | `uv run alembic downgrade -1` |
| Roll back a single module | `uv run alembic downgrade <module>@base` |
| Single Python test | `uv run pytest path/to/test_file.py::test_name` |
| Single JS test | `cd client_app && npx vitest run <path>` |
| Format + lint Python | `uv run ruff format . && uv run ruff check .` |
| Type-check Python | `uv run ty check` |
| Format + lint JS | `cd client_app && npx biome check .` |
| Type-check JS | `cd client_app && npx tsc --noEmit` |
| Free stuck dev ports | `lsof -ti:8000,5050 \| xargs kill -9` |

## Working on the framework itself

If you're contributing to `simple_module_python` — not consuming it — the **framework repo's** Makefile is bigger: it includes `make new-module`, `make doctor`, `make lint`, `make test`, `make migration`, `make worker`, `make memray-run`, `make loadtest`, etc. Those targets exist because the framework repo is a multi-package workspace, not because they're the user-facing surface. See the [release playbook](/release) and the repo's `Makefile` for that flow.

## Next steps

- [Environment variables](/reference/env-vars) — every `SM_*` knob the framework reads.
- [Diagnostic codes](/reference/diagnostic-codes) — what each `SM0XX` from boot diagnostics means and how to fix it.
- [Deployment](/reference/deployment) — taking a build to production.
