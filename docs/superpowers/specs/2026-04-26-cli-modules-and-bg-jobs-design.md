# CLI: project setup with modules and background jobs

**Date:** 2026-04-26
**Status:** Draft, pending implementation

## Problem

`smpy new <name>` today only pre-wires three modules (`users`, `dashboard`, `permissions`) and ignores the cost of opting in to anything else. To stand up a project that uses `background_tasks`, the user has to:

1. Add `simple_module_background_tasks` to `pyproject.toml` by hand.
2. Set `SM_BG_TASKS_BROKER_URL` in `.env`.
3. Author a `scripts/run_worker.py` that builds the Celery app.
4. Add `worker` / `beat` / `worker-docker` targets to `Makefile`.
5. Author a `docker-compose.yml` with `redis`, `worker`, and `beat` services and a `worker.Dockerfile`.

That is enough friction that "I want background jobs" turns into a half-day yak-shave. The same goes, to a lesser extent, for any module outside the hardcoded standard three. We want one command that scaffolds a project with any chosen subset of modules — including background jobs — and produces a runnable project.

## Goals

- `smpy new` accepts an explicit module list via flags, or runs an interactive wizard when no flags are given.
- Selecting `background_tasks` lands a runnable Celery worker + beat + Redis stack via `docker compose up`, plus host Make targets and `scripts/run_worker.py`, with no manual editing required.
- Module dependencies are resolved transitively and added silently (with a printed note).
- The CLI catalog is hardcoded — adding a new module to the catalog is a CLI code change.
- The framework layer remains free of devex concerns (Makefile / compose). Recipes live in the CLI package.

## Non-goals

- Third-party module registration. The catalog is closed for this change.
- A TUI library (`questionary`, `inquirer`, etc.). Wizard uses `click.prompt` and `click.confirm`.
- Worker queue configuration, autoscaling, beat-only deployments.
- Replacing or deprecating `smpy create-host` — it remains the lower-level "deps-only" command.

## Design

### File layout

Replace `framework/hosting/simple_module_hosting/cli.py` with a package:

```
framework/hosting/simple_module_hosting/cli/
├── __init__.py    # click group; re-exports existing commands
├── new.py         # `smpy new` — flags + wizard, calls into catalog/wizard/recipes
├── catalog.py     # ModuleEntry, CATALOG, PRESETS, expand_deps()
├── wizard.py      # interactive prompts (db, tenancy, preset, custom-pick)
└── recipes.py     # Recipe protocol + per-module post-scaffold actions
```

Each file has one responsibility and stays under the 300-line cap. Existing commands (`create-host`, `create-module`, `gen-pages`, `sync-js-deps`) move into `cli/__init__.py` (or thin per-command modules) so the `smpy` console script keeps working.

### Catalog

```python
# cli/catalog.py
from dataclasses import dataclass

@dataclass(frozen=True)
class ModuleEntry:
    name: str             # "background_tasks" — snake_case key
    package: str          # "simple_module_background_tasks"
    display: str          # "Background Tasks"
    requires: tuple[str, ...] = ()   # other catalog keys
    recipe: str | None = None        # key into RECIPES, or None

CATALOG: dict[str, ModuleEntry] = {
    "auth":             ModuleEntry("auth",             "simple_module_auth",             "Auth"),
    "users":            ModuleEntry("users",            "simple_module_users",            "Users",            requires=("auth",)),
    "permissions":      ModuleEntry("permissions",      "simple_module_permissions",      "Permissions",      requires=("auth", "users")),
    "dashboard":        ModuleEntry("dashboard",        "simple_module_dashboard",        "Dashboard",        requires=("users", "products")),
    "settings":         ModuleEntry("settings",         "simple_module_settings",         "Settings"),
    "feature_flags":    ModuleEntry("feature_flags",    "simple_module_feature_flags",    "Feature Flags"),
    "file_storage":     ModuleEntry("file_storage",     "simple_module_file_storage",     "File Storage",     requires=("settings",)),
    "products":         ModuleEntry("products",         "simple_module_products",         "Products"),
    "datasets":         ModuleEntry("datasets",         "simple_module_datasets",         "Datasets",         requires=("file_storage", "background_tasks")),
    "background_tasks": ModuleEntry("background_tasks", "simple_module_background_tasks", "Background Tasks", requires=("users",), recipe="background_tasks"),
}

PRESETS: dict[str, tuple[str, ...]] = {
    "minimal":  ("users",),
    "standard": ("users", "dashboard", "permissions"),
    "full":     tuple(CATALOG),
}

def expand_deps(selected: Iterable[str]) -> tuple[list[str], list[tuple[str, str]]]:
    """Return (resolved_topo_order, auto_added_pairs).
    auto_added_pairs is [(added_module, required_by), ...] for printing."""
```

`requires=` values mirror each module's real `ModuleMeta.depends_on`, transcribed to the snake_case catalog key.

`expand_deps` is the only non-trivial function: BFS over `requires`, append-only, preserves topo order so the resulting list is always loadable. Unknown name raises `KeyError("unknown module: <x>; available: ...")`.

### `smpy new` interface

```
smpy new <name>
  --dest <path>
  --db sqlite|postgres                  (existing)
  --tenancy/--no-tenancy                (existing)
  --preset minimal|standard|full        NEW
  --with mod1,mod2,...                  NEW — added on top of preset
  --yes/-y                              (existing — skips wizard, uses defaults)
  --no-install                          (existing)
```

Resolution rule: `selected = preset_modules ∪ --with`, then `expand_deps(selected)`. For each `(added, required_by)` pair, print `Added <added> (required by <required_by>)`.

Defaults when `--yes` is given without `--preset`/`--with`: preset `standard` (matches today's pre-wired set, no behavior change for existing scripts).

Conflict rule: if `--with` includes an unknown module name, exit 1 with the available list. If both `--preset` and `--with` are given, both are honored (union).

### Wizard

When `--yes` is absent and neither `--preset` nor `--with` is given, prompt in this order using `click.prompt` / `click.confirm`:

1. `Database backend [sqlite/postgres]:` (default sqlite)
2. `Enable multi-tenancy? [y/N]:`
3. `Preset: [1] minimal  [2] standard  [3] full  [4] custom` (default 2)
4. If choice 4: per-module `Include <Display Name>? [y/N]:` loop in catalog order.
5. Resolve deps. Print: `Selected modules: <list>` and any `Added X (required by Y)` lines.
6. `Proceed? [Y/n]:`

If `--yes` and any of `--preset`/`--with` is given, skip the wizard entirely.

### Recipes

```python
# cli/recipes.py
from typing import Protocol
from dataclasses import dataclass
from pathlib import Path

@dataclass
class ScaffoldCtx:
    name: str
    db: str
    tenancy: bool
    selected: tuple[str, ...]

class Recipe(Protocol):
    def apply(self, target: Path, ctx: ScaffoldCtx) -> None: ...

RECIPES: dict[str, Recipe] = {
    "background_tasks": BackgroundTasksRecipe(),
}
```

`BackgroundTasksRecipe.apply` performs:

1. `_set_env_key(target/".env.example", "SM_BG_TASKS_BROKER_URL", "redis://redis:6379/0")`.
2. Copy `templates/host/_optional/background_tasks/run_worker.py` to `target/scripts/run_worker.py`.
3. Append the `Makefile` snippet (worker / beat / worker-docker targets) — idempotent, skipped if any target already present.
4. Write `target/docker-compose.yml` with `redis`, `worker`, `beat` services. The host template does not ship a `docker-compose.yml`, so the recipe owns the file outright — no YAML merge needed, no `pyyaml` dependency. The compose file is shipped as a static template.
5. Copy `templates/host/_optional/background_tasks/worker.Dockerfile` to `target/docker/worker.Dockerfile`.

The recipe receives `ScaffoldCtx`. `name` is reused for the compose project name; `db`/`tenancy` are unused for `background_tasks` today but are part of the protocol so future recipes can read them.

### Templates

New package-data files alongside the existing host templates:

```
framework/hosting/simple_module_hosting/templates/host/_optional/
└── background_tasks/
    ├── run_worker.py
    ├── docker-compose.yml
    ├── Makefile.snippet
    └── worker.Dockerfile
```

The `_optional/` segment is filtered out by `_apply_template_files` so it's not copied during the default `create_host` pass — it's only consumed by recipes. Add an explicit skip for any path containing `/_optional/` in the host-template walker.

`run_worker.py` is the same shape as the in-tree `scripts/run_worker.py`:

```python
from background_tasks.celery_app import build_celery
from background_tasks.settings import BackgroundTasksSettings
celery = build_celery(BackgroundTasksSettings())
```

### Wiring into `create_app_project`

`create_app_project` gains a `selected: Sequence[str] | None = None` parameter (default `None` → `PRESETS["standard"]`). Internally:

1. Resolve `selected` via `expand_deps`.
2. Build `_APP_PY_DEPS` by mapping each catalog entry to `f"{entry.package}=={_FRAMEWORK_VERSION}"` instead of the current hardcoded list.
3. Call `create_host(target, name=name, modules=[entry.display for entry in resolved])` so the dependency declarations match.
4. After scaffolding, for each entry with a `recipe`, look it up in `RECIPES` and call `apply(target, ctx)`.

The two existing kwargs — `db` and `tenancy` — keep their current behavior.

### Backward compat

- `smpy create-host --with=` keeps current "deps-only" behavior unchanged.
- `smpy new --yes` with no other flags → standard preset → same outcome as today.
- `create_app_project` callers passing only `name`, `db`, `tenancy` keep working (default `selected=None`).

## Tests

- `framework/hosting/tests/test_cli_catalog.py` — `expand_deps` returns transitive closure; auto-add list correct; unknown name raises with available-list message; idempotent on already-resolved input.
- `framework/hosting/tests/test_cli_wizard.py` — `CliRunner` driving each preset path (1/2/3/4) and the custom checkbox loop; verifies dep auto-add notice prints; verifies `--yes` skips prompts.
- `framework/hosting/tests/test_cli_recipes.py` — `BackgroundTasksRecipe.apply` against a fresh tempdir already populated by `create_host`. Asserts `.env.example` contains `SM_BG_TASKS_BROKER_URL`, `scripts/run_worker.py` exists with the expected import, `Makefile` contains `worker:` / `beat:` targets, `docker-compose.yml` parses to YAML with `redis`, `worker`, `beat` keys under `services`.
- `framework/hosting/tests/test_cli_new.py` — end-to-end smoke: `smpy new demo --yes --preset=full --no-install --dest=<tmp>` produces a project that contains the union of all modules, a runnable compose file, Make targets, and `pyproject.toml` listing every package.

## Failure modes

- **Existing files when applying recipes.** `Makefile` and `.env.example` are edited idempotently (skip if marker present). `docker-compose.yml`, `scripts/run_worker.py`, and `docker/worker.Dockerfile` are written outright; if any already exist when the recipe runs, the recipe errors out — collision means user-authored content from a previous scaffold attempt and we don't clobber.
- **Catalog drift.** A unit test loads every package referenced in the catalog (by import name) and asserts the Python distribution exists in the workspace. Catches typos and renames at CI time, not at user-runtime.
- **`--with` typos.** Print available module list with the closest match (`difflib.get_close_matches`).

## Migration

This change is additive:

- `cli.py` becomes `cli/__init__.py` plus four new files. The `smpy` console-script entry point in `framework/hosting/pyproject.toml` continues to point at `simple_module_hosting.cli:main` — `__init__.py` exposes `main` from the new package.
- No template changes that affect existing host scaffolds. The new `_optional/` tree is additive.
- `create_app_project`'s positional/kwarg signature is unchanged; only the new `selected=` kwarg is added.

## Open questions

None blocking. The catalog `requires=` mappings will be re-verified against each module's real `ModuleMeta.depends_on` during implementation; the values in the Catalog section above are the current best mapping and may be tightened.
