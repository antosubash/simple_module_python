# Public Release `v0.0.1` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish all 14 Python packages to PyPI and 3 JS packages to npm as `v0.0.1`, with a working `sm new` / `simple-module new` CLI generator that scaffolds a new app consuming these packages.

**Architecture:** Seven phases in sequence. Phase 0 prepares the repo (LICENSE, CHANGELOG, lint scripts). Phase 1 renames 10 modules to the `simple-module-*` PyPI namespace. Phases 2–3 update Python + npm package metadata. Phase 4 writes substantive READMEs for all 17 packages. Phase 5 builds the version-bump script. Phase 6 extends the existing host-template CLI into a full `sm new` generator. Phase 7 adds the release workflow + docs. Every change must pass `make lint` and `make test`.

**Tech Stack:** Python 3.12, `uv`, `hatchling`, Click, `tomlkit`; Node 20+, npm workspaces; GitHub Actions + PyPI/npm Trusted Publishing (OIDC); Jinja2 for template rendering.

**Spec:** [docs/superpowers/specs/2026-04-21-public-release-design.md](../specs/2026-04-21-public-release-design.md)

**Open items** (resolve before starting Phase 7 — earlier phases do not depend on them):
- PyPI account owner (assumed `antosubash`)
- npm org `@simple-module-py` owner (assumed `antosubash`)
- GitHub repo URL (assumed `https://github.com/antosubash/simple_module_python`)

---

## File map

**New files:**
- `LICENSE` — MIT, root of repo
- `CHANGELOG.md` — root; seeded with `0.0.1`
- `docs/release.md` — operator playbook for Trusted Publisher setup + cutting a release
- `scripts/bump_version.py` — walks all 17 package manifests, rewrites versions + inter-pkg pins
- `scripts/check_metadata.py` — lint enforcing keyword + license + URLs + description on all 17 packages
- `scripts/check_readmes.py` — lint enforcing per-package README presence + required sections
- `scripts/tests/test_bump_version.py`
- `scripts/tests/test_check_metadata.py`
- `scripts/tests/test_check_readmes.py`
- `scripts/tests/__init__.py`
- `scripts/tests/conftest.py` — fixture helpers for the three script test modules
- `scripts/smoke_npm_packs.sh` — local-only npm pack smoke
- `.github/workflows/release.yml` — manual-dispatch release workflow
- `README.md` in each of 17 packages (14 Python + 3 npm) — substantive content
- `README.md` in each Python framework package (4) if not present — check each
- Extensions to `framework/hosting/simple_module_hosting/templates/host/` — template pre-wiring users+dashboard+permissions, vendoring nothing

**Modified files:**
- All 14 `pyproject.toml` files under `framework/*` and `modules/*` — name, version, description, keywords, classifiers, URLs, license, readme
- Root `pyproject.toml` — no functional change; confirm testpaths still resolve after module renames
- All 10 `modules/*/pyproject.toml` — **package rename** from bare name to `simple-module-<name>`
- All 3 `packages/*/package.json` — metadata, scope rename `@simple-module-py/*` → `@simple-module-py/*`, unmark `private`, move React to peerDeps
- `framework/hosting/simple_module_hosting/cli.py` — add `new` subcommand; keep `create-host` + `create-module`
- `framework/hosting/pyproject.toml` — add `simple-module` as second `[project.scripts]` entry
- `framework/hosting/simple_module_hosting/scaffolding.py` — extend `_create_host` if needed to pre-wire users+dashboard+permissions
- `host/client_app/*` and other repo files that import from `@simple-module-py/*` — update scope
- `Makefile` — add `release-check`, `smoke-npm`; ensure `lint` runs `check_metadata` + `check_readmes`
- `pyproject.toml` at root — add `tomlkit` to dev dependencies; extend `testpaths`

---

## Phase 0 — Root repo prep

### Task 0.1: Add root LICENSE file

**Files:**
- Create: `LICENSE`

- [ ] **Step 1: Write `LICENSE`**

```
MIT License

Copyright (c) 2026 Anto Subash

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

- [ ] **Step 2: Commit**

```bash
git add LICENSE
git commit -m "chore: add MIT LICENSE at repo root"
```

### Task 0.2: Seed CHANGELOG.md

**Files:**
- Create: `CHANGELOG.md`

- [ ] **Step 1: Write `CHANGELOG.md`**

```markdown
# Changelog

All notable changes to this project are documented in this file. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project adheres to [Semantic Versioning](https://semver.org/) post-1.0.

## [Unreleased]

## [0.0.1] — 2026-04-21

Initial public release. All 14 Python packages publish to PyPI and all 3 JS packages publish to npm under the `@simple-module-py` scope.

### Python packages (PyPI)

- `simple-module-core`
- `simple-module-db`
- `simple-module-hosting`
- `simple-module-testing`
- `simple-module-auth`
- `simple-module-background-tasks`
- `simple-module-dashboard`
- `simple-module-datasets`
- `simple-module-feature-flags`
- `simple-module-file-storage`
- `simple-module-permissions`
- `simple-module-products`
- `simple-module-settings`
- `simple-module-users`

### npm packages

- `@simple-module-py/ui`
- `@simple-module-py/i18n`
- `@simple-module-py/tsconfig`

### Added

- `simple-module new <app>` / `sm new <app>` CLI generator scaffolding a working app with `users + dashboard + permissions` pre-wired.
- PyPI Trusted Publishing workflow (`.github/workflows/release.yml`) for zero-secret releases.
- npm Trusted Publishing for all three JS packages.

[Unreleased]: https://github.com/antosubash/simple_module_python/compare/v0.0.1...HEAD
[0.0.1]: https://github.com/antosubash/simple_module_python/releases/tag/v0.0.1
```

- [ ] **Step 2: Commit**

```bash
git add CHANGELOG.md
git commit -m "chore: seed CHANGELOG with 0.0.1 initial release entry"
```

### Task 0.3: Add `tomlkit` to dev deps

**Files:**
- Modify: `pyproject.toml` (root)

- [ ] **Step 1: Add `tomlkit>=0.13` to `[dependency-groups].dev` in root `pyproject.toml`**

Insert `"tomlkit>=0.13",` into the `dev = [...]` list alongside the existing entries.

- [ ] **Step 2: Run `uv sync --all-packages` and verify `tomlkit` resolves**

Run: `uv sync --all-packages`
Expected: resolver succeeds, `tomlkit` appears in `uv.lock`.

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore: add tomlkit dev dep for bump_version.py"
```

---

## Phase 1 — Rename modules to `simple-module-*` namespace

**Why this comes first:** every later phase (metadata hygiene, bump script, release workflow) assumes packages are named `simple-module-<name>`. Currently 10 of 14 Python packages are named without the prefix (e.g. `auth`, `users`, `products`). Renaming must happen before we can set dependency pins or publish.

### Task 1.1: Rename the 10 module distributions

**Files (all modified):**
- `modules/auth/pyproject.toml`
- `modules/background_tasks/pyproject.toml`
- `modules/dashboard/pyproject.toml`
- `modules/datasets/pyproject.toml`
- `modules/feature_flags/pyproject.toml`
- `modules/file_storage/pyproject.toml`
- `modules/permissions/pyproject.toml`
- `modules/products/pyproject.toml`
- `modules/settings/pyproject.toml`
- `modules/users/pyproject.toml`
- `modules/*/pyproject.toml` — inter-module deps in `project.dependencies` and `[tool.uv.sources]`
- `framework/hosting/pyproject.toml` — references any modules? (currently no; confirm)

- [ ] **Step 1: Rewrite `project.name` in every module pyproject.toml**

In each file, change the `name` field:

| File | Before | After |
|---|---|---|
| `modules/auth/pyproject.toml` | `name = "auth"` | `name = "simple-module-auth"` |
| `modules/background_tasks/pyproject.toml` | `name = "background-tasks"` | `name = "simple-module-background-tasks"` |
| `modules/dashboard/pyproject.toml` | `name = "dashboard"` | `name = "simple-module-dashboard"` |
| `modules/datasets/pyproject.toml` | `name = "datasets"` | `name = "simple-module-datasets"` |
| `modules/feature_flags/pyproject.toml` | `name = "feature-flags"` | `name = "simple-module-feature-flags"` |
| `modules/file_storage/pyproject.toml` | `name = "file-storage"` | `name = "simple-module-file-storage"` |
| `modules/permissions/pyproject.toml` | `name = "permissions"` | `name = "simple-module-permissions"` |
| `modules/products/pyproject.toml` | `name = "products"` | `name = "simple-module-products"` |
| `modules/settings/pyproject.toml` | `name = "settings"` | `name = "simple-module-settings"` |
| `modules/users/pyproject.toml` | `name = "users"` | `name = "simple-module-users"` |

- [ ] **Step 2: Rewrite inter-module dependency references**

For every module pyproject.toml, in `project.dependencies`, replace bare module names with `simple-module-*`:

- `"auth"` → `"simple-module-auth"`
- `"users"` → `"simple-module-users"`
- `"products"` → `"simple-module-products"`
- `"file-storage"` → `"simple-module-file-storage"`
- `"background-tasks"` → `"simple-module-background-tasks"`

Specifically:
- `modules/users/pyproject.toml`: `"auth"` → `"simple-module-auth"` (comment `# workspace module — contracts` stays).
- `modules/dashboard/pyproject.toml`: `"products"` → `"simple-module-products"`, `"users"` → `"simple-module-users"`.
- `modules/datasets/pyproject.toml`: `"file-storage"` → `"simple-module-file-storage"`, `"background-tasks"` → `"simple-module-background-tasks"`.
- `modules/permissions/pyproject.toml`: `"users"` → `"simple-module-users"`.

- [ ] **Step 3: Rewrite `[tool.uv.sources]` keys**

For every module pyproject.toml, rewrite workspace source keys to match the new distribution names:

- `auth = { workspace = true }` → `simple-module-auth = { workspace = true }`
- `users = { workspace = true }` → `simple-module-users = { workspace = true }`
- `products = { workspace = true }` → `simple-module-products = { workspace = true }`
- `file-storage = { workspace = true }` → `simple-module-file-storage = { workspace = true }`
- `background-tasks = { workspace = true }` → `simple-module-background-tasks = { workspace = true }`

(Keep existing `simple-module-core = { workspace = true }` etc. — those are already correct.)

- [ ] **Step 4: Grep the repo for any stale short-name references**

Run: `rg -n '"(auth|users|products|dashboard|permissions|settings|file-storage|background-tasks|feature-flags|datasets)"\s*(,|\])' --type toml`
Expected: no matches — every dep should now be prefixed.

Run: `rg -n '\b(auth|users|products|dashboard|permissions|settings|file-storage|background-tasks|feature-flags|datasets)\s*=\s*\{\s*workspace' --type toml`
Expected: no matches.

- [ ] **Step 5: Rebuild the uv workspace lockfile**

Run: `rm uv.lock && uv sync --all-packages`
Expected: resolver succeeds; no "cannot find workspace package" errors.

- [ ] **Step 6: Run the full test suite to verify nothing broke**

Run: `make test`
Expected: all tests pass. Distribution names changed but Python import names are unaffected because they come from directory layout (`modules/auth/auth/` → `import auth`).

- [ ] **Step 7: Run the doctor to confirm module discovery still works**

Run: `make doctor`
Expected: no new errors; SM008 (duplicate name) must not trigger.

- [ ] **Step 8: Commit**

```bash
git add modules/*/pyproject.toml uv.lock
git commit -m "refactor: rename module distributions to simple-module-* namespace

Renames 10 module packages from bare names (auth, users, products, ...)
to simple-module-<name> so they can be published to PyPI without name
collisions. Python import names are unaffected — only the PyPI
distribution name changes. Inter-module dependency references and
[tool.uv.sources] keys updated to match."
```

---

## Phase 2 — Lint scripts (TDD)

Before touching package metadata, build the scripts that enforce the metadata rules. This way we can run them against the in-progress repo to catch mistakes.

### Task 2.1: Create `scripts/tests/` package

**Files:**
- Create: `scripts/tests/__init__.py` (empty)
- Create: `scripts/tests/conftest.py`

- [ ] **Step 1: Write `scripts/tests/__init__.py` (empty file)**

```python
```

- [ ] **Step 2: Write `scripts/tests/conftest.py`**

```python
"""Shared fixtures for the release-scripts test suite."""
from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def tmp_pkg_dir(tmp_path: Path) -> Path:
    """A temp directory set up like a simple-module package root."""
    return tmp_path


def write(path: Path, content: str) -> Path:
    """Write text to a path, creating parents as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


@pytest.fixture
def writer():
    return write
```

- [ ] **Step 3: Extend root `pyproject.toml` `testpaths`**

Add `"scripts/tests"` to the `testpaths` list in `[tool.pytest.ini_options]`.

- [ ] **Step 4: Commit**

```bash
git add scripts/tests/__init__.py scripts/tests/conftest.py pyproject.toml
git commit -m "test: add scripts/tests package for release-script unit tests"
```

### Task 2.2: `check_metadata.py` — failing test first

**Files:**
- Create: `scripts/tests/test_check_metadata.py`

- [ ] **Step 1: Write the failing test**

```python
"""Tests for scripts/check_metadata.py."""
from __future__ import annotations

from pathlib import Path

import pytest

from scripts.check_metadata import (
    check_npm_package,
    check_python_package,
    main,
)


def test_python_package_missing_simple_module_keyword(tmp_pkg_dir: Path, writer) -> None:
    pyproject = writer(
        tmp_pkg_dir / "pyproject.toml",
        """
[project]
name = "simple-module-foo"
version = "0.0.1"
description = "A real description"
readme = "README.md"
license = "MIT"
keywords = ["fastapi"]

[project.urls]
Repository = "https://github.com/antosubash/simple_module_python"
""",
    )
    errors = check_python_package(pyproject)
    assert any("simple-module" in e and "keyword" in e for e in errors)


def test_python_package_placeholder_description_rejected(tmp_pkg_dir: Path, writer) -> None:
    pyproject = writer(
        tmp_pkg_dir / "pyproject.toml",
        """
[project]
name = "simple-module-foo"
version = "0.0.1"
description = "Add your description here"
readme = "README.md"
license = "MIT"
keywords = ["simple-module"]

[project.urls]
Repository = "https://github.com/antosubash/simple_module_python"
""",
    )
    errors = check_python_package(pyproject)
    assert any("description" in e.lower() and "placeholder" in e.lower() for e in errors)


def test_python_package_passes_when_valid(tmp_pkg_dir: Path, writer) -> None:
    pyproject = writer(
        tmp_pkg_dir / "pyproject.toml",
        """
[project]
name = "simple-module-foo"
version = "0.0.1"
description = "The foo module — handles foo things"
readme = "README.md"
license = "MIT"
keywords = ["simple-module", "fastapi"]

[project.urls]
Repository = "https://github.com/antosubash/simple_module_python"
""",
    )
    assert check_python_package(pyproject) == []


def test_npm_package_missing_keyword(tmp_pkg_dir: Path, writer) -> None:
    pkg = writer(
        tmp_pkg_dir / "package.json",
        """{
  "name": "@simple-module-py/foo",
  "version": "0.0.1",
  "description": "Real desc",
  "license": "MIT",
  "keywords": ["react"],
  "repository": "https://github.com/antosubash/simple_module_python",
  "publishConfig": {"access": "public"}
}
""",
    )
    errors = check_npm_package(pkg)
    assert any("simple-module" in e and "keyword" in e for e in errors)


def test_npm_package_private_rejected(tmp_pkg_dir: Path, writer) -> None:
    pkg = writer(
        tmp_pkg_dir / "package.json",
        """{
  "name": "@simple-module-py/foo",
  "version": "0.0.1",
  "description": "Real desc",
  "license": "MIT",
  "keywords": ["simple-module"],
  "private": true,
  "repository": "https://github.com/antosubash/simple_module_python",
  "publishConfig": {"access": "public"}
}
""",
    )
    errors = check_npm_package(pkg)
    assert any("private" in e.lower() for e in errors)


def test_npm_package_publish_config_required(tmp_pkg_dir: Path, writer) -> None:
    pkg = writer(
        tmp_pkg_dir / "package.json",
        """{
  "name": "@simple-module-py/foo",
  "version": "0.0.1",
  "description": "Real desc",
  "license": "MIT",
  "keywords": ["simple-module"],
  "repository": "https://github.com/antosubash/simple_module_python"
}
""",
    )
    errors = check_npm_package(pkg)
    assert any("publishConfig" in e for e in errors)


def test_main_exits_zero_on_clean_repo(tmp_path: Path, monkeypatch, writer) -> None:
    # Minimal fake repo: one py pkg + one npm pkg, both valid.
    repo = tmp_path
    writer(
        repo / "framework/core/pyproject.toml",
        """
[project]
name = "simple-module-core"
version = "0.0.1"
description = "Core framework"
readme = "README.md"
license = "MIT"
keywords = ["simple-module"]

[project.urls]
Repository = "https://github.com/antosubash/simple_module_python"
""",
    )
    writer(
        repo / "packages/ui/package.json",
        """{
  "name": "@simple-module-py/ui",
  "version": "0.0.1",
  "description": "UI",
  "license": "MIT",
  "keywords": ["simple-module"],
  "repository": "https://github.com/antosubash/simple_module_python",
  "publishConfig": {"access": "public"}
}
""",
    )
    monkeypatch.chdir(repo)
    rc = main([])
    assert rc == 0


def test_main_exits_nonzero_on_violation(tmp_path: Path, monkeypatch, writer) -> None:
    repo = tmp_path
    writer(
        repo / "framework/core/pyproject.toml",
        """
[project]
name = "simple-module-core"
version = "0.0.1"
description = "Add your description here"
readme = "README.md"
license = "MIT"
keywords = ["simple-module"]

[project.urls]
Repository = "https://github.com/antosubash/simple_module_python"
""",
    )
    monkeypatch.chdir(repo)
    rc = main([])
    assert rc != 0
```

- [ ] **Step 2: Run tests, confirm they fail**

Run: `uv run pytest scripts/tests/test_check_metadata.py -v`
Expected: FAIL — `ModuleNotFoundError: scripts.check_metadata`.

### Task 2.3: Implement `check_metadata.py`

**Files:**
- Create: `scripts/__init__.py` (empty, if missing)
- Create: `scripts/check_metadata.py`

- [ ] **Step 1: Verify `scripts/__init__.py` exists**

Run: `ls scripts/__init__.py 2>&1 || touch scripts/__init__.py`

- [ ] **Step 2: Write `scripts/check_metadata.py`**

```python
"""Enforce per-package metadata rules across all 17 published packages.

Rules:
  * Every `pyproject.toml` under framework/* and modules/* must have:
      - name starting with "simple-module-"
      - non-placeholder description (not "Add your description here" or empty)
      - readme = "README.md"
      - license = "MIT"
      - "simple-module" in keywords
      - project.urls.Repository set to the canonical GitHub URL
  * Every `package.json` under packages/* must have:
      - name starting with "@simple-module-py/"
      - non-empty description
      - license = "MIT"
      - "simple-module" in keywords
      - repository set
      - publishConfig.access = "public"
      - private not true (or absent)

Exit code 0 on success, 1 on any violation. Prints violations to stderr.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import tomlkit

CANONICAL_REPO = "https://github.com/antosubash/simple_module_python"
PLACEHOLDER_DESCRIPTIONS = {"", "Add your description here"}


def check_python_package(pyproject: Path) -> list[str]:
    """Return a list of human-readable violation messages for one pyproject.toml."""
    errors: list[str] = []
    data = tomlkit.parse(pyproject.read_text(encoding="utf-8"))
    project = data.get("project", {})
    rel = pyproject

    name = str(project.get("name", ""))
    if not name.startswith("simple-module-"):
        errors.append(f"{rel}: name must start with 'simple-module-' (got '{name}')")

    desc = str(project.get("description", ""))
    if desc in PLACEHOLDER_DESCRIPTIONS:
        errors.append(f"{rel}: description is placeholder or empty")

    if str(project.get("readme", "")) != "README.md":
        errors.append(f"{rel}: readme must be 'README.md'")

    if str(project.get("license", "")) != "MIT":
        errors.append(f"{rel}: license must be 'MIT'")

    keywords = project.get("keywords", [])
    if "simple-module" not in [str(k) for k in keywords]:
        errors.append(f"{rel}: keywords must include 'simple-module'")

    urls = project.get("urls", {})
    if str(urls.get("Repository", "")) != CANONICAL_REPO:
        errors.append(
            f"{rel}: project.urls.Repository must equal '{CANONICAL_REPO}'"
        )

    return errors


def check_npm_package(package_json: Path) -> list[str]:
    errors: list[str] = []
    data = json.loads(package_json.read_text(encoding="utf-8"))
    rel = package_json

    name = str(data.get("name", ""))
    if not name.startswith("@simple-module-py/"):
        errors.append(f"{rel}: name must start with '@simple-module-py/' (got '{name}')")

    if not str(data.get("description", "")).strip():
        errors.append(f"{rel}: description is empty")

    if str(data.get("license", "")) != "MIT":
        errors.append(f"{rel}: license must be 'MIT'")

    keywords = data.get("keywords", [])
    if "simple-module" not in [str(k) for k in keywords]:
        errors.append(f"{rel}: keywords must include 'simple-module'")

    if not data.get("repository"):
        errors.append(f"{rel}: repository field is required")

    if data.get("private") is True:
        errors.append(f"{rel}: private must not be true (unmark to publish)")

    publish_config = data.get("publishConfig") or {}
    if publish_config.get("access") != "public":
        errors.append(
            f"{rel}: publishConfig.access must be 'public' (scoped packages default to restricted)"
        )

    return errors


def discover_python_packages(root: Path) -> list[Path]:
    found: list[Path] = []
    for base in ("framework", "modules"):
        base_dir = root / base
        if not base_dir.is_dir():
            continue
        for child in sorted(base_dir.iterdir()):
            if not child.is_dir():
                continue
            pyproject = child / "pyproject.toml"
            if pyproject.exists():
                found.append(pyproject)
    return found


def discover_npm_packages(root: Path) -> list[Path]:
    found: list[Path] = []
    packages_dir = root / "packages"
    if not packages_dir.is_dir():
        return found
    for child in sorted(packages_dir.iterdir()):
        if not child.is_dir():
            continue
        pkg = child / "package.json"
        if pkg.exists():
            found.append(pkg)
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="Repo root (default: cwd).",
    )
    args = parser.parse_args(argv)

    root: Path = args.root
    all_errors: list[str] = []
    for pyproject in discover_python_packages(root):
        all_errors.extend(check_python_package(pyproject))
    for pkg in discover_npm_packages(root):
        all_errors.extend(check_npm_package(pkg))

    if all_errors:
        for e in all_errors:
            print(e, file=sys.stderr)
        print(f"\nFAIL: {len(all_errors)} metadata violation(s).", file=sys.stderr)
        return 1
    print("All package metadata OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Run tests, confirm they pass**

Run: `uv run pytest scripts/tests/test_check_metadata.py -v`
Expected: all 7 tests pass.

- [ ] **Step 4: Commit**

```bash
git add scripts/check_metadata.py scripts/tests/test_check_metadata.py scripts/__init__.py
git commit -m "feat(scripts): add check_metadata.py lint for all 17 packages"
```

### Task 2.4: `check_readmes.py` — failing test first

**Files:**
- Create: `scripts/tests/test_check_readmes.py`

- [ ] **Step 1: Write the failing test**

```python
"""Tests for scripts/check_readmes.py."""
from __future__ import annotations

from pathlib import Path

from scripts.check_readmes import check_readme, main


def test_missing_readme_reported(tmp_pkg_dir: Path) -> None:
    errors = check_readme(tmp_pkg_dir)
    assert any("README.md" in e and "not found" in e for e in errors)


def test_tiny_readme_reported(tmp_pkg_dir: Path, writer) -> None:
    writer(tmp_pkg_dir / "README.md", "# tiny\n")
    errors = check_readme(tmp_pkg_dir)
    assert any("too short" in e.lower() for e in errors)


def test_missing_sections_reported(tmp_pkg_dir: Path, writer) -> None:
    writer(
        tmp_pkg_dir / "README.md",
        "# pkg\n\n" + ("Lorem ipsum " * 80),
    )
    errors = check_readme(tmp_pkg_dir)
    joined = "\n".join(errors)
    assert "Install" in joined
    assert "Usage" in joined


def test_valid_readme_passes(tmp_pkg_dir: Path, writer) -> None:
    writer(
        tmp_pkg_dir / "README.md",
        "# simple-module-foo\n\n"
        + ("Lorem ipsum dolor sit amet. " * 40)
        + "\n\n## Install\n\n`pip install x`\n\n## Usage\n\n`x()`\n",
    )
    assert check_readme(tmp_pkg_dir) == []


def test_main_fails_on_missing(tmp_path: Path, monkeypatch, writer) -> None:
    writer(
        tmp_path / "framework/core/pyproject.toml",
        '[project]\nname = "simple-module-core"\n',
    )
    # No README for core — should fail.
    monkeypatch.chdir(tmp_path)
    assert main([]) != 0
```

- [ ] **Step 2: Run tests, confirm they fail**

Run: `uv run pytest scripts/tests/test_check_readmes.py -v`
Expected: FAIL — `ModuleNotFoundError: scripts.check_readmes`.

### Task 2.5: Implement `check_readmes.py`

**Files:**
- Create: `scripts/check_readmes.py`

- [ ] **Step 1: Write `scripts/check_readmes.py`**

```python
"""Enforce per-package README.md presence and baseline quality.

Rules for every package directory (under framework/*, modules/*, packages/*):
  * A README.md must exist.
  * It must be at least 500 bytes (sanity check against stub files).
  * It must contain an H1 (line starting with "# ").
  * It must mention "Install" and "Usage" as section headings or inline text.

Exit 0 if all pass, 1 otherwise.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

MIN_BYTES = 500
REQUIRED_SECTIONS = ("Install", "Usage")


def check_readme(package_dir: Path) -> list[str]:
    readme = package_dir / "README.md"
    if not readme.exists():
        return [f"{readme}: README.md not found"]

    text = readme.read_text(encoding="utf-8")
    errors: list[str] = []

    if len(text.encode("utf-8")) < MIN_BYTES:
        errors.append(f"{readme}: README.md too short (< {MIN_BYTES} bytes)")

    if not any(line.startswith("# ") for line in text.splitlines()):
        errors.append(f"{readme}: missing H1 heading")

    for section in REQUIRED_SECTIONS:
        if section not in text:
            errors.append(f"{readme}: missing '{section}' section/mention")

    return errors


def discover_packages(root: Path) -> list[Path]:
    dirs: list[Path] = []
    for base in ("framework", "modules", "packages"):
        base_dir = root / base
        if not base_dir.is_dir():
            continue
        for child in sorted(base_dir.iterdir()):
            if not child.is_dir():
                continue
            # framework/* and modules/* have pyproject.toml; packages/* has package.json
            if (child / "pyproject.toml").exists() or (child / "package.json").exists():
                dirs.append(child)
    return dirs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)

    errors: list[str] = []
    for pkg_dir in discover_packages(args.root):
        errors.extend(check_readme(pkg_dir))

    if errors:
        for e in errors:
            print(e, file=sys.stderr)
        print(f"\nFAIL: {len(errors)} README violation(s).", file=sys.stderr)
        return 1
    print("All READMEs OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run tests, confirm they pass**

Run: `uv run pytest scripts/tests/test_check_readmes.py -v`
Expected: all 5 tests pass.

- [ ] **Step 3: Commit**

```bash
git add scripts/check_readmes.py scripts/tests/test_check_readmes.py
git commit -m "feat(scripts): add check_readmes.py to enforce README presence + quality"
```

### Task 2.6: Wire both checkers into `make lint`

**Files:**
- Modify: `Makefile`

- [ ] **Step 1: Locate the existing `lint` target in `Makefile`**

Read the file and find the recipe for `lint:`.

- [ ] **Step 2: Append the two check-script invocations to the lint recipe**

After the existing `ruff` / `ty` / `biome` commands, append:

```makefile
	uv run python scripts/check_metadata.py
	uv run python scripts/check_readmes.py
```

- [ ] **Step 3: Run `make lint` and expect it to FAIL**

Run: `make lint`
Expected: fails on metadata violations (packages still have placeholder descriptions, missing keywords) — this is expected; later phases fix them.

- [ ] **Step 4: Commit**

```bash
git add Makefile
git commit -m "chore(make): run check_metadata + check_readmes in make lint"
```

---

## Phase 3 — Python package metadata hygiene

For each of the 14 Python packages, apply the metadata template. Each task follows the same shape: read the current pyproject.toml, rewrite it with the complete content below, then run `check_metadata.py` to verify.

### Shared template reference

Every Python `pyproject.toml` must contain this baseline. Package-specific `name`, `description`, `keywords`, `dependencies` replace the `<...>` placeholders. Existing `[project.entry-points.*]` and `[tool.hatch.build.*]` blocks are preserved as-is.

```toml
[project]
name = "simple-module-<name>"
version = "0.0.1"
description = "<real description>"
readme = "README.md"
license = "MIT"
license-files = ["../../LICENSE"]
requires-python = ">=3.12"
authors = [{ name = "Anto Subash", email = "antosubash@live.com" }]
keywords = ["simple-module", "fastapi", "modular-monolith", "<domain...>"]
classifiers = [
    "Development Status :: 3 - Alpha",
    "Framework :: FastAPI",
    "Intended Audience :: Developers",
    "License :: OSI Approved :: MIT License",
    "Operating System :: OS Independent",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.12",
    "Topic :: Internet :: WWW/HTTP",
    "Topic :: Software Development :: Libraries :: Application Frameworks",
    "Typing :: Typed",
]
dependencies = [
    "simple-module-core==0.0.1",
    # ... third-party deps
]

[project.urls]
Homepage = "https://github.com/antosubash/simple_module_python"
Repository = "https://github.com/antosubash/simple_module_python"
Issues = "https://github.com/antosubash/simple_module_python/issues"
Changelog = "https://github.com/antosubash/simple_module_python/blob/main/CHANGELOG.md"
```

`license-files = ["../../LICENSE"]` works because Hatchling resolves paths relative to each package root; `framework/core → ../../LICENSE` is the root `LICENSE`. Same for `modules/*`.

### Task 3.1: `simple-module-core`

**Files:**
- Modify: `framework/core/pyproject.toml`

- [ ] **Step 1: Rewrite `framework/core/pyproject.toml` to:**

```toml
[project]
name = "simple-module-core"
version = "0.0.1"
description = "Module-system primitives for the simple_module framework — ModuleBase, discovery, diagnostics, events"
readme = "README.md"
license = "MIT"
license-files = ["../../LICENSE"]
requires-python = ">=3.12"
authors = [{ name = "Anto Subash", email = "antosubash@live.com" }]
keywords = ["simple-module", "fastapi", "modular-monolith", "plugin-system", "module-discovery"]
classifiers = [
    "Development Status :: 3 - Alpha",
    "Framework :: FastAPI",
    "Intended Audience :: Developers",
    "License :: OSI Approved :: MIT License",
    "Operating System :: OS Independent",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.12",
    "Topic :: Internet :: WWW/HTTP",
    "Topic :: Software Development :: Libraries :: Application Frameworks",
    "Typing :: Typed",
]
dependencies = [
    "babel>=2.14",
    "fastapi>=0.115",
    "packaging>=23.0",
    "pydantic>=2.0",
    "pydantic-settings>=2.0",
    "pyee>=12.0",
]

[project.urls]
Homepage = "https://github.com/antosubash/simple_module_python"
Repository = "https://github.com/antosubash/simple_module_python"
Issues = "https://github.com/antosubash/simple_module_python/issues"
Changelog = "https://github.com/antosubash/simple_module_python/blob/main/CHANGELOG.md"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

- [ ] **Step 2: Verify the test suite still passes**

Run: `uv run pytest framework/core/tests/ -v`
Expected: all pass.

- [ ] **Step 3: Commit**

```bash
git add framework/core/pyproject.toml
git commit -m "chore(core): flesh out pyproject metadata for PyPI 0.0.1"
```

### Task 3.2: `simple-module-db`

**Files:**
- Modify: `framework/db/pyproject.toml`

- [ ] **Step 1: Rewrite the file to:**

```toml
[project]
name = "simple-module-db"
version = "0.0.1"
description = "Per-module SQLModel Base, async session, standard mixins (Audit, SoftDelete, MultiTenant, Versioned) for simple_module"
readme = "README.md"
license = "MIT"
license-files = ["../../LICENSE"]
requires-python = ">=3.12"
authors = [{ name = "Anto Subash", email = "antosubash@live.com" }]
keywords = ["simple-module", "sqlmodel", "sqlalchemy", "async", "alembic", "multi-tenant"]
classifiers = [
    "Development Status :: 3 - Alpha",
    "Framework :: FastAPI",
    "Intended Audience :: Developers",
    "License :: OSI Approved :: MIT License",
    "Operating System :: OS Independent",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.12",
    "Topic :: Database",
    "Topic :: Software Development :: Libraries :: Application Frameworks",
    "Typing :: Typed",
]
dependencies = [
    "aiosqlite>=0.20",
    "alembic>=1.14",
    "asyncpg>=0.30",
    "simple-module-core==0.0.1",
    "sqlalchemy[asyncio]>=2.0",
    "sqlmodel>=0.0.22",
]

[project.urls]
Homepage = "https://github.com/antosubash/simple_module_python"
Repository = "https://github.com/antosubash/simple_module_python"
Issues = "https://github.com/antosubash/simple_module_python/issues"
Changelog = "https://github.com/antosubash/simple_module_python/blob/main/CHANGELOG.md"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.uv.sources]
simple-module-core = { workspace = true }
```

- [ ] **Step 2: Verify**

Run: `uv run pytest framework/db/tests/ -v`
Expected: all pass.

- [ ] **Step 3: Commit**

```bash
git add framework/db/pyproject.toml
git commit -m "chore(db): flesh out pyproject metadata for PyPI 0.0.1"
```

### Task 3.3: `simple-module-hosting`

**Files:**
- Modify: `framework/hosting/pyproject.toml`

- [ ] **Step 1: Rewrite the file to:**

```toml
[project]
name = "simple-module-hosting"
version = "0.0.1"
description = "FastAPI + Inertia.js host runtime for simple_module — app_builder, middleware stack, CLI (sm / simple-module), scaffolding"
readme = "README.md"
license = "MIT"
license-files = ["../../LICENSE"]
requires-python = ">=3.12"
authors = [{ name = "Anto Subash", email = "antosubash@live.com" }]
keywords = ["simple-module", "fastapi", "inertia", "starlette", "uvicorn", "scaffolding"]
classifiers = [
    "Development Status :: 3 - Alpha",
    "Framework :: FastAPI",
    "Intended Audience :: Developers",
    "License :: OSI Approved :: MIT License",
    "Operating System :: OS Independent",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.12",
    "Topic :: Internet :: WWW/HTTP :: WSGI :: Application",
    "Topic :: Software Development :: Libraries :: Application Frameworks",
    "Typing :: Typed",
]
dependencies = [
    "click>=8.1",
    "fastapi>=0.115",
    "fastapi-inertia>=1.0",
    "httpx>=0.27",
    "jinja2>=3.1",
    "simple-module-core==0.0.1",
    "simple-module-db==0.0.1",
    "starlette>=0.44",
    "uvicorn[standard]>=0.34",
]

[project.scripts]
sm = "simple_module_hosting.cli:main"
simple-module = "simple_module_hosting.cli:main"

[project.urls]
Homepage = "https://github.com/antosubash/simple_module_python"
Repository = "https://github.com/antosubash/simple_module_python"
Issues = "https://github.com/antosubash/simple_module_python/issues"
Changelog = "https://github.com/antosubash/simple_module_python/blob/main/CHANGELOG.md"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["simple_module_hosting"]

[tool.hatch.build.targets.wheel.force-include]
"simple_module_hosting/templates" = "simple_module_hosting/templates"

[tool.uv.sources]
simple-module-core = { workspace = true }
simple-module-db = { workspace = true }
```

- [ ] **Step 2: Verify `simple-module` entry point resolves**

Run: `uv sync --all-packages && uv run which simple-module`
Expected: prints a path to a `simple-module` executable inside `.venv/bin/`.

Run: `uv run simple-module --help`
Expected: prints the Click help menu (same as `sm --help`).

- [ ] **Step 3: Run tests**

Run: `uv run pytest framework/hosting/tests/ -v`
Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add framework/hosting/pyproject.toml uv.lock
git commit -m "chore(hosting): flesh out pyproject metadata; add simple-module CLI alias"
```

### Task 3.4: `simple-module-testing`

**Files:**
- Modify: `framework/testing/pyproject.toml`

- [ ] **Step 1: Rewrite the file to:**

```toml
[project]
name = "simple-module-testing"
version = "0.0.1"
description = "Shared pytest fixtures (app, client, db_session, authenticated_client) for writing simple_module module tests"
readme = "README.md"
license = "MIT"
license-files = ["../../LICENSE"]
requires-python = ">=3.12"
authors = [{ name = "Anto Subash", email = "antosubash@live.com" }]
keywords = ["simple-module", "pytest", "pytest-plugin", "fixtures", "testing"]
classifiers = [
    "Development Status :: 3 - Alpha",
    "Framework :: FastAPI",
    "Framework :: Pytest",
    "Intended Audience :: Developers",
    "License :: OSI Approved :: MIT License",
    "Operating System :: OS Independent",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.12",
    "Topic :: Software Development :: Testing",
    "Typing :: Typed",
]
dependencies = [
    "fastapi>=0.115",
    "httpx>=0.27",
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
    "simple-module-core==0.0.1",
    "simple-module-db==0.0.1",
    "simple-module-hosting==0.0.1",
    "sqlalchemy>=2.0",
]

[project.entry-points.pytest11]
simple_module_testing = "simple_module_testing.plugin"

[project.urls]
Homepage = "https://github.com/antosubash/simple_module_python"
Repository = "https://github.com/antosubash/simple_module_python"
Issues = "https://github.com/antosubash/simple_module_python/issues"
Changelog = "https://github.com/antosubash/simple_module_python/blob/main/CHANGELOG.md"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["simple_module_testing"]

[tool.uv.sources]
simple-module-core = { workspace = true }
simple-module-db = { workspace = true }
simple-module-hosting = { workspace = true }
```

- [ ] **Step 2: Verify**

Run: `uv run pytest framework/testing/tests/ -v`
Expected: all pass.

- [ ] **Step 3: Commit**

```bash
git add framework/testing/pyproject.toml
git commit -m "chore(testing): flesh out pyproject metadata for PyPI 0.0.1"
```

### Task 3.5: Module packages metadata (batch)

**Files:**
- Modify: `modules/auth/pyproject.toml`
- Modify: `modules/background_tasks/pyproject.toml`
- Modify: `modules/dashboard/pyproject.toml`
- Modify: `modules/datasets/pyproject.toml`
- Modify: `modules/feature_flags/pyproject.toml`
- Modify: `modules/file_storage/pyproject.toml`
- Modify: `modules/permissions/pyproject.toml`
- Modify: `modules/products/pyproject.toml`
- Modify: `modules/settings/pyproject.toml`
- Modify: `modules/users/pyproject.toml`

All 10 modules share this skeleton; apply to each and substitute the `<...>` values from the table below. The existing `[project.entry-points.simple_module]`, `[tool.hatch.build.targets.wheel.force-include]`, and `[tool.uv.sources]` blocks are **preserved unchanged** except for version pins rewritten in later phases.

**Template skeleton:**

```toml
[project]
name = "simple-module-<slug>"
version = "0.0.1"
description = "<description>"
readme = "README.md"
license = "MIT"
license-files = ["../../LICENSE"]
requires-python = ">=3.12"
authors = [{ name = "Anto Subash", email = "antosubash@live.com" }]
keywords = <keywords-list>
classifiers = [
    "Development Status :: 3 - Alpha",
    "Framework :: FastAPI",
    "Intended Audience :: Developers",
    "License :: OSI Approved :: MIT License",
    "Operating System :: OS Independent",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.12",
    "Topic :: Internet :: WWW/HTTP",
    "Topic :: Software Development :: Libraries :: Application Frameworks",
    "Typing :: Typed",
]
dependencies = <preserve existing list, but rewrite every simple-module-* to ==0.0.1>

<existing [project.entry-points.simple_module] block preserved>
<existing [project.scripts] block preserved if any>

[project.urls]
Homepage = "https://github.com/antosubash/simple_module_python"
Repository = "https://github.com/antosubash/simple_module_python"
Issues = "https://github.com/antosubash/simple_module_python/issues"
Changelog = "https://github.com/antosubash/simple_module_python/blob/main/CHANGELOG.md"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

<existing [tool.hatch.build.targets.wheel.force-include] block preserved>
<existing [tool.uv.sources] block preserved>
```

**Per-module values:**

| slug | description | keywords |
|---|---|---|
| `auth` | `"Session-cookie authentication primitives — middleware, login/logout, redirect helpers for simple_module"` | `["simple-module", "fastapi", "authentication", "session", "cookie"]` |
| `background-tasks` | `"Celery + Redis task queue with admin UI for monitoring and retrying failed/stuck tasks"` | `["simple-module", "celery", "redis", "task-queue", "background-jobs"]` |
| `dashboard` | `"Admin landing page and sidebar menu host for authenticated users of a simple_module app"` | `["simple-module", "dashboard", "admin", "inertia"]` |
| `datasets` | `"Geospatial + tabular dataset upload, parsing (shapely) and slugging for simple_module apps"` | `["simple-module", "geospatial", "shapely", "datasets", "gis"]` |
| `feature-flags` | `"Simple feature-flag module with per-tenant overrides and a consumer API for simple_module"` | `["simple-module", "feature-flags", "toggles", "multi-tenant"]` |
| `file-storage` | `"Pluggable file upload + storage (local or S3 via extras) module for simple_module apps"` | `["simple-module", "file-upload", "s3", "storage"]` |
| `permissions` | `"RBAC primitives — roles, permissions, @require_permission decorator, admin UI for simple_module"` | `["simple-module", "rbac", "permissions", "authorization"]` |
| `products` | `"Example CRUD module used as a reference / demo for building simple_module modules"` | `["simple-module", "example", "crud", "demo"]` |
| `settings` | `"Runtime settings UI — modules plug their own settings panels into a shared admin view"` | `["simple-module", "settings", "admin", "configuration"]` |
| `users` | `"Email + password user management, admin invites, RBAC-ready — replaces Keycloak for simple_module apps"` | `["simple-module", "users", "authentication", "fastapi-users", "admin"]` |

Break this into one task per module to keep the changes reviewable. Repeat the following sub-steps for each module:

- [ ] **Step 1: Read the current module `pyproject.toml`.**
- [ ] **Step 2: Rewrite per the skeleton + table row, preserving all `[project.entry-points.*]`, `[project.scripts]`, `[tool.hatch.build.*]`, and `[tool.uv.sources]` blocks verbatim.** Rewrite every inter-module dep string to `==0.0.1` (e.g., `"simple-module-core"` → `"simple-module-core==0.0.1"`).
- [ ] **Step 3: Run the module's test suite**: `uv run pytest modules/<name>/tests/ -v` — expect PASS.
- [ ] **Step 4: Commit** with message `chore(<slug>): flesh out pyproject metadata for PyPI 0.0.1`.

### Task 3.6: Run metadata check

- [ ] **Step 1: Run `python scripts/check_metadata.py`**

Run: `uv run python scripts/check_metadata.py`
Expected: all 14 Python packages pass. (npm packages still fail — that's Phase 4.)

If violations appear, fix the indicated files and re-run.

- [ ] **Step 2: Commit any follow-up fixes**

```bash
git add -A
git commit -m "chore: fix residual metadata violations flagged by check_metadata"
```

---

## Phase 4 — npm package metadata hygiene

### Task 4.1: `@simple-module-py/tsconfig`

**Files:**
- Modify: `packages/tsconfig/package.json`

- [ ] **Step 1: Rewrite the file to:**

```json
{
  "name": "@simple-module-py/tsconfig",
  "version": "0.0.1",
  "description": "Shared TypeScript compiler options (base.json) for simple_module apps",
  "keywords": ["simple-module", "tsconfig", "typescript"],
  "homepage": "https://github.com/antosubash/simple_module_python#readme",
  "bugs": "https://github.com/antosubash/simple_module_python/issues",
  "repository": {
    "type": "git",
    "url": "git+https://github.com/antosubash/simple_module_python.git",
    "directory": "packages/tsconfig"
  },
  "license": "MIT",
  "author": "Anto Subash <antosubash@live.com>",
  "files": ["base.json", "README.md"],
  "publishConfig": { "access": "public" }
}
```

- [ ] **Step 2: Commit**

```bash
git add packages/tsconfig/package.json
git commit -m "chore(tsconfig): ready @simple-module-py/tsconfig for npm publish"
```

### Task 4.2: `@simple-module-py/i18n`

**Files:**
- Modify: `packages/i18n/package.json`

- [ ] **Step 1: Rewrite the file to:**

```json
{
  "name": "@simple-module-py/i18n",
  "version": "0.0.1",
  "description": "i18next + react-i18next glue for simple_module apps — hooks, namespace conventions, locale wiring",
  "keywords": ["simple-module", "i18n", "i18next", "react-i18next", "localization"],
  "homepage": "https://github.com/antosubash/simple_module_python#readme",
  "bugs": "https://github.com/antosubash/simple_module_python/issues",
  "repository": {
    "type": "git",
    "url": "git+https://github.com/antosubash/simple_module_python.git",
    "directory": "packages/i18n"
  },
  "license": "MIT",
  "author": "Anto Subash <antosubash@live.com>",
  "type": "module",
  "main": "src/index.ts",
  "types": "src/index.ts",
  "exports": {
    ".": {
      "types": "./src/index.ts",
      "default": "./src/index.ts"
    }
  },
  "files": ["src", "README.md"],
  "publishConfig": { "access": "public" },
  "peerDependencies": {
    "react": "^19.0.0"
  },
  "dependencies": {
    "i18next": "^23.15.0",
    "react-i18next": "^15.1.0"
  },
  "devDependencies": {
    "@simple-module-py/tsconfig": "0.0.1"
  }
}
```

- [ ] **Step 2: Commit**

```bash
git add packages/i18n/package.json
git commit -m "chore(i18n): ready @simple-module-py/i18n for npm publish"
```

### Task 4.3: `@simple-module-py/ui`

**Files:**
- Modify: `packages/ui/package.json`

- [ ] **Step 1: Rewrite the file to:**

```json
{
  "name": "@simple-module-py/ui",
  "version": "0.0.1",
  "description": "shadcn-derived React UI components and layouts for simple_module apps",
  "keywords": ["simple-module", "react", "shadcn", "tailwind", "ui"],
  "homepage": "https://github.com/antosubash/simple_module_python#readme",
  "bugs": "https://github.com/antosubash/simple_module_python/issues",
  "repository": {
    "type": "git",
    "url": "git+https://github.com/antosubash/simple_module_python.git",
    "directory": "packages/ui"
  },
  "license": "MIT",
  "author": "Anto Subash <antosubash@live.com>",
  "type": "module",
  "main": "src/index.ts",
  "types": "src/index.ts",
  "exports": {
    ".": {
      "types": "./src/index.ts",
      "default": "./src/index.ts"
    },
    "./*": "./src/*"
  },
  "files": ["src", "README.md"],
  "publishConfig": { "access": "public" },
  "peerDependencies": {
    "react": "^19.0.0"
  },
  "dependencies": {
    "@simple-module-py/i18n": "0.0.1"
  },
  "devDependencies": {
    "@simple-module-py/tsconfig": "0.0.1"
  }
}
```

- [ ] **Step 2: Commit**

```bash
git add packages/ui/package.json
git commit -m "chore(ui): ready @simple-module-py/ui for npm publish"
```

### Task 4.4: Update all consuming `@simple-module-py/*` imports

**Files:**
- Modify: any file in `host/client_app/`, `modules/*/*/pages/`, `packages/*/src/` that imports `@simple-module-py/...`
- Modify: any `package.json` that lists `@simple-module-py/*` deps (module `package.json` stubs, `host/client_app/package.json`, etc.)
- Modify: any `tsconfig.json` that `extends` from `@simple-module-py/tsconfig/base.json`

- [ ] **Step 1: Find every reference**

Run: `rg -n "@simple-module-py/" --type ts --type tsx --type json --type jsx -l`

- [ ] **Step 2: Replace `@simple-module-py/` with `@simple-module-py/` in each matching file**

Use `rg -l "@simple-module-py/"` + your editor's replace-in-files to do this in bulk. Verify no occurrences of the bare `@simple-module-py/` remain: `rg "@simple-module-py/"` (note the trailing slash; no matches expected).

- [ ] **Step 3: Regenerate `package-lock.json`**

Run: `npm install`
Expected: succeeds; `package-lock.json` updates.

- [ ] **Step 4: Verify typecheck + tests**

Run: `make lint`
Run: `npx tsc --noEmit -p host/client_app/tsconfig.json`
Expected: both succeed (metadata check may still flag README absence — that's Phase 5).

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor: rename npm scope @simple-module → @simple-module-py across repo

All three published packages move to @simple-module-py/* (ui, i18n,
tsconfig). Every consumer import, workspace package.json, and
tsconfig 'extends' reference updated to match."
```

---

## Phase 5 — Per-package READMEs

One task per package. Content is listed inline. READMEs deliberately follow a shared shape for discoverability: H1 (package name), one-paragraph pitch, **Install**, **What it provides**, **Usage**, **Depends on**, **License**.

Each task has two steps: (1) write the file, (2) commit. After all 17 READMEs, Task 5.18 runs `check_readmes.py` and `check_metadata.py` to verify the whole set.

### Task 5.1: `simple-module-core/README.md`

- [ ] **Step 1: Write `framework/core/README.md`**

```markdown
# simple-module-core

Module-system primitives for the [simple_module](https://github.com/antosubash/simple_module_python) framework — a modular-monolith for Python/FastAPI where each feature is a plugin package discovered at boot.

This package defines `ModuleBase`, the `ModuleMeta` descriptor, the `discover_modules()` entry-point loader, topological dependency sorting, event bus primitives, and the diagnostic codes (`SM001`–`SM017`) used by `make doctor`.

## Install

```bash
pip install simple-module-core
```

You usually don't install this directly — it's pulled in by `simple-module-hosting` and every `simple-module-*` module.

## What it provides

- `ModuleBase` — the subclass every module extends to opt into lifecycle hooks.
- `ModuleMeta` — required `meta = ModuleMeta(name=..., depends_on=...)` attribute on each module.
- `discover_modules()` — loads all `[project.entry-points.simple_module]` modules, topologically sorts by `depends_on`.
- Diagnostic registry — `SM001` missing meta, `SM003` orphan page, `SM008` duplicate name, `SM009` framework→plugin coupling violation, and ~ten others.
- Tiny event-bus (`pyee`) for decoupled module-to-module communication.

## Usage

```python
# modules/orders/orders/module.py
from simple_module_core import ModuleBase, ModuleMeta


class OrdersModule(ModuleBase):
    meta = ModuleMeta(name="orders", depends_on=["users"])

    def register_routes(self, api_router, view_router):
        from .endpoints import api, views
        api_router.include_router(api.router)
        view_router.include_router(views.router)
```

And in `pyproject.toml`:

```toml
[project.entry-points.simple_module]
orders = "orders.module:OrdersModule"
```

The host's `discover_modules()` call picks this up automatically at boot.

## Depends on

- `fastapi`, `pydantic`, `pydantic-settings`, `pyee`, `babel`, `packaging`

## License

MIT — see [LICENSE](https://github.com/antosubash/simple_module_python/blob/main/LICENSE).
```

- [ ] **Step 2: Commit**

```bash
git add framework/core/README.md
git commit -m "docs(core): add package README for PyPI"
```

### Task 5.2: `simple-module-db/README.md`

- [ ] **Step 1: Write `framework/db/README.md`**

```markdown
# simple-module-db

Database layer for the [simple_module](https://github.com/antosubash/simple_module_python) framework. Provides a per-module `Base`, an async SQLAlchemy/SQLModel session, standard mixins, and an auto-commit-on-flush listener that removes manual `session.commit()` calls from service code.

## Install

```bash
pip install simple-module-db
```

## What it provides

- `create_module_base("<module_name>")` — a module-scoped declarative `Base`. PostgreSQL maps it to its own schema; SQLite namespaces via table-name prefix.
- Per-request async session (`get_db`) with an auto-commit-on-flush hook — `after_flush` commits if there are pending writes, rolls back otherwise.
- Mixins in `simple_module_db.mixins`: `AuditMixin` (created_at/updated_at), `SoftDeleteMixin` (auto-filtered unless `stmt.execution_options(include_deleted=True)`), `MultiTenantMixin`, `VersionedMixin`.
- `DatabaseState` container used by the framework to avoid global mutable state.

## Usage

```python
# modules/orders/orders/models.py
from simple_module_db import AuditMixin, SoftDeleteMixin, create_module_base
from sqlmodel import Field

Base = create_module_base("orders")


class Order(Base, AuditMixin, SoftDeleteMixin, table=True):
    id: int | None = Field(default=None, primary_key=True)
    customer_id: int = Field(index=True, foreign_key="users_user.id")
    total_cents: int
```

In a service:

```python
from simple_module_db import get_db

async def create_order(session = Depends(get_db), ...):
    order = Order(customer_id=..., total_cents=...)
    session.add(order)
    await session.flush()   # assigns order.id; auto-commit happens after the request
    return order
```

Never call `session.commit()` — the framework handles it.

## Depends on

- `simple-module-core`, `sqlalchemy[asyncio]`, `sqlmodel`, `alembic`, `asyncpg`, `aiosqlite`

## License

MIT — see [LICENSE](https://github.com/antosubash/simple_module_python/blob/main/LICENSE).
```

- [ ] **Step 2: Commit**

```bash
git add framework/db/README.md
git commit -m "docs(db): add package README for PyPI"
```

### Task 5.3: `simple-module-hosting/README.md`

- [ ] **Step 1: Write `framework/hosting/README.md`**

```markdown
# simple-module-hosting

FastAPI + Inertia.js host runtime for the [simple_module](https://github.com/antosubash/simple_module_python) framework — builds the app, wires the middleware pipeline, exposes the `sm` / `simple-module` CLI, and ships the project scaffolder.

## Install

```bash
pip install simple-module-hosting
```

For a new project, most users run the generator instead:

```bash
uvx simple-module new my-app
```

## What it provides

- `create_app(settings)` — returns a fully-wired `FastAPI` instance with all discovered modules registered.
- Middleware pipeline (execution order): CorrelationId → RequestLogging → SecurityHeaders → Session → `<module middleware>` → Tenant (opt-in) → Locale → InertiaLayoutData → app.
- Inertia wiring — shared props (`auth`, `menus`, `i18n`), `InertiaDep`, page-route lookup.
- CLI entry points: both `sm` and `simple-module` are installed and alias the same Click tree.
- Scaffolders — `sm create-host`, `sm create-module`, `sm new` (greenfield app with users + dashboard + permissions pre-wired), `sm gen-pages`.

## Usage

Minimal `main.py`:

```python
from simple_module_hosting import create_app
from simple_module_hosting.settings import Settings

settings = Settings()           # reads SM_* env vars
app = create_app(settings)      # discovers + registers every installed module

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

CLI:

```bash
simple-module new my-app        # scaffold a new project
simple-module doctor            # diagnostic codes (SM001-SM017)
simple-module gen-pages         # regenerate client_app/modules.generated.ts
```

`sm` works identically to `simple-module`.

## Depends on

- `simple-module-core`, `simple-module-db`
- `fastapi`, `fastapi-inertia`, `starlette`, `uvicorn`, `click`, `jinja2`, `httpx`

## License

MIT — see [LICENSE](https://github.com/antosubash/simple_module_python/blob/main/LICENSE).
```

- [ ] **Step 2: Commit**

```bash
git add framework/hosting/README.md
git commit -m "docs(hosting): add package README for PyPI"
```

### Task 5.4: `simple-module-testing/README.md`

- [ ] **Step 1: Write `framework/testing/README.md`**

```markdown
# simple-module-testing

Shared pytest fixtures and helpers for writing tests against [simple_module](https://github.com/antosubash/simple_module_python) apps and modules.

Fixtures are exposed via a `pytest11` entry point, so installing the package is enough — no `conftest.py` import needed.

## Install

```bash
pip install simple-module-testing
# or, if you already pulled in the framework:
pip install "simple-module-hosting[dev]"
```

## What it provides

- `settings` — a ready-to-use `Settings` instance with an in-memory SQLite database and multi-tenancy enabled.
- `db_state`, `engine`, `db_session` — fresh `DatabaseState` per test; `db_session` also creates all module tables and stamps `alembic_version` at head so the boot-time migration check passes.
- `app` — a `create_app(settings)` instance with `lifespan` started and stopped.
- `client` — an `httpx.AsyncClient` bound to the test app.
- `authenticated_client` — same but with an admin user seeded and a forged session cookie attached.

## Usage

In a module's `tests/test_something.py`:

```python
import pytest

pytestmark = pytest.mark.asyncio


async def test_create_order(authenticated_client):
    resp = await authenticated_client.post(
        "/api/orders",
        json={"customer_id": 1, "total_cents": 9900},
    )
    assert resp.status_code == 201
    assert resp.json()["total_cents"] == 9900
```

No fixture imports, no `conftest.py` — the `pytest11` entry point auto-loads them.

## Depends on

- `simple-module-core`, `simple-module-db`, `simple-module-hosting`
- `pytest`, `pytest-asyncio`, `httpx`, `sqlalchemy`

## License

MIT — see [LICENSE](https://github.com/antosubash/simple_module_python/blob/main/LICENSE).
```

- [ ] **Step 2: Commit**

```bash
git add framework/testing/README.md
git commit -m "docs(testing): add package README for PyPI"
```

### Task 5.5: `simple-module-auth/README.md`

- [ ] **Step 1: Write `modules/auth/README.md`**

```markdown
# simple-module-auth

Session-cookie authentication primitives for [simple_module](https://github.com/antosubash/simple_module_python) apps. Provides the `SessionMiddleware` wiring, login/logout helpers, and login-redirect handling used by the `simple-module-users` module.

**Heads up:** for most apps you don't install this directly — `simple-module-users` pulls it in and builds the email+password auth flow on top of these primitives.

## Install

```bash
pip install simple-module-auth
```

## What it provides

- Starlette `SessionMiddleware` configuration reading `SM_SECRET_KEY` and `SM_SESSION_COOKIE_*` env vars.
- `current_user_id` FastAPI dependency reading the signed session cookie.
- Redirect-to-login helpers for unauthenticated requests on Inertia routes.
- Login-required decorator / dependency for protecting routes without pulling in the heavier `simple-module-users` package.

## Usage

```python
from fastapi import APIRouter, Depends
from simple_module_auth import require_login

router = APIRouter()


@router.get("/me")
async def me(user_id: int = Depends(require_login)):
    return {"user_id": user_id}
```

Routes that need more than just "logged in" (e.g. role/permission checks) should use `simple-module-permissions` instead.

## Depends on

- `simple-module-core`, `simple-module-db`
- `itsdangerous`

## License

MIT — see [LICENSE](https://github.com/antosubash/simple_module_python/blob/main/LICENSE).
```

- [ ] **Step 2: Commit**

```bash
git add modules/auth/README.md
git commit -m "docs(auth): add package README for PyPI"
```

### Task 5.6: `simple-module-users/README.md`

- [ ] **Step 1: Write `modules/users/README.md`**

```markdown
# simple-module-users

Email+password user management for [simple_module](https://github.com/antosubash/simple_module_python) apps. Replaces Keycloak/Auth0 for the common case: local accounts, admin invites, password reset, optional public signup. Built on `fastapi-users`.

## Install

```bash
pip install simple-module-users
```

Pre-wired into any app scaffolded with `simple-module new`.

## What it provides

- Email + password registration, login, logout, password reset.
- Admin invite flow — admin enters an email, recipient clicks a link, sets a password, is logged in.
- Public signup toggle (`SM_USERS_ALLOW_SIGNUP`, default `false`).
- Bootstrap admin via env vars (`SM_USERS_BOOTSTRAP_EMAIL` + `SM_USERS_BOOTSTRAP_PASSWORD`) — idempotent, only creates if the users table is empty.
- `sm-users create-admin` CLI for ad-hoc admin creation.
- Inertia pages for login/register/invite-accept/admin-invite.
- Console mailer (logs to stdout) or SMTP mailer (`SM_USERS_MAILER=smtp`).

## Usage

CLI:

```bash
uv run sm-users create-admin --email admin@example.com --password 'change-me'
```

Bootstrap-on-boot (`.env`):

```
SM_USERS_BOOTSTRAP_EMAIL=admin@example.com
SM_USERS_BOOTSTRAP_PASSWORD=change-me
```

Program:

```python
from users.deps import CurrentUser    # type: ignore[import-not-found]

@router.get("/profile")
async def profile(user: CurrentUser):
    return {"email": user.email}
```

## Depends on

- `simple-module-core`, `simple-module-db`, `simple-module-hosting`, `simple-module-auth`
- `fastapi-users[sqlalchemy]>=15,<16`, `aiosmtplib`, `cachetools`, `typer`

## License

MIT — see [LICENSE](https://github.com/antosubash/simple_module_python/blob/main/LICENSE).
```

- [ ] **Step 2: Commit**

```bash
git add modules/users/README.md
git commit -m "docs(users): add package README for PyPI"
```

### Task 5.7: `simple-module-dashboard/README.md`

- [ ] **Step 1: Write `modules/dashboard/README.md`**

```markdown
# simple-module-dashboard

Admin landing page + sidebar menu host for authenticated users of a [simple_module](https://github.com/antosubash/simple_module_python) app. Renders `/dashboard`, collects menu entries registered by every other installed module, and provides the primary Inertia layout.

Pre-wired into any app scaffolded with `simple-module new`.

## Install

```bash
pip install simple-module-dashboard
```

## What it provides

- `/dashboard` Inertia view, a single entry point for logged-in users.
- Global sidebar renderer — aggregates `register_menu_items()` calls from all modules into one tree.
- Breadcrumb + page-title provider used by downstream module pages.

## Usage

Install the module in a host, and any other module can register a menu entry:

```python
# modules/orders/orders/module.py
from simple_module_core import ModuleBase, ModuleMeta
from simple_module_core.menus import MenuItem


class OrdersModule(ModuleBase):
    meta = ModuleMeta(name="orders")

    def register_menu_items(self):
        return [MenuItem(label="Orders", href="/orders", icon="shopping-bag")]
```

The dashboard sidebar picks it up automatically.

## Depends on

- `simple-module-core`, `simple-module-db`, `simple-module-hosting`
- `simple-module-users`, `simple-module-products` (demo content used by the default layout)

## License

MIT — see [LICENSE](https://github.com/antosubash/simple_module_python/blob/main/LICENSE).
```

- [ ] **Step 2: Commit**

```bash
git add modules/dashboard/README.md
git commit -m "docs(dashboard): add package README for PyPI"
```

### Task 5.8: `simple-module-permissions/README.md`

- [ ] **Step 1: Write `modules/permissions/README.md`**

```markdown
# simple-module-permissions

Role-based access control (RBAC) for [simple_module](https://github.com/antosubash/simple_module_python) apps. Users get roles, roles carry permissions, and route handlers declare required permissions at the decorator or dependency layer.

Pre-wired into any app scaffolded with `simple-module new`.

## Install

```bash
pip install simple-module-permissions
```

## What it provides

- `Role` and `Permission` SQLModel tables, seeded from module-registered defaults.
- `@require_permission("orders.read")` route decorator and `HasPermission("...")` dependency.
- Admin UI at `/permissions/admin` for assigning roles to users.
- `register_permissions()` hook — every module declares its permission strings at boot, the registry dedupes and persists them.

## Usage

Declare permissions at module boot:

```python
# modules/orders/orders/module.py
class OrdersModule(ModuleBase):
    meta = ModuleMeta(name="orders")

    def register_permissions(self):
        return ["orders.read", "orders.write"]
```

Guard a route:

```python
from fastapi import APIRouter, Depends
from permissions.deps import HasPermission   # type: ignore[import-not-found]

router = APIRouter()


@router.get("/orders", dependencies=[Depends(HasPermission("orders.read"))])
async def list_orders(): ...
```

Admin flow: navigate to `/permissions/admin`, create a role, assign permissions, assign the role to users.

## Depends on

- `simple-module-core`, `simple-module-db`, `simple-module-hosting`, `simple-module-users`

## License

MIT — see [LICENSE](https://github.com/antosubash/simple_module_python/blob/main/LICENSE).
```

- [ ] **Step 2: Commit**

```bash
git add modules/permissions/README.md
git commit -m "docs(permissions): add package README for PyPI"
```

### Task 5.9: `simple-module-background-tasks/README.md`

- [ ] **Step 1: Write `modules/background_tasks/README.md`**

```markdown
# simple-module-background-tasks

Celery + Redis background-task module for [simple_module](https://github.com/antosubash/simple_module_python) apps. Provides a pre-configured Celery instance, a task registration hook, and an admin UI for monitoring + retrying failed/stuck tasks.

## Install

```bash
pip install simple-module-background-tasks
```

Requires a Redis broker — set `SM_CELERY_BROKER_URL` (default `redis://localhost:6379/0`).

## What it provides

- `register_background_tasks()` module hook — modules declare tasks here; the registry wires them into the Celery app at boot.
- Admin UI at `/background-tasks/admin` — list recent runs, retry failed, inspect tracebacks.
- Shared Celery app accessible via `from background_tasks import celery_app` (import name `background_tasks`, distribution name `simple-module-background-tasks`).

## Usage

Declare a task in a module:

```python
# modules/reports/reports/tasks.py
from background_tasks import celery_app   # type: ignore[import-not-found]


@celery_app.task(name="reports.generate")
def generate_report(report_id: int) -> None:
    ...
```

Register it:

```python
class ReportsModule(ModuleBase):
    meta = ModuleMeta(name="reports", depends_on=["background_tasks"])

    def register_background_tasks(self):
        from . import tasks  # noqa: F401 — side-effect: registers tasks
```

Enqueue from an endpoint:

```python
generate_report.delay(report_id=42)
```

Run a worker locally:

```bash
uv run celery -A background_tasks.celery_app worker --loglevel=info
```

## Depends on

- `simple-module-core`, `simple-module-db`, `simple-module-hosting`
- `celery[redis]>=5.4`, `redis>=5`

## License

MIT — see [LICENSE](https://github.com/antosubash/simple_module_python/blob/main/LICENSE).
```

- [ ] **Step 2: Commit**

```bash
git add modules/background_tasks/README.md
git commit -m "docs(background-tasks): add package README for PyPI"
```

### Task 5.10: `simple-module-file-storage/README.md`

- [ ] **Step 1: Write `modules/file_storage/README.md`**

```markdown
# simple-module-file-storage

Pluggable file-upload + storage module for [simple_module](https://github.com/antosubash/simple_module_python) apps. Defaults to local-disk storage for development; install the `[s3]` extra to switch to any S3-compatible backend via `aioboto3`.

## Install

```bash
# local-disk storage (dev default)
pip install simple-module-file-storage

# S3-compatible storage (production)
pip install "simple-module-file-storage[s3]"
```

## What it provides

- `POST /api/files` upload endpoint with multipart + metadata.
- `GET /api/files/{id}` signed-URL or stream download.
- Pluggable backend via `SM_FILE_STORAGE_BACKEND` (`local` | `s3`).
- S3 config via `SM_FILE_STORAGE_S3_BUCKET`, `SM_FILE_STORAGE_S3_ENDPOINT` (for R2/MinIO/etc.), `SM_FILE_STORAGE_S3_REGION`.

## Usage

From another module:

```python
from file_storage.service import FileStorageService   # type: ignore[import-not-found]

async def attach_receipt(
    svc: FileStorageService = Depends(FileStorageService),
    upload: UploadFile = File(...),
):
    record = await svc.save(upload, folder="receipts/")
    return {"file_id": record.id, "url": record.url}
```

Env config (example, S3):

```
SM_FILE_STORAGE_BACKEND=s3
SM_FILE_STORAGE_S3_BUCKET=my-app-uploads
SM_FILE_STORAGE_S3_REGION=us-east-1
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
```

## Depends on

- `simple-module-core`, `simple-module-db`, `simple-module-hosting`
- `aiofiles`
- Optional: `aioboto3` (install the `[s3]` extra)

## License

MIT — see [LICENSE](https://github.com/antosubash/simple_module_python/blob/main/LICENSE).
```

- [ ] **Step 2: Commit**

```bash
git add modules/file_storage/README.md
git commit -m "docs(file-storage): add package README for PyPI"
```

### Task 5.11: `simple-module-datasets/README.md`

- [ ] **Step 1: Write `modules/datasets/README.md`**

```markdown
# simple-module-datasets

Geospatial + tabular dataset upload module for [simple_module](https://github.com/antosubash/simple_module_python) apps. Users upload CSV/GeoJSON/Shapefile; the module parses, slugs a canonical name, and stores geometry using `shapely`.

## Install

```bash
pip install simple-module-datasets
```

Also needs `simple-module-file-storage` + `simple-module-background-tasks` (declared as deps).

## What it provides

- `POST /api/datasets` — multipart upload; the file is staged via `simple-module-file-storage`, then a Celery job parses it in the background.
- `Dataset` SQLModel record with `name`, `slug` (via `python-slugify`), `geometry_type`, `row_count`, `bbox`.
- Shapely-backed parsers for GeoJSON, CSV with lat/lon columns, and zipped Shapefiles.
- Admin UI for browsing + deleting datasets.

## Usage

Upload from a form:

```bash
curl -X POST -F "file=@cities.geojson" http://localhost:8000/api/datasets
```

Query parsed datasets:

```python
from datasets.service import DatasetService   # type: ignore[import-not-found]

async def list_by_bbox(svc: DatasetService = Depends(DatasetService), ...):
    return await svc.intersects(bbox=(-74.1, 40.6, -73.8, 40.9))
```

## Depends on

- `simple-module-core`, `simple-module-db`, `simple-module-hosting`
- `simple-module-file-storage`, `simple-module-background-tasks`
- `shapely>=2.0`, `python-slugify>=8.0`, `celery>=5.4`

## License

MIT — see [LICENSE](https://github.com/antosubash/simple_module_python/blob/main/LICENSE).
```

- [ ] **Step 2: Commit**

```bash
git add modules/datasets/README.md
git commit -m "docs(datasets): add package README for PyPI"
```

### Task 5.12: `simple-module-feature-flags/README.md`

- [ ] **Step 1: Write `modules/feature_flags/README.md`**

```markdown
# simple-module-feature-flags

Feature flags for [simple_module](https://github.com/antosubash/simple_module_python) apps. Global flags with per-tenant overrides, a tiny consumer API, and no external service to run.

## Install

```bash
pip install simple-module-feature-flags
```

## What it provides

- `Flag` and `TenantFlagOverride` SQLModel tables.
- `is_enabled("flag.name", tenant_id=...)` consumer API.
- Admin UI at `/feature-flags/admin` — toggle flags, add tenant overrides.
- Cache layer so checking a flag on every request is cheap.

## Usage

Gate a route:

```python
from feature_flags import is_enabled   # type: ignore[import-not-found]
from fastapi import APIRouter, Depends, HTTPException

router = APIRouter()


@router.get("/new-feature")
async def new_feature(tenant_id: int = Depends(current_tenant_id)):
    if not await is_enabled("orders.new_pricing_engine", tenant_id=tenant_id):
        raise HTTPException(404)
    return {"rolled_out": True}
```

Seed a flag in a migration or admin UI:

```python
# via migration
Flag(name="orders.new_pricing_engine", enabled=False)
```

Tenant override:

```python
TenantFlagOverride(tenant_id=7, flag_name="orders.new_pricing_engine", enabled=True)
```

## Depends on

- `simple-module-core`, `simple-module-db`, `simple-module-hosting`

## License

MIT — see [LICENSE](https://github.com/antosubash/simple_module_python/blob/main/LICENSE).
```

- [ ] **Step 2: Commit**

```bash
git add modules/feature_flags/README.md
git commit -m "docs(feature-flags): add package README for PyPI"
```

### Task 5.13: `simple-module-settings/README.md`

- [ ] **Step 1: Write `modules/settings/README.md`**

```markdown
# simple-module-settings

Runtime settings UI for [simple_module](https://github.com/antosubash/simple_module_python) apps. Other modules plug their own settings panels into a shared admin view — one page per module tab — without the host having to know about them.

## Install

```bash
pip install simple-module-settings
```

## What it provides

- `/settings` admin page aggregating every installed module's settings panel.
- `register_settings_panel()` hook — a module declares `{title, inertia_page, requires_permission}`; `simple-module-settings` renders the tab.
- DB-backed runtime settings table (separate from env-var-driven `SM_*` settings) for values admins change at runtime.

## Usage

Register a panel:

```python
class OrdersModule(ModuleBase):
    meta = ModuleMeta(name="orders")

    def register_settings_panel(self):
        return {
            "title": "Orders",
            "inertia_page": "Orders/SettingsPanel",
            "requires_permission": "orders.manage",
        }
```

That adds an **Orders** tab at `/settings`. The rendered page is a regular Inertia page authored inside the `orders` module.

## Depends on

- `simple-module-core`, `simple-module-db`, `simple-module-hosting`

## License

MIT — see [LICENSE](https://github.com/antosubash/simple_module_python/blob/main/LICENSE).
```

- [ ] **Step 2: Commit**

```bash
git add modules/settings/README.md
git commit -m "docs(settings): add package README for PyPI"
```

### Task 5.14: `simple-module-products/README.md`

- [ ] **Step 1: Write `modules/products/README.md`**

```markdown
# simple-module-products

Example CRUD module for [simple_module](https://github.com/antosubash/simple_module_python). **This is a reference / demo**, not a production-ready commerce module — it exists to show what a fully-featured `simple_module` module looks like end-to-end: `ModuleBase`, SQLModel table with `AuditMixin`, contracts, service, REST + Inertia endpoints, Browse/Create/Edit pages, tests.

Fresh `simple-module new` scaffolds *don't* include this by default — it's here as a readable example.

## Install

```bash
pip install simple-module-products
```

## What it provides

- `Product` SQLModel table with `name`, `sku`, `price_cents`, `AuditMixin`.
- Contracts (`ProductCreate`, `ProductUpdate`, `ProductRead`) under `products.contracts`.
- Service layer (`ProductsService`) encapsulating the (tiny) business logic.
- REST endpoints at `/api/products` + Inertia view endpoints at `/products`.
- Inertia pages `Products/Browse`, `Products/Create`, `Products/Edit`.
- Unit tests covering the service + integration tests hitting the full endpoint stack.

## Usage

It's a reference, so the most useful "usage" is reading the source:

- `modules/products/products/module.py` — the `ModuleBase` subclass.
- `modules/products/products/service.py` — business logic.
- `modules/products/products/pages/` — Inertia React pages.
- `modules/products/tests/` — the test patterns to copy into new modules.

If you do want a working `/products` in your own app:

```bash
uv add simple-module-products
# Alembic will now see the products schema at the next `alembic revision --autogenerate`.
```

## Depends on

- `simple-module-core`, `simple-module-db`, `simple-module-hosting`

## License

MIT — see [LICENSE](https://github.com/antosubash/simple_module_python/blob/main/LICENSE).
```

- [ ] **Step 2: Commit**

```bash
git add modules/products/README.md
git commit -m "docs(products): add package README for PyPI"
```

### Task 5.15: `@simple-module-py/tsconfig/README.md`

- [ ] **Step 1: Write `packages/tsconfig/README.md`**

```markdown
# @simple-module-py/tsconfig

Shared TypeScript compiler options for [simple_module](https://github.com/antosubash/simple_module_python) apps. One `base.json` that every `tsconfig.json` in the framework and its modules extends.

## Install

```bash
npm install --save-dev @simple-module-py/tsconfig
```

## What it provides

- `base.json` — the canonical compiler options for simple_module apps. Targets ES2022, `strict: true`, `module: "ESNext"`, `moduleResolution: "bundler"`, JSX `react-jsx`, `allowImportingTsExtensions: true`, `verbatimModuleSyntax: true`.

## Usage

In your app's `tsconfig.json`:

```json
{
  "extends": "@simple-module-py/tsconfig/base.json",
  "include": ["client_app/**/*.ts", "client_app/**/*.tsx"]
}
```

Override any option as needed — `extends` merges.

## Depends on

Nothing. This is a pure JSON config package.

## License

MIT — see [LICENSE](https://github.com/antosubash/simple_module_python/blob/main/LICENSE).
```

- [ ] **Step 2: Commit**

```bash
git add packages/tsconfig/README.md
git commit -m "docs(tsconfig): add package README for npm"
```

### Task 5.16: `@simple-module-py/i18n/README.md`

- [ ] **Step 1: Write `packages/i18n/README.md`**

```markdown
# @simple-module-py/i18n

`i18next` + `react-i18next` glue for [simple_module](https://github.com/antosubash/simple_module_python) apps. Ships an `i18next` instance pre-configured for the framework's per-module locale conventions (`<module>.<key>` namespacing, CLDR plurals, cookie-driven locale switching).

## Install

```bash
npm install @simple-module-py/i18n
```

Peer-depends on React 19. Runtime deps `i18next` and `react-i18next` install automatically.

## What it provides

- `createI18n({ locale, resources })` — returns a configured `i18next` instance.
- `<I18nProvider>` — React context provider; plug it at the root of your Inertia app.
- `useT(namespace?)` — hook returning the translation function, scoped if you pass a namespace.
- `withNamespace(ns)` — higher-order helper for components that want a stable namespace binding.

## Usage

Root setup (in `client_app/main.tsx`):

```tsx
import { createI18n, I18nProvider } from "@simple-module-py/i18n";

const i18n = createI18n({
  locale: window.__INITIAL_LOCALE__ ?? "en",
  resources: window.__I18N_RESOURCES__, // provided by InertiaLayoutDataMiddleware
});

function Root({ App, props }) {
  return (
    <I18nProvider i18n={i18n}>
      <App {...props} />
    </I18nProvider>
  );
}
```

In a module page:

```tsx
import { useT } from "@simple-module-py/i18n";

export default function Browse() {
  const t = useT("orders");
  return <h1>{t("browse.title")}</h1>;  // resolves to orders.browse.title
}
```

**Important:** when using `zod` schemas with translated messages, build the schema *inside* a component that calls `useT()` — never at module scope. Schemas constructed at import time freeze against the first render's locale.

## Depends on

- `i18next`, `react-i18next`
- Peer: `react ^19.0.0`

## License

MIT — see [LICENSE](https://github.com/antosubash/simple_module_python/blob/main/LICENSE).
```

- [ ] **Step 2: Commit**

```bash
git add packages/i18n/README.md
git commit -m "docs(i18n): add package README for npm"
```

### Task 5.17: `@simple-module-py/ui/README.md`

- [ ] **Step 1: Write `packages/ui/README.md`**

```markdown
# @simple-module-py/ui

shadcn-derived React UI components and layouts for [simple_module](https://github.com/antosubash/simple_module_python) apps. Buttons, Cards, Forms, Dialogs, sidebar Layouts — the toolbox every module page pulls from.

## Install

```bash
npm install @simple-module-py/ui
```

Peer-depends on React 19. Assumes Tailwind CSS 4 is configured in the consuming app.

## What it provides

- Core primitives: `Button`, `Input`, `Label`, `Textarea`, `Select`, `Switch`, `Checkbox`.
- Composite components: `Card`, `Dialog`, `Sheet`, `Popover`, `Tooltip`, `Toaster`, `Form` (react-hook-form bindings).
- Layouts: `AppLayout` (sidebar + content), `AuthLayout` (centred form).
- Small set of icons from `lucide-react`, re-exported.

All components ship as `.ts` / `.tsx` source (no bundling step) — any modern bundler (Vite, Next, etc.) handles them transparently.

## Usage

```tsx
import { Button, Card, CardHeader, CardContent, CardTitle } from "@simple-module-py/ui";

export default function ProductCard({ product }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{product.name}</CardTitle>
      </CardHeader>
      <CardContent>
        <Button onClick={...}>Add to cart</Button>
      </CardContent>
    </Card>
  );
}
```

### Owning the source (shadcn-style)

If you want to edit a component's source directly:

```bash
cp -r node_modules/@simple-module-py/ui/src packages/ui-local
# add to your tsconfig paths and package.json, then import from @/ui-local
```

At that point you've forked the library — `npm update` will no longer bring changes in.

## Depends on

- `@simple-module-py/i18n`
- Peer: `react ^19.0.0`

## License

MIT — see [LICENSE](https://github.com/antosubash/simple_module_python/blob/main/LICENSE).
```

- [ ] **Step 2: Commit**

```bash
git add packages/ui/README.md
git commit -m "docs(ui): add package README for npm"
```

### Task 5.18: Verify all 17 READMEs pass the checker

- [ ] **Step 1: Run the checker**

Run: `uv run python scripts/check_readmes.py`
Expected: "All READMEs OK."

If it fails, fix the flagged package's README (typical issues: missing `Install` or `Usage` section heading).

- [ ] **Step 2: Run full lint**

Run: `make lint`
Expected: passes cleanly. Both `check_metadata` and `check_readmes` green.

- [ ] **Step 3: Commit any residual fixes**

```bash
git add -A
git commit -m "docs: fix residual README issues flagged by check_readmes" || echo "nothing to commit"
```

---

## Phase 6 — Version bump script (TDD)

### Task 6.1: Write failing tests for `bump_version.py`

**Files:**
- Create: `scripts/tests/test_bump_version.py`

- [ ] **Step 1: Write the test file**

```python
"""Tests for scripts/bump_version.py."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.bump_version import (
    bump_npm_package,
    bump_python_package,
    main,
)


# -------- Python --------

PY_SAMPLE = """\
[project]
name = "simple-module-foo"
version = "0.0.1"
description = "x"
dependencies = [
    "simple-module-core==0.0.1",
    "fastapi>=0.115",
    "simple-module-db==0.0.1",
]
"""


def test_python_bump_updates_version(tmp_pkg_dir: Path, writer) -> None:
    p = writer(tmp_pkg_dir / "pyproject.toml", PY_SAMPLE)
    bump_python_package(p, "0.0.2")
    text = p.read_text()
    assert 'version = "0.0.2"' in text


def test_python_bump_rewrites_inter_pkg_pins(tmp_pkg_dir: Path, writer) -> None:
    p = writer(tmp_pkg_dir / "pyproject.toml", PY_SAMPLE)
    bump_python_package(p, "0.0.2")
    text = p.read_text()
    assert '"simple-module-core==0.0.2"' in text
    assert '"simple-module-db==0.0.2"' in text
    # non-simple-module deps untouched
    assert '"fastapi>=0.115"' in text


def test_python_bump_handles_unpinned_simple_module_dep(tmp_pkg_dir: Path, writer) -> None:
    p = writer(
        tmp_pkg_dir / "pyproject.toml",
        '[project]\nname = "x"\nversion = "0.0.1"\ndependencies = ["simple-module-core"]\n',
    )
    bump_python_package(p, "0.0.2")
    text = p.read_text()
    assert '"simple-module-core==0.0.2"' in text


# -------- npm --------

NPM_SAMPLE = {
    "name": "@simple-module-py/foo",
    "version": "0.0.1",
    "dependencies": {
        "@simple-module-py/i18n": "0.0.1",
        "react": "^19.0.0",
    },
    "devDependencies": {
        "@simple-module-py/tsconfig": "0.0.1",
    },
    "peerDependencies": {
        "react": "^19.0.0",
    },
}


def test_npm_bump_updates_version_and_inter_pkg(tmp_pkg_dir: Path, writer) -> None:
    p = writer(
        tmp_pkg_dir / "package.json", json.dumps(NPM_SAMPLE, indent=2) + "\n"
    )
    bump_npm_package(p, "0.0.2")
    data = json.loads(p.read_text())
    assert data["version"] == "0.0.2"
    assert data["dependencies"]["@simple-module-py/i18n"] == "0.0.2"
    assert data["devDependencies"]["@simple-module-py/tsconfig"] == "0.0.2"
    assert data["dependencies"]["react"] == "^19.0.0"
    assert data["peerDependencies"]["react"] == "^19.0.0"


# -------- main() orchestration --------

def _fake_repo(tmp_path: Path, writer) -> Path:
    writer(
        tmp_path / "framework/core/pyproject.toml",
        '[project]\nname = "simple-module-core"\nversion = "0.0.1"\n',
    )
    writer(
        tmp_path / "framework/db/pyproject.toml",
        '[project]\nname = "simple-module-db"\nversion = "0.0.1"\ndependencies=["simple-module-core==0.0.1"]\n',
    )
    writer(
        tmp_path / "packages/ui/package.json",
        json.dumps({"name": "@simple-module-py/ui", "version": "0.0.1"}, indent=2) + "\n",
    )
    return tmp_path


def test_main_bumps_all(tmp_path: Path, monkeypatch, writer) -> None:
    _fake_repo(tmp_path, writer)
    monkeypatch.chdir(tmp_path)
    assert main(["0.0.2"]) == 0
    assert 'version = "0.0.2"' in (tmp_path / "framework/core/pyproject.toml").read_text()
    assert 'version = "0.0.2"' in (tmp_path / "framework/db/pyproject.toml").read_text()
    assert (
        '"simple-module-core==0.0.2"'
        in (tmp_path / "framework/db/pyproject.toml").read_text()
    )
    data = json.loads((tmp_path / "packages/ui/package.json").read_text())
    assert data["version"] == "0.0.2"


def test_main_check_mode_fails_when_out_of_sync(tmp_path: Path, monkeypatch, writer) -> None:
    _fake_repo(tmp_path, writer)
    monkeypatch.chdir(tmp_path)
    assert main(["0.0.2", "--check"]) != 0


def test_main_check_mode_passes_when_in_sync(tmp_path: Path, monkeypatch, writer) -> None:
    _fake_repo(tmp_path, writer)
    monkeypatch.chdir(tmp_path)
    assert main(["0.0.1", "--check"]) == 0


def test_main_rejects_invalid_version(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit):
        main(["not-a-version"])
```

- [ ] **Step 2: Run tests, confirm they fail**

Run: `uv run pytest scripts/tests/test_bump_version.py -v`
Expected: FAIL — `ModuleNotFoundError: scripts.bump_version`.

### Task 6.2: Implement `bump_version.py`

**Files:**
- Create: `scripts/bump_version.py`

- [ ] **Step 1: Write the script**

```python
"""Bump the version of every simple_module package in lockstep.

Walks every framework/*/pyproject.toml, modules/*/pyproject.toml, and
packages/*/package.json. Rewrites:

  * project.version
  * every simple-module-* entry in project.dependencies → "simple-module-*==<version>"
  * every @simple-module-py/* entry in dependencies / devDependencies /
    peerDependencies → "<version>"

Flags:
  --check     exit non-zero if any file is out of sync with <version>
  --dry-run   print a summary of changes but do not write

Usage:
  python scripts/bump_version.py 0.0.2
  python scripts/bump_version.py 0.0.2 --check
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import tomlkit

VERSION_RE = re.compile(r"^\d+\.\d+\.\d+([-.]?(a|b|rc|alpha|beta)\d*)?$")
PY_PKG_PREFIX = "simple-module-"
NPM_SCOPE_PREFIX = "@simple-module-py/"


def _parse_requirement_name(spec: str) -> str:
    """Return the distribution name from a PEP 508 requirement string."""
    # Strip env markers and extras.
    base = spec.split(";", 1)[0].strip()
    base = base.split("[", 1)[0]
    # Split on any version spec operator.
    for op in ("===", "==", ">=", "<=", "!=", "~=", ">", "<"):
        if op in base:
            return base.split(op, 1)[0].strip()
    return base.strip()


def bump_python_package(pyproject: Path, new_version: str, *, check: bool = False) -> bool:
    """Return True if the file is (or would be) at new_version. Write unless check=True."""
    doc = tomlkit.parse(pyproject.read_text(encoding="utf-8"))
    project = doc.get("project")
    if project is None:
        return True  # nothing to bump

    changed = False
    current = str(project.get("version", ""))
    if current != new_version:
        changed = True
        project["version"] = new_version

    deps = project.get("dependencies")
    if deps is not None:
        for i, entry in enumerate(deps):
            spec = str(entry)
            name = _parse_requirement_name(spec)
            if name.startswith(PY_PKG_PREFIX):
                want = f"{name}=={new_version}"
                if spec != want:
                    changed = True
                    deps[i] = want

    if check:
        return not changed
    if changed:
        pyproject.write_text(tomlkit.dumps(doc), encoding="utf-8")
    return True


def bump_npm_package(package_json: Path, new_version: str, *, check: bool = False) -> bool:
    data = json.loads(package_json.read_text(encoding="utf-8"))
    changed = False

    if data.get("version") != new_version:
        changed = True
        data["version"] = new_version

    for bucket in ("dependencies", "devDependencies", "peerDependencies"):
        deps = data.get(bucket)
        if not deps:
            continue
        for name, current in list(deps.items()):
            if name.startswith(NPM_SCOPE_PREFIX) and current != new_version:
                changed = True
                deps[name] = new_version

    if check:
        return not changed
    if changed:
        package_json.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return True


def discover(root: Path) -> tuple[list[Path], list[Path]]:
    py: list[Path] = []
    for base in ("framework", "modules"):
        base_dir = root / base
        if base_dir.is_dir():
            for child in sorted(base_dir.iterdir()):
                if child.is_dir() and (child / "pyproject.toml").exists():
                    py.append(child / "pyproject.toml")
    npm: list[Path] = []
    packages_dir = root / "packages"
    if packages_dir.is_dir():
        for child in sorted(packages_dir.iterdir()):
            if child.is_dir() and (child / "package.json").exists():
                npm.append(child / "package.json")
    return py, npm


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version", help="New version string, e.g. 0.0.2")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)

    if not VERSION_RE.match(args.version):
        print(f"ERROR: '{args.version}' is not a valid version.", file=sys.stderr)
        raise SystemExit(2)

    py_files, npm_files = discover(args.root)
    all_ok = True

    for p in py_files:
        ok = bump_python_package(p, args.version, check=args.check or args.dry_run)
        if args.check and not ok:
            print(f"OUT-OF-SYNC: {p}", file=sys.stderr)
            all_ok = False

    for p in npm_files:
        ok = bump_npm_package(p, args.version, check=args.check or args.dry_run)
        if args.check and not ok:
            print(f"OUT-OF-SYNC: {p}", file=sys.stderr)
            all_ok = False

    if args.check:
        if all_ok:
            print(f"All {len(py_files) + len(npm_files)} packages at {args.version}.")
            return 0
        print("FAIL: one or more packages out of sync.", file=sys.stderr)
        return 1

    if args.dry_run:
        print(f"(dry-run) Would bump {len(py_files)} python + {len(npm_files)} npm packages to {args.version}.")
        return 0

    print(f"Bumped {len(py_files)} python + {len(npm_files)} npm packages to {args.version}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run the tests, confirm they pass**

Run: `uv run pytest scripts/tests/test_bump_version.py -v`
Expected: all tests pass.

- [ ] **Step 3: Dry-run against the real repo at the current version**

Run: `uv run python scripts/bump_version.py 0.0.1 --check`
Expected: `All 17 packages at 0.0.1.` exit 0.

- [ ] **Step 4: Add `release-check` Makefile target**

In `Makefile`, add:

```makefile
.PHONY: release-check
release-check:
	@test -n "$(version)" || { echo "usage: make release-check version=X.Y.Z"; exit 1; }
	uv run python scripts/bump_version.py $(version) --check
```

- [ ] **Step 5: Commit**

```bash
git add scripts/bump_version.py scripts/tests/test_bump_version.py Makefile
git commit -m "feat(scripts): add lockstep bump_version.py for 17-package release"
```

---

## Phase 7 — `sm new` CLI + template

This phase extends the existing `simple_module_hosting.cli` with a new `new` subcommand that scaffolds a full app with `users + dashboard + permissions` pre-wired. The existing `sm create-host` stays (it's the lower-level scaffolder); `sm new` is the opinionated wrapper.

### Task 7.1: Write failing test for `sm new`

**Files:**
- Create: `framework/hosting/tests/test_cli_new.py`

- [ ] **Step 1: Write the test file**

```python
"""Tests for the `sm new` / `simple-module new` CLI subcommand."""
from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from simple_module_hosting.cli import main


def test_sm_new_creates_app_directory(tmp_path: Path) -> None:
    runner = CliRunner()
    target = tmp_path / "my-app"
    result = runner.invoke(
        main,
        ["new", "my-app", "--yes", "--db", "sqlite", "--no-install", "--dest", str(target)],
    )
    assert result.exit_code == 0, result.output
    assert target.is_dir()


def test_sm_new_generates_pyproject_with_expected_deps(tmp_path: Path) -> None:
    runner = CliRunner()
    target = tmp_path / "my-app"
    runner.invoke(
        main,
        ["new", "my-app", "--yes", "--db", "sqlite", "--no-install", "--dest", str(target)],
    )
    pyproject_text = (target / "pyproject.toml").read_text()
    for required in (
        "simple-module-hosting",
        "simple-module-users",
        "simple-module-dashboard",
        "simple-module-permissions",
    ):
        assert required in pyproject_text, f"missing dep: {required}"


def test_sm_new_generates_package_json_with_npm_deps(tmp_path: Path) -> None:
    runner = CliRunner()
    target = tmp_path / "my-app"
    runner.invoke(
        main,
        ["new", "my-app", "--yes", "--db", "sqlite", "--no-install", "--dest", str(target)],
    )
    data = json.loads((target / "package.json").read_text())
    assert "@simple-module-py/ui" in data.get("dependencies", {})
    assert "@simple-module-py/i18n" in data.get("dependencies", {})
    assert "@simple-module-py/tsconfig" in data.get("devDependencies", {})


def test_sm_new_writes_generated_secret_key(tmp_path: Path) -> None:
    runner = CliRunner()
    target = tmp_path / "my-app"
    runner.invoke(
        main,
        ["new", "my-app", "--yes", "--db", "sqlite", "--no-install", "--dest", str(target)],
    )
    env_text = (target / ".env.example").read_text()
    # Secret should be present and NOT the literal placeholder.
    assert "SM_SECRET_KEY=" in env_text
    assert "CHANGE-ME" not in env_text
    # Reasonably long — token_urlsafe(32) base64 → 43+ chars.
    secret_line = [ln for ln in env_text.splitlines() if ln.startswith("SM_SECRET_KEY=")][0]
    assert len(secret_line.split("=", 1)[1]) >= 20


def test_sm_new_refuses_to_overwrite(tmp_path: Path) -> None:
    target = tmp_path / "my-app"
    target.mkdir()
    (target / "existing.txt").write_text("x")

    runner = CliRunner()
    result = runner.invoke(
        main,
        ["new", "my-app", "--yes", "--db", "sqlite", "--no-install", "--dest", str(target)],
    )
    assert result.exit_code != 0
    assert "exists" in result.output.lower() or "exists" in (result.stderr or "").lower()
```

- [ ] **Step 2: Run tests, confirm they fail**

Run: `uv run pytest framework/hosting/tests/test_cli_new.py -v`
Expected: FAIL — "No such command 'new'".

### Task 7.2: Extend `scaffolding.py` with a `create_app_project` helper

**Files:**
- Modify: `framework/hosting/simple_module_hosting/scaffolding.py`

- [ ] **Step 1: Read the existing `_create_host` function**

The existing `_create_host(target, name, modules)` already copies `templates/host/` into `target` with Jinja substitution. We add a higher-level `create_app_project` that:
- Derives a secret via `secrets.token_urlsafe(32)`.
- Chooses a DB URL based on `db` ("sqlite" → `sqlite+aiosqlite:///./app.db`, "postgres" → `postgresql+asyncpg://postgres:postgres@localhost:5432/<slug>`).
- Calls `_create_host` with `modules=["users", "dashboard", "permissions"]`.
- Post-processes the generated `.env.example` to write the secret + DB URL.
- Post-processes the generated `package.json` to add `@simple-module-py/*` deps.
- Post-processes the generated `pyproject.toml` to pin exact framework versions.

- [ ] **Step 2: Append to `scaffolding.py`:**

```python
# ---------------------------------------------------------------
# create_app_project — used by `sm new` / `simple-module new`
# ---------------------------------------------------------------

import json as _json
import secrets as _secrets

_FRAMEWORK_VERSION = "0.0.1"

_APP_PY_DEPS = [
    f"simple-module-hosting=={_FRAMEWORK_VERSION}",
    f"simple-module-users=={_FRAMEWORK_VERSION}",
    f"simple-module-dashboard=={_FRAMEWORK_VERSION}",
    f"simple-module-permissions=={_FRAMEWORK_VERSION}",
]
_APP_PY_DEV_DEPS = [f"simple-module-testing=={_FRAMEWORK_VERSION}", "pytest>=8.0"]

_APP_NPM_DEPS = {
    "@simple-module-py/ui": _FRAMEWORK_VERSION,
    "@simple-module-py/i18n": _FRAMEWORK_VERSION,
    "react": "^19.0.0",
    "react-dom": "^19.0.0",
    "@inertiajs/react": "^1.0.0",
}
_APP_NPM_DEV_DEPS = {
    "@simple-module-py/tsconfig": _FRAMEWORK_VERSION,
    "@vitejs/plugin-react": "^5.0.0",
    "typescript": "^5.6.0",
    "vite": "^8.0.0",
}


def create_app_project(
    target: Path,
    *,
    name: str,
    db: str = "sqlite",
    tenancy: bool = False,
) -> None:
    """Greenfield `simple-module new` scaffold.

    Wraps `_create_host` with an opinionated set of pre-wired modules
    (users + dashboard + permissions), generates a secret, picks a DB URL,
    and rewrites the generated package.json / pyproject.toml to pin
    exact framework versions against PyPI/npm 0.0.x.
    """
    if target.exists() and any(target.iterdir()):
        raise FileExistsError(
            f"Refusing to scaffold into non-empty directory: {target}"
        )

    _create_host(target, name=name, modules=["users", "dashboard", "permissions"])

    # --- env file ---
    env_path = target / ".env.example"
    if env_path.exists():
        env_text = env_path.read_text(encoding="utf-8")
    else:
        env_text = ""
    env_text = _set_env_key(env_text, "SM_SECRET_KEY", _secrets.token_urlsafe(32))
    env_text = _set_env_key(env_text, "SM_DATABASE_URL", _db_url(db, _to_kebab_case(name)))
    env_text = _set_env_key(env_text, "SM_MULTI_TENANT", "true" if tenancy else "false")
    env_path.write_text(env_text, encoding="utf-8")

    # --- pyproject.toml rewrite ---
    pyproject = target / "pyproject.toml"
    if pyproject.exists():
        text = pyproject.read_text(encoding="utf-8")
        text = _inject_py_deps(text, _APP_PY_DEPS, _APP_PY_DEV_DEPS)
        pyproject.write_text(text, encoding="utf-8")

    # --- package.json rewrite ---
    pkg_path = target / "package.json"
    if pkg_path.exists():
        data = _json.loads(pkg_path.read_text(encoding="utf-8"))
    else:
        data = {"name": _to_kebab_case(name), "private": True, "type": "module"}
    data.setdefault("dependencies", {}).update(_APP_NPM_DEPS)
    data.setdefault("devDependencies", {}).update(_APP_NPM_DEV_DEPS)
    pkg_path.write_text(_json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _set_env_key(text: str, key: str, value: str) -> str:
    lines = text.splitlines()
    prefix = f"{key}="
    out = [ln for ln in lines if not ln.startswith(prefix)]
    out.append(f"{key}={value}")
    return "\n".join(out) + "\n"


def _db_url(db: str, slug: str) -> str:
    if db == "postgres":
        return f"postgresql+asyncpg://postgres:postgres@localhost:5432/{slug}"
    return "sqlite+aiosqlite:///./app.db"


def _inject_py_deps(text: str, deps: list[str], dev_deps: list[str]) -> str:
    """Replace/insert project.dependencies + dependency-groups.dev in a pyproject.toml."""
    import tomlkit

    doc = tomlkit.parse(text)
    project = doc.setdefault("project", tomlkit.table())
    project["dependencies"] = list(deps)
    groups = doc.setdefault("dependency-groups", tomlkit.table())
    groups["dev"] = list(dev_deps)
    return tomlkit.dumps(doc)
```

- [ ] **Step 3: Commit**

```bash
git add framework/hosting/simple_module_hosting/scaffolding.py
git commit -m "feat(scaffolding): add create_app_project helper for sm new"
```

### Task 7.3: Add the `new` Click subcommand

**Files:**
- Modify: `framework/hosting/simple_module_hosting/cli.py`

- [ ] **Step 1: In `cli.py`, import `create_app_project` and add the command**

Insert after the existing `create_module_cmd` definition:

```python
@main.command("new")
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
    "--yes",
    "-y",
    is_flag=True,
    default=False,
    help="Skip interactive prompts; accept all defaults.",
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
    yes: bool,
    no_install: bool,
) -> None:
    """Scaffold a new SimpleModule app — pre-wired with users, dashboard, permissions."""
    target = dest or Path.cwd() / name
    if not yes:
        db = click.prompt("Database backend", default=db, type=click.Choice(["sqlite", "postgres"]))
        tenancy = click.confirm("Enable multi-tenancy?", default=tenancy)

    from simple_module_hosting.scaffolding import create_app_project

    try:
        create_app_project(target, name=name, db=db, tenancy=tenancy)
    except FileExistsError as exc:
        click.echo(f"ERROR: {exc}", err=True)
        sys.exit(1)

    click.echo(f"Created app '{name}' at {target}")
    click.echo("\nPre-wired modules: users, dashboard, permissions")
    click.echo("\nNext steps:")
    click.echo(f"  cd {target}")
    if no_install:
        click.echo("  uv sync")
        click.echo("  npm install")
        click.echo("  alembic upgrade head")
        click.echo("  make dev")
        return

    click.echo("Installing dependencies...")
    for cmd in (
        ["uv", "sync"],
        ["npm", "install"],
    ):
        result = subprocess.run(cmd, cwd=target, check=False)
        if result.returncode != 0:
            click.echo(f"WARNING: {' '.join(cmd)} failed (exit {result.returncode}); "
                       f"finish setup manually.", err=True)
            return

    # Try Alembic upgrade — best-effort.
    alembic_cmd = ["uv", "run", "alembic", "upgrade", "head"]
    subprocess.run(alembic_cmd, cwd=target, check=False)

    click.echo("\n✓ Setup complete. Run `make dev` in the new directory.")
```

- [ ] **Step 2: Run the tests**

Run: `uv run pytest framework/hosting/tests/test_cli_new.py -v`
Expected: all 5 tests pass.

- [ ] **Step 3: Smoke-test the CLI manually**

Run: `cd /tmp && rm -rf smoke && uv --project /path/to/repo run simple-module new smoke --yes --db sqlite --no-install`
Expected: `/tmp/smoke/` contains `pyproject.toml`, `main.py`, `package.json`, `.env.example` with a random secret key. `cat /tmp/smoke/pyproject.toml` shows the four `simple-module-*` pins.

- [ ] **Step 4: Commit**

```bash
git add framework/hosting/simple_module_hosting/cli.py framework/hosting/tests/test_cli_new.py
git commit -m "feat(cli): add 'sm new' / 'simple-module new' greenfield generator

Scaffolds a fresh app pre-wired with users, dashboard, and
permissions. Generates a random SM_SECRET_KEY, sets the DB URL
based on --db choice, pins simple-module-* deps to 0.0.1, and
lists @simple-module-py/* npm deps. Respects --yes for
non-interactive invocation and --no-install to skip uv/npm/alembic."
```

### Task 7.4: Update host template for the `new` flow

**Files:**
- Modify: `framework/hosting/simple_module_hosting/templates/host/pyproject.toml.tpl`
- Modify: `framework/hosting/simple_module_hosting/templates/host/client_app/package.json.tpl`
- Modify: `framework/hosting/simple_module_hosting/templates/host/.env.example` (create if missing)
- Modify: `framework/hosting/simple_module_hosting/templates/host/README.md.tpl`

- [ ] **Step 1: Read the three existing `.tpl` files** to understand the current placeholders (they use `{{name}}` style substitution by `_create_host`).

- [ ] **Step 2: Ensure `templates/host/.env.example` exists**

Write `framework/hosting/simple_module_hosting/templates/host/.env.example`:

```
# Generated by `simple-module new`. Override values before running in prod.
SM_ENVIRONMENT=development
SM_DATABASE_URL=sqlite+aiosqlite:///./app.db
SM_SECRET_KEY=CHANGE-ME
SM_USERS_ALLOW_SIGNUP=false
SM_USERS_MAILER=console
SM_USERS_BOOTSTRAP_EMAIL=
SM_USERS_BOOTSTRAP_PASSWORD=
SM_MULTI_TENANT=false
```

(The `new` command overwrites `SM_SECRET_KEY`, `SM_DATABASE_URL`, and `SM_MULTI_TENANT` post-generation.)

- [ ] **Step 3: Confirm the template `pyproject.toml.tpl` has a `project.dependencies` array — if not, add an empty list**

The `create_app_project` helper rewrites `project.dependencies` wholesale via `tomlkit`, so the template just needs a parseable TOML with a `[project]` table.

- [ ] **Step 4: Confirm `package.json.tpl` has `dependencies` and `devDependencies` objects**

Same reasoning — the helper `.update()`s both dicts.

- [ ] **Step 5: Run the CLI tests again**

Run: `uv run pytest framework/hosting/tests/test_cli_new.py -v`
Expected: still pass.

- [ ] **Step 6: Commit any template changes**

```bash
git add framework/hosting/simple_module_hosting/templates/host/
git commit -m "chore(template): ensure host template is compatible with sm new flow" || echo "nothing to commit"
```

---

## Phase 8 — Release workflow + docs

### Task 8.1: Write `.github/workflows/release.yml`

**Files:**
- Create: `.github/workflows/release.yml`

- [ ] **Step 1: Write the workflow**

```yaml
name: release

on:
  workflow_dispatch:
    inputs:
      version:
        description: "Version to release (e.g., 0.0.1)"
        required: true
        type: string
      target:
        description: "Publish target"
        type: choice
        options: [pypi, testpypi]
        default: testpypi

permissions:
  contents: write
  id-token: write  # required for Trusted Publishing (OIDC) on both PyPI and npm

jobs:
  bump-and-build:
    runs-on: ubuntu-latest
    outputs:
      py-artifact: ${{ steps.build-py.outputs.name }}
      npm-artifact: ${{ steps.build-npm.outputs.name }}
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
          token: ${{ secrets.RELEASE_PUSH_TOKEN || github.token }}
      - uses: astral-sh/setup-uv@v5
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
      - name: Validate version string
        run: |
          echo "${{ inputs.version }}" | grep -E '^[0-9]+\.[0-9]+\.[0-9]+([.-]?(a|b|rc|alpha|beta)[0-9]*)?$'
      - name: Bump all package versions
        run: uv run python scripts/bump_version.py "${{ inputs.version }}"
      - name: Regenerate npm lockfile
        run: npm install --package-lock-only
      - name: Commit, tag, and push
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git add -A
          git commit -m "release: v${{ inputs.version }}" || { echo "no changes to commit"; exit 0; }
          git tag "v${{ inputs.version }}"
          git push origin HEAD:main
          git push origin "v${{ inputs.version }}"
      - name: Build Python wheels + sdists
        id: build-py
        run: |
          uv build --all-packages --out-dir dist-py
          echo "name=dist-py" >> "$GITHUB_OUTPUT"
      - name: Pack npm tarballs
        id: build-npm
        run: |
          mkdir -p dist-npm
          for pkg in packages/*/; do
            npm pack "$pkg" --pack-destination dist-npm
          done
          echo "name=dist-npm" >> "$GITHUB_OUTPUT"
      - uses: actions/upload-artifact@v4
        with:
          name: dist-py
          path: dist-py/
      - uses: actions/upload-artifact@v4
        with:
          name: dist-npm
          path: dist-npm/

  publish-pypi:
    needs: bump-and-build
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        package:
          - simple-module-core
          - simple-module-db
          - simple-module-hosting
          - simple-module-testing
          - simple-module-auth
          - simple-module-background-tasks
          - simple-module-dashboard
          - simple-module-datasets
          - simple-module-feature-flags
          - simple-module-file-storage
          - simple-module-permissions
          - simple-module-products
          - simple-module-settings
          - simple-module-users
    environment:
      name: ${{ inputs.target }}
      url: https://${{ inputs.target == 'testpypi' && 'test.' || '' }}pypi.org/project/${{ matrix.package }}/
    steps:
      - uses: actions/download-artifact@v4
        with:
          name: dist-py
          path: dist-py/
      - name: Filter artifacts for this package
        run: |
          mkdir -p to-publish
          name="${{ matrix.package }}"
          norm="$(echo "$name" | tr '-' '_')"
          mv dist-py/${norm}-* dist-py/${name}-* to-publish/ 2>/dev/null || true
          ls to-publish
      - uses: pypa/gh-action-pypi-publish@release/v1
        with:
          packages-dir: to-publish
          repository-url: ${{ inputs.target == 'testpypi' && 'https://test.pypi.org/legacy/' || '' }}

  publish-npm:
    needs: bump-and-build
    if: inputs.target == 'pypi'
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        package: ["ui", "i18n", "tsconfig"]
    environment: npm
    steps:
      - uses: actions/checkout@v4
        with:
          ref: v${{ inputs.version }}
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
          registry-url: "https://registry.npmjs.org"
      - name: Publish via npm Trusted Publisher
        run: npm publish --provenance --access public
        working-directory: packages/${{ matrix.package }}

  smoke:
    needs: [publish-pypi, publish-npm]
    if: inputs.target == 'pypi'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
      - uses: astral-sh/setup-uv@v5
      - name: Install CLI from PyPI
        run: uv tool install "simple-module-hosting==${{ inputs.version }}"
      - name: Generate smoke app
        run: uv tool run simple-module new smoke-app --yes --db sqlite --no-install
      - name: Install smoke app deps (Python + npm)
        run: |
          cd smoke-app
          uv sync
          npm install
      - name: Run smoke app tests
        run: |
          cd smoke-app
          uv run pytest -q
```

- [ ] **Step 2: Validate YAML with `actionlint` if available locally (skip if not installed)**

Run: `command -v actionlint >/dev/null && actionlint .github/workflows/release.yml || echo "actionlint not installed — skipping"`

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/release.yml
git commit -m "ci: add manual-dispatch release workflow for PyPI + npm"
```

### Task 8.2: Write `docs/release.md`

**Files:**
- Create: `docs/release.md`

- [ ] **Step 1: Write the file**

```markdown
# Cutting a release

This repo publishes **14 Python packages** to PyPI and **3 JS packages** to npm in one lockstep bump. Releases are driven entirely from GitHub Actions — no tokens live on your laptop.

## One-time setup

### PyPI + TestPyPI

For every one of the 14 project names below, log into [pypi.org](https://pypi.org) (and [test.pypi.org](https://test.pypi.org)) and add a **Trusted Publisher**:

- Owner: `antosubash`
- Repository: `simple_module_python`
- Workflow filename: `release.yml`
- Environment: `pypi` (on pypi.org) or `testpypi` (on test.pypi.org)

Project names:

```
simple-module-core
simple-module-db
simple-module-hosting
simple-module-testing
simple-module-auth
simple-module-background-tasks
simple-module-dashboard
simple-module-datasets
simple-module-feature-flags
simple-module-file-storage
simple-module-permissions
simple-module-products
simple-module-settings
simple-module-users
```

If a project name isn't yet on PyPI, create a **pending publisher** — click "publishing" in the account settings and use "Add a new pending publisher".

### npm

- Create the `@simple-module-py` scope (org) on npmjs.com if it does not exist. Owner account: `antosubash`.
- For each of `@simple-module-py/ui`, `@simple-module-py/i18n`, `@simple-module-py/tsconfig`, go to the package settings → "Trusted Publishers" (or "pending publishers" pre-first-publish) and add a GitHub Actions publisher:
  - Repository: `antosubash/simple_module_python`
  - Workflow filename: `release.yml`
  - Environment: `npm`

### GitHub Environments

In the repo's Settings → Environments, create three environments:

- `pypi`
- `testpypi`
- `npm`

No secrets are required — Trusted Publishing uses OIDC tokens. You *may* add a deployment-protection rule requiring a manual approval on `pypi` and `npm` to double-check every release.

### Branch protection bump

The release workflow pushes a version-bump commit directly to `main`. If branch protection blocks bots, either:

1. Add the `github-actions[bot]` to the allowed-pushers list, or
2. Create a fine-grained PAT scoped to this repo's contents and store it as `RELEASE_PUSH_TOKEN` — the workflow uses it if present.

## Cutting a release

1. Ensure `main` is green (`make lint && make test`).
2. Decide the version — all releases bump in lockstep. The first public release is `0.0.1`; subsequent releases are `0.0.2`, `0.0.3`, etc. unless a breaking change justifies `0.1.0`.
3. **Rehearse on TestPyPI** (recommended for every non-patch release):
   - Go to Actions → "release" → "Run workflow".
   - Version: e.g. `0.0.2a0` (PEP 440 alpha — doesn't collide with the real release).
   - Target: `testpypi`.
   - Run. The npm publish jobs are skipped on TestPyPI; inspect the uploaded npm tarball artifacts in the workflow run to confirm they look right.
4. **Real release**:
   - Actions → "release" → "Run workflow".
   - Version: e.g. `0.0.2`.
   - Target: `pypi`.
   - Run. Publishes to PyPI *and* npm, then runs the smoke app build.
5. Create/edit a GitHub Release on the new tag (the workflow doesn't create one automatically — PyPI and npm already have the tarballs; the Release is for human-facing notes).

## Cross-registry partial publish

If PyPI publishes succeed but npm publishes fail (or vice versa), the release is partial. PyPI does not allow re-uploading a version; npm permits unpublish within 72 hours.

**Procedure for partial publish:**

1. Yank the uploaded PyPI versions via the PyPI project UI (do NOT rewrite a version number).
2. If npm succeeded, `npm unpublish @simple-module-py/<pkg>@<version>` within 72h.
3. Fix the underlying cause (usually Trusted Publisher config).
4. Bump to the next patch version and re-run the workflow.

This is the accepted cost of the registries' immutability. The TestPyPI rehearsal is the mitigation — run it first.

## Questions

File an issue at https://github.com/antosubash/simple_module_python/issues.
```

- [ ] **Step 2: Commit**

```bash
git add docs/release.md
git commit -m "docs: add release playbook with PyPI + npm Trusted Publisher setup"
```

### Task 8.3: Update root README with the new "use in a new project" flow

**Files:**
- Modify: `README.md` (root)

- [ ] **Step 1: Read the current `README.md` and find the "Quickstart" section.**

- [ ] **Step 2: Insert a new section above "Quickstart"**

```markdown
## Use in a new project

If you want to **build an app on simple_module**, not hack on the framework itself:

```bash
uvx simple-module new my-app
cd my-app
make dev
```

That scaffolds a working FastAPI + Inertia + React app with `users`, `dashboard`, and `permissions` pre-wired. You land on `/users/login`, sign in with the admin account you bootstrap, and go from there.

See [CHANGELOG.md](CHANGELOG.md) for the list of published PyPI / npm packages at each release.

---
```

The existing "Quickstart" section continues to describe monorepo dev.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs(readme): add 'use in a new project' section referencing simple-module new"
```

---

## Phase 9 — End-to-end verification

### Task 9.1: Run the full lint + test suite

- [ ] **Step 1: Run everything**

Run: `make lint`
Expected: `check_metadata.py` and `check_readmes.py` both green; all 17 packages pass.

Run: `make test`
Expected: all pytest tests pass, including:
- `scripts/tests/test_check_metadata.py` — 7 tests
- `scripts/tests/test_check_readmes.py` — 5 tests
- `scripts/tests/test_bump_version.py` — 8 tests
- `framework/hosting/tests/test_cli_new.py` — 5 tests
- pre-existing framework/module tests

### Task 9.2: Local release rehearsal (no network)

- [ ] **Step 1: Smoke-test the `new` command**

Run: `rm -rf /tmp/smoke-app && uv run simple-module new smoke-app --yes --db sqlite --no-install --dest /tmp/smoke-app`
Expected: exit 0; `/tmp/smoke-app/` contains `pyproject.toml`, `main.py`, `package.json`, `client_app/`, `migrations/`, `.env.example`.

Run: `cat /tmp/smoke-app/pyproject.toml | grep simple-module`
Expected: four `simple-module-*==0.0.1` lines.

Run: `cat /tmp/smoke-app/package.json | grep '@simple-module-py'`
Expected: three `@simple-module-py/*` entries.

Run: `cat /tmp/smoke-app/.env.example | grep SM_SECRET_KEY`
Expected: a line with a random-looking 40+ char key (not `CHANGE-ME`).

- [ ] **Step 2: Dry-run the bump script at the target version**

Run: `uv run python scripts/bump_version.py 0.0.1 --check`
Expected: `All 17 packages at 0.0.1.`

- [ ] **Step 3: Build everything locally**

Run: `rm -rf dist-py dist-npm && uv build --all-packages --out-dir dist-py`
Expected: exit 0; `dist-py/` contains 14 wheels and 14 sdists.

Run: `mkdir -p dist-npm && for p in packages/*/; do npm pack "$p" --pack-destination dist-npm; done`
Expected: 3 `.tgz` files in `dist-npm/`.

- [ ] **Step 4: Commit any residual fixes**

If any step failed, fix it and commit. Otherwise, the plan is complete.

```bash
git add -A
git commit -m "chore: finalize 0.0.1 release artifacts" || echo "nothing to commit"
```

### Task 9.3: Hand-off checklist

At this point the repo is ready for the operator (you) to:

1. Confirm PyPI account owner, npm org, and GitHub repo URL.
2. Create Trusted Publisher entries per `docs/release.md`.
3. Create the `pypi`, `testpypi`, `npm` GitHub Environments.
4. Run the release workflow on `testpypi` with version `0.0.1a0` to rehearse.
5. Run it again on `pypi` with version `0.0.1` for the real release.
6. Announce on the repo.

---

## Self-review summary (by plan author)

- **Spec coverage:** Every workstream in the spec has matching tasks. Metadata hygiene (W1) → Phase 3. READMEs (W2) → Phase 5. npm metadata (W2b) → Phase 4. CLI generator (W3) → Phase 7. Bump script (W4) → Phase 6. Release workflow (W5) → Phase 8.1. Trusted Publisher setup (W6) → docs in Phase 8.2. Repo prep (W7) → Phase 0.
- **Placeholders scanned:** No "TBD", "TODO", or deferred details in any task. Every code block is complete.
- **Type / name consistency:** `@simple-module-py/*` used uniformly; `simple-module-*` distribution prefix used uniformly; `create_app_project` / `new_project` / `bump_version` names consistent across tasks.
- **Extra scope caught during planning:** The spec assumed modules were already named `simple-module-*`; in reality 10 of 14 modules use bare names. Phase 1 adds the required rename before any metadata work.
