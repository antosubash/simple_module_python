---
name: simple-module-cli
description: Use when invoking the `smpy` CLI for a simple_module_python project — starting a new app, scaffolding a host or a publishable module, regenerating the Inertia page manifest, importing settings overrides from env, creating an admin user, or installing the bundled agent skills. Triggers on "smpy new", "smpy create-host", "smpy create-module", "smpy host gen-pages", "smpy users create-admin", "smpy skills add", or any unfamiliar `smpy` subcommand.
---

# simple_module_python: the `smpy` CLI

The `smpy` command is provided by `simple_module_cli` (installed as a dep of `simple_module_hosting`). It groups four kinds of operations: scaffolding new things, project-time helpers for the host, admin shortcuts for the bundled modules, and installing the bundled agent skills.

## Top-level commands

| Command | When to use |
|---|---|
| `smpy new <name>` | Greenfield: scaffold a complete app (host + selected modules) in one shot, with an interactive wizard for DB / tenancy / module preset |
| `smpy create-host <name>` | You want just a bare host project; you'll add modules later by `pip install`-ing them |
| `smpy create-module <name>` | You're authoring a publishable module package (separate repo, distributed via PyPI) |
| `smpy skills …` | Install / update the bundled agent-skill packs into a project (`add`, `list`, `update`) |
| `smpy host …` | Project-time helpers run from inside a host directory (page manifest, JS dep sync) |
| `smpy settings …` | Settings-module admin — currently `import-from-env` |
| `smpy users …` | Users-module admin — currently `create-admin` |

## `smpy new <name>` — the wizard

The fastest way from zero to a working app. It calls `create-host` under the hood, then installs and wires up the modules you pick.

```bash
# Interactive (asks for DB, tenancy, preset, module list)
smpy new MyApp

# Non-interactive: take all defaults (sqlite, no tenancy, standard preset)
smpy new MyApp --yes

# Pick a preset and add extras
smpy new MyApp --preset full --tenancy --db postgres
smpy new MyApp --preset minimal --with background_tasks,file_storage --yes

# Scaffold only — skip uv sync / npm install / alembic upgrade head
smpy new MyApp --no-install
```

**Module presets:**

| Preset | Modules included |
|---|---|
| `minimal` | `users` (and `auth` as a dep) |
| `standard` (default) | `users`, `dashboard`, `permissions` (+ deps) |
| `full` | every module in the catalog |
| `custom` | interactive — pick each module yes/no |

`--with` accepts a comma-separated list of catalog keys (`auth, users, permissions, products, dashboard, settings, feature_flags, file_storage, background_tasks, …`). Transitive `requires` are auto-added; the wizard prints `Added X (required by Y)` so you can see what got pulled in.

**Options summary:**

| Flag | Default | Meaning |
|---|---|---|
| `--dest <PATH>` | `./<name>` | Where to write the project |
| `--db sqlite\|postgres` | `sqlite` | Backend configured in `.env.example` |
| `--tenancy / --no-tenancy` | `--no-tenancy` | Enable the multi-tenant middleware |
| `--preset minimal\|standard\|full` | wizard asks | Module bundle |
| `--with <names>` | none | Extra catalog keys beyond the preset |
| `--yes / -y` | off | Skip prompts; accept defaults |
| `--no-install` | off | Skip `uv sync` / `npm install` / `alembic upgrade head` |

## `smpy create-host <name>` — bare host

```bash
smpy create-host MyApp                       # empty host, no modules declared
smpy create-host MyApp --with Auth,Products  # declare module deps in pyproject.toml
smpy create-host MyApp --dest ./apps/myapp   # custom destination
```

`--with` takes **PascalCase module names** (matching `ModuleMeta.name`), not catalog keys. Use this when you want to drive the build yourself rather than via `smpy new`'s wizard.

## `smpy create-module <name>` — module package

For module authors publishing to PyPI. Scaffolds a standalone repo containing one module.

```bash
smpy create-module orders                    # writes ./simple_module_orders/
smpy create-module orders --dest ./packages/orders
```

The result is a complete package: `pyproject.toml` with the entry point declared, `module.py` with `ModuleBase`/`ModuleMeta` skeleton, `models.py`, `contracts/`, `endpoints/{api,views}.py`, `pages/`, `locales/en.json`, plus a tests directory wired up with `simple_module_test` fixtures.

`<name>` accepts any case — `orders`, `Orders`, `ORDERS`, `blog_posts` all work. The CLI lowercases it for the directory and PascalCases it for `ModuleMeta.name`.

For the post-scaffold steps (entry point, Inertia namespace, etc.) see **simple-module-creating**.

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

## Related skills

- **simple-module-creating** — what `smpy create-module` produces and the post-scaffold contract
- **simple-module-inertia-pages** — what `smpy host gen-pages` regenerates and why
- **simple-module-migrations** — the `alembic upgrade head` step `smpy new` runs
