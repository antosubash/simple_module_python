# CLI: project setup with modules and background jobs — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade `smpy new` so it scaffolds a SimpleModule project with any chosen subset of modules (presets or custom) and lands a runnable Celery worker + beat + Redis stack when `background_tasks` is selected — no manual editing required.

**Architecture:** Replace the single-file `framework/hosting/simple_module_hosting/cli.py` with a `cli/` package containing a hardcoded module **catalog** (with transitive-dep resolution), an interactive **wizard**, and per-module **recipes** that perform post-scaffold actions. The `background_tasks` recipe writes `scripts/run_worker.py`, appends Make targets, and emits a `docker-compose.yml` + `worker.Dockerfile`.

**Tech Stack:** Python 3.12, `click` (existing dep), Click `CliRunner` for tests, `pytest`. No new runtime deps. Templates ship as package data under `simple_module_hosting/templates/host/_optional/background_tasks/`.

**Spec:** `docs/superpowers/specs/2026-04-26-cli-modules-and-bg-jobs-design.md`

---

## File Structure (created or modified)

| Path | Role |
|---|---|
| `framework/hosting/simple_module_hosting/cli.py` | **Deleted** — replaced by package below |
| `framework/hosting/simple_module_hosting/cli/__init__.py` | Click group; existing commands `create-host`, `create-module`, `gen-pages`, `sync-js-deps` live here. Re-exports `main`. |
| `framework/hosting/simple_module_hosting/cli/catalog.py` | `ModuleEntry`, `CATALOG`, `PRESETS`, `expand_deps()` |
| `framework/hosting/simple_module_hosting/cli/wizard.py` | `run_wizard(default_db, default_tenancy)` returning `(db, tenancy, selected)` |
| `framework/hosting/simple_module_hosting/cli/recipes.py` | `Recipe` protocol, `ScaffoldCtx`, `RECIPES` dict, `BackgroundTasksRecipe` |
| `framework/hosting/simple_module_hosting/cli/new.py` | The upgraded `new_project` command |
| `framework/hosting/simple_module_hosting/scaffolding.py` | `create_app_project` gains `selected: Sequence[str] \| None` param |
| `framework/hosting/simple_module_hosting/templates/host/_optional/background_tasks/run_worker.py` | Static template (no `.tpl` suffix; verbatim copy by recipe — bypass `_apply_template_files`) |
| `framework/hosting/simple_module_hosting/templates/host/_optional/background_tasks/docker-compose.yml` | Compose stack: redis + worker + beat |
| `framework/hosting/simple_module_hosting/templates/host/_optional/background_tasks/Makefile.snippet` | `worker` / `beat` / `worker-docker` targets |
| `framework/hosting/simple_module_hosting/templates/host/_optional/background_tasks/worker.Dockerfile` | Celery image for worker + beat |
| `framework/hosting/tests/test_cli_catalog.py` | New |
| `framework/hosting/tests/test_cli_wizard.py` | New |
| `framework/hosting/tests/test_cli_recipes.py` | New |
| `framework/hosting/tests/test_cli_new.py` | Extended with preset + recipe tests |

`framework/hosting/pyproject.toml` does **not** change — the entry point `sm = "simple_module_hosting.cli:main"` resolves the same after `cli.py` becomes `cli/__init__.py` because `main` is re-exported.

---

## Task 1: Convert `cli.py` → `cli/` package (no behavior change)

**Files:**
- Delete: `framework/hosting/simple_module_hosting/cli.py`
- Create: `framework/hosting/simple_module_hosting/cli/__init__.py`
- Test: `framework/hosting/tests/test_cli_new.py` (existing — must keep passing)

This task is a pure refactor. We move every existing command into `cli/__init__.py` verbatim so the test suite continues to pass before any behavior change.

- [ ] **Step 1: Run existing CLI tests baseline**

Run: `uv run pytest framework/hosting/tests/test_cli_new.py -v`
Expected: PASS (3 tests)

- [ ] **Step 2: Create the package directory**

```bash
mkdir -p framework/hosting/simple_module_hosting/cli
git mv framework/hosting/simple_module_hosting/cli.py framework/hosting/simple_module_hosting/cli/__init__.py
```

- [ ] **Step 3: Run tests to confirm move is transparent**

Run: `uv run pytest framework/hosting/tests/test_cli_new.py -v`
Expected: PASS (3 tests). Python imports `cli/__init__.py` for `simple_module_hosting.cli` exactly the same as `cli.py`, so `main` is still findable.

- [ ] **Step 4: Verify `smpy` console script still resolves**

Run: `uv run smpy --help`
Expected: Lists `new`, `create-host`, `create-module`, `gen-pages`, `sync-js-deps` — same as before.

- [ ] **Step 5: Commit**

```bash
git add framework/hosting/simple_module_hosting/cli/__init__.py
git rm framework/hosting/simple_module_hosting/cli.py
git commit -m "refactor(cli): move cli.py to cli/__init__.py (no behavior change)

Preparing the file for split into a package — catalog, wizard, recipes,
new will land in dedicated modules. Console-script entry point unchanged."
```

---

## Task 2: Build the module catalog with transitive dep resolution

**Files:**
- Create: `framework/hosting/simple_module_hosting/cli/catalog.py`
- Create: `framework/hosting/tests/test_cli_catalog.py`

The catalog is a pure data + one pure function (`expand_deps`). TDD it.

- [ ] **Step 1: Write failing tests for `expand_deps`**

```python
# framework/hosting/tests/test_cli_catalog.py
"""Tests for the module catalog and dependency expansion."""

from __future__ import annotations

import pytest
from simple_module_hosting.cli.catalog import (
    CATALOG,
    PRESETS,
    ModuleEntry,
    expand_deps,
)


def test_catalog_keys_match_entry_names() -> None:
    for key, entry in CATALOG.items():
        assert key == entry.name, f"catalog key {key!r} != entry.name {entry.name!r}"


def test_every_requires_value_is_a_known_catalog_key() -> None:
    for entry in CATALOG.values():
        for required in entry.requires:
            assert required in CATALOG, f"{entry.name} requires unknown module {required!r}"


def test_presets_only_reference_known_modules() -> None:
    for name, mods in PRESETS.items():
        for m in mods:
            assert m in CATALOG, f"preset {name!r} references unknown module {m!r}"


def test_expand_deps_returns_input_when_no_requires() -> None:
    resolved, added = expand_deps(["auth"])
    assert resolved == ["auth"]
    assert added == []


def test_expand_deps_pulls_in_transitive_dep() -> None:
    # users requires auth (per ModuleMeta.depends_on)
    resolved, added = expand_deps(["users"])
    assert set(resolved) == {"auth", "users"}
    assert added == [("auth", "users")]


def test_expand_deps_pulls_in_chain() -> None:
    # datasets -> file_storage -> settings AND datasets -> background_tasks -> users -> auth
    resolved, added = expand_deps(["datasets"])
    assert set(resolved) == {
        "datasets",
        "file_storage",
        "settings",
        "background_tasks",
        "users",
        "auth",
    }
    # Every added pair points to a real requirer in the input or already-added set.
    added_names = {a for a, _ in added}
    assert added_names == {"file_storage", "settings", "background_tasks", "users", "auth"}


def test_expand_deps_idempotent_when_input_already_complete() -> None:
    resolved1, _ = expand_deps(["users"])
    resolved2, added2 = expand_deps(resolved1)
    assert sorted(resolved1) == sorted(resolved2)
    assert added2 == []


def test_expand_deps_unknown_name_raises_with_available_list() -> None:
    with pytest.raises(KeyError) as exc:
        expand_deps(["does_not_exist"])
    msg = str(exc.value)
    assert "does_not_exist" in msg
    assert "auth" in msg  # one of the available names in the message


def test_expand_deps_preserves_load_order_dep_before_dependent() -> None:
    """The resolved list must be in topo order: a module's deps appear before it."""
    resolved, _ = expand_deps(["dashboard"])
    for i, name in enumerate(resolved):
        for required in CATALOG[name].requires:
            assert resolved.index(required) < i, (
                f"{required} must appear before {name} in {resolved}"
            )


def test_module_entry_is_frozen() -> None:
    entry = ModuleEntry(name="x", package="simple_module_x", display="X")
    with pytest.raises(Exception):  # FrozenInstanceError or AttributeError
        entry.name = "y"  # type: ignore[misc]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest framework/hosting/tests/test_cli_catalog.py -v`
Expected: All tests fail with `ModuleNotFoundError: No module named 'simple_module_hosting.cli.catalog'`.

- [ ] **Step 3: Implement `cli/catalog.py`**

```python
# framework/hosting/simple_module_hosting/cli/catalog.py
"""Hardcoded catalog of installable SimpleModule modules.

Each :class:`ModuleEntry` declares the PyPI package name, a human display
name, transitive `requires` (other catalog keys), and an optional `recipe`
key for post-scaffold actions handled by :mod:`.recipes`.

`expand_deps` takes a user-selected subset and returns a topologically
ordered superset including every transitive requirement, plus the list
of `(added, required_by)` pairs for printing back to the user.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

__all__ = ["CATALOG", "PRESETS", "ModuleEntry", "expand_deps"]


@dataclass(frozen=True)
class ModuleEntry:
    name: str
    package: str
    display: str
    requires: tuple[str, ...] = field(default_factory=tuple)
    recipe: str | None = None


# Keys are snake_case; values mirror each module's real
# ``ModuleMeta.depends_on`` (transcribed to catalog keys).
CATALOG: dict[str, ModuleEntry] = {
    "auth": ModuleEntry("auth", "simple_module_auth", "Auth"),
    "users": ModuleEntry("users", "simple_module_users", "Users", requires=("auth",)),
    "permissions": ModuleEntry(
        "permissions", "simple_module_permissions", "Permissions", requires=("auth", "users")
    ),
    "products": ModuleEntry("products", "simple_module_products", "Products"),
    "dashboard": ModuleEntry(
        "dashboard", "simple_module_dashboard", "Dashboard", requires=("users", "products")
    ),
    "settings": ModuleEntry("settings", "simple_module_settings", "Settings"),
    "feature_flags": ModuleEntry("feature_flags", "simple_module_feature_flags", "Feature Flags"),
    "file_storage": ModuleEntry(
        "file_storage", "simple_module_file_storage", "File Storage", requires=("settings",)
    ),
    "background_tasks": ModuleEntry(
        "background_tasks",
        "simple_module_background_tasks",
        "Background Tasks",
        requires=("users",),
        recipe="background_tasks",
    ),
    "datasets": ModuleEntry(
        "datasets",
        "simple_module_datasets",
        "Datasets",
        requires=("file_storage", "background_tasks"),
    ),
}


PRESETS: dict[str, tuple[str, ...]] = {
    "minimal": ("users",),
    "standard": ("users", "dashboard", "permissions"),
    "full": tuple(CATALOG),
}


def expand_deps(selected: Iterable[str]) -> tuple[list[str], list[tuple[str, str]]]:
    """Return (topo-ordered resolved list, [(added, required_by), ...]).

    Raises ``KeyError`` if any input name is not in the catalog. The
    error message lists the available catalog keys.
    """
    selected_list = list(selected)
    for name in selected_list:
        if name not in CATALOG:
            available = ", ".join(sorted(CATALOG))
            raise KeyError(f"unknown module: {name!r}; available: {available}")

    explicit = set(selected_list)
    resolved: list[str] = []
    in_resolved: set[str] = set()
    added: list[tuple[str, str]] = []

    def _visit(name: str, required_by: str | None) -> None:
        if name in in_resolved:
            return
        for dep in CATALOG[name].requires:
            _visit(dep, required_by=name)
        resolved.append(name)
        in_resolved.add(name)
        if required_by is not None and name not in explicit:
            added.append((name, required_by))

    for name in selected_list:
        _visit(name, required_by=None)
    return resolved, added
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest framework/hosting/tests/test_cli_catalog.py -v`
Expected: All 9 tests pass.

- [ ] **Step 5: Commit**

```bash
git add framework/hosting/simple_module_hosting/cli/catalog.py framework/hosting/tests/test_cli_catalog.py
git commit -m "feat(cli): module catalog with transitive dep expansion

Adds CATALOG, PRESETS, and expand_deps() — pure data + one pure
function. Will be wired into 'smpy new' in a follow-up."
```

---

## Task 3: Implement the interactive wizard

**Files:**
- Create: `framework/hosting/simple_module_hosting/cli/wizard.py`
- Create: `framework/hosting/tests/test_cli_wizard.py`

Wizard owns the prompt sequence: db → tenancy → preset (or custom checkbox loop) → confirmation. Returns the resolved tuple `(db, tenancy, selected_topo_ordered)`.

- [ ] **Step 1: Write failing tests for the wizard**

```python
# framework/hosting/tests/test_cli_wizard.py
"""Tests for the `smpy new` interactive wizard."""

from __future__ import annotations

import click
from click.testing import CliRunner
from simple_module_hosting.cli.wizard import run_wizard


def _drive(answers: list[str]) -> tuple[str, bool, list[str], str]:
    """Run the wizard with stdin pre-fed; return (db, tenancy, selected, output)."""

    captured: dict = {}

    @click.command()
    def wrapper() -> None:
        db, tenancy, selected = run_wizard(default_db="sqlite", default_tenancy=False)
        captured["db"] = db
        captured["tenancy"] = tenancy
        captured["selected"] = selected

    runner = CliRunner()
    result = runner.invoke(wrapper, input="\n".join(answers) + "\n")
    assert result.exit_code == 0, result.output
    return captured["db"], captured["tenancy"], captured["selected"], result.output


def test_wizard_standard_preset_default_path() -> None:
    # Answers: db=<enter for sqlite>, tenancy=<enter for n>, preset=<enter for 2 standard>, confirm=<enter for y>
    db, tenancy, selected, out = _drive(["", "", "", ""])
    assert db == "sqlite"
    assert tenancy is False
    assert "users" in selected and "dashboard" in selected and "permissions" in selected
    # auth auto-added because users/permissions require it
    assert "auth" in selected
    assert "Added auth (required by" in out


def test_wizard_postgres_with_tenancy() -> None:
    db, tenancy, _selected, _out = _drive(["postgres", "y", "", ""])
    assert db == "postgres"
    assert tenancy is True


def test_wizard_minimal_preset() -> None:
    _, _, selected, _ = _drive(["", "", "1", ""])
    # minimal = users; users requires auth
    assert set(selected) == {"users", "auth"}


def test_wizard_full_preset_includes_background_tasks() -> None:
    _, _, selected, _ = _drive(["", "", "3", ""])
    assert "background_tasks" in selected
    assert "datasets" in selected
    assert len(selected) >= 10


def test_wizard_custom_picks_only_yes_answers() -> None:
    # preset=4 (custom). Per-module loop walks CATALOG order:
    # auth, users, permissions, products, dashboard, settings, feature_flags,
    # file_storage, background_tasks, datasets — answer y to background_tasks only.
    answers = ["", "", "4"] + ["n"] * 8 + ["y", "n", ""]
    _, _, selected, out = _drive(answers)
    # background_tasks pulls in users (its only require), which pulls in auth.
    assert set(selected) == {"background_tasks", "users", "auth"}
    assert "Added users (required by background_tasks)" in out
    assert "Added auth (required by users)" in out


def test_wizard_aborts_on_confirm_no() -> None:
    captured: dict = {}

    @click.command()
    def wrapper() -> None:
        try:
            run_wizard(default_db="sqlite", default_tenancy=False)
        except click.Abort:
            captured["aborted"] = True
            raise

    runner = CliRunner()
    result = runner.invoke(wrapper, input="\n".join(["", "", "", "n"]) + "\n")
    assert result.exit_code != 0
    assert captured.get("aborted") is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest framework/hosting/tests/test_cli_wizard.py -v`
Expected: All 6 tests fail with `ModuleNotFoundError: No module named 'simple_module_hosting.cli.wizard'`.

- [ ] **Step 3: Implement `cli/wizard.py`**

```python
# framework/hosting/simple_module_hosting/cli/wizard.py
"""Interactive prompt sequence for `smpy new`.

Returns the user's choices as ``(db, tenancy, selected)`` where ``selected``
is the topologically resolved module list (already includes transitive
requires). All prompts use ``click`` — no extra TUI dep.
"""

from __future__ import annotations

import click

from .catalog import CATALOG, PRESETS, expand_deps

__all__ = ["run_wizard"]


_PRESET_CHOICES = ("minimal", "standard", "full", "custom")


def run_wizard(*, default_db: str, default_tenancy: bool) -> tuple[str, bool, list[str]]:
    db = click.prompt(
        "Database backend",
        default=default_db,
        type=click.Choice(["sqlite", "postgres"]),
    )
    tenancy = click.confirm("Enable multi-tenancy?", default=default_tenancy)

    click.echo("\nPreset:")
    click.echo("  [1] minimal  — users only")
    click.echo("  [2] standard — users, dashboard, permissions  (default)")
    click.echo("  [3] full     — every module")
    click.echo("  [4] custom   — pick modules one by one")
    choice = click.prompt(
        "Choose",
        default="2",
        type=click.Choice(["1", "2", "3", "4"]),
        show_choices=False,
    )
    preset_name = _PRESET_CHOICES[int(choice) - 1]

    if preset_name == "custom":
        picked = [
            name
            for name in CATALOG
            if click.confirm(f"Include {CATALOG[name].display}?", default=False)
        ]
    else:
        picked = list(PRESETS[preset_name])

    resolved, added = expand_deps(picked)
    for name, required_by in added:
        click.echo(f"Added {name} (required by {required_by})")
    click.echo(f"Selected modules: {', '.join(resolved)}")

    if not click.confirm("Proceed?", default=True):
        raise click.Abort()
    return db, tenancy, resolved
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest framework/hosting/tests/test_cli_wizard.py -v`
Expected: All 6 tests pass.

- [ ] **Step 5: Commit**

```bash
git add framework/hosting/simple_module_hosting/cli/wizard.py framework/hosting/tests/test_cli_wizard.py
git commit -m "feat(cli): interactive wizard for smpy new

db -> tenancy -> preset (or custom checkbox loop) -> confirm. Auto-adds
required deps with a printed note. No new TUI dependency."
```

---

## Task 4: Add `background_tasks` recipe + templates

**Files:**
- Create: `framework/hosting/simple_module_hosting/templates/host/_optional/background_tasks/run_worker.py`
- Create: `framework/hosting/simple_module_hosting/templates/host/_optional/background_tasks/docker-compose.yml`
- Create: `framework/hosting/simple_module_hosting/templates/host/_optional/background_tasks/Makefile.snippet`
- Create: `framework/hosting/simple_module_hosting/templates/host/_optional/background_tasks/worker.Dockerfile`
- Modify: `framework/hosting/simple_module_hosting/scaffolding.py:58-72` — make `_iter_template_files` skip `_optional/`
- Create: `framework/hosting/simple_module_hosting/cli/recipes.py`
- Create: `framework/hosting/tests/test_cli_recipes.py`

### Step group A — templates

- [ ] **Step 1: Write the worker run script template**

Create `framework/hosting/simple_module_hosting/templates/host/_optional/background_tasks/run_worker.py`:

```python
"""Entry point for the Celery worker and beat services.

Both the web process and the worker go through the same
``background_tasks.celery_app.build_celery`` factory so the broker
config, autodiscovered tasks, and signal handlers stay in lockstep.

Run locally:
    uv run celery -A scripts.run_worker:celery worker -l info
    uv run celery -A scripts.run_worker:celery beat   -l info
"""

from __future__ import annotations

from background_tasks.celery_app import build_celery
from background_tasks.settings import BackgroundTasksSettings

celery = build_celery(BackgroundTasksSettings())
```

- [ ] **Step 2: Write the docker-compose template**

Create `framework/hosting/simple_module_hosting/templates/host/_optional/background_tasks/docker-compose.yml`:

```yaml
services:
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redisdata:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 10

  worker:
    build:
      context: .
      dockerfile: docker/worker.Dockerfile
    env_file: .env
    environment:
      SM_BG_TASKS_BROKER_URL: redis://redis:6379/0
      SM_BG_TASKS_RESULT_BACKEND: redis://redis:6379/1
    depends_on:
      redis:
        condition: service_healthy
    command:
      - "uv"
      - "run"
      - "celery"
      - "-A"
      - "scripts.run_worker:celery"
      - "worker"
      - "-l"
      - "info"
      - "--concurrency=4"

  beat:
    build:
      context: .
      dockerfile: docker/worker.Dockerfile
    env_file: .env
    environment:
      SM_BG_TASKS_BROKER_URL: redis://redis:6379/0
      SM_BG_TASKS_RESULT_BACKEND: redis://redis:6379/1
    depends_on:
      redis:
        condition: service_healthy
      worker:
        condition: service_started
    command:
      - "uv"
      - "run"
      - "celery"
      - "-A"
      - "scripts.run_worker:celery"
      - "beat"
      - "-l"
      - "info"

volumes:
  redisdata:
```

- [ ] **Step 3: Write the Makefile snippet**

Create `framework/hosting/simple_module_hosting/templates/host/_optional/background_tasks/Makefile.snippet`:

```make
# --- background_tasks ----------------------------------------------------
.PHONY: worker beat worker-docker

worker:                     ## Run a Celery worker locally against $(SM_BG_TASKS_BROKER_URL)
	uv run celery -A scripts.run_worker:celery worker -l info

beat:                       ## Run the Celery beat scheduler locally
	uv run celery -A scripts.run_worker:celery beat -l info

worker-docker:              ## Build + run the worker + beat services in docker
	docker compose up --build worker beat
# --- end background_tasks ------------------------------------------------
```

- [ ] **Step 4: Write the worker Dockerfile template**

Create `framework/hosting/simple_module_hosting/templates/host/_optional/background_tasks/worker.Dockerfile`:

```dockerfile
# Celery worker image for the BackgroundTasks module.
# Serves both the worker and beat services in docker-compose — they
# differ only by command.

FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_SYSTEM_PYTHON=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        curl \
        ca-certificates \
        build-essential \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir uv

WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY scripts/ scripts/
COPY client_app/ client_app/

RUN uv sync --frozen --no-dev

RUN useradd --system --uid 10001 --home /app --shell /usr/sbin/nologin worker \
    && chown -R worker:worker /app
USER worker

ENV CELERY_APP=scripts.run_worker:celery
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD uv run celery -A $CELERY_APP inspect ping -d celery@$HOSTNAME || exit 1

CMD ["uv", "run", "celery", "-A", "scripts.run_worker:celery", "worker", "-l", "info"]
```

- [ ] **Step 5: Update `_iter_template_files` to skip `_optional/`**

In `framework/hosting/simple_module_hosting/scaffolding.py`, replace the `_iter_template_files` function (lines ~58-62):

```python
def _iter_template_files(template_root: Path):
    """Yield every file under ``template_root``, preserving relative paths.

    Skips any path under an ``_optional/`` segment — those are recipe-managed
    templates consumed by :mod:`simple_module_hosting.cli.recipes`, not by
    the default scaffolding pass.
    """
    for path in template_root.rglob("*"):
        if not path.is_file():
            continue
        if "_optional" in path.relative_to(template_root).parts:
            continue
        yield path
```

- [ ] **Step 6: Run existing scaffolding tests to confirm `_optional/` is excluded**

Run: `uv run pytest framework/hosting/tests/test_scaffolding_host.py framework/hosting/tests/test_cli_new.py -v`
Expected: All existing tests still pass — the `_optional/` files do **not** leak into the scaffolded host.

### Step group B — recipe

- [ ] **Step 7: Write failing tests for `BackgroundTasksRecipe`**

```python
# framework/hosting/tests/test_cli_recipes.py
"""Tests for per-module post-scaffold recipes."""

from __future__ import annotations

from pathlib import Path

import pytest
from simple_module_hosting.cli.recipes import (
    RECIPES,
    BackgroundTasksRecipe,
    ScaffoldCtx,
)
from simple_module_hosting.scaffolding import create_host


def _scaffold_minimal_host(target: Path) -> None:
    create_host(target, name="demo", modules=["Users"])


def test_background_tasks_recipe_registered() -> None:
    assert "background_tasks" in RECIPES
    assert isinstance(RECIPES["background_tasks"], BackgroundTasksRecipe)


def test_recipe_writes_run_worker_script(tmp_path: Path) -> None:
    _scaffold_minimal_host(tmp_path)
    BackgroundTasksRecipe().apply(
        tmp_path,
        ScaffoldCtx(name="demo", db="sqlite", tenancy=False, selected=("background_tasks",)),
    )
    script = tmp_path / "scripts" / "run_worker.py"
    assert script.is_file()
    text = script.read_text()
    assert "from background_tasks.celery_app import build_celery" in text
    assert "celery = build_celery(BackgroundTasksSettings())" in text


def test_recipe_writes_compose_with_redis_worker_beat(tmp_path: Path) -> None:
    _scaffold_minimal_host(tmp_path)
    BackgroundTasksRecipe().apply(
        tmp_path,
        ScaffoldCtx(name="demo", db="sqlite", tenancy=False, selected=("background_tasks",)),
    )
    compose = (tmp_path / "docker-compose.yml").read_text()
    assert "redis:" in compose
    assert "worker:" in compose
    assert "beat:" in compose
    assert "scripts.run_worker:celery" in compose


def test_recipe_writes_worker_dockerfile(tmp_path: Path) -> None:
    _scaffold_minimal_host(tmp_path)
    BackgroundTasksRecipe().apply(
        tmp_path,
        ScaffoldCtx(name="demo", db="sqlite", tenancy=False, selected=("background_tasks",)),
    )
    dockerfile = (tmp_path / "docker" / "worker.Dockerfile").read_text()
    assert "FROM python:3.12-slim" in dockerfile
    assert "scripts.run_worker:celery" in dockerfile


def test_recipe_appends_makefile_targets(tmp_path: Path) -> None:
    _scaffold_minimal_host(tmp_path)
    BackgroundTasksRecipe().apply(
        tmp_path,
        ScaffoldCtx(name="demo", db="sqlite", tenancy=False, selected=("background_tasks",)),
    )
    makefile = (tmp_path / "Makefile").read_text()
    assert "worker:" in makefile
    assert "beat:" in makefile
    assert "worker-docker:" in makefile


def test_recipe_sets_broker_url_env_var(tmp_path: Path) -> None:
    _scaffold_minimal_host(tmp_path)
    BackgroundTasksRecipe().apply(
        tmp_path,
        ScaffoldCtx(name="demo", db="sqlite", tenancy=False, selected=("background_tasks",)),
    )
    env_text = (tmp_path / ".env.example").read_text()
    assert "SM_BG_TASKS_BROKER_URL=redis://redis:6379/0" in env_text


def test_recipe_makefile_snippet_idempotent(tmp_path: Path) -> None:
    _scaffold_minimal_host(tmp_path)
    ctx = ScaffoldCtx(name="demo", db="sqlite", tenancy=False, selected=("background_tasks",))
    BackgroundTasksRecipe().apply(tmp_path, ctx)
    first = (tmp_path / "Makefile").read_text()
    # Re-running on the same target must error or be idempotent — collisions
    # on run_worker.py / compose / Dockerfile must raise.
    with pytest.raises(FileExistsError):
        BackgroundTasksRecipe().apply(tmp_path, ctx)
    assert (tmp_path / "Makefile").read_text() == first


def test_recipe_errors_on_existing_run_worker(tmp_path: Path) -> None:
    _scaffold_minimal_host(tmp_path)
    (tmp_path / "scripts").mkdir(exist_ok=True)
    (tmp_path / "scripts" / "run_worker.py").write_text("# user-authored\n")
    with pytest.raises(FileExistsError):
        BackgroundTasksRecipe().apply(
            tmp_path,
            ScaffoldCtx(name="demo", db="sqlite", tenancy=False, selected=("background_tasks",)),
        )
```

- [ ] **Step 8: Run tests to verify they fail**

Run: `uv run pytest framework/hosting/tests/test_cli_recipes.py -v`
Expected: All tests fail with `ModuleNotFoundError: No module named 'simple_module_hosting.cli.recipes'`.

- [ ] **Step 9: Implement `cli/recipes.py`**

```python
# framework/hosting/simple_module_hosting/cli/recipes.py
"""Per-module post-scaffold recipes.

A recipe is invoked by ``smpy new`` after the base host scaffold lands. It
performs module-specific actions (write helper scripts, append Make
targets, drop a docker-compose stack). The framework layer is kept free
of devex concerns — recipes know about Makefiles and compose, framework
scaffolding does not.
"""

from __future__ import annotations

import importlib.resources
import shutil
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

__all__ = [
    "BackgroundTasksRecipe",
    "RECIPES",
    "Recipe",
    "ScaffoldCtx",
]

_OPTIONAL_PACKAGE = "simple_module_hosting.templates.host._optional"
_BG_BROKER_ENV_KEY = "SM_BG_TASKS_BROKER_URL"
_BG_BROKER_DEFAULT = "redis://redis:6379/0"
_MAKEFILE_MARKER = "# --- background_tasks --"


@dataclass(frozen=True)
class ScaffoldCtx:
    name: str
    db: str
    tenancy: bool
    selected: Sequence[str]


class Recipe(Protocol):
    def apply(self, target: Path, ctx: ScaffoldCtx) -> None: ...


def _optional_template_root(name: str) -> Path:
    return Path(str(importlib.resources.files(_OPTIONAL_PACKAGE) / name))


def _set_env_key(text: str, key: str, value: str) -> str:
    """Replace or append ``KEY=VALUE`` in an env-style file body."""
    lines = [ln for ln in text.splitlines() if not ln.startswith(f"{key}=")]
    lines.append(f"{key}={value}")
    return "\n".join(lines) + "\n"


class BackgroundTasksRecipe:
    """Lays down run_worker.py + compose + Dockerfile + Make targets."""

    def apply(self, target: Path, ctx: ScaffoldCtx) -> None:
        templates = _optional_template_root("background_tasks")

        run_worker_dest = target / "scripts" / "run_worker.py"
        compose_dest = target / "docker-compose.yml"
        dockerfile_dest = target / "docker" / "worker.Dockerfile"

        for path in (run_worker_dest, compose_dest, dockerfile_dest):
            if path.exists():
                raise FileExistsError(
                    f"{path} already exists — refusing to clobber. "
                    "Remove the file or run `smpy new` against an empty directory."
                )

        run_worker_dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(templates / "run_worker.py", run_worker_dest)

        shutil.copy2(templates / "docker-compose.yml", compose_dest)

        dockerfile_dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(templates / "worker.Dockerfile", dockerfile_dest)

        env_path = target / ".env.example"
        env_text = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
        env_path.write_text(
            _set_env_key(env_text, _BG_BROKER_ENV_KEY, _BG_BROKER_DEFAULT),
            encoding="utf-8",
        )

        makefile_path = target / "Makefile"
        snippet = (templates / "Makefile.snippet").read_text(encoding="utf-8")
        existing = makefile_path.read_text(encoding="utf-8") if makefile_path.exists() else ""
        if _MAKEFILE_MARKER not in existing:
            sep = "" if existing.endswith("\n") or not existing else "\n"
            makefile_path.write_text(existing + sep + snippet, encoding="utf-8")


RECIPES: dict[str, Recipe] = {
    "background_tasks": BackgroundTasksRecipe(),
}
```

- [ ] **Step 10: Run tests to verify they pass**

Run: `uv run pytest framework/hosting/tests/test_cli_recipes.py -v`
Expected: All 8 tests pass.

- [ ] **Step 11: Commit**

```bash
git add framework/hosting/simple_module_hosting/templates/host/_optional/ \
        framework/hosting/simple_module_hosting/scaffolding.py \
        framework/hosting/simple_module_hosting/cli/recipes.py \
        framework/hosting/tests/test_cli_recipes.py
git commit -m "feat(cli): background_tasks recipe + opt-in templates

Recipes lay down post-scaffold artifacts (run_worker.py, docker-compose
with redis/worker/beat, worker.Dockerfile, Makefile targets, env var)
without touching framework scaffolding. Templates live under
templates/host/_optional/ and are skipped by the default copy walker."
```

---

## Task 5: Refactor `create_app_project` to accept a `selected=` list

**Files:**
- Modify: `framework/hosting/simple_module_hosting/scaffolding.py:198-268`
- Test: `framework/hosting/tests/test_cli_new.py` (add new test cases)

`create_app_project` currently hardcodes `["users", "dashboard", "permissions"]` and a hardcoded `_APP_PY_DEPS`. Make both come from the catalog so the wizard / flags can drive it.

- [ ] **Step 1: Add failing tests for the new `selected=` parameter**

Append to `framework/hosting/tests/test_cli_new.py`:

```python
def test_create_app_project_with_selected_kwarg(tmp_path: Path) -> None:
    from simple_module_hosting.scaffolding import create_app_project

    target = tmp_path / "demo"
    create_app_project(
        target, name="demo", db="sqlite", tenancy=False, selected=["users", "background_tasks"]
    )

    pyproject = (target / "pyproject.toml").read_text()
    # background_tasks selected -> dep listed
    assert "simple_module_background_tasks" in pyproject
    # auth auto-added (users requires auth)
    assert "simple_module_auth" in pyproject
    # dashboard NOT requested -> NOT listed
    assert "simple_module_dashboard" not in pyproject


def test_create_app_project_runs_recipe_for_background_tasks(tmp_path: Path) -> None:
    from simple_module_hosting.scaffolding import create_app_project

    target = tmp_path / "demo"
    create_app_project(
        target, name="demo", db="sqlite", tenancy=False, selected=["background_tasks"]
    )

    assert (target / "scripts" / "run_worker.py").is_file()
    assert (target / "docker-compose.yml").is_file()
    assert (target / "docker" / "worker.Dockerfile").is_file()
    makefile_text = (target / "Makefile").read_text()
    assert "worker:" in makefile_text


def test_create_app_project_default_selected_keeps_back_compat(tmp_path: Path) -> None:
    from simple_module_hosting.scaffolding import create_app_project

    target = tmp_path / "demo"
    create_app_project(target, name="demo", db="sqlite", tenancy=False)
    pyproject = (target / "pyproject.toml").read_text()
    for required in ("simple_module_users", "simple_module_dashboard", "simple_module_permissions"):
        assert required in pyproject
```

- [ ] **Step 2: Run new tests to verify they fail**

Run: `uv run pytest framework/hosting/tests/test_cli_new.py::test_create_app_project_with_selected_kwarg framework/hosting/tests/test_cli_new.py::test_create_app_project_runs_recipe_for_background_tasks -v`
Expected: FAIL — `selected` is an unexpected kwarg.

- [ ] **Step 3: Refactor `create_app_project`**

Replace the function body in `framework/hosting/simple_module_hosting/scaffolding.py` (around lines 198-268). Drop the hardcoded `_APP_PY_DEPS` constant; build deps from the catalog. Add `selected: Sequence[str] | None = None`.

```python
# Near the top of scaffolding.py (after existing imports), add:
from simple_module_hosting.cli.catalog import CATALOG, PRESETS, expand_deps
from simple_module_hosting.cli.recipes import RECIPES, ScaffoldCtx
```

(Keep these imports at module bottom-of-imports to avoid circulars — `cli/recipes.py` imports nothing from `scaffolding.py` at module scope.)

Then replace `create_app_project`:

```python
def create_app_project(
    target: Path,
    *,
    name: str,
    db: str = "sqlite",
    tenancy: bool = False,
    selected: Sequence[str] | None = None,
) -> None:
    """Greenfield ``simple-module new`` scaffold.

    Wraps :func:`create_host` with a chosen module list (defaults to the
    'standard' preset), generates a secret, picks a DB URL, rewrites the
    generated package.json / pyproject.toml to pin exact framework
    versions, and applies any matching post-scaffold recipes.
    """
    if target.exists() and any(target.iterdir()):
        raise FileExistsError(
            f"Destination {target} already exists and is non-empty; "
            "choose a new path or remove its contents first."
        )

    chosen = list(selected) if selected is not None else list(PRESETS["standard"])
    resolved, _added = expand_deps(chosen)

    # create_host expects display names (PascalCase) for the {{MODULE_DEPS}} template.
    display_names = [CATALOG[m].display.replace(" ", "") for m in resolved]
    create_host(target, name=name, modules=display_names)

    py_deps = [f"simple_module_hosting=={_FRAMEWORK_VERSION}"] + [
        f"{CATALOG[m].package}=={_FRAMEWORK_VERSION}" for m in resolved
    ]

    env_path = target / ".env.example"
    env_text = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
    env_text = _set_env_key(env_text, "SM_SECRET_KEY", _secrets.token_urlsafe(32))
    env_text = _set_env_key(env_text, "SM_DATABASE_URL", _db_url(db, _to_kebab_case(name)))
    env_text = _set_env_key(env_text, "SM_MULTI_TENANT", "true" if tenancy else "false")
    env_path.write_text(env_text, encoding="utf-8")

    pyproject = target / "pyproject.toml"
    if pyproject.exists():
        text = pyproject.read_text(encoding="utf-8")
        text = _inject_py_deps(text, py_deps, _APP_PY_DEV_DEPS)
        pyproject.write_text(text, encoding="utf-8")

    pkg_path = target / "package.json"
    if pkg_path.exists():
        data = _json.loads(pkg_path.read_text(encoding="utf-8"))
    else:
        data = {"name": _to_kebab_case(name), "private": True, "type": "module"}
    data.setdefault("dependencies", {}).update(_APP_NPM_DEPS)
    data.setdefault("devDependencies", {}).update(_APP_NPM_DEV_DEPS)
    pkg_path.write_text(_json.dumps(data, indent=2) + "\n", encoding="utf-8")

    ctx = ScaffoldCtx(name=name, db=db, tenancy=tenancy, selected=tuple(resolved))
    for mod_name in resolved:
        recipe_key = CATALOG[mod_name].recipe
        if recipe_key is not None and recipe_key in RECIPES:
            RECIPES[recipe_key].apply(target, ctx)
```

Delete the now-unused `_APP_PY_DEPS` constant.

- [ ] **Step 4: Run all CLI/scaffolding tests**

Run: `uv run pytest framework/hosting/tests/test_cli_new.py framework/hosting/tests/test_cli_catalog.py framework/hosting/tests/test_cli_wizard.py framework/hosting/tests/test_cli_recipes.py framework/hosting/tests/test_scaffolding_host.py -v`
Expected: All pass — including the three new tests from Step 1 and the back-compat test.

- [ ] **Step 5: Commit**

```bash
git add framework/hosting/simple_module_hosting/scaffolding.py framework/hosting/tests/test_cli_new.py
git commit -m "feat(scaffolding): create_app_project accepts selected= module list

Default 'standard' preset preserves existing behavior. Selected modules
drive both Python deps (from catalog) and post-scaffold recipes."
```

---

## Task 6: Wire `smpy new` to use catalog + wizard + recipes

**Files:**
- Create: `framework/hosting/simple_module_hosting/cli/new.py`
- Modify: `framework/hosting/simple_module_hosting/cli/__init__.py` — register `new_project` command from `new.py`, drop the old inline definition
- Test: `framework/hosting/tests/test_cli_new.py` — add flag-driven coverage

- [ ] **Step 1: Write failing tests for the new flag interface**

Append to `framework/hosting/tests/test_cli_new.py`:

```python
def test_sm_new_with_preset_full_includes_background_tasks(tmp_path: Path) -> None:
    runner = CliRunner()
    target = tmp_path / "demo"
    result = runner.invoke(
        main,
        ["new", "demo", "--yes", "--preset", "full", "--no-install", "--dest", str(target)],
    )
    assert result.exit_code == 0, result.output
    assert (target / "scripts" / "run_worker.py").is_file()
    assert (target / "docker-compose.yml").is_file()
    pyproject = (target / "pyproject.toml").read_text()
    assert "simple_module_background_tasks" in pyproject


def test_sm_new_with_explicit_with_flag(tmp_path: Path) -> None:
    runner = CliRunner()
    target = tmp_path / "demo"
    result = runner.invoke(
        main,
        [
            "new",
            "demo",
            "--yes",
            "--preset",
            "minimal",
            "--with",
            "background_tasks",
            "--no-install",
            "--dest",
            str(target),
        ],
    )
    assert result.exit_code == 0, result.output
    pyproject = (target / "pyproject.toml").read_text()
    # users (from minimal) + background_tasks + transitively auth
    assert "simple_module_users" in pyproject
    assert "simple_module_background_tasks" in pyproject
    assert "simple_module_auth" in pyproject


def test_sm_new_unknown_with_module_errors(tmp_path: Path) -> None:
    runner = CliRunner()
    target = tmp_path / "demo"
    result = runner.invoke(
        main,
        ["new", "demo", "--yes", "--with", "does_not_exist", "--no-install", "--dest", str(target)],
    )
    assert result.exit_code != 0
    assert "does_not_exist" in result.output
    assert "available" in result.output.lower()


def test_sm_new_yes_with_no_flags_uses_standard_preset(tmp_path: Path) -> None:
    """Back-compat: --yes alone keeps today's pre-wired set."""
    runner = CliRunner()
    target = tmp_path / "demo"
    result = runner.invoke(
        main,
        ["new", "demo", "--yes", "--no-install", "--dest", str(target)],
    )
    assert result.exit_code == 0, result.output
    pyproject = (target / "pyproject.toml").read_text()
    for required in ("simple_module_users", "simple_module_dashboard", "simple_module_permissions"):
        assert required in pyproject
    # background_tasks not in standard preset
    assert "simple_module_background_tasks" not in pyproject


def test_sm_new_interactive_full_preset(tmp_path: Path) -> None:
    """Wizard path: db, tenancy, preset=3 (full), proceed."""
    runner = CliRunner()
    target = tmp_path / "demo"
    result = runner.invoke(
        main,
        ["new", "demo", "--no-install", "--dest", str(target)],
        input="\n".join(["", "", "3", ""]) + "\n",
    )
    assert result.exit_code == 0, result.output
    assert (target / "docker-compose.yml").is_file()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest framework/hosting/tests/test_cli_new.py -v`
Expected: New tests fail (current `new` command doesn't accept `--preset` / `--with`).

- [ ] **Step 3: Create `cli/new.py`**

```python
# framework/hosting/simple_module_hosting/cli/new.py
"""The upgraded `smpy new` command.

Combines flag-driven non-interactive use (`--preset` / `--with`) with the
interactive wizard. All paths converge on
:func:`simple_module_hosting.scaffolding.create_app_project` with a
resolved module list.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import click

from simple_module_hosting.scaffolding import create_app_project

from .catalog import PRESETS, expand_deps
from .wizard import run_wizard

__all__ = ["new_project"]


@click.command("new")
@click.argument("name")
@click.option(
    "--dest",
    type=click.Path(file_okay=False, path_type=Path),
    default=None,
    help="Destination directory. Defaults to ./<name>.",
)
@click.option(
    "--db",
    type=click.Choice(["sqlite", "postgres"]),
    default="sqlite",
    show_default=True,
    help="Database backend to configure in .env.example.",
)
@click.option(
    "--tenancy/--no-tenancy",
    default=False,
    show_default=True,
    help="Enable the multi-tenant middleware by default.",
)
@click.option(
    "--preset",
    type=click.Choice(["minimal", "standard", "full"]),
    default=None,
    help="Module preset. Mutually compatible with --with (union).",
)
@click.option(
    "--with",
    "extra",
    default="",
    help="Comma-separated extra module names to include (e.g. background_tasks,file_storage).",
)
@click.option(
    "--yes",
    "-y",
    is_flag=True,
    default=False,
    help="Skip interactive prompts; accept defaults.",
)
@click.option(
    "--no-install",
    is_flag=True,
    default=False,
    help="Skip 'uv sync' / 'npm install' / 'alembic upgrade head' after scaffolding.",
)
def new_project(
    name: str,
    dest: Path | None,
    db: str,
    tenancy: bool,
    preset: str | None,
    extra: str,
    yes: bool,
    no_install: bool,
) -> None:
    """Scaffold a new SimpleModule app, optionally with background jobs."""
    target = dest or Path.cwd() / name

    extra_list = [m.strip() for m in extra.split(",") if m.strip()]
    flag_driven = preset is not None or bool(extra_list)

    if yes or flag_driven:
        chosen = list(PRESETS[preset or "standard"]) + extra_list
        try:
            resolved, added = expand_deps(chosen)
        except KeyError as exc:
            click.echo(f"ERROR: {exc}", err=True)
            sys.exit(1)
        for added_name, required_by in added:
            click.echo(f"Added {added_name} (required by {required_by})")
    else:
        try:
            db, tenancy, resolved = run_wizard(default_db=db, default_tenancy=tenancy)
        except click.Abort:
            click.echo("Aborted.", err=True)
            sys.exit(1)

    try:
        create_app_project(target, name=name, db=db, tenancy=tenancy, selected=resolved)
    except FileExistsError as exc:
        click.echo(f"ERROR: {exc}", err=True)
        sys.exit(1)

    click.echo(f"Created app '{name}' at {target}")
    click.echo(f"Modules: {', '.join(resolved)}")
    click.echo("\nNext steps:")
    click.echo(f"  cd {target}")
    if no_install:
        click.echo("  uv sync")
        click.echo("  npm install")
        click.echo("  alembic upgrade head")
        click.echo("  make dev")
        if "background_tasks" in resolved:
            click.echo("  docker compose up -d redis worker beat   # background jobs")
        return

    click.echo("Installing dependencies...")
    for cmd in (["uv", "sync"], ["npm", "install"]):
        result = subprocess.run(cmd, cwd=target, check=False)
        if result.returncode != 0:
            click.echo(
                f"WARNING: {' '.join(cmd)} failed (exit {result.returncode}); "
                "finish setup manually.",
                err=True,
            )
            return

    subprocess.run(["uv", "run", "alembic", "upgrade", "head"], cwd=target, check=False)
    click.echo("\nSetup complete. Run `make dev` in the new directory.")
    if "background_tasks" in resolved:
        click.echo("For background jobs, also run: docker compose up -d redis worker beat")
```

- [ ] **Step 4: Strip the old `new_project` from `cli/__init__.py` and import from `new.py`**

In `framework/hosting/simple_module_hosting/cli/__init__.py`:

1. Remove the entire existing `@main.command("new")`-decorated `new_project` function.
2. Add the import + registration at the bottom of the file (after `main` is defined):

```python
from .new import new_project as _new_project

main.add_command(_new_project)
```

- [ ] **Step 5: Run the full CLI test suite**

Run: `uv run pytest framework/hosting/tests/test_cli_new.py framework/hosting/tests/test_cli_catalog.py framework/hosting/tests/test_cli_wizard.py framework/hosting/tests/test_cli_recipes.py framework/hosting/tests/test_scaffolding_host.py -v`
Expected: All tests pass — both the existing (`--yes --db sqlite`) tests and the five new flag/wizard tests from Step 1.

- [ ] **Step 6: Manual smoke check**

Run:
```bash
TMP=$(mktemp -d) && uv run smpy new demo --yes --preset full --no-install --dest "$TMP/demo"
ls "$TMP/demo/scripts/run_worker.py" "$TMP/demo/docker-compose.yml" "$TMP/demo/docker/worker.Dockerfile"
grep -E '^(worker|beat|worker-docker):' "$TMP/demo/Makefile"
grep SM_BG_TASKS_BROKER_URL "$TMP/demo/.env.example"
```
Expected: every file/grep matches; no errors.

- [ ] **Step 7: Commit**

```bash
git add framework/hosting/simple_module_hosting/cli/new.py \
        framework/hosting/simple_module_hosting/cli/__init__.py \
        framework/hosting/tests/test_cli_new.py
git commit -m "feat(cli): smpy new with --preset, --with, and wizard

Scaffolds a project with any chosen subset of modules. Selecting
background_tasks lands a runnable Celery worker + beat + Redis stack
via docker compose, host Make targets, and scripts/run_worker.py — no
manual editing required."
```

---

## Task 7: Lint, type-check, and final verification

**Files:** none

- [ ] **Step 1: Run the project lint suite**

Run: `make lint`
Expected: PASS. `ty` and `ruff` are happy with the new package; per-file 300-line cap is not breached.

- [ ] **Step 2: Run the full Python test suite**

Run: `uv run pytest`
Expected: All tests pass — including the existing scaffolding/host tests, which must not regress.

- [ ] **Step 3: Verify `make doctor` on a generated project**

Run:
```bash
TMP=$(mktemp -d) && uv run smpy new demo --yes --preset full --no-install --dest "$TMP/demo"
cd "$TMP/demo" && uv sync && uv run smpy doctor 2>&1 || true
cd -
```
Expected: Exits clean (no SM001/SM008/SM009 errors). SM010 may surface because the freshly-scaffolded project has no migration history yet — that's existing behavior.

- [ ] **Step 4: Final commit if any cleanup applied**

If lint or tests required follow-up edits:
```bash
git add -p
git commit -m "chore(cli): post-implementation cleanup"
```

Otherwise skip.

---

## Self-Review (run after writing the plan)

**Spec coverage:** Every section of the spec is mapped to a task —
- Catalog → Task 2
- Wizard → Task 3
- `smpy new` flags → Task 6
- Recipes + templates → Task 4
- `create_app_project` refactor → Task 5
- File-layout reorg into `cli/` package → Task 1
- Tests for catalog / wizard / recipes / smoke → Tasks 2, 3, 4, 6
- Lint / line-cap → Task 7

**No placeholders:** every code block is complete, every command shown.

**Type consistency:** `ScaffoldCtx`, `Recipe`, `ModuleEntry`, `expand_deps` signatures are identical across catalog.py / recipes.py / new.py / scaffolding.py. `selected=` keyword is the same in `create_app_project` and `ScaffoldCtx`.

**Out of scope:** third-party catalog extension; YAML merging; new TUI deps.
