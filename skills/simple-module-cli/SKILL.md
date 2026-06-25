---
name: simple-module-cli
description: Use when invoking the `smpy` CLI for a simple_module_python project — starting a new app, scaffolding a host or a publishable module, bumping simple_module_* dependencies to their latest PyPI versions, regenerating the Inertia page manifest, importing settings overrides from env, creating an admin user, or installing the bundled agent skills. Triggers on "smpy new", "smpy create-host", "smpy create-module", "smpy package-update", "smpy host gen-pages", "smpy users create-admin", "smpy skills add", or any unfamiliar `smpy` subcommand.
---

# simple_module_python: the `smpy` CLI

The `smpy` command is provided by `simple_module_cli` (installed as a dep of `simple_module_hosting`); `simple-module` is an identical alias for the same entry point. It groups several kinds of operations: scaffolding new things, project-time helpers for the host, admin shortcuts for the bundled modules, installing the bundled agent skills, and bumping `simple_module_*` deps.

`new`, `create-host`, `create-module`, `package-update`, and `skills` are built into `simple_module_cli` and always present. `host` / `settings` / `users` are **plugin subgroups** contributed by installed packages (`simple_module_hosting` / `simple_module_settings` / `simple_module_users`) through the `simple_module_cli.cli_plugins` entry-point group — they only show up when that package is installed, which is why a fresh bare host won't list `smpy users` until the users module is added.

## Top-level commands

| Command | When to use |
|---|---|
| `smpy new <name>` | Greenfield: scaffold a complete app (host + selected modules) in one shot, with an interactive wizard for DB / tenancy / module preset |
| `smpy create-host <name>` | You want just a bare host project; you'll add modules later by `pip install`-ing them |
| `smpy create-module <name>` | You're authoring a publishable module package (separate repo, distributed via PyPI) |
| `smpy package-update` | Bump every `simple_module_*` / `simple-module-*` dependency in `pyproject.toml` to its latest non-yanked PyPI release (workspace/path/git/URL sources are left untouched) |
| `smpy skills …` | Install / update the bundled agent-skill packs into a project (`add`, `list`, `update`) |
| `smpy host …` | Project-time helpers run from inside a host directory (page manifest, JS dep sync) |
| `smpy settings …` | Settings-module admin — currently `import-from-env` |
| `smpy users …` | Users-module admin — currently `create-admin` |

## `smpy new <name>` — the wizard

The fastest way from zero to a working app. It calls `create-host` under the hood, then installs and wires up the modules you pick.

App names must be **lowercase** with a single separator style (`my_app`, `my-app`, or `myapp`) — `smpy new` rejects mixed case / spaces / mixed separators up front (`MyApp`, `foo_bar-baz` error out). `create-host` and `create-module` are lenient and accept any case.

```bash
# Interactive (asks for DB, tenancy, preset, module list)
smpy new my_app

# Non-interactive: take all defaults (sqlite, no tenancy, standard preset)
smpy new my_app --yes

# Pick a preset and add extras
smpy new my_app --preset full --tenancy --db postgres
smpy new my_app --preset minimal --with background_tasks,file_storage --yes

# Consume-only host: no modules/ dir, no sample module to author against
smpy new my_app --preset standard --flat --yes

# Scaffold only — skip uv sync / npm install / the initial migration
smpy new my_app --no-install
```

**Module presets:**

| Preset | Modules included |
|---|---|
| `minimal` | `users` (and `auth` as a dep) |
| `standard` (default) | `users`, `dashboard`, `permissions` (+ deps) |
| `full` | every module **in the scaffolder catalog** (the 8 keys below) — *not* every module in the monorepo |
| `custom` | interactive — pick each catalog module yes/no |

`--preset` only accepts `minimal`, `standard`, or `full`. **`custom` is wizard-only** — there's no `--preset custom`; to hand-pick modules non-interactively, start from any preset and add the rest with `--with`.

`--with` accepts a comma-separated list of catalog keys (`auth, users, permissions, dashboard, settings, feature_flags, file_storage, background_tasks`). Transitive `requires` are auto-added; the wizard prints `Added X (required by Y)` so you can see what got pulled in. An unknown key fails fast with the available list (so `--with=does_not_exist` is self-correcting). Note the catalog is a curated subset — repo modules like `products`, `keycloak`, and `audit_log` are **not** catalog keys; add those to an existing host by installing the package (see the pitfall below).

Selecting `background_tasks` also runs its post-scaffold **recipe**: it drops `docker-compose.yml`, `scripts/run_worker.py`, host/worker Dockerfiles, a `SM_BG_TASKS_BROKER_URL` entry in `.env.example`, and Celery `make` targets. The closing "Next steps" then reminds you to run `docker compose up -d redis worker beat` for the worker/beat processes.

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

Passing `--preset` or any `--with` value switches `smpy new` into flag-driven mode (no wizard) even without `--yes`; DB and tenancy then come from `--db` / `--tenancy` defaults. The validated name is also normalized to a PyPI-safe kebab-case slug — `smpy new my_app` prints `Normalizing PyPI name to 'my-app'.` and uses that for the package metadata.

## `smpy create-host <name>` — bare host

```bash
smpy create-host MyApp                       # empty host, no modules declared
smpy create-host MyApp --with Auth,Products  # declare module deps in pyproject.toml
smpy create-host MyApp --dest ./apps/myapp   # custom destination
```

`--with` takes **PascalCase module names** (matching `ModuleMeta.name`), not catalog keys — each is lowercased into a `simple_module_<name>` dependency in `pyproject.toml`. Unlike `smpy new`, the names are **not** checked against the scaffolder catalog, so any published module works (e.g. `--with Products` → `simple_module_products`). No deps are installed and no transitive `requires` are resolved; you drive `uv sync` and migrations yourself. Use this when you want to wire the build by hand rather than via `smpy new`'s wizard.

## `smpy create-module <name>` — module package

For module authors publishing to PyPI. Scaffolds a standalone repo containing one module.

```bash
smpy create-module orders                    # writes ./simple_module_orders/
smpy create-module orders --dest ./packages/orders
```

The result is a complete package: `pyproject.toml` with the entry point declared, `module.py` with `ModuleBase`/`ModuleMeta` skeleton, `models.py`, `contracts/`, `endpoints/{api,views}.py`, `pages/`, `locales/en.json`, plus a tests directory wired up with `simple_module_test` fixtures.

`<name>` accepts any case — `orders`, `Orders`, `ORDERS`, `blog_posts` all work. The CLI lowercases it for the directory and PascalCases it for `ModuleMeta.name`.

For the post-scaffold steps (entry point, Inertia namespace, etc.) see **simple-module-creating**.

## `smpy package-update` — bump `simple_module_*` deps

Walks the project's `pyproject.toml` (plus every `[tool.uv.workspace]` member), finds each dependency whose distribution name matches `simple_module_*` / `simple-module-*`, queries PyPI for the latest non-yanked release, and rewrites the constraint to `name>=<latest>`. PyPI lookups run in parallel, so it's quick even across a multi-package workspace.

```bash
smpy package-update                      # rewrite constraints in ./pyproject.toml (+ workspace members)
smpy package-update --dry-run            # show "old  →  new" per file, write nothing
smpy package-update --include-pre        # also consider pre-releases (a/b/rc/dev/post)
smpy package-update --path apps/web      # point at another project root or a pyproject.toml
```

| Flag | Default | Meaning |
|---|---|---|
| `--path <DIR\|FILE>` | cwd | Project root or an explicit `pyproject.toml` |
| `--dry-run` | off | Print planned changes only; don't write |
| `--include-pre` | off | Allow pre-release versions as the "latest" |

**Deps it deliberately skips:** anything whose `[tool.uv.sources]` entry points at a workspace member, a local `path`, a `git` ref, or a `url` — those don't come from PyPI, so their version lives elsewhere. Skipped deps are listed with a reason (`workspace/local source`, `not found on PyPI`). The command only edits constraints; **run `uv sync` afterward** to actually install the new versions (it reminds you to).

## `smpy skills` — install the bundled agent skills

`simple_module_cli` ships a set of [SKILL.md](https://agentskills.io/specification) packs (the ones in this directory). Drop them into any project so Claude Code / Cursor / Codex / etc. find them automatically.

```bash
smpy skills list                                          # see what's available
smpy skills add                                           # install ALL skills into ./.claude/skills/
smpy skills add simple-module-creating simple-module-cli  # specific ones only
smpy skills add -g                                        # ~/.claude/skills (machine-wide)
smpy skills add --dest agents/skills                      # explicit target dir
smpy skills add --symlink                                 # symlink to bundled source (good when iterating on the skills themselves)
smpy skills update                                        # re-pull whatever is already installed at the dest
smpy skills update simple-module-doctor                   # explicitly re-pull one (always force-overwrites)
```

**Without `--force`, `smpy skills add` skips skills that already exist at the destination** — so re-running it is safe. Use `--force` (or `smpy skills update`) to overwrite.

The bundle resolves against your installed `simple_module_cli`. To get newer skills, upgrade the CLI (`uv sync` or `pip install -U simple_module_cli`) and re-run `smpy skills update`.

## `smpy host gen-pages` — regenerate the Inertia manifest

Run from a host project. Scans every installed module's `pages/*.tsx`, writes `client_app/modules.{manifest.json,generated.ts,generated.css}`, and extends Vite's `server.fs.allow`.

```bash
smpy host gen-pages                              # uses ./client_app
smpy host gen-pages --host-dir=apps/web/client_app
```

`smpy new` runs this at scaffold time; you only need to call it manually after adding/renaming `.tsx` files mid-session, or after `pip install`-ing a new module that ships pages.

## `smpy host sync-js-deps` — install module JS deps

Wheel-installed modules ship `package.json` declarations that need to land in the host's `client_app/node_modules`. This command does that. **In-repo workspace modules don't need it** — npm workspaces resolve them automatically.

```bash
smpy host sync-js-deps                           # uses ./client_app
smpy host sync-js-deps --host-client-app=apps/web/client_app
smpy host sync-js-deps --dry-run                 # print the npm install command without running it
```

Run after `pip install <module>` if the new module ships frontend code.

## `smpy settings import-from-env`

Walks the live environment for every `SM_<PREFIX>_<FIELD>` variable matching a registered settings dataclass and writes a SYSTEM-tier override into the settings module's store. Useful when promoting from environment-driven config (typical in Docker) to in-DB overrides (manageable in the admin UI) without re-keying values by hand.

```bash
smpy settings import-from-env
```

## `smpy users create-admin`

Bootstraps the first admin user, or rotates an existing admin's password.

```bash
smpy users create-admin -e admin@example.com -p hunter2
smpy users create-admin -e admin@example.com -p new-password --force      # rotate
smpy users create-admin -e admin@example.com -p hunter2 --full-name "Admin"
```

| Flag | Meaning |
|---|---|
| `-e, --email` (required) | Admin email |
| `-p, --password` (required) | Initial password (or new password with `--force`) |
| `--full-name` | Display name |
| `--force` | Update the password if the admin already exists; without it, the command exits if the email is taken |

Don't bake `--password` literals into a script you commit; use a secrets store and pass via shell expansion.

## Pitfalls

- **Wrong shell for `--with`.** `smpy new` `--with auth,users` (catalog keys, lowercase). `smpy create-host` `--with Auth,Users` (`ModuleMeta.name`, PascalCase). They're not interchangeable.
- **Ran `smpy new` inside an existing project.** The default `--dest ./<name>` creates a sibling directory. If the directory already exists and is non-empty, the command errors out — pass `--dest` explicitly to disambiguate.
- **Ran `smpy host gen-pages` from outside the host directory.** Defaults to `./client_app`; pass `--host-dir` from elsewhere.
- **Forgot `smpy host sync-js-deps` after `pip install`-ing a module with pages.** Vite resolves module imports against `client_app/node_modules`; the new module's JS deps won't land until you sync.
- **Used `smpy create-module` to add a module to an existing host.** That command is for **publishable** packages, intended to live in their own repo. To add a module to an existing host: install it (`pip install simple_module_<name>` or add to `pyproject.toml` and `uv sync`), then autogenerate a migration. See **simple-module-creating** + **simple-module-migrations**.
- **Calling `smpy create-admin` before migrations have run.** The users tables don't exist yet; the command will error. Run `alembic upgrade head` first (or use `smpy new` which does it for you when `--no-install` isn't set).
- **Expecting `--with products` (or `keycloak` / `audit_log`) to work on `smpy new`.** Those modules exist in the monorepo but aren't scaffolder-catalog keys, so `smpy new --with products` errors. Either scaffold without them and `pip install simple_module_products` into the host afterward, or use `smpy create-host --with Products` (which doesn't validate against the catalog).
- **`smpy package-update` "did nothing" for a workspace dep.** Deps sourced from a `[tool.uv.sources]` workspace/path/git/URL entry are intentionally skipped (their version isn't on PyPI) — they show up in the output as `skipped`, not updated. Also remember to run `uv sync` after; `package-update` only rewrites the constraint strings.

## Related skills

- **simple-module-creating** — what `smpy create-module` produces and the post-scaffold contract
- **simple-module-inertia-pages** — what `smpy host gen-pages` regenerates and why
- **simple-module-migrations** — the migration step `smpy new` runs (`make migration` + `make migrate`, or `alembic upgrade head` directly)
