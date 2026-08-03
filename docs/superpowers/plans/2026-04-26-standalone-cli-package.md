# Standalone `simple-module` CLI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Carve the scaffolder out of `simple_module_hosting` into a new PyPI distribution `simple-module` whose only deps are `typer` + `tomlkit`. Single `smpy` console script; plugin subcommands (`smpy host gen-pages`, `smpy users create-admin`, …) discovered via Python entry points. All `sm-*` sibling scripts go away.

**Architecture:** New workspace member `framework/cli/` containing the importable package `simple_module`. Click → Typer 1:1 port at the decorator layer; logic, templates, and tests are copies. `simple_module_hosting` keeps only its runtime + a new `host_cli.py` Typer app registered as a plugin. Modules `users` and `settings` swap their `sm-*` console-script entries for `simple_module.cli_plugins` entry-point entries.

**Tech Stack:** Python 3.12, `typer>=0.12`, `tomlkit>=0.13`, `pytest`, `typer.testing.CliRunner`, `importlib.metadata.entry_points`, hatchling, uv workspaces.

**Spec:** [docs/superpowers/specs/2026-04-26-standalone-cli-package-design.md](docs/superpowers/specs/2026-04-26-standalone-cli-package-design.md)

---

## File-structure summary

| Path | Role |
|---|---|
| `framework/cli/pyproject.toml` | New distribution `simple-module`, deps: `typer`, `tomlkit`. |
| `framework/cli/simple_module/__init__.py` | Empty, marks the package. |
| `framework/cli/simple_module/_env.py` | `set_env_key` (moved from `simple_module_hosting/_env.py`). |
| `framework/cli/simple_module/case.py` | `_to_snake_case`, `_to_kebab_case`, `_to_pascal_case` (moved from `scaffolding.py`). |
| `framework/cli/simple_module/scaffolding.py` | `create_host`, `create_module`, template walker (moved). |
| `framework/cli/simple_module/app_project.py` | `create_app_project` + helpers (moved). |
| `framework/cli/simple_module/catalog.py` | `ModuleEntry`, `CATALOG`, `PRESETS`, `expand_deps` (moved). |
| `framework/cli/simple_module/wizard.py` | `run_wizard` (moved + Typer port). |
| `framework/cli/simple_module/recipes.py` | `Recipe`, `BackgroundTasksRecipe`, `RECIPES` (moved). |
| `framework/cli/simple_module/new.py` | `smpy new` Typer command (moved + ported). |
| `framework/cli/simple_module/cli.py` | Root Typer app + `create-host` / `create-module` commands + plugin mount + `main`. |
| `framework/cli/simple_module/plugins.py` | Entry-point discovery + mounting. |
| `framework/cli/simple_module/templates/` | All template files (moved from hosting). |
| `framework/cli/tests/test_*.py` | Migrated CLI tests (`test_cli_catalog`, `test_cli_wizard`, `test_cli_recipes`, `test_cli_new`, `test_scaffolding_host`, `test_scaffolding_module`, plus new `test_plugin_discovery`, `test_no_framework_deps`). |
| `framework/hosting/simple_module_hosting/host_cli.py` | New: Typer app with `gen-pages` + `sync-js-deps`. |
| `framework/hosting/simple_module_hosting/cli/` | **Deleted** — entire package. |
| `framework/hosting/simple_module_hosting/scaffolding.py` | **Deleted**. |
| `framework/hosting/simple_module_hosting/app_project.py` | **Deleted**. |
| `framework/hosting/simple_module_hosting/_env.py` | **Deleted**. |
| `framework/hosting/simple_module_hosting/templates/` | **Deleted** (moved). |
| `framework/hosting/simple_module_hosting/manifest.py` | Stays — used by `host_cli.py`. |
| `framework/hosting/pyproject.toml` | Drops `smpy`/`simple-module` scripts; adds `simple_module.cli_plugins` entry. |
| `modules/users/pyproject.toml` | Drops `smpy users` script; adds `simple_module.cli_plugins` entry. |
| `modules/settings/pyproject.toml` | Drops `smpy settings` script; adds `simple_module.cli_plugins` entry. |
| `modules/settings/settings/cli.py` | Rewritten as Typer app. |
| `Makefile` | `smpy gen-pages` → `smpy host gen-pages`; `smpy sync-js-deps` → `smpy host sync-js-deps`. |
| `pyproject.toml` (root) | Workspace `members = ["framework/*", …]` already covers `framework/cli`; verify ruff `extend-exclude` updated to point at the new templates path. |
| `README.md` | `smpy users` / `smpy settings` snippets updated to `smpy users …` / `smpy settings …`. |

---

## Task 1: Bootstrap the `simple-module` distribution

**Files:**
- Create: `framework/cli/pyproject.toml`
- Create: `framework/cli/README.md`
- Create: `framework/cli/LICENSE` (copy of root `LICENSE`)
- Create: `framework/cli/simple_module/__init__.py` (empty)
- Modify: `pyproject.toml` (root) — verify `framework/cli` is covered by `framework/*` workspace glob.

- [ ] **Step 1: Create the distribution directory and minimal Python package**

```bash
mkdir -p framework/cli/simple_module framework/cli/tests
touch framework/cli/simple_module/__init__.py
touch framework/cli/tests/__init__.py
```

- [ ] **Step 2: Write `framework/cli/pyproject.toml`**

Create `framework/cli/pyproject.toml`:

```toml
[project]
name = "simple-module"
version = "0.0.1"
description = "Standalone scaffolder for the SimpleModule framework — `smpy new`, `smpy create-module`, plugin host."
readme = "README.md"
license = "MIT"
license-files = ["LICENSE"]
requires-python = ">=3.12"
authors = [{ name = "Anto Subash", email = "antosubash@live.com" }]
keywords = ["simple-module", "scaffolding", "cli", "fastapi", "modular-monolith"]
classifiers = [
    "Development Status :: 3 - Alpha",
    "Intended Audience :: Developers",
    "License :: OSI Approved :: MIT License",
    "Operating System :: OS Independent",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.12",
    "Topic :: Software Development :: Code Generators",
    "Topic :: Software Development :: Libraries :: Application Frameworks",
    "Typing :: Typed",
]
dependencies = [
    "typer>=0.12",
    "tomlkit>=0.13",
]

[project.scripts]
smpy = "simple_module.cli:main"
simple-module = "simple_module.cli:main"

[project.urls]
Homepage = "https://github.com/antosubash/simple_module_python"
Repository = "https://github.com/antosubash/simple_module_python"
Issues = "https://github.com/antosubash/simple_module_python/issues"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["simple_module"]
```

- [ ] **Step 3: Stub `simple_module/cli.py` so the entry point resolves**

Create `framework/cli/simple_module/cli.py`:

```python
"""Root `smpy` command — scaffolders + plugin mount.

This file gets fleshed out in Task 5 (Typer port) and Task 6 (plugin
discovery). For now it exists only so the ``sm = simple_module.cli:main``
console-script entry point resolves cleanly during workspace install.
"""

from __future__ import annotations


def main() -> int:
    raise SystemExit(
        "simple-module CLI is being installed but its commands have not "
        "been wired up yet. Re-install once Task 5 lands."
    )
```

- [ ] **Step 4: Copy the LICENSE and write a README**

```bash
cp LICENSE framework/cli/LICENSE
```

Create `framework/cli/README.md`:

````markdown
# simple-module

Standalone scaffolder for the [SimpleModule framework](https://github.com/antosubash/simple_module_python).

```bash
pip install simple-module      # or: pipx install simple-module
smpy new my-app                  # interactive wizard
smpy new my-app --yes --preset full
```

Provides three built-in commands: `smpy new`, `smpy create-host`, `smpy create-module`.

When other framework packages are installed, they contribute additional subcommands via the `simple_module.cli_plugins` entry-point group:

| Package | Commands |
|---|---|
| `simple_module_hosting` | `smpy host gen-pages`, `smpy host sync-js-deps` |
| `simple_module_users`   | `smpy users create-admin` |
| `simple_module_settings` | `smpy settings import-from-env` |

## License

MIT — see [LICENSE](LICENSE).
````

- [ ] **Step 5: Confirm workspace + uv sync resolves**

The root `pyproject.toml` declares `members = ["framework/*", "modules/*", "host"]`. The new `framework/cli/` is automatically picked up.

Run: `uv sync --all-packages`
Expected: succeeds; the new `simple-module` distribution appears in `uv pip list`. Run `uv pip list 2>&1 | grep simple-module` and expect a row.

- [ ] **Step 6: Verify the stub console script resolves**

Run: `uv run smpy --help 2>&1 | head -3`
Expected: prints the SystemExit message from Step 3 (proves the entry point + package import works).

- [ ] **Step 7: Commit**

```bash
git add framework/cli/ pyproject.toml
git commit -m "feat(cli): bootstrap simple-module distribution

$(cat <<'EOF'
New workspace member framework/cli/ shipping the simple-module PyPI
distribution. Contains stub cli.py for the sm entry point; real
commands land in subsequent commits.
EOF
)"
```

---

## Task 2: Move `_env.py` and case helpers

Two pure-utility modules with no Click/Typer surface, no template I/O. Move first to establish the import-rewrite pattern.

**Files:**
- Create: `framework/cli/simple_module/_env.py`
- Create: `framework/cli/simple_module/case.py`
- Modify: `framework/hosting/simple_module_hosting/scaffolding.py:148-164` (remove `_to_snake_case`, `_to_kebab_case`, `_to_pascal_case`).
- Delete: `framework/hosting/simple_module_hosting/_env.py`
- Modify: `framework/hosting/simple_module_hosting/app_project.py` (update import).
- Modify: `framework/hosting/simple_module_hosting/cli/recipes.py` (update import).

- [ ] **Step 1: Create `framework/cli/simple_module/_env.py`**

```python
"""Shared helpers for editing dotenv-style files at scaffold time."""

from __future__ import annotations

__all__ = ["set_env_key"]


def set_env_key(text: str, key: str, value: str) -> str:
    """Replace or append ``KEY=VALUE`` in an env-style file body."""
    lines = [ln for ln in text.splitlines() if not ln.startswith(f"{key}=")]
    lines.append(f"{key}={value}")
    return "\n".join(lines) + "\n"
```

- [ ] **Step 2: Create `framework/cli/simple_module/case.py`**

```python
"""Identifier case-conversion helpers used by every scaffolder.

Module/host names are accepted in any case style and normalized to the
three forms the templates need: snake_case (Python package + entry-point
key), kebab-case (PyPI slug), and PascalCase (display name in Meta).
"""

from __future__ import annotations

import re

__all__ = ["to_kebab_case", "to_pascal_case", "to_snake_case"]


def to_snake_case(name: str) -> str:
    """'MyFeature' / 'my-feature' / 'My Feature' -> 'my_feature'."""
    s = re.sub(r"(?<!^)(?=[A-Z])", "_", name)
    s = re.sub(r"[\s\-]+", "_", s)
    return s.lower()


def to_kebab_case(name: str) -> str:
    """'MyFeature' / 'my_feature' -> 'my-feature' (used as the PyPI slug)."""
    return to_snake_case(name).replace("_", "-")


def to_pascal_case(name: str) -> str:
    """'my-feature' / 'my_feature' -> 'MyFeature' (the display name in Meta)."""
    snake = to_snake_case(name)
    return "".join(part.capitalize() for part in snake.split("_") if part)
```

(Note: leading `_` removed — these are now public helpers under `simple_module.case`.)

- [ ] **Step 3: Add `simple-module` as a workspace dep of `simple_module_hosting`**

Edit `framework/hosting/pyproject.toml` — add to `dependencies`:

```toml
dependencies = [
    "click>=8.1",
    "fastapi>=0.115",
    "fastapi-inertia>=1.0",
    "httpx>=0.27",
    "jinja2>=3.1",
    "simple_module==0.0.1",        # NEW
    "simple_module_core==0.0.1",
    "simple_module_db==0.0.1",
    "starlette>=0.44",
    "tomlkit>=0.13",
    "uvicorn[standard]>=0.34",
]
```

And add to `[tool.uv.sources]`:

```toml
[tool.uv.sources]
simple_module = { workspace = true }
simple_module_core = { workspace = true }
simple_module_db = { workspace = true }
```

(Keep this dep through the rest of the migration so `simple_module_hosting` can re-import freely from `simple_module`. It's removed in Task 9.)

- [ ] **Step 4: Run `uv sync --all-packages`**

Run: `uv sync --all-packages`
Expected: succeeds.

- [ ] **Step 5: Update `simple_module_hosting/app_project.py` to import from `simple_module`**

Replace the existing imports (currently at top of file + a local import inside `create_app_project`):

```python
# At top of framework/hosting/simple_module_hosting/app_project.py
from simple_module._env import set_env_key
from simple_module.case import to_kebab_case, to_pascal_case
```

Inside `create_app_project`, drop the local import of `_to_kebab_case`, `_to_pascal_case`, `create_host` from `simple_module_hosting.scaffolding` — keep only the `create_host` local import (case helpers are now top-level):

```python
def create_app_project(
    target: Path,
    *,
    name: str,
    db: str = "sqlite",
    tenancy: bool = False,
    selected: Sequence[str] | None = None,
) -> None:
    from simple_module_hosting.cli.catalog import CATALOG, PRESETS, expand_deps
    from simple_module_hosting.cli.recipes import RECIPES, ScaffoldCtx
    from simple_module_hosting.scaffolding import create_host

    ...
```

Replace the two call sites:
- `_to_kebab_case(name)` → `to_kebab_case(name)`
- `_to_pascal_case(CATALOG[m].display)` → `to_pascal_case(CATALOG[m].display)`

- [ ] **Step 6: Update `simple_module_hosting/cli/recipes.py` to import from `simple_module`**

Replace `from simple_module_hosting._env import set_env_key` with:

```python
from simple_module._env import set_env_key
```

- [ ] **Step 7: Delete the case helpers from `scaffolding.py`**

Edit `framework/hosting/simple_module_hosting/scaffolding.py`. Remove the three definitions:

```python
def _to_snake_case(name: str) -> str: ...
def _to_kebab_case(name: str) -> str: ...
def _to_pascal_case(name: str) -> str: ...
```

(They lived around lines 148-164; they're no longer needed.) `create_module` calls them; update it to import from `simple_module.case`:

```python
# Top of scaffolding.py
from simple_module.case import to_kebab_case, to_pascal_case, to_snake_case
```

Inside `create_module`, replace `_to_pascal_case(name)` → `to_pascal_case(name)`, `_to_kebab_case(name)` → `to_kebab_case(name)`, `_to_snake_case(name)` → `to_snake_case(name)`.

- [ ] **Step 8: Delete `framework/hosting/simple_module_hosting/_env.py`**

```bash
git rm framework/hosting/simple_module_hosting/_env.py
```

- [ ] **Step 9: Run the full hosting test suite**

Run: `uv run pytest framework/hosting/ -q`
Expected: all 144 tests pass.

- [ ] **Step 10: Commit**

```bash
git add framework/cli/ framework/hosting/ pyproject.toml
git commit -m "refactor(cli): move _env and case helpers to simple_module package

$(cat <<'EOF'
Pure utilities; first pieces of the simple-module distribution. Hosting
keeps temporary workspace dep on simple-module so existing modules can
import from both during the migration.
EOF
)"
```

---

## Task 3: Move `scaffolding.py` (`create_host`, `create_module`) and templates

**Files:**
- Create: `framework/cli/simple_module/scaffolding.py`
- Move: `framework/hosting/simple_module_hosting/templates/` → `framework/cli/simple_module/templates/`
- Modify: `framework/cli/pyproject.toml` (declare templates as package data via hatch).
- Modify: `framework/hosting/simple_module_hosting/scaffolding.py` (becomes a re-export shim).
- Move: `framework/hosting/tests/test_scaffolding_host.py` → `framework/cli/tests/test_scaffolding_host.py`
- Move: `framework/hosting/tests/test_scaffolding_module.py` → `framework/cli/tests/test_scaffolding_module.py`
- Update: import sites in moved tests + in `simple_module_hosting/cli/recipes.py` + in `simple_module_hosting/app_project.py`.
- Modify: root `pyproject.toml` `[tool.ruff] extend-exclude` to point at the new templates path.

- [ ] **Step 1: Move templates wholesale**

```bash
git mv framework/hosting/simple_module_hosting/templates framework/cli/simple_module/templates
```

- [ ] **Step 2: Update root `pyproject.toml` ruff exclude**

Edit `pyproject.toml` (root). Replace:

```toml
extend-exclude = ["framework/hosting/simple_module_hosting/templates"]
```

with:

```toml
extend-exclude = ["framework/cli/simple_module/templates"]
```

- [ ] **Step 3: Create `framework/cli/simple_module/scaffolding.py`**

This is a near-verbatim copy of the current `framework/hosting/simple_module_hosting/scaffolding.py`, **minus** `create_app_project` (still in hosting; moves in Task 4) and minus the case helpers (moved in Task 2).

```python
"""Host + module scaffolding via package-data templates.

* :func:`create_host` materializes a new host project from the templates
  under ``simple_module/templates/host/``.
* :func:`create_module` materializes a new module package from
  ``simple_module/templates/module/``.

The frontend pages manifest + per-module JS dep discovery live in
:mod:`simple_module_hosting.manifest` (those need module-discovery and
stay in hosting).
"""

from __future__ import annotations

import importlib.resources
import logging
import re
import shutil
from collections.abc import Mapping, Sequence
from pathlib import Path

from simple_module.case import to_kebab_case, to_pascal_case, to_snake_case

__all__ = ["create_host", "create_module"]

logger = logging.getLogger(__name__)

_TEMPLATES_PACKAGE = "simple_module.templates"
_PACKAGE_PATH_TOKEN = "__PACKAGE__"


def _module_to_pypi_name(name: str) -> str:
    return f"simple_module_{name.lower()}"


def _iter_template_files(template_root: Path):
    """Yield every file under ``template_root``. Skips ``_optional/`` paths."""
    for path in template_root.rglob("*"):
        if not path.is_file():
            continue
        if "_optional" in path.relative_to(template_root).parts:
            continue
        yield path


def _require_empty_dest(dest: Path) -> None:
    if dest.exists() and any(dest.iterdir()):
        raise FileExistsError(
            f"Destination {dest} already exists and is non-empty. "
            "Choose a new path or remove the contents first."
        )
    dest.mkdir(parents=True, exist_ok=True)


def _resolve_template_root(subdir: str, override: Path | None) -> Path:
    if override is not None:
        return Path(override)
    return Path(str(importlib.resources.files(_TEMPLATES_PACKAGE) / subdir))


def _apply_template_files(
    src_root: Path,
    dest: Path,
    substitutions: Mapping[str, str],
    *,
    path_rewrites: Mapping[str, str] | None = None,
) -> None:
    for src in _iter_template_files(src_root):
        rel_str = str(src.relative_to(src_root))
        for old, new in (path_rewrites or {}).items():
            rel_str = rel_str.replace(old, new)
        rel_str = rel_str.removesuffix(".tpl")
        target = dest / rel_str
        target.parent.mkdir(parents=True, exist_ok=True)
        if src.suffix == ".tpl":
            text = src.read_text(encoding="utf-8")
            for placeholder, value in substitutions.items():
                text = text.replace(placeholder, value)
            target.write_text(text, encoding="utf-8")
        else:
            shutil.copy2(src, target)


def create_host(
    dest: Path,
    name: str,
    modules: Sequence[str],
    template_root: Path | None = None,
) -> Path:
    dest = Path(dest)
    _require_empty_dest(dest)
    module_dep_lines = "\n".join(f'    "{_module_to_pypi_name(m)}>=0.1,<1.0",' for m in modules)
    _apply_template_files(
        _resolve_template_root("host", template_root),
        dest,
        {"{{HOST_NAME}}": name, "{{MODULE_DEPS}}": module_dep_lines},
    )
    logger.info(
        "Scaffolded host '%s' at %s (modules: %s)", name, dest, ", ".join(modules) or "<none>"
    )
    return dest


def create_module(
    dest: Path,
    name: str,
    template_root: Path | None = None,
) -> Path:
    dest = Path(dest)
    _require_empty_dest(dest)
    display_name = to_pascal_case(name)
    slug = to_kebab_case(name)
    package_name = to_snake_case(name)
    _apply_template_files(
        _resolve_template_root("module", template_root),
        dest,
        substitutions={
            "{{MODULE_NAME}}": display_name,
            "{{MODULE_SLUG}}": slug,
            "{{PACKAGE_NAME}}": package_name,
        },
        path_rewrites={_PACKAGE_PATH_TOKEN: package_name},
    )
    logger.info("Scaffolded module '%s' at %s (package: %s)", display_name, dest, package_name)
    return dest
```

- [ ] **Step 4: Add `force-include` for templates in `framework/cli/pyproject.toml`**

Append to the `[tool.hatch.build.targets.wheel]` block in `framework/cli/pyproject.toml`:

```toml
[tool.hatch.build.targets.wheel]
packages = ["simple_module"]

[tool.hatch.build.targets.wheel.shared-data]
"simple_module/templates" = "simple_module/templates"
```

(Hatchling auto-includes anything inside a `packages = [...]` directory by default. The shared-data block is belt-and-braces for files like `Makefile.snippet` whose extensions aren't recognized as package code.)

- [ ] **Step 5: Reduce hosting's `scaffolding.py` to a thin shim**

Replace `framework/hosting/simple_module_hosting/scaffolding.py` with:

```python
"""Re-exports of moved scaffolding APIs.

The actual implementations live in :mod:`simple_module.scaffolding`. This
shim lets the in-tree hosting code keep importing from the historical
path during the migration; it is removed in the final cleanup task.
"""

from __future__ import annotations

from simple_module.scaffolding import create_host, create_module

from simple_module_hosting.manifest import (
    collect_module_js_deps,
    compute_module_pages,
    read_module_package_json,
    repo_root_from_client_app,
    write_module_pages_manifest,
)

# create_app_project lives in app_project.py; re-exported via __all__.
from simple_module_hosting.app_project import create_app_project as create_app_project

__all__ = [
    "collect_module_js_deps",
    "compute_module_pages",
    "create_app_project",
    "create_host",
    "create_module",
    "read_module_package_json",
    "repo_root_from_client_app",
    "write_module_pages_manifest",
]
```

- [ ] **Step 6: Update hosting's `app_project.py` to import `create_host` from the new location**

Inside `create_app_project`, change the local import:

```python
from simple_module.scaffolding import create_host
```

(Keep the `simple_module_hosting.cli.{catalog,recipes}` imports — those move in Task 4.)

- [ ] **Step 7: Move test files**

```bash
git mv framework/hosting/tests/test_scaffolding_host.py framework/cli/tests/test_scaffolding_host.py
git mv framework/hosting/tests/test_scaffolding_module.py framework/cli/tests/test_scaffolding_module.py
```

- [ ] **Step 8: Update imports in the moved tests**

In both moved files, replace `from simple_module_hosting.scaffolding import ...` with `from simple_module.scaffolding import ...`. The `from simple_module_hosting.cli import main` in the `Click smpy create-host/create-module` integration tests stays — those tests get rewritten in Task 5.

Concretely, in `framework/cli/tests/test_scaffolding_host.py`:
- Line 14: `from simple_module_hosting.scaffolding import compute_module_pages` — leave for now (`compute_module_pages` is re-exported via the shim — works through Task 8).
- All other `from simple_module_hosting.scaffolding import create_host` / `compute_module_pages` lines: leave them; they work through the shim.

In `framework/cli/tests/test_scaffolding_module.py`:
- All `from simple_module_hosting.scaffolding import create_module` lines: leave them; the shim re-exports `create_module`.

This is intentional — Task 3 just relocates; the shim keeps tests green. Tests get retargeted in Task 8 when the shim is removed.

- [ ] **Step 9: Add `framework/cli/conftest.py` if needed**

If the moved tests reference framework-level fixtures (like `db_session`), they pull in heavy deps. Inspect:

Run: `grep -n 'db_session\|app\|authenticated_client\|settings' framework/cli/tests/test_scaffolding_host.py framework/cli/tests/test_scaffolding_module.py`
Expected: no matches (these are pure scaffolding tests, no fixture deps).

If matches appear, decide test-by-test: either leave the test in `framework/hosting/tests/` (if it really needs runtime fixtures) or write a slim `framework/cli/conftest.py` covering only the needed bits. For the planned moves, no conftest is needed.

- [ ] **Step 10: Run pytest**

Run: `uv run pytest framework/cli/ framework/hosting/ -q`
Expected: all tests pass (the relocated `test_scaffolding_*` files run from their new home; everything else unaffected).

- [ ] **Step 11: Commit**

```bash
git add -A
git commit -m "refactor(cli): move scaffolding + templates to simple_module package

$(cat <<'EOF'
create_host, create_module, _apply_template_files, and the entire
templates/ tree relocate from simple_module_hosting to the new
simple_module package. Hosting's scaffolding.py becomes a re-export
shim so existing import sites keep working through Task 7.
EOF
)"
```

---

## Task 4: Move `app_project.py`, `catalog.py`, `wizard.py`, `recipes.py`

Click is still in play — this task only relocates code without changing the framework. Typer port lands in Task 5.

**Files:**
- Move: `framework/hosting/simple_module_hosting/app_project.py` → `framework/cli/simple_module/app_project.py`
- Move: `framework/hosting/simple_module_hosting/cli/{catalog,wizard,recipes}.py` → `framework/cli/simple_module/{catalog,wizard,recipes}.py`
- Move: tests `test_cli_{catalog,wizard,recipes}.py` → `framework/cli/tests/`
- Modify: `framework/hosting/simple_module_hosting/scaffolding.py` (shim — `create_app_project` re-import path).
- Modify: `framework/hosting/simple_module_hosting/cli/__init__.py` — drop the catalog/wizard/recipes imports from `new_project`.

- [ ] **Step 1: Move the four source files**

```bash
git mv framework/hosting/simple_module_hosting/app_project.py framework/cli/simple_module/app_project.py
git mv framework/hosting/simple_module_hosting/cli/catalog.py framework/cli/simple_module/catalog.py
git mv framework/hosting/simple_module_hosting/cli/wizard.py framework/cli/simple_module/wizard.py
git mv framework/hosting/simple_module_hosting/cli/recipes.py framework/cli/simple_module/recipes.py
```

- [ ] **Step 2: Fix imports inside the moved files**

In `framework/cli/simple_module/app_project.py`, change:
- `from simple_module._env import set_env_key` — already correct.
- `from simple_module.case import to_kebab_case, to_pascal_case` — already correct.
- Inside `create_app_project`, replace the local imports:

```python
def create_app_project(
    target: Path,
    *,
    name: str,
    db: str = "sqlite",
    tenancy: bool = False,
    selected: Sequence[str] | None = None,
) -> None:
    from simple_module.catalog import CATALOG, PRESETS, expand_deps
    from simple_module.recipes import RECIPES, ScaffoldCtx
    from simple_module.scaffolding import create_host

    ...
```

In `framework/cli/simple_module/wizard.py`:
- `from .catalog import CATALOG, PRESETS, expand_deps` → `from simple_module.catalog import CATALOG, PRESETS, expand_deps`
- (Or use relative imports; they all live in the same package now: `from .catalog import ...` still works.)

In `framework/cli/simple_module/recipes.py`:
- `from simple_module._env import set_env_key` — already correct.
- The `_optional_template_root` helper currently does `importlib.resources.files("simple_module_hosting")` — change to `importlib.resources.files("simple_module")`:

```python
def _optional_template_root(name: str) -> Path:
    """Resolve ``templates/host/_optional/<name>/`` from package data."""
    base = importlib.resources.files("simple_module")
    return Path(str(base / "templates" / "host" / "_optional" / name))
```

In `framework/cli/simple_module/catalog.py`:
- No external imports — leave as is.

- [ ] **Step 3: Move the three test files**

```bash
git mv framework/hosting/tests/test_cli_catalog.py framework/cli/tests/test_cli_catalog.py
git mv framework/hosting/tests/test_cli_wizard.py framework/cli/tests/test_cli_wizard.py
git mv framework/hosting/tests/test_cli_recipes.py framework/cli/tests/test_cli_recipes.py
```

- [ ] **Step 4: Update imports in the three moved test files**

`framework/cli/tests/test_cli_catalog.py`:
```python
from simple_module.catalog import (
    CATALOG,
    PRESETS,
    ModuleEntry,
    expand_deps,
)
```

`framework/cli/tests/test_cli_wizard.py`:
```python
from simple_module.wizard import run_wizard
```

`framework/cli/tests/test_cli_recipes.py`:
```python
from simple_module.recipes import (
    RECIPES,
    BackgroundTasksRecipe,
    ScaffoldCtx,
)
from simple_module.scaffolding import create_host
```

- [ ] **Step 5: Patch the hosting scaffolding shim**

The shim from Task 3 already re-exports `create_app_project` from `simple_module_hosting.app_project` — but that file just moved. Update the shim to re-export from the new home:

In `framework/hosting/simple_module_hosting/scaffolding.py`, change:

```python
from simple_module_hosting.app_project import create_app_project as create_app_project
```

to:

```python
from simple_module.app_project import create_app_project as create_app_project
```

- [ ] **Step 6: Patch the hosting `cli/__init__.py` imports**

The Click `new_project` command in `framework/hosting/simple_module_hosting/cli/__init__.py` is removed in Task 5; for now, just adjust its imports so tests keep passing:

Edit `framework/hosting/simple_module_hosting/cli/__init__.py`:
- The bottom-of-file `from .new import new_project as _new_project` line: change to `from simple_module.new import new_project as _new_project` for now. (Both files still exist via Click; Task 5 deletes the `new.py` in hosting.)

Wait — `cli/new.py` was already moved out by `git mv` in Task 4 Step 1? No — I only moved `catalog.py`, `wizard.py`, `recipes.py`. The `new.py` is still in `simple_module_hosting/cli/new.py`. Move it now too:

```bash
git mv framework/hosting/simple_module_hosting/cli/new.py framework/cli/simple_module/new.py
```

In the moved `framework/cli/simple_module/new.py`, update imports:

```python
from simple_module.app_project import create_app_project
from simple_module.catalog import PRESETS, expand_deps
from simple_module.wizard import run_wizard
```

And in `framework/hosting/simple_module_hosting/cli/__init__.py`:

```python
from simple_module.new import new_project as _new_project  # noqa: E402
```

- [ ] **Step 7: Move `test_cli_new.py` and update imports**

```bash
git mv framework/hosting/tests/test_cli_new.py framework/cli/tests/test_cli_new.py
```

In `framework/cli/tests/test_cli_new.py`, change:
- `from simple_module_hosting.cli import main` — leave for now; `simple_module_hosting.cli:main` still works (Click group + the relocated `new_project` registered into it). The Typer port in Task 5 will switch this to `from simple_module.cli import app` and `runner.invoke(app, ...)`.
- All `from simple_module_hosting.scaffolding import create_app_project` — leave; works through the Task 3 shim.

- [ ] **Step 8: Run the test suite**

Run: `uv run pytest framework/cli/ framework/hosting/ -q`
Expected: all tests pass — the existing Click `smpy` is still functional through the hosting package; tests in `framework/cli/tests/` import from the moved homes and exercise the same code.

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "refactor(cli): move app_project, catalog, wizard, recipes, new to simple_module

$(cat <<'EOF'
All scaffolding logic now lives in the simple_module package. Hosting's
cli/__init__.py click group still works (it imports new_project from
the new location); fully replaced by the Typer port in the next commit.
EOF
)"
```

---

## Task 5: Convert CLI to Typer + build root `cli.py`

Big change. Rewrites the four command files — `new.py`, `cli.py` (new), and the wizard's prompt usage — from Click to Typer. Updates the test runner.

**Files:**
- Modify: `framework/cli/simple_module/new.py` (Click decorators → Typer).
- Modify: `framework/cli/simple_module/wizard.py` (Click prompts → Typer prompts).
- Create: `framework/cli/simple_module/cli.py` (root Typer app + `create-host` / `create-module` commands + `main`).
- Modify: all five `framework/cli/tests/test_cli_*.py` files: `from click.testing import CliRunner` → `from typer.testing import CliRunner`; `from simple_module_hosting.cli import main` → `from simple_module.cli import app`.
- Delete: `framework/hosting/simple_module_hosting/cli/__init__.py` (and the empty `cli/` dir).

- [ ] **Step 1: Rewrite `framework/cli/simple_module/new.py` in Typer style**

Replace the entire file with:

```python
"""``smpy new`` Typer command — flag-driven or interactive scaffolder."""

from __future__ import annotations

import subprocess
import sys
from enum import Enum
from pathlib import Path
from typing import Annotated

import typer

from simple_module.app_project import create_app_project
from simple_module.catalog import PRESETS, expand_deps
from simple_module.wizard import run_wizard

__all__ = ["new_project"]


class Db(str, Enum):
    sqlite = "sqlite"
    postgres = "postgres"


class Preset(str, Enum):
    minimal = "minimal"
    standard = "standard"
    full = "full"


def new_project(
    name: Annotated[str, typer.Argument(help="App name (used for directory + package).")],
    dest: Annotated[
        Path | None,
        typer.Option("--dest", help="Destination directory. Defaults to ./<name>."),
    ] = None,
    db: Annotated[
        Db,
        typer.Option("--db", help="Database backend to configure in .env.example."),
    ] = Db.sqlite,
    tenancy: Annotated[
        bool,
        typer.Option("--tenancy/--no-tenancy", help="Enable the multi-tenant middleware."),
    ] = False,
    preset: Annotated[
        Preset | None,
        typer.Option("--preset", help="Module preset. Combine with --with."),
    ] = None,
    extra: Annotated[
        str,
        typer.Option(
            "--with",
            help="Comma-separated extra modules (e.g. background_tasks,file_storage).",
        ),
    ] = "",
    yes: Annotated[
        bool,
        typer.Option("--yes", "-y", help="Skip interactive prompts; accept defaults."),
    ] = False,
    no_install: Annotated[
        bool,
        typer.Option(
            "--no-install",
            help="Skip 'uv sync' / 'npm install' / 'alembic upgrade head' after scaffolding.",
        ),
    ] = False,
) -> None:
    """Scaffold a new SimpleModule app, optionally with background jobs."""
    target = dest or Path.cwd() / name
    extra_list = [m.strip() for m in extra.split(",") if m.strip()]
    flag_driven = preset is not None or bool(extra_list)
    db_value: str = db.value
    tenancy_value: bool = tenancy

    if yes or flag_driven:
        chosen = list(PRESETS[(preset or Preset.standard).value]) + extra_list
        try:
            resolved, added = expand_deps(chosen)
        except KeyError as exc:
            typer.echo(f"ERROR: {exc}", err=True)
            raise typer.Exit(code=1) from exc
        for added_name, required_by in added:
            typer.echo(f"Added {added_name} (required by {required_by})")
    else:
        try:
            db_value, tenancy_value, resolved = run_wizard(
                default_db=db.value, default_tenancy=tenancy
            )
        except typer.Abort:
            typer.echo("Aborted.", err=True)
            raise typer.Exit(code=1)

    try:
        create_app_project(target, name=name, db=db_value, tenancy=tenancy_value, selected=resolved)
    except FileExistsError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(f"Created app '{name}' at {target}")
    typer.echo(f"Modules: {', '.join(resolved)}")
    typer.echo("\nNext steps:")
    typer.echo(f"  cd {target}")
    if no_install:
        typer.echo("  uv sync")
        typer.echo("  npm install")
        typer.echo("  alembic upgrade head")
        typer.echo("  make dev")
        if "background_tasks" in resolved:
            typer.echo("  docker compose up -d redis worker beat   # background jobs")
        return

    typer.echo("Installing dependencies...")
    for cmd in (["uv", "sync"], ["npm", "install"]):
        result = subprocess.run(cmd, cwd=target, check=False)
        if result.returncode != 0:
            typer.echo(
                f"WARNING: {' '.join(cmd)} failed (exit {result.returncode}); "
                "finish setup manually.",
                err=True,
            )
            return

    subprocess.run(["uv", "run", "alembic", "upgrade", "head"], cwd=target, check=False)
    typer.echo("\nSetup complete. Run `make dev` in the new directory.")
    if "background_tasks" in resolved:
        typer.echo("For background jobs, also run: docker compose up -d redis worker beat")
```

- [ ] **Step 2: Rewrite `framework/cli/simple_module/wizard.py` to use Typer prompts**

Replace the file with:

```python
"""Interactive prompt sequence for ``smpy new``."""

from __future__ import annotations

import typer

from simple_module.catalog import CATALOG, PRESETS, expand_deps

__all__ = ["run_wizard"]

_PRESET_CHOICES = ("minimal", "standard", "full", "custom")


def run_wizard(*, default_db: str, default_tenancy: bool) -> tuple[str, bool, list[str]]:
    db = typer.prompt("Database backend", default=default_db, type=str)
    if db not in ("sqlite", "postgres"):
        typer.echo(f"Invalid database: {db!r}; expected sqlite or postgres", err=True)
        raise typer.Abort()
    tenancy = typer.confirm("Enable multi-tenancy?", default=default_tenancy)

    typer.echo("\nPreset:")
    typer.echo("  [1] minimal  — users only")
    typer.echo("  [2] standard — users, dashboard, permissions  (default)")
    typer.echo("  [3] full     — every module")
    typer.echo("  [4] custom   — pick modules one by one")
    choice = typer.prompt("Choose", default="2", type=str)
    if choice not in {"1", "2", "3", "4"}:
        typer.echo(f"Invalid choice: {choice!r}", err=True)
        raise typer.Abort()
    preset_name = _PRESET_CHOICES[int(choice) - 1]

    if preset_name == "custom":
        picked = [
            name
            for name in CATALOG
            if typer.confirm(f"Include {CATALOG[name].display}?", default=False)
        ]
    else:
        picked = list(PRESETS[preset_name])

    resolved, added = expand_deps(picked)
    for name, required_by in added:
        typer.echo(f"Added {name} (required by {required_by})")
    typer.echo(f"Selected modules: {', '.join(resolved)}")

    if not typer.confirm("Proceed?", default=True):
        raise typer.Abort()
    return db, tenancy, resolved
```

(Note: typer.prompt doesn't have a built-in `choice` validator the way `click.prompt` does, so we validate manually after the prompt and raise `typer.Abort` on invalid input. Behavior equivalent for the test scenarios.)

- [ ] **Step 3: Create `framework/cli/simple_module/cli.py`** (root app)

Replace the stub from Task 1 with:

```python
"""Root `smpy` Typer app — scaffolders + plugin mount.

Built-in commands:
  smpy new
  smpy create-host
  smpy create-module

Plugins discovered via the ``simple_module.cli_plugins`` entry-point
group are mounted as named subgroups (e.g. ``smpy host gen-pages``).
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from typing import Annotated

import typer

from simple_module.case import to_kebab_case
from simple_module.new import new_project
from simple_module.plugins import discover_and_mount
from simple_module.scaffolding import create_host as _create_host
from simple_module.scaffolding import create_module as _create_module

app = typer.Typer(
    help="SimpleModule developer CLI.",
    no_args_is_help=True,
    add_completion=False,
)

# Built-in commands
app.command("new")(new_project)


@app.command("create-host")
def create_host(
    name: Annotated[str, typer.Argument(help="Host project name.")],
    dest: Annotated[
        Path | None,
        typer.Option("--dest", help="Destination directory. Defaults to ./<name>."),
    ] = None,
    modules: Annotated[
        str,
        typer.Option(
            "--with",
            help="Comma-separated module names to declare as deps (e.g. Auth,Products).",
        ),
    ] = "",
) -> None:
    """Scaffold a new SimpleModule host project at ./<NAME>."""
    target = dest or Path.cwd() / name
    selected = [m.strip() for m in modules.split(",") if m.strip()]
    try:
        _create_host(target, name=name, modules=selected)
    except FileExistsError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(f"Created host '{name}' at {target}")
    if selected:
        typer.echo(f"Declared modules: {', '.join(selected)}")
    typer.echo("\nNext steps:")
    typer.echo(f"  cd {target}")
    typer.echo("  uv sync")
    typer.echo("  cp .env.example .env")
    typer.echo('  alembic revision --autogenerate -m "initial schema"')
    typer.echo("  alembic upgrade head")
    typer.echo("  python main.py")


@app.command("create-module")
def create_module(
    name: Annotated[str, typer.Argument(help="Module name (any case).")],
    dest: Annotated[
        Path | None,
        typer.Option("--dest", help="Destination dir. Defaults to ./simple_module_<name>."),
    ] = None,
) -> None:
    """Scaffold a publishable SimpleModule module package."""
    slug = to_kebab_case(name)
    package = slug.replace("-", "_")
    target = dest or Path.cwd() / f"simple_module_{package}"
    try:
        _create_module(target, name=name)
    except FileExistsError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(f"Created module 'simple_module_{package}' at {target}")
    typer.echo("\nNext steps:")
    typer.echo(f"  cd {target}")
    typer.echo("  uv sync --extra dev")
    typer.echo("  uv run pytest")


# Plugin discovery — mount any installed `simple_module.cli_plugins`
# entry-point apps as named subgroups (e.g. `smpy host gen-pages`).
discover_and_mount(app)


def main() -> None:
    """Entry point for the `smpy` console script."""
    app()


if __name__ == "__main__":
    main()
```

(Note: `discover_and_mount` is implemented in Task 6. For now this import will fail — that's OK; we land both tasks before re-running the suite.)

- [ ] **Step 4: Stub `framework/cli/simple_module/plugins.py`**

Create a minimal stub so Task 5 can run end-to-end before Task 6 fleshes it out:

```python
"""Plugin discovery via ``simple_module.cli_plugins`` entry points.

Real implementation lands in Task 6. For now this is a no-op so the
root Typer app imports cleanly.
"""

from __future__ import annotations

import typer


def discover_and_mount(app: typer.Typer) -> None:
    """No-op stub. Implemented in Task 6."""
```

- [ ] **Step 5: Update test files for Typer**

Replace `from click.testing import CliRunner` with `from typer.testing import CliRunner` in:
- `framework/cli/tests/test_cli_new.py`
- (`test_cli_wizard.py` uses Click's CliRunner inside a wrapper — see below)

In `framework/cli/tests/test_cli_new.py`:
- `from simple_module_hosting.cli import main` → `from simple_module.cli import app`
- All `runner.invoke(main, ["new", ...])` → `runner.invoke(app, ["new", ...])`
- All `from simple_module_hosting.scaffolding import create_app_project` → `from simple_module.app_project import create_app_project`

In `framework/cli/tests/test_cli_wizard.py`:

The wizard tests currently wrap `run_wizard` inside an ad-hoc `@click.command` for stdin driving. Rewrite the helper to use a Typer app:

```python
from __future__ import annotations

import typer
from typer.testing import CliRunner

from simple_module.wizard import run_wizard


def _drive(answers: list[str]) -> tuple[str, bool, list[str], str]:
    captured: dict = {}
    wrapper_app = typer.Typer()

    @wrapper_app.command()
    def wrapper() -> None:
        db, tenancy, selected = run_wizard(default_db="sqlite", default_tenancy=False)
        captured["db"] = db
        captured["tenancy"] = tenancy
        captured["selected"] = selected

    runner = CliRunner()
    result = runner.invoke(wrapper_app, [], input="\n".join(answers) + "\n")
    assert result.exit_code == 0, result.output
    return captured["db"], captured["tenancy"], captured["selected"], result.output


def test_wizard_aborts_on_confirm_no() -> None:
    captured: dict = {}
    wrapper_app = typer.Typer()

    @wrapper_app.command()
    def wrapper() -> None:
        try:
            run_wizard(default_db="sqlite", default_tenancy=False)
        except typer.Abort:
            captured["aborted"] = True
            raise

    runner = CliRunner()
    result = runner.invoke(wrapper_app, [], input="\n".join(["", "", "", "n"]) + "\n")
    assert result.exit_code != 0
    assert captured.get("aborted") is True
```

(All other wizard test bodies stay the same — they call `_drive(...)` and assert.)

- [ ] **Step 6: Delete the hosting CLI package**

The Click `smpy` entry point in `simple_module_hosting` is being replaced by `simple_module.cli:main`. Delete:

```bash
git rm -r framework/hosting/simple_module_hosting/cli/
```

(This removes `__init__.py`, `__pycache__/`, and any leftover files.)

In `framework/hosting/pyproject.toml`, drop the script entries (Task 7 adds the entry-point line):

```toml
# REMOVE THESE TWO LINES:
sm = "simple_module_hosting.cli:main"
simple-module = "simple_module_hosting.cli:main"
```

Leave the `[project.scripts]` table empty for now (or remove it entirely if no scripts remain).

- [ ] **Step 7: Update remaining hosting test files for the move**

The two tests that import `from simple_module_hosting.cli import main` (`framework/cli/tests/test_scaffolding_host.py`, `framework/cli/tests/test_scaffolding_module.py`) need updating:

```python
# Before
from simple_module_hosting.cli import main

runner.invoke(main, ["create-host", ...])

# After
from simple_module.cli import app

runner.invoke(app, ["create-host", ...])
```

Also switch `from click.testing import CliRunner` → `from typer.testing import CliRunner` in those two files.

- [ ] **Step 8: Update `framework/cli/tests/test_cli_recipes.py`**

`from simple_module_hosting.scaffolding import create_host` → `from simple_module.scaffolding import create_host`. The shim still works, but the direct path is preferred now.

- [ ] **Step 9: Re-install workspace and run tests**

Run: `uv sync --all-packages && uv run pytest framework/cli/ framework/hosting/ -q`
Expected: all tests pass. The `smpy` console script is now provided by `simple-module`; the old `simple_module_hosting.cli:main` no longer exists.

Smoke check the binary:

Run: `uv run smpy --help`
Expected: lists `new`, `create-host`, `create-module` (no plugins yet — Task 6).

Run: `uv run smpy new demo --yes --preset full --no-install --dest /tmp/sm-typer-smoke`
Expected: works the same as before; produces the demo project. Clean up: `rm -rf /tmp/sm-typer-smoke`.

- [ ] **Step 10: Commit**

```bash
git add -A
git commit -m "feat(cli): port sm to Typer; new simple-module package owns the binary

$(cat <<'EOF'
- All Click decorators rewritten in Typer's Annotated[] style.
- Wizard uses typer.prompt / typer.confirm.
- Tests use typer.testing.CliRunner (drop-in for click.testing).
- simple_module_hosting drops sm/simple-module console scripts.
- simple_module_hosting/cli/ package deleted.
- Plugin discovery hook added (no-op stub; real impl next commit).
EOF
)"
```

---

## Task 6: Plugin discovery

**Files:**
- Modify: `framework/cli/simple_module/plugins.py` (real implementation).
- Create: `framework/cli/tests/test_plugin_discovery.py`

- [ ] **Step 1: Write the failing test**

Create `framework/cli/tests/test_plugin_discovery.py`:

```python
"""Tests for entry-point-based plugin discovery."""

from __future__ import annotations

from importlib.metadata import EntryPoint

import pytest
import typer
from typer.testing import CliRunner

from simple_module.plugins import discover_and_mount


def _make_entry(name: str, module_attr: str) -> EntryPoint:
    return EntryPoint(name=name, value=module_attr, group="simple_module.cli_plugins")


@pytest.fixture
def fake_plugin_module(tmp_path, monkeypatch):
    """Create a tiny package on sys.path that exports a Typer ``app``."""
    import sys
    import textwrap

    pkg_dir = tmp_path / "fake_sm_plugin"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text(
        textwrap.dedent(
            """
            import typer
            app = typer.Typer(help="Fake plugin.")

            @app.command("ping")
            def ping():
                typer.echo("pong-from-fake")
            """
        )
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    yield "fake_sm_plugin:app"
    sys.modules.pop("fake_sm_plugin", None)


def test_discover_mounts_valid_plugin(monkeypatch, fake_plugin_module) -> None:
    monkeypatch.setattr(
        "simple_module.plugins._iter_plugin_entries",
        lambda: [_make_entry("fake", fake_plugin_module)],
    )
    root = typer.Typer()
    discover_and_mount(root)

    runner = CliRunner()
    result = runner.invoke(root, ["fake", "ping"])
    assert result.exit_code == 0, result.output
    assert "pong-from-fake" in result.output


def test_discover_skips_broken_plugin(monkeypatch) -> None:
    bad = _make_entry("broken", "nonexistent_module:app")
    monkeypatch.setattr("simple_module.plugins._iter_plugin_entries", lambda: [bad])
    root = typer.Typer()
    discover_and_mount(root)  # should not raise

    runner = CliRunner()
    result = runner.invoke(root, ["broken"])
    assert result.exit_code != 0  # subgroup absent → error


def test_discover_warns_on_duplicate_subgroup(monkeypatch, fake_plugin_module, capsys) -> None:
    a = _make_entry("dup", fake_plugin_module)
    b = _make_entry("dup", fake_plugin_module)
    monkeypatch.setattr("simple_module.plugins._iter_plugin_entries", lambda: [a, b])
    root = typer.Typer()
    discover_and_mount(root)
    captured = capsys.readouterr()
    assert "duplicate" in captured.err.lower() or "already" in captured.err.lower()


def test_discover_with_no_plugins_is_noop(monkeypatch) -> None:
    monkeypatch.setattr("simple_module.plugins._iter_plugin_entries", lambda: [])
    root = typer.Typer()
    discover_and_mount(root)  # no error, no commands added
    runner = CliRunner()
    result = runner.invoke(root, ["--help"])
    assert result.exit_code == 0
```

- [ ] **Step 2: Run the failing tests**

Run: `uv run pytest framework/cli/tests/test_plugin_discovery.py -v`
Expected: FAIL — `_iter_plugin_entries` does not exist yet, plus the stub doesn't actually mount.

- [ ] **Step 3: Implement `framework/cli/simple_module/plugins.py`**

Replace the stub with:

```python
"""Plugin discovery for ``smpy`` via the ``simple_module.cli_plugins`` group.

Each entry-point's value (``module:attr``) must resolve to a
:class:`typer.Typer` instance. The entry-point name becomes the
subcommand namespace under ``smpy`` (e.g. ``smpy host gen-pages``).

Failed loads (broken import, wrong type) print one line to stderr and
are skipped — ``smpy`` keeps working with whatever else loads.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from importlib.metadata import EntryPoint, entry_points

import typer

__all__ = ["discover_and_mount"]

_GROUP = "simple_module.cli_plugins"


def _iter_plugin_entries() -> Iterator[EntryPoint]:
    """Indirection point for tests to inject fake entry points."""
    yield from entry_points(group=_GROUP)


def discover_and_mount(root: typer.Typer) -> None:
    """Mount every installed plugin under its entry-point name."""
    seen: set[str] = set()
    for entry in _iter_plugin_entries():
        if entry.name in seen:
            print(
                f"[simple-module] duplicate plugin subgroup '{entry.name}' "
                f"from {entry.value!r}; keeping first registration.",
                file=sys.stderr,
            )
            continue
        try:
            plugin_app = entry.load()
        except Exception as exc:  # noqa: BLE001 — plugin authors can fail in any way
            print(
                f"[simple-module] failed to load plugin '{entry.name}' ({entry.value}): {exc}",
                file=sys.stderr,
            )
            continue
        if not isinstance(plugin_app, typer.Typer):
            print(
                f"[simple-module] plugin '{entry.name}' did not export a "
                f"typer.Typer instance (got {type(plugin_app).__name__}); skipping.",
                file=sys.stderr,
            )
            continue
        root.add_typer(plugin_app, name=entry.name)
        seen.add(entry.name)
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest framework/cli/tests/test_plugin_discovery.py -v`
Expected: 4 tests pass.

- [ ] **Step 5: Verify `smpy --help` still works (no plugins installed yet)**

Run: `uv run smpy --help`
Expected: same output as before, no errors. No `host`, `users`, or `settings` subgroups appear yet (those are wired in Tasks 7 & 8).

- [ ] **Step 6: Commit**

```bash
git add framework/cli/simple_module/plugins.py framework/cli/tests/test_plugin_discovery.py
git commit -m "feat(cli): plugin discovery via simple_module.cli_plugins entry points

$(cat <<'EOF'
discover_and_mount() walks the entry-point group, validates each load
target is a typer.Typer, and mounts it under its entry name. Broken or
duplicate plugins log one line to stderr and are skipped.
EOF
)"
```

---

## Task 7: Carve out `simple_module_hosting.host_cli` plugin

**Files:**
- Create: `framework/hosting/simple_module_hosting/host_cli.py` (Typer app with `gen-pages` + `sync-js-deps`).
- Modify: `framework/hosting/pyproject.toml` (add `[project.entry-points."simple_module.cli_plugins"]`).
- Modify: `Makefile` (`smpy gen-pages` → `smpy host gen-pages`; `smpy sync-js-deps` → `smpy host sync-js-deps`).
- Create: `framework/hosting/tests/test_host_cli.py` (smoke).

- [ ] **Step 1: Write the failing test**

Create `framework/hosting/tests/test_host_cli.py`:

```python
"""Smoke tests for the simple_module_hosting host_cli Typer plugin."""

from __future__ import annotations

from pathlib import Path

import typer
from typer.testing import CliRunner

from simple_module_hosting.host_cli import app


def test_app_is_typer_instance() -> None:
    assert isinstance(app, typer.Typer)


def test_help_lists_gen_pages_and_sync_js_deps() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "gen-pages" in result.output
    assert "sync-js-deps" in result.output


def test_gen_pages_errors_on_missing_client_app(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["gen-pages", "--host-dir", str(tmp_path / "does-not-exist")])
    assert result.exit_code != 0
    assert "not found" in result.output.lower() or "not found" in (result.stderr or "").lower()
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest framework/hosting/tests/test_host_cli.py -v`
Expected: FAIL — `simple_module_hosting.host_cli` does not exist.

- [ ] **Step 3: Create `framework/hosting/simple_module_hosting/host_cli.py`**

Translate the existing `gen-pages` and `sync-js-deps` Click commands to Typer:

```python
"""``smpy host`` plugin — project-time helpers exposed through the simple-module CLI.

Commands here need module discovery (``simple_module_core.discover_modules``)
and the manifest helpers; they're not part of the standalone scaffolder.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Annotated

import typer
from simple_module_core import discover_modules

from simple_module_hosting.manifest import (
    collect_module_js_deps,
    repo_root_from_client_app,
    write_module_pages_manifest,
)

app = typer.Typer(
    help="Project-time helpers (frontend pages manifest, module JS dep sync).",
    no_args_is_help=True,
)


@app.command("gen-pages")
def gen_pages(
    host_dir: Annotated[
        Path,
        typer.Option(
            "--host-dir",
            help="Path to the host's client_app directory. Defaults to ./client_app.",
        ),
    ] = Path("client_app"),
) -> None:
    """Regenerate client_app/modules.{manifest.json,generated.ts,generated.css}."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    if not host_dir.is_dir():
        typer.echo(f"ERROR: client_app directory not found at {host_dir}", err=True)
        raise typer.Exit(code=1)
    modules = discover_modules()
    written = write_module_pages_manifest(modules, host_dir)
    typer.echo(
        f"Wrote {written['manifest'].name}, {written['generated'].name}, "
        f"{written['css'].name} to {host_dir}"
    )


@app.command("sync-js-deps")
def sync_js_deps(
    host_client_app: Annotated[
        Path,
        typer.Option(
            "--host-client-app",
            help="Path to host/client_app. Defaults to ./client_app.",
        ),
    ] = Path("client_app"),
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Print the npm install command only.")
    ] = False,
) -> None:
    """Install JS deps declared by installed modules into host's node_modules."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    if not host_client_app.is_dir():
        typer.echo(f"ERROR: client_app directory not found at {host_client_app}", err=True)
        raise typer.Exit(code=1)

    modules = discover_modules()
    by_module = collect_module_js_deps(modules)
    if not by_module:
        typer.echo("No module JS dependencies declared.")
        return

    specs: list[str] = []
    for mod_name in sorted(by_module):
        for dep, rng in sorted(by_module[mod_name].items()):
            specs.append(f"{dep}@{rng}")
    deduped: list[str] = []
    seen: set[str] = set()
    for spec in specs:
        if spec not in seen:
            seen.add(spec)
            deduped.append(spec)

    npm = shutil.which("npm")
    if npm is None:
        typer.echo("ERROR: npm not found on PATH.", err=True)
        raise typer.Exit(code=1)

    repo_root = repo_root_from_client_app(host_client_app)
    try:
        workspace = str(host_client_app.resolve().relative_to(repo_root))
    except ValueError:
        workspace = str(host_client_app.resolve())

    cmd = [
        npm,
        "install",
        "--workspace",
        workspace,
        "--save=false",
        "--no-audit",
        "--no-fund",
        *deduped,
    ]
    typer.echo("Installing module JS deps:")
    for spec in deduped:
        typer.echo(f"  {spec}")
    if dry_run:
        typer.echo("(dry-run) " + " ".join(cmd))
        return
    result = subprocess.run(cmd, cwd=repo_root, check=False)
    raise typer.Exit(code=result.returncode)
```

- [ ] **Step 4: Register the plugin entry point in `framework/hosting/pyproject.toml`**

After `[project.urls]`, add:

```toml
[project.entry-points."simple_module.cli_plugins"]
host = "simple_module_hosting.host_cli:app"
```

The `[project.scripts]` table should already be empty (or removed) from Task 5.

- [ ] **Step 5: Run hosting tests**

Run: `uv run pytest framework/hosting/tests/test_host_cli.py -v`
Expected: 3 tests pass.

- [ ] **Step 6: Re-install workspace and verify the plugin mounts**

Run: `uv sync --all-packages && uv run smpy --help`
Expected: `host` appears in the subcommand list (from the entry point).

Run: `uv run smpy host --help`
Expected: lists `gen-pages` and `sync-js-deps`.

- [ ] **Step 7: Update Makefile**

In `Makefile`, replace:

```makefile
gen-pages:
	uv run --project host smpy gen-pages --host-dir=host/client_app

sync-module-deps:
	uv run --project host smpy sync-js-deps --host-client-app=host/client_app
```

with:

```makefile
gen-pages:
	uv run --project host smpy host gen-pages --host-dir=host/client_app

sync-module-deps:
	uv run --project host smpy host sync-js-deps --host-client-app=host/client_app
```

- [ ] **Step 8: Verify Make targets still work**

Run: `make gen-pages 2>&1 | tail -3`
Expected: Wrote manifest.json, generated.ts, generated.css. (Or, if the host hasn't been bootstrapped, an unrelated error — what matters is the CLI invocation itself works. Confirm by inspecting stdout for the new "Wrote …" line.)

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "feat(hosting): host_cli plugin (smpy host gen-pages, smpy host sync-js-deps)

$(cat <<'EOF'
gen-pages and sync-js-deps move out of the deleted smpy console script
and into a Typer plugin published under the simple_module.cli_plugins
entry-point group. Makefile updated for the new smpy host * shape.
EOF
)"
```

---

## Task 8: Convert `users` and `settings` modules to plugins

**Files:**
- Modify: `modules/users/pyproject.toml` (drop `smpy users`, add entry point).
- Modify: `modules/users/users/cli.py` (already a Typer app — verify; minimal changes).
- Modify: `modules/settings/settings/cli.py` (rewrite as Typer app named `app`).
- Modify: `modules/settings/pyproject.toml` (drop `smpy settings`, add entry point).
- Modify: `README.md` (`smpy users` / `smpy settings` snippets → `smpy users` / `smpy settings`).

- [ ] **Step 1: Update `modules/users/pyproject.toml`**

Find:

```toml
[project.scripts]
smpy users = "users.cli:app"
```

Replace with:

```toml
[project.entry-points."simple_module.cli_plugins"]
users = "users.cli:app"
```

`modules/users/users/cli.py` is already a Typer app named `app` — no code change needed.

- [ ] **Step 2: Rewrite `modules/settings/settings/cli.py` as a Typer plugin**

Replace the entire file with:

```python
"""``smpy settings`` plugin — currently only ``import-from-env``.

One-shot migration: walks every registered module's BaseSettings and
writes a SYSTEM-scoped override for each ``SM_<PREFIX>_<FIELD>`` env
var that is set.
"""

from __future__ import annotations

import asyncio
import os

import typer
from fastapi import FastAPI

from settings.constants import MODULE_PACKAGE
from settings.env_vars import env_prefix_for
from settings.hydrate import value_type_for_field
from settings.store import SettingsStore

app = typer.Typer(help="Settings module administration.", no_args_is_help=True)


async def import_from_env_impl(app_inst: FastAPI, store: SettingsStore) -> int:
    """Write a SYSTEM override for every ``SM_<PREFIX>_<FIELD>`` env var set."""
    registry = getattr(app_inst.state, MODULE_PACKAGE).module_registry
    count = 0
    for package, cls in registry.items():
        prefix = env_prefix_for(package)
        for field_name in cls.model_fields:
            raw = os.environ.get(f"{prefix}{field_name.upper()}")
            if raw is None:
                continue
            vtype = value_type_for_field(cls, field_name)
            await store.set_override(package, field_name, raw, vtype)
            count += 1
    return count


@app.command("import-from-env")
def import_from_env() -> None:
    """Write SYSTEM overrides for every SM_<PREFIX>_<FIELD> env var set."""
    from simple_module_hosting.app_builder import create_app
    from simple_module_hosting.settings import Settings

    from settings.service import SettingService

    fastapi_app = create_app(Settings())

    async def run() -> int:
        async with (
            fastapi_app.router.lifespan_context(fastapi_app),
            fastapi_app.state.sm.db.session_factory() as session,
        ):
            store = SettingsStore(SettingService(session))
            n = await import_from_env_impl(fastapi_app, store)
            await session.commit()
            typer.echo(f"Imported {n} override(s) from environment.")
        return 0

    raise typer.Exit(code=asyncio.run(run()))
```

- [ ] **Step 3: Update `modules/settings/pyproject.toml`**

Find:

```toml
[project.scripts]
smpy settings = "settings.cli:main"
```

Replace with:

```toml
[project.entry-points."simple_module.cli_plugins"]
settings = "settings.cli:app"
```

- [ ] **Step 4: Update existing settings test if any**

Run: `grep -n "smpy settings\|settings.cli.main\|from settings.cli import main" modules/settings/tests/`
If there are matches, fix them — `main` no longer exists. The new entry is `app`. Most likely there are no test changes needed (the existing settings tests target `import_from_env_impl` directly).

- [ ] **Step 5: Re-install + smoke**

Run: `uv sync --all-packages && uv run smpy --help 2>&1 | head -20`
Expected: subgroups `host`, `users`, `settings` all appear.

Run: `uv run smpy users --help` and `uv run smpy settings --help`
Expected: each lists their subcommand(s).

- [ ] **Step 6: Update README**

In `README.md`, replace:
- `uv run smpy users create-admin --email …` → `uv run smpy users create-admin --email …`
- `uv run smpy settings import-from-env` → `uv run smpy settings import-from-env`
- Any other occurrences of `smpy users` / `smpy settings`.

- [ ] **Step 7: Run the full test suite**

Run: `uv run pytest -q`
Expected: all tests pass.

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "refactor(modules): convert users + settings to sm plugins

$(cat <<'EOF'
Drops smpy users and smpy settings console scripts. Both modules now
register Typer apps under the simple_module.cli_plugins entry-point
group, mounted as `smpy users` and `smpy settings`. settings/cli.py
rewritten as a Typer app (was hand-rolled Click-style argv parsing).
README updated for the new command shape.
EOF
)"
```

---

## Task 9: Final cleanup, dep guard, lint, full verification

**Files:**
- Delete: `framework/hosting/simple_module_hosting/scaffolding.py` (the shim).
- Modify: `framework/hosting/pyproject.toml` (drop `simple_module` workspace dep — hosting no longer needs it).
- Modify: any remaining test imports referencing `simple_module_hosting.scaffolding`.
- Create: `framework/cli/tests/test_no_framework_deps.py`.
- Final: lint + typecheck + file-size + full pytest.

- [ ] **Step 1: Find all remaining import sites of the shim**

Run: `grep -rn 'from simple_module_hosting.scaffolding\|from simple_module_hosting.app_project\|from simple_module_hosting._env\|simple_module_hosting.cli' --include="*.py" framework/ modules/ host/ scripts/ tests/ 2>/dev/null`
Expected: a small list of test files and possibly internal hosting modules.

For each match:
- If it's in a test file under `framework/cli/tests/`, change to import from the new `simple_module` location directly.
- If it's in `framework/hosting/simple_module_hosting/manifest.py` or another hosting runtime file, update to `simple_module.scaffolding` / `simple_module.app_project` etc.
- If it's outside the framework (host code, modules), update similarly.

Concretely the planned remaining sites are in `framework/cli/tests/test_scaffolding_*.py` (already updated in Task 5 Step 7), `framework/cli/tests/test_cli_*.py` (updated Task 5 Step 5/8). Sweep once more to be sure.

- [ ] **Step 2: Delete the shim**

```bash
git rm framework/hosting/simple_module_hosting/scaffolding.py
```

- [ ] **Step 3: Drop the `simple_module` workspace dep from hosting**

In `framework/hosting/pyproject.toml`, remove:

```toml
"simple_module==0.0.1",
```

from `dependencies` and remove `simple_module = { workspace = true }` from `[tool.uv.sources]`. Hosting's runtime (app_builder, middleware, manifest, host_cli) no longer needs to import from `simple_module` at runtime — `host_cli` imports stay because they depend on `discover_modules` from core, not anything in `simple_module`. Verify:

Run: `grep -rn 'from simple_module\b\|import simple_module\b' --include="*.py" framework/hosting/simple_module_hosting/`
Expected: no matches. If anything appears, update it.

- [ ] **Step 4: Re-sync workspace**

Run: `uv sync --all-packages`
Expected: succeeds. If `simple_module` is now an unused dep anywhere, the resolver removes it cleanly.

- [ ] **Step 5: Add the no-framework-deps guard test**

Create `framework/cli/tests/test_no_framework_deps.py`:

```python
"""Guard: `simple-module` distribution depends only on typer + tomlkit.

If a future change accidentally pulls in simple_module_core, FastAPI,
SQLModel, or anything else, this test fires immediately.
"""

from __future__ import annotations

from importlib.metadata import distribution


def _normalize(req: str) -> str:
    """'typer (>=0.12)' -> 'typer'. Strip version specs + extras + spaces."""
    return (
        req.split(";")[0]
        .split("(")[0]
        .split(">=")[0]
        .split(">")[0]
        .split("<")[0]
        .split("==")[0]
        .split("[")[0]
        .strip()
        .lower()
        .replace("_", "-")
    )


def test_simple_module_runtime_deps_are_minimal() -> None:
    requires = distribution("simple-module").requires or []
    names = {_normalize(r) for r in requires}
    # Allowed: declared deps + their transitive obligations are NOT checked here;
    # only the direct deps of `simple-module` itself.
    assert names == {"typer", "tomlkit"}, (
        f"simple-module direct deps drifted; got {sorted(names)}, expected {{'typer', 'tomlkit'}}"
    )
```

- [ ] **Step 6: Run the dep-guard test**

Run: `uv run pytest framework/cli/tests/test_no_framework_deps.py -v`
Expected: PASS.

- [ ] **Step 7: Run the project lint suite**

Run: `make lint`
Expected: all checks pass — ruff, ty, file-size, biome, tsc, metadata, readmes.

If file-size fires for any moved file, split it (the moved files all stayed close to their previous sizes; recipes ≈ 95 lines, app_project ≈ 130, etc., well under 300).

- [ ] **Step 8: Run the full test suite**

Run: `uv run pytest -q`
Expected: all tests green. The plan's planned test count is roughly:
- Original 1009 tests still passing.
- 47 CLI tests (now under `framework/cli/tests/`).
- 4 plugin discovery tests (new).
- 3 host_cli tests (new).
- 1 no-framework-deps test (new).
- Total expected: ~1064.

- [ ] **Step 9: Final smoke test of the user-visible CLI**

Run:
```bash
uv run smpy --help
uv run smpy host --help
uv run smpy users --help
uv run smpy settings --help
TMP=$(mktemp -d) && uv run smpy new demo --yes --preset full --no-install --dest "$TMP/demo"
ls "$TMP/demo/scripts/run_worker.py" "$TMP/demo/docker-compose.yml"
```
Expected: every command works; the new project lands all background-task scaffolding correctly.

- [ ] **Step 10: Commit**

```bash
git add -A
git commit -m "refactor(cli): finish the standalone simple-module carve-out

$(cat <<'EOF'
- Delete the simple_module_hosting.scaffolding shim and the
  workspace dep on simple_module.
- Add framework/cli/tests/test_no_framework_deps.py to guard
  against future dep drift in the standalone scaffolder.
- README + Makefile reflect the final smpy host/users/settings shape.
EOF
)"
```

---

## Self-Review

**Spec coverage:**
- Distribution layout (`framework/cli/`, dep tuple typer + tomlkit) → Task 1.
- File moves (`_env`, case helpers, scaffolding, app_project, catalog, wizard, recipes, new, templates) → Tasks 2–4.
- Click → Typer port → Task 5.
- Plugin discovery (`simple_module.cli_plugins`, `discover_and_mount`, error handling, dup detection) → Task 6.
- `host_cli` plugin (gen-pages, sync-js-deps), Makefile rename → Task 7.
- `users` + `settings` plugin migration, drop smpy users/smpy settings scripts → Task 8.
- No-framework-deps guard → Task 9.
- Cleanup, README updates, full verification → Tasks 8 & 9.

**No placeholders:** every step contains the actual code or command needed.

**Type consistency:** `app` is the Typer instance everywhere it's referenced; `discover_and_mount(app)` is the same name in `cli.py`, `plugins.py`, and the tests; `_iter_plugin_entries` is the test seam used in both `plugins.py` and `test_plugin_discovery.py`. Case helpers renamed without leading underscores (`to_snake_case` / `to_kebab_case` / `to_pascal_case`) consistently across all modules.

**Out of scope:** version bumps, release-workflow matrix updates, doc-site changes — all deferred to the public-release plan.
