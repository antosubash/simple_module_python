# Standalone `simple-module` CLI distribution

**Date:** 2026-04-26
**Status:** Draft, pending implementation

## Problem

`sm new` is currently shipped inside `simple_module_hosting`, which means `pip install simple-module-hosting` (or anything on top of it like `pipx install`) drags in FastAPI, Starlette, Inertia, Uvicorn, SQLModel, and the rest of the runtime — even when the user only wants to scaffold a new project. There is also no single CLI surface: hosting registers `sm`, `simple_module_hosting`'s helpers (`gen-pages`, `sync-js-deps`) are crammed into the same binary, and individual modules register their own `sm-users`, `sm-settings`, … console scripts. A new user who runs `pip install simple-module` should get a small, runnable scaffolder; a developer working inside a project should get one consolidated `sm` whose subcommand surface grows as plugins are installed.

## Goals

- A new PyPI distribution `simple-module` whose only runtime dependencies are `typer` and `tomlkit`. No framework-runtime deps.
- A single `sm` console script. All today's `sm-*` scripts (`sm-host`, `sm-users`, `sm-settings`) go away.
- Built-in (always-available) commands: `sm new`, `sm create-host`, `sm create-module`.
- Plugin commands provided via Python entry points: `simple_module_hosting` contributes `sm host gen-pages` and `sm host sync-js-deps`; the `users` and `settings` modules contribute `sm users …` and `sm settings …`.
- `pip install simple-module` works on a machine with no other framework packages installed and gives the user a working scaffolder.

## Non-goals

- Bumping versions, cutting a release, or interacting with `release.yml` (covered by the existing public-release spec).
- Reorganizing internal module-CLI behavior beyond the necessary `Typer` shape changes.
- Documentation rewrites beyond the README install snippet and the Makefile.
- A namespace or grouping convention for future module CLIs beyond what entry points + Typer naturally give.

## Design

### Distribution layout

```
framework/cli/                                 ← NEW workspace member
├── pyproject.toml                             name="simple-module"
├── README.md
├── LICENSE
└── simple_module/                             importable package
    ├── __init__.py
    ├── _env.py                                set_env_key
    ├── case.py                                _to_snake_case / _to_kebab_case / _to_pascal_case
    ├── scaffolding.py                         create_host, create_module, _apply_template_files
    ├── app_project.py                         create_app_project + helpers
    ├── catalog.py                             ModuleEntry, CATALOG, PRESETS, expand_deps
    ├── wizard.py                              run_wizard
    ├── recipes.py                             Recipe protocol, BackgroundTasksRecipe, RECIPES
    ├── new.py                                 `sm new` Typer command
    ├── plugins.py                             entry-point discovery + mounting
    ├── cli.py                                 root Typer app, mounts plugins, exposes `main`
    └── templates/                             package data
        ├── host/
        ├── module/
        └── host/_optional/background_tasks/
```

`framework/cli/pyproject.toml`:

```toml
[project]
name = "simple-module"
version = "0.0.1"
description = "Standalone scaffolder for the SimpleModule framework — `sm new`, `sm create-module`, plugin host."
readme = "README.md"
license = "MIT"
requires-python = ">=3.12"
keywords = ["simple-module", "scaffolding", "cli"]
dependencies = [
    "typer>=0.12",
    "tomlkit>=0.13",
]

[project.scripts]
sm = "simple_module.cli:main"
simple-module = "simple_module.cli:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["simple_module"]
```

### Plugin entry-point contract

Group: `simple_module.cli_plugins`.

Each plugin's `pyproject.toml` adds an entry under that group whose **key** becomes the subcommand namespace and whose **value** is a `module:attr` reference to a `typer.Typer` instance:

```toml
# framework/hosting/pyproject.toml
[project.entry-points."simple_module.cli_plugins"]
host = "simple_module_hosting.host_cli:app"

# modules/users/pyproject.toml
[project.entry-points."simple_module.cli_plugins"]
users = "users.cli:app"

# modules/settings/pyproject.toml
[project.entry-points."simple_module.cli_plugins"]
settings = "settings.cli:app"
```

At startup, `simple_module.plugins.discover()` calls `importlib.metadata.entry_points(group="simple_module.cli_plugins")`, loads each entry, and mounts it on the root app via `root.add_typer(plugin_app, name=entry.name)`. A failed entry-point load (broken import, missing attribute) prints a single warning and is skipped — `sm` itself keeps working. Discovery is unconditional but cheap; loading is eager so `--help` shows the full surface.

Resulting CLI surface:

```
sm new …                              (built-in)
sm create-host …                      (built-in)
sm create-module …                    (built-in)
sm host gen-pages …                   (when simple_module_hosting installed)
sm host sync-js-deps …                (when simple_module_hosting installed)
sm users create-admin …               (when users module installed)
sm settings import-from-env …         (when settings module installed)
```

### File moves

| From | To |
|---|---|
| `framework/hosting/simple_module_hosting/_env.py` | `framework/cli/simple_module/_env.py` |
| `framework/hosting/simple_module_hosting/scaffolding.py` (`create_host`, `create_module`, `_apply_template_files`, `_iter_template_files`, `_resolve_template_root`, etc.) | `framework/cli/simple_module/scaffolding.py` |
| `_to_snake_case` / `_to_kebab_case` / `_to_pascal_case` (currently in `scaffolding.py`) | `framework/cli/simple_module/case.py` |
| `framework/hosting/simple_module_hosting/app_project.py` | `framework/cli/simple_module/app_project.py` |
| `framework/hosting/simple_module_hosting/cli/{catalog,wizard,recipes,new}.py` | `framework/cli/simple_module/{catalog,wizard,recipes,new}.py` |
| `framework/hosting/simple_module_hosting/cli/__init__.py` (only the `create-host` and `create-module` halves) | `framework/cli/simple_module/cli.py` |
| `framework/hosting/simple_module_hosting/cli/__init__.py` (only the `gen-pages` and `sync-js-deps` halves) | `framework/hosting/simple_module_hosting/host_cli.py` (Typer `app`) |
| `framework/hosting/simple_module_hosting/templates/{host,module,host/_optional}/` | `framework/cli/simple_module/templates/{host,module,host/_optional}/` |
| `framework/hosting/tests/test_cli_*.py` | `framework/cli/tests/test_cli_*.py` (imports update from `simple_module_hosting.cli.*` → `simple_module.*`) |
| `framework/hosting/tests/test_scaffolding_host.py` | `framework/cli/tests/test_scaffolding.py` |

The `simple_module_hosting` package keeps its **runtime** (`app_builder.py`, middleware, `Settings`, `health.py`, manifest helpers, etc.) and gains `host_cli.py`. It loses `cli/`, `app_project.py`, `scaffolding.py`, `_env.py`, and the `templates/` tree.

### Code-level changes

Every Click decorator in the moved code is rewritten to Typer's signature style. Concretely:

- `@click.command(...)` + `@click.option(...)` decorators → `def cmd(arg: Annotated[T, typer.Option(...)] = default): ...` registered via `@app.command()`.
- `click.Choice(["sqlite", "postgres"])` → string `Enum` (e.g. `class Db(str, Enum): sqlite = "sqlite"; postgres = "postgres"`) referenced as the parameter type. Typer renders the same shell-completion + help.
- `click.prompt`, `click.confirm`, `click.echo`, `click.Abort` → `typer.prompt`, `typer.confirm`, `typer.echo`, `typer.Abort` (re-exports of the Click implementations; behavior identical).
- Tests: `from click.testing import CliRunner` → `from typer.testing import CliRunner`. Same `runner.invoke(...)` / `input=` API.

The interactive wizard logic, `expand_deps`, the recipe protocol, the catalog data, and the templates are unchanged.

### Module-CLI updates

`modules/users/users/cli.py` is already a Typer app exporting `app`; only the `pyproject.toml` script declaration changes:

```toml
# Before
[project.scripts]
sm-users = "users.cli:app"

# After
[project.entry-points."simple_module.cli_plugins"]
users = "users.cli:app"
```

`modules/settings/settings/cli.py` is currently Click-style with a `main` function. Convert to a Typer app named `app`. Same pyproject.toml swap (`sm-settings` script → entry-point under `simple_module.cli_plugins`).

`framework/hosting/pyproject.toml` drops `sm = "simple_module_hosting.cli:main"` and gains:

```toml
[project.entry-points."simple_module.cli_plugins"]
host = "simple_module_hosting.host_cli:app"
```

Note: the `simple-module` console-script alias is dropped from `simple_module_hosting` too — it now lives only in the `simple-module` package.

### Workspace + Makefile wiring

- Root `pyproject.toml`: add `framework/cli` to workspace members.
- `[tool.uv.sources]`: add `simple-module = { workspace = true }` so in-tree dev resolves to the local copy.
- `host/pyproject.toml`: add `simple-module==0.0.1` as a dependency. (Hosting and module packages do **not** depend on `simple-module`.)
- `Makefile`: rename `sm gen-pages` → `sm host gen-pages` and `sm sync-js-deps` → `sm host sync-js-deps` in the `gen-pages` and `sync-module-deps` targets. The `make new-module` target keeps invoking `sm create-module`.
- Existing CI (`.github/workflows/pr.yml`) needs no change — `make lint` and `make test` will pick up the new workspace member automatically.
- Release matrix (`.github/workflows/release.yml`): one new entry for the `simple-module` package alongside the existing 14.

### Test strategy

- The 47 CLI tests move from `framework/hosting/tests/test_cli_*.py` → `framework/cli/tests/test_cli_*.py`. Imports update mechanically (find/replace on `simple_module_hosting.cli` → `simple_module`, `simple_module_hosting.scaffolding` → `simple_module.scaffolding`). The Click `CliRunner` import becomes `from typer.testing import CliRunner`. The Click `result.output` / `result.exit_code` API is identical under Typer's runner.
- `framework/cli/tests/test_no_framework_deps.py` (new): asserts that `importlib.metadata.requires("simple-module")` is exactly `["typer>=0.12", "tomlkit>=0.13"]`. Guards against accidental dep drift introducing `simple_module_core` / `simple_module_hosting` deps.
- `framework/cli/tests/test_plugin_discovery.py` (new): exercises `simple_module.plugins.discover()` against a fake entry-point group injected via `monkeypatch.setattr(importlib.metadata, "entry_points", ...)`. Asserts that valid plugins mount, broken plugins are skipped with a warning, and the resulting Typer app's `--help` lists the expected subgroups.
- `framework/hosting/tests/test_host_cli.py` (new): smoke-tests `sm-host`'s `gen-pages` and `sync-js-deps` happy paths after the move. The existing `test_scaffolding_host.py` becomes `framework/cli/tests/test_scaffolding.py`.
- `framework/hosting/tests/test_app.py` etc. unchanged.

### Failure modes

- **A plugin's entry point references a missing module or non-Typer object.** Log a warning (`sm` keeps working with whatever else is installed). Test covers this.
- **Two plugins claim the same subgroup name** (e.g. two installs both register `host`). `add_typer` raises; we catch the second registration and warn, keeping the first. Test covers this.
- **A user has `simple-module` installed but no plugins.** Built-in commands work; `sm --help` shows only `new` / `create-host` / `create-module`. No errors.
- **Templates package-data shipping.** The `_optional/` directory tree is copied as `package-data` under the wheel; verified by `framework/cli/tests/test_cli_recipes.py` reading the package-data path at runtime (same pattern that works today).

### Backward compat

This is a pre-`0.0.1` framework with no external consumers. There are no shims or aliases:

- `simple_module_hosting.cli` package, `simple_module_hosting.scaffolding`, and `simple_module_hosting.app_project` are **deleted**, not re-exported.
- All in-tree callers are updated mechanically: tests, the `Makefile`, `host/pyproject.toml`, the per-module `pyproject.toml` files.
- The `sm-users` and `sm-settings` console scripts are deleted. Anyone running `sm-users create-admin` switches to `sm users create-admin`.

## Open questions

None blocking. The dep guard test (`test_no_framework_deps.py`) is intentionally narrow: it pins the declared dep list to exactly `typer` and `tomlkit`. If we ever decide to relax to `typer-slim` to drop `rich`, that's a single-line change with the test caught the moment.
