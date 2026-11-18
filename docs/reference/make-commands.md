# Commands

Two surfaces drive day-to-day work:

1. **The `smpy` CLI** — installed globally with `uv tool install simple_module_cli` (upgrade with `uv tool upgrade simple_module_cli`). Used to scaffold apps and modules and to bump dependency versions.
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
| `smpy add <spec>` | Add a module dependency and wire it up. `<spec>` is a PyPI requirement, a `git+URL[@ref][#subdirectory=dir]`, or a local path. Writes `pyproject.toml`, then runs `uv sync`. If the host has a `client_app`, it runs `gen-pages`, installs JS dependencies declared by modules via `sync-js-deps` with `--save=false`, and skips `gen-i18n` when the i18n package is absent. Use `--no-sync` to skip these steps. Workspace apps sync from the app root with `uv sync --all-packages`. |
| `smpy update [name]` | Update git-sourced modules to their newest release tag. Omit the name to update every git-sourced module; `--dry-run` previews. |

`smpy add` handles a repo containing several modules: `--module a,b` picks specific dist names and `--all` takes every module it finds.

Modules from one repo move **in lockstep** — one repo, one ref. `smpy update` takes every module sourced from the same URL to the same new tag, which must be a `v*` semver tag satisfying every sibling's declared dependency range. Version bumps preserve explicit ceilings, excluded releases, and the implicit upper bound of `~=` constraints, so later updates still respect the original policy. Mixing tags from one source tree is how you end up with a module built against a sibling it was never shipped with. Branch-pinned sources re-lock to the newest SHA (dev mode), rev-pinned sources are left alone, and a plain PyPI name delegates to `uv lock --upgrade-package`.

Git tag updates also advance the dependency's version floor, preserving its
extras and environment marker. For example, updating to `v0.2.0` changes
`simple_module_blog[s3]>=0.1,<1.0; python_version >= "3.12"` to
`simple_module_blog[s3]>=0.2.0,<1.0; python_version >= "3.12"`.

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
| `smpy package-update` | Bump `simple_module_*` dependencies, optional extras and dependency groups across the uv workspace, keeping operators. Update root/member and `client_app/package.json` `@simple-module-py/*` pins to the selected core version when published on npm. `--dry-run` writes nothing; `--loosen` rewrites Python constraints to `>=`. |
| `smpy skills add\|list\|update` | Install or update the bundled agent skills under `.claude/skills/` for use with Claude Code. |

### Module-contributed plugins

When a module declares a `simple_module_cli.cli_plugins` entry point, the CLI mounts it as a `sm <name> ...` subgroup. The bundled modules contribute:

| Command | From | What |
|---|---|---|
| `smpy gen` | `simple_module_hosting` | Run pages, i18n keys, module JS dep sync and API types. Per-stage content hashes and output checks in the local `.smpy/gen.json` cache skip unchanged work without touching files. API generation covers local modules already carrying `pages/api.generated.ts`; use `smpy openapi gen-types --module <pkg>` to opt in. |
| `smpy dev` | `simple_module_hosting` | Generate first, then run API and Vite together. API defaults to 8000 (`--port`); Vite uses the first free port from 5050 (`--vite-port` pins it). Python reads dotenv and passes the selected `SM_VITE_DEV_URL` to both children. Ctrl-C, SIGTERM or either child exiting stops both owned process groups. |
| `smpy host gen-pages` | `simple_module_hosting` | Regenerate `client_app/modules.{manifest.json,generated.ts,generated.css,assets.json}` from the installed modules. Run when you add or remove pages or assets. |
| `smpy host gen-i18n` | `simple_module_hosting` | Regenerate `keys.generated.ts` and `generated-resources.ts` into the installed `@simple-module-py/i18n/src` directory (or `packages/i18n/src` in the framework repo) without booting the app. Fails if neither exists unless `--skip-if-missing` is set. |
| `smpy host sync-js-deps` | `simple_module_hosting` | Install module-declared JS deps into the host. Module-root npm workspace manifests are installed by npm automatically; dependency-only manifests inside Python packages need this sync even for editable installs. |
| `smpy settings import-from-env` | `simple_module_settings` | One-shot migration: read every `SM_<MODULE>_*` env var and seed it as a SYSTEM-scope row in the DB-backed settings store. Idempotent. |

`smpy users create-admin` is contributed by the `users` module as a `smpy users` subcommand:

```bash
uv run smpy users create-admin --email admin@example.com
```

## Scaffolded-app Makefile

`smpy new` defaults to a **workspace** layout: the app root owns the uv and npm workspaces and the Makefile; the host lives in `host/`, with its frontend in `host/client_app/` and local modules under `modules/`. `smpy new --flat` and `smpy create-host` use a **flat** layout: the host is at the app root and its frontend is in `client_app/`.

Run `make` from the app root in either layout. The current templates use `smpy gen` for generation and `smpy dev` to run API and Vite together:

| Command | Flat layout | Workspace layout |
|---|---|---|
| `make install` | `uv sync`, `cd client_app && npm install`, then `make gen`. | `uv sync --all-packages`, root `npm install`, then `make gen`. |
| `make dev-api` | `uv run uvicorn main:app --reload --reload-include '*locales/*.json' --port $(API_PORT)`. | Runs uvicorn from `host/`, also watching `.` and `../modules` with `--reload-dir`. |
| `make dev-ui` | `cd client_app && npm run dev`. | Root `npm run dev`, which delegates to the `host/client_app` npm workspace. |
| `make migrate` | `uv run alembic upgrade heads`. | `uv run --project host alembic -c host/alembic.ini upgrade heads`. |
| `make build` | `make gen`, then `cd client_app && npm run build`. | `make gen`, then root `npm run build` (delegates to `host/client_app`). |
| JS dependency sync | `make sync-js-deps`. | `make sync-module-deps`. |

Both JS dependency sync targets call `smpy host sync-js-deps` through its Python entry point. Root module npm manifests are installed by npm workspaces; manifests inside Python packages need this sync even for editable installs. Both migration targets apply **all** branch heads (`upgrade heads`, plural).

The remaining targets have the same purpose in both layouts:

| Command | What |
|---|---|
| `make install` | `uv sync` + `cd client_app && npm install` + `smpy gen`. Workspace apps use `uv sync --all-packages` and root `npm install`. Re-runs are safe. |
| `make dev` | Runs `uv run smpy dev`. Pass options with `make dev ARGS="--port 8010 --vite-port 5201"`. Vite auto-selects a free port when omitted. |
| `make migrate` | Apply all branch heads using the layout-specific command above. Idempotent. |
| `make build` | `smpy gen`, then `cd client_app && npm run build` (root `npm run build` in a workspace). Produces the production frontend bundle. |
| `make gen` | Same incremental pipeline as `uv run smpy gen`. Install, dev, build and module verify call it automatically. Generation errors stop startup/build. |
| `make gen-pages` | Regenerate `modules.manifest.json`, `modules.generated.ts`, `modules.generated.css` and `modules.assets.json` in the host's frontend directory. Install, dev and build include this stage via `smpy gen`. Same effect as `smpy host gen-pages`. |
| `make sync-js-deps` (flat) / `make sync-module-deps` (workspace) | Install module-declared JS deps as described above. Same effect as `smpy host sync-js-deps`. |
| `make gen-i18n` | Regenerate `keys.generated.ts` and `generated-resources.ts` for typed `t(keys.<ns>...)` calls. Writes into the installed `@simple-module-py/i18n/src`: under `client_app/node_modules` in a flat app or root `node_modules` in a workspace. Install, dev and build include this stage via `smpy gen`. Same effect as `smpy host gen-i18n`. |
| `make doctor` | Run module diagnostics, including migration state and table coverage. Structural checks also run at development boot; production does not run that suite. |
| `make kill` | Print stop guidance: Ctrl-C in the `smpy dev` terminal, or send SIGTERM to its supervisor PID. No processes are searched for or killed by port/name. |

If you included `background_tasks` in `smpy new`, the scaffold appends `worker`, `beat`, and `worker-docker` targets that wrap the Celery commands — read your `Makefile` to see the exact invocations.

## Routine ops without a target

The scaffolded Makefile intentionally doesn't wrap one-off things. Run them directly:

| Need | Command |
|---|---|
| New Alembic migration | `uv run alembic revision --autogenerate -m "..."` |
| Downgrade one revision | `uv run alembic downgrade -1` |
| Remove one module's schema | See [Removing one module's schema](/database/migrations#removing-one-modules-schema); `<module>@base` rolls back the whole chain beneath it |
| Single Python test | `uv run pytest path/to/test_file.py::test_name` |
| Single JS test | `cd client_app && npx vitest run <path>` |
| Format + lint Python | `uv run ruff format . && uv run ruff check .` |
| Type-check Python | `uv run ty check` |
| Format + lint JS | `cd client_app && npx biome check .` |
| Type-check JS | `cd client_app && npx tsc --noEmit` |
| Free stuck dev ports | Ctrl-C / SIGTERM the `smpy dev` supervisor |

## Working on the framework itself

If you're contributing to `simple_module_python` — not consuming it — the **framework repo's** Makefile is bigger: it includes `make new-module`, `make doctor`, `make lint`, `make test`, `make migration`, `make worker`, `make memray-run`, `make loadtest`, etc. Those targets exist because the framework repo is a multi-package workspace, not because they're the user-facing surface. See the [release playbook](/release) and the repo's `Makefile` for that flow.

## Next steps

- [Environment variables](/reference/env-vars) — every `SM_*` knob the framework reads.
- [Diagnostic codes](/reference/diagnostic-codes) — what each `SM0XX` from boot diagnostics means and how to fix it.
- [Deployment](/reference/deployment) — taking a build to production.

The individual generators remain available for explicit regeneration and CI. In the framework repo, `ci-i18n-fresh` and `ci-api-types-fresh` bypass the incremental cache and compare contents before/after generation, so stale committed files still fail. i18n output stays in the existing package location: its exports and type augmentation depend on those files; app-owned output needs a separate package integration change.
