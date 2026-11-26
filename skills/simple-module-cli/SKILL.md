---
name: simple-module-cli
description: Use when invoking the `uv run smpy` CLI for a simple_module_python project — starting a new app, scaffolding a host or a publishable module, bumping simple_module_* dependencies to their latest PyPI versions, regenerating the Inertia page manifest, importing settings overrides from env, creating an admin user, or installing the bundled agent skills. Triggers on "uv run smpy new", "uv run smpy create-host", "uv run smpy create-module", "uv run smpy update", "uv run smpy host gen-pages", "uv run smpy users create-admin", "uv run smpy skills add", or any unfamiliar `uv run smpy` subcommand.
---

# simple_module_python: the `uv run smpy` CLI

The `uv run smpy` command is provided by `simple_module_cli` (installed as a dep of `simple_module_hosting`); `simple-module` is an identical alias for the same entry point. It groups several kinds of operations: scaffolding new things, project-time helpers for the host, admin shortcuts for the bundled modules, installing the bundled agent skills, and bumping `simple_module_*` deps.

`new`, `create-host`, `create-module`, `add`, `update`, `migrations`, and `skills` are built into `simple_module_cli` and always present. `host` / `settings` / `users` are **plugin subgroups** contributed by installed packages (`simple_module_hosting` / `simple_module_settings` / `simple_module_users`) through the `simple_module_cli.cli_plugins` entry-point group — they only show up when that package is installed, which is why a fresh bare host won't list `uv run smpy users` until the users module is added.

## Top-level commands

| Command | When to use |
|---|---|
| `uv run smpy new <name>` | Greenfield: scaffold a complete app (host + selected modules) in one shot, with an interactive wizard for DB / tenancy / module preset |
| `uv run smpy create-host <name>` | You want just a bare host project; you'll add modules later by `pip install`-ing them |
| `uv run smpy create-module <name>` | You're adding a module to a `uv run smpy new` app (`--dest modules/<name>`), or authoring a publishable module package in its own repo |
| `uv run smpy update` | Update every `simple_module_*` / `simple-module-*` dependency, optional extra and dependency group to its latest non-yanked PyPI release, and `@simple-module-py/*` npm pins to the same core version (git tags update together per repo; workspace/path/URL sources stay local). Sync Python/npm lockfiles and run generation |
| `uv run smpy migrations prepare <upgrade-id> --head <label>@head` | Write the host-side revision for a framework data upgrade that boot or `make doctor` reported (`mail.settings_namespace_v1`, `users.hashed_bearer_tokens_v1`); it never applies it — run your migrate step afterwards |
| `uv run smpy doctor` | Run the module diagnostics (`SM0xx`, including `SM033` data-compatibility findings) against this host's database |
| `uv run smpy skills …` | Install / update the bundled agent-skill packs into a project (`add`, `list`, `update`) |
| `uv run smpy host …` | Project-time helpers run from inside a host directory (page manifest, JS dep sync) |
| `uv run smpy settings …` | Settings-module admin — currently `import-from-env` |
| `uv run smpy users …` | Users-module admin — currently `create-admin` |

## `uv run smpy new <name>` — the wizard

The fastest way from zero to a working app. It calls `create-host` under the hood, then installs and wires up the modules you pick.

App names must be **lowercase** with a single separator style (`my_app`, `my-app`, or `myapp`) — `uv run smpy new` rejects mixed case / spaces / mixed separators up front (`MyApp`, `foo_bar-baz` error out). `create-host` and `create-module` are lenient and accept any case.

```bash
# Interactive (asks for DB, tenancy, preset, module list)
uv run smpy new my_app

# Non-interactive: take all defaults (sqlite, no tenancy, standard preset)
uv run smpy new my_app --yes

# Pick a preset and add extras
uv run smpy new my_app --preset full --tenancy --db postgres
uv run smpy new my_app --preset minimal --with background_tasks,file_storage --yes

# Consume-only host: no modules/ dir, no sample module to author against
uv run smpy new my_app --preset standard --flat --yes

# Scaffold only — skip uv sync / npm install / the initial migration
uv run smpy new my_app --no-install
```

**Module presets:**

| Preset | Modules included |
|---|---|
| `minimal` | `users` (and `auth` as a dep) |
| `standard` (default) | `users`, `dashboard`, `permissions` (+ deps) |
| `full` | every module **in the scaffolder catalog** (the 8 keys below) — *not* every module in the monorepo |
| `custom` | interactive — pick each catalog module yes/no |

`--preset` only accepts `minimal`, `standard`, or `full`. **`custom` is wizard-only** — there's no `--preset custom`; to hand-pick modules non-interactively, start from any preset and add the rest with `--with`.

`--with` accepts a comma-separated list of catalog keys (`auth, users, permissions, dashboard, settings, feature_flags, file_storage, background_tasks`). Transitive `requires` are auto-added; the wizard prints `Added X (required by Y)` so you can see what got pulled in. An unknown key fails fast with the available list (so `--with=does_not_exist` is self-correcting). Note the catalog is a curated subset — repo modules like `keycloak`, `audit_log`, and `branding` are **not** catalog keys; add those to an existing host by installing the package (see the pitfall below).

Selecting `background_tasks` also runs its post-scaffold **recipe**: it drops `docker-compose.yml`, `scripts/run_worker.py`, a shared app/worker Dockerfile, an `SM_REDIS_URL` entry in `.env.example`, and Celery `make` targets. App, worker and beat share that one Redis URL; `uv run smpy docker add-worker` copies it. Keep `SM_BG_TASKS_BROKER_URL` / `SM_BG_TASKS_RESULT_BACKEND` for per-field overrides such as non-Redis transports. The closing "Next steps" then reminds you to run `docker compose up -d redis worker beat` for the worker/beat processes.

**Options summary:**

| Flag | Default | Meaning |
|---|---|---|
| `--dest <PATH>` | `./<name>` | Where to write the project |
| `--db sqlite\|postgres` | `sqlite` | Backend configured in `.env.example` |
| `--tenancy / --no-tenancy` | `--no-tenancy` | Enable the multi-tenant middleware |
| `--preset minimal\|standard\|full` | wizard asks | Module bundle (no `custom` — that's wizard-only) |
| `--with <names>` | none | Extra catalog keys beyond the preset |
| `--flat` | off | Skip the `modules/` directory and the sample module — for a host that only ever consumes published modules and never authors its own |
| `--yes / -y` | off | Skip prompts; accept defaults |
| `--no-install` | off | Skip `uv sync` / `npm install` / the autogenerated initial migration; the printed next steps use `make migration` / `make migrate` / `make dev` instead |

Passing `--preset` or any `--with` value switches `uv run smpy new` into flag-driven mode (no wizard) even without `--yes`; DB and tenancy then come from `--db` / `--tenancy` defaults. The validated name is also normalized to a PyPI-safe kebab-case slug — `uv run smpy new my_app` prints `Normalizing PyPI name to 'my-app'.` and uses that for the package metadata.

## `uv run smpy create-host <name>` — bare host

```bash
uv run smpy create-host MyApp                       # empty host, no modules declared
uv run smpy create-host MyApp --with Auth,Products  # declare module deps in pyproject.toml
uv run smpy create-host MyApp --dest ./apps/myapp   # custom destination
```

`--with` takes **PascalCase module names** (matching `ModuleMeta.name`), not catalog keys — each is lowercased into a `simple_module_<name>` dependency in `pyproject.toml`. Unlike `uv run smpy new`, the names are **not** checked against the scaffolder catalog, so any published module works (e.g. `--with Products` → `simple_module_products`). Products above is an example published module, not a module in this monorepo. No deps are installed and no transitive `requires` are resolved; you drive `uv sync` and migrations yourself. Use this when you want to wire the build by hand rather than via `uv run smpy new`'s wizard.

## `uv run smpy create-module <name>` — module package

Scaffolds one module package: inside a `uv run smpy new` app, or as a standalone repo to publish to PyPI.

```bash
uv run smpy create-module orders --dest modules/orders   # inside an app: a workspace member
uv run smpy create-module orders                         # writes ./simple_module_orders/
```

Inside a workspace app, `uv run smpy create-module` wires the module into the host,
runs `uv sync --all-packages` and `npm install` from the app root, then `uv run smpy gen`.
The next step is `uv run smpy migrations new orders -m "init"`; review the revision,
run `make migrate` and restart `make dev`. Do not sync from inside the module.
Outside an app, the scaffolder keeps the standalone package flow.

Settings are opt-in: pass `--with-settings` to add `core/settings.py`,
`core/services.py` and the DB-backed `register_settings` hook. Without it,
none of that plumbing is generated. In this repo use
`make new-module name=orders ARGS=--with-settings`.

The result is a complete package: `pyproject.toml` with the entry point declared, `module.py` with `ModuleBase`/`ModuleMeta` skeleton, `models.py`, `contracts/`, `web/endpoints/{api,views}.py`, `pages/`, `locales/en.json`, `core/constants.py`, `web/{deps,service}.py`, plus nested `tests/<area>/<feature>/test_<module>_*.py` wired up with `simple_module_test` fixtures.

`<name>` accepts any case — `orders`, `Orders`, `ORDERS`, `blog_posts` all work. The CLI lowercases it for the directory and PascalCases it for `ModuleMeta.name`.

For the post-scaffold steps (entry point, Inertia namespace, etc.) see **simple-module-creating**.

## `uv run smpy update` — update pins and install

Walks the project's `pyproject.toml` (plus every `[tool.uv.workspace]` member), finds each dependency whose distribution name matches `simple_module_*` / `simple-module-*`, queries PyPI for the latest non-yanked release, and rewrites the constraint to the latest release, keeping its operator (`==` stays `==`, `>=` stays `>=`; `--loosen` rewrites to `>=<latest>`). It covers `[project] dependencies`, optional-dependency extras and `[dependency-groups]`. It also bumps `@simple-module-py/*` pins in each root/member `package.json` and `client_app/package.json` to the selected `simple_module_core` version (keeping `^`/`~`, never downgrading, skipping versions not on npm or when the Python core pin was held back). PyPI lookups run in parallel, so it's quick even across a multi-package workspace.

```bash
uv run smpy update                      # rewrite constraints in ./pyproject.toml (+ workspace members)
uv run smpy update --dry-run            # show "old  →  new" per file, write nothing
uv run smpy update --include-pre        # also consider pre-releases (a/b/rc/dev/post)
uv run smpy update --path apps/web      # point at another project root or a pyproject.toml
```

| Flag | Default | Meaning |
|---|---|---|
| `--path <DIR\|FILE>` | cwd | Project root or an explicit `pyproject.toml` |
| `--dry-run` | off | Print planned changes only; don't write |
| `--include-pre` | off | Allow pre-release versions as the "latest" |
| `--loosen` | off | Rewrite Python constraints to `>=<latest>` instead of keeping their operator |

Git sources move together per repository URL to a compatible release tag; branch
sources refresh their locked SHA, and immutable revisions stay pinned. Workspace,
path and URL sources stay unchanged. After editing manifests, the command runs
`uv sync` (`--all-packages` at a workspace root), `npm install` where the frontend
lives, then `uv run smpy gen`. Python-only apps skip frontend steps. A failed step stops
the command; fix it and rerun. `uv run smpy package-update` is a deprecated alias, removed
in 0.0.50. `--dry-run` neither writes nor installs.

## `uv run smpy migrations prepare` — framework data upgrades

A scaffolded host owns its Alembic history, so framework data migrations don't
reach it. When boot (outside development it refuses on an `error`) or
`make doctor` (`SM033`) names an upgrade id, generate the revision into the
host and apply it like any other:

```bash
uv run smpy migrations prepare users.hashed_bearer_tokens_v1 --head users@head
uv run alembic -c host/alembic.ini upgrade heads
```

The token upgrade deletes existing bearer tokens before altering the columns,
so every client signs in again; stop old workers first.

## `uv run smpy skills` — install the bundled agent skills

`simple_module_cli` ships a set of [SKILL.md](https://agentskills.io/specification) packs (the ones in this directory). Drop them into any project so Claude Code / Cursor / Codex / etc. find them automatically.

```bash
uv run smpy skills list                                          # see what's available
uv run smpy skills add                                           # install ALL skills into ./.claude/skills/
uv run smpy skills add simple-module-creating simple-module-cli  # specific ones only
uv run smpy skills add -g                                        # ~/.claude/skills (machine-wide)
uv run smpy skills add --dest agents/skills                      # explicit target dir
uv run smpy skills add --symlink                                 # symlink to bundled source (good when iterating on the skills themselves)
uv run smpy skills update                                        # re-pull whatever is already installed at the dest
uv run smpy skills update simple-module-doctor                   # explicitly re-pull one (always force-overwrites)
```

**Without `--force`, `uv run smpy skills add` skips skills that already exist at the destination** — so re-running it is safe. Use `--force` (or `uv run smpy skills update`) to overwrite.

The bundle resolves against your installed `simple_module_cli`. To get newer skills, upgrade the CLI (`uv sync` or `pip install -U simple_module_cli`) and re-run `uv run smpy skills update`.

## `uv run smpy gen` and `uv run smpy dev` — the normal app loop

Run `uv run smpy gen` from the app root to generate pages, i18n keys, module npm deps and local API types together. Install, dev, build and module verify call it automatically. Content hashes and output checks in the local `.smpy/gen.json` cache skip unchanged stages without touching files. Generation failures stop dev/build. Existing individual generator commands and their flags remain available; CI freshness checks run them unconditionally. i18n output belongs to editable modules and the app client directory; the framework repo also retains central compatibility exports. Installed npm packages are never rewritten.

Run `uv run smpy dev` to generate first and supervise API + Vite. API defaults to 8000; choose a spare one with `--port 8201`. Vite chooses the first free port from 5050; `--vite-port 5201` pins it and fails if occupied. Python loads dotenv (exported env wins), then passes the selected `SM_VITE_DEV_URL` to both children. Do not parse dotenv in Vite or Make. Ctrl-C/SIGTERM stops only the child process groups the supervisor started, including reload workers. Either child exiting stops the other. `make dev ARGS="--port 8201"` is equivalent in a scaffold; the framework repo first starts its shared Docker services. `make kill` prints stop guidance without searching by process name or port.

## `uv run smpy host gen-pages` — regenerate the Inertia manifest

Run from a host project. Scans every installed module's `pages/*.tsx`, writes `client_app/modules.{manifest.json,generated.ts,generated.css}`, and extends Vite's `server.fs.allow`.

```bash
uv run smpy host gen-pages                              # uses ./client_app
uv run smpy host gen-pages --host-dir=apps/web/client_app
```

`uv run smpy new` runs this at scaffold time; you only need to call it manually after adding/renaming `.tsx` files mid-session, or after `pip install`-ing a new module that ships pages.

## `uv run smpy host typecheck`

Checks the host and installed module sources using generated defaults; existing
module tsconfig.json files override the defaults. CI typecheck rejects uninstalled
workspace modules with frontend sources; frontend builds pass `--installed-only`
to allow intentional exclusions. Test files run through Vitest.
Run `uv run smpy host typecheck --host-dir=client_app` after gen-pages. Standalone modules
use `uv run smpy module verify` to install a host toolchain and run typecheck plus Vite.

## `uv run smpy host sync-js-deps` — install module JS deps

Wheel-installed modules ship `package.json` declarations that need to land in the host's `client_app/node_modules`. This command does that. **Module-root workspace manifests don't need it** — npm workspaces install those automatically. A dependency-only manifest inside the Python package ships in wheels without extra packaging config and needs this sync even for an editable install. Modules with no extra deps need no manifest.

```bash
uv run smpy host sync-js-deps                           # uses ./client_app
uv run smpy host sync-js-deps --host-client-app=apps/web/client_app
uv run smpy host sync-js-deps --dry-run                 # print the npm install command without running it
```

Run after `pip install <module>` if the new module ships frontend code.

## `uv run smpy settings import-from-env`

Walks the live environment for every `SM_<PREFIX>_<FIELD>` variable matching a registered settings dataclass and writes a SYSTEM-tier override into the settings module's store. Useful when promoting from environment-driven config (typical in Docker) to in-DB overrides (manageable in the admin UI) without re-keying values by hand.

```bash
uv run smpy settings import-from-env
```

## `uv run smpy users create-admin`

Bootstraps the first admin user, or rotates an existing admin's password.

```bash
uv run smpy users create-admin -e admin@example.com                       # prompts for the password
uv run smpy users create-admin -e admin@example.com -p hunter2
uv run smpy users create-admin -e admin@example.com -p new-password --force      # rotate
uv run smpy users create-admin -e admin@example.com -p hunter2 --full-name "Admin"
```

| Flag | Meaning |
|---|---|
| `-e, --email` (required) | Admin email |
| `-p, --password` (required) | Initial password (or new password with `--force`) |
| `--full-name` | Display name |
| `--force` | Update the password if the admin already exists; without it, the command exits if the email is taken |

Don't bake `--password` literals into a script you commit; use a secrets store and pass via shell expansion.

## The project CLI (`smdev`)

A host can ship its own CLI over its REST API, generated from a bundled OpenAPI schema by `simple_module_remote` (`build_cli(name, schema_path, defaults_path)`). The dev host's is `uv run smdev`:

```bash
uv run smdev env add local --url http://localhost:8000
printf '%s\n' "$PAT" | uv run smdev --env local login --token-stdin
uv run smdev whoami
uv run smdev users admin-list-users -o json
uv run smdev users admin-update-user <id> --set email=a@b.c --set full_name=Ada --dry-run
```

Only operations a personal access token may call (`x-sm-token`) exist as commands. In CI set `SMDEV_ENV` and `SMDEV_TOKEN`. After an API change run `make cli-schema` and commit `host_cli/smdev_cli/openapi.json`. See `docs/guide/project-cli.md`.

## Pitfalls

- **Wrong shell for `--with`.** `uv run smpy new` `--with auth,users` (catalog keys, lowercase). `uv run smpy create-host` `--with Auth,Users` (`ModuleMeta.name`, PascalCase). They're not interchangeable.
- **Ran `uv run smpy new` inside an existing project.** The default `--dest ./<name>` creates a sibling directory. If the directory already exists and is non-empty, the command errors out — pass `--dest` explicitly to disambiguate.
- **Ran `uv run smpy host gen-pages` from outside the host directory.** Defaults to `./client_app`; pass `--host-dir` from elsewhere.
- **Forgot `uv run smpy host sync-js-deps` after `pip install`-ing a module with pages.** Vite resolves module imports against `client_app/node_modules`; the new module's JS deps won't land until you sync.
- **Ran `uv sync` inside a module of a `uv run smpy new` app.** That syncs the module's own project and uninstalls the app's other packages from the shared venv. Run `make install` (`uv sync --all-packages`) at the app root instead; a plain `uv sync` at the root also works, since the root depends on the host.
- **`uv run smpy` warns that the app uses another framework version, or `uv run smpy doctor` says the CLI is not installed in the project's venv.** The app CLI is missing; run `uv sync --all-packages` so the app's own CLI is installed, then `uv run smpy …`.
- **Editing `locales/*.json` doesn't reload `make dev`** in an app made before 0.0.47: add `--reload-include '*locales/*.json'` to the `uvicorn` line of `dev-api`.
- **A module added while `make dev` runs logs "installed but … cannot be imported in this process".** The reload keeps the import path the server started with; restart `make dev`.
- **Calling `uv run smpy users create-admin` before migrations have run.** The users tables don't exist yet; the command will error. Run `alembic upgrade heads` first (or use `uv run smpy new` which does it for you when `--no-install` isn't set).
- **Expecting `--with keycloak` (or `audit_log` / `branding`) to work on `uv run smpy new`.** Those modules exist in the monorepo but aren't scaffolder-catalog keys, so `uv run smpy new --with keycloak` errors. Either scaffold without them and `pip install simple_module_keycloak` into the host afterward, or use `uv run smpy create-host MyApp --with Keycloak` (which doesn't validate against the catalog).
- **Port 5050 already taken when starting a scaffolded app.** Use `uv run smpy dev`: it selects a free Vite port automatically. Pin with `--vite-port 5310` only when needed; change the API with `--port 8010`.
- **`uv run smpy update` "did nothing" for a workspace dep.** Deps sourced from a `[tool.uv.sources]` workspace/path/URL entry are intentionally skipped (their version isn't on PyPI) — they show up in the output as `skipped`, not updated. Git refs update separately; the command also installs and generates.

## Related skills

- **simple-module-creating** — what `uv run smpy create-module` produces and the post-scaffold contract
- **simple-module-inertia-pages** — what `uv run smpy host gen-pages` regenerates and why
- **simple-module-migrations** — the migration step `uv run smpy new` runs (`make migration` + `make migrate`, or `alembic upgrade heads` directly)
