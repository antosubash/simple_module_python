# Out-of-tree Module JS/CSS DX Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the frontend half of a standalone module repo work out of the box: correct tsconfig/npm setup, a `smpy module verify` command that proves the module's TSX + CSS compile against a real scaffolded host, and a `smpy module build` command for `static_mounts()` assets.

**Architecture:** Extend `framework/cli/simple_module_cli` — variant-aware module templates (standalone overlay under `templates/module/_optional/standalone/`), plus a new `smpy module` Typer group whose commands share a cached ephemeral host at `.smpy/verify-host/` scaffolded from the existing `create-host` templates. Spec: `docs/superpowers/specs/2026-08-06-out-of-tree-frontend-dx-design.md`.

**Tech Stack:** Python 3.12, Typer, uv, npm, Vite, TypeScript. No new Python or JS dependencies.

## Global Constraints

- 300-line cap on `.py`/`.ts`/`.tsx` files (`scripts/check_file_size.py` in CI).
- Test files need globally-unique basenames (no `__init__.py` in tests dirs).
- All new CLI code lives in `framework/cli/simple_module_cli/` — framework code must not import from `modules/*` (SM009).
- Lint gate: `uv run ruff format . && uv run ruff check . && uv run ty check` must pass; full gate is `make lint`.
- Root pytest config sets `asyncio_mode=auto` and excludes `-m 'not e2e and not perf'` by default.
- When checking exit codes in shell, redirect output to a file — never pipe into `grep`/`head` (the pipe's status masks the real one).
- Worktree bootstrap (already done if tests pass): `uv sync --all-packages && npm install && make gen-pages`.
- Template placeholders use `{{NAME}}` substitution via `_apply_template_files` (`scaffolding.py:135`); `.tpl` suffix is stripped, non-`.tpl` files are copied verbatim.

## Reference: existing code you will touch

- `framework/cli/simple_module_cli/scaffolding.py` — `create_module(dest, name, template_root=None, *, framework_version=None, include_ci=True)`, `create_host(dest, name, modules, template_root=None, framework_version="*", *, preserve_existing=...)`, `_apply_template_files`, `_resolve_template_root`, `_should_pin_framework_version`.
- `framework/cli/simple_module_cli/cli.py` — `create-module` command (line ~86) computes `include_ci = standalone or not is_inside_existing_repo(target)`.
- `framework/cli/simple_module_cli/app_project.py:198` — calls `create_module(..., include_ci=False)`.
- `framework/cli/simple_module_cli/pins.py` — `resolve_framework_version() -> str`, `pin_framework_deps(pyproject_path, version)` (pins every `simple_module_*` dep to `==version`, including optional-dependency extras).
- `framework/cli/simple_module_cli/templates/module/` — the module scaffold templates.
- `framework/cli/simple_module_cli/templates/host/` — the host scaffold templates. A scaffolded host runs gen-pages as `uv run python -m simple_module_hosting gen-pages --host-dir=client_app` (see its `Makefile`), and its `client_app/package.json.tpl` pins `@simple-module-py/*` npm deps to `{{FRAMEWORK_VERSION}}`.
- `framework/cli/tests/` — existing test style: plain async test methods in classes, `tmp_path`, direct imports from `simple_module_cli.*` inside the test.

---

### Task 1: Fix the module tsconfig for both real audiences + `{{FRAMEWORK_VERSION}}` substitution in `create_module`

The current `templates/module/tsconfig.json.tpl` maps `@simple-module-py/ui/*` to `../../packages/ui/src/*` — that path only exists in the framework monorepo (whose own modules are scaffolded by `scripts/new_module.py`, not this CLI). For a `smpy new` workspace the correct path is the hoisted root `node_modules`; the standalone variant comes in Task 2. Also thread `{{FRAMEWORK_VERSION}}` into `create_module`'s substitutions so npm pins can be templated.

**Files:**
- Modify: `framework/cli/simple_module_cli/templates/module/tsconfig.json.tpl`
- Modify: `framework/cli/simple_module_cli/scaffolding.py` (`create_module`)
- Test: `framework/cli/tests/test_scaffolding_module_js.py` (new)

**Interfaces:**
- Consumes: `create_module`, `_apply_template_files` as they exist today.
- Produces: `create_module` renders `{{FRAMEWORK_VERSION}}` in module templates (concrete version when pinning, `"*"` otherwise). Task 2 relies on this.

- [ ] **Step 1: Write the failing test**

Create `framework/cli/tests/test_scaffolding_module_js.py`:

```python
"""Tests for the module scaffold's JS config: tsconfig paths + npm version pins."""

from __future__ import annotations


class TestModuleTsconfig:
    async def test_tsconfig_resolves_ui_from_node_modules(self, tmp_path):
        """In a workspace, @simple-module-py/ui hoists to the root node_modules."""
        from simple_module_cli.scaffolding import create_module

        dest = tmp_path / "simple-module-my-feature"
        create_module(dest, name="MyFeature")

        tsconfig = (dest / "tsconfig.json").read_text(encoding="utf-8")
        assert "../../node_modules/@simple-module-py/ui/src/*" in tsconfig
        assert "packages/ui/src" not in tsconfig


class TestFrameworkVersionSubstitution:
    async def test_concrete_version_renders_in_templates(self, tmp_path):
        from simple_module_cli.scaffolding import create_module

        dest = tmp_path / "simple-module-my-feature"
        create_module(dest, name="MyFeature", framework_version="0.0.27")
        # package.json gains pinned @simple-module-py/* devDeps in Task 2;
        # here we only prove the substitution map carries the version through
        # (the template that uses it lands in Task 2, so assert indirectly on
        # the pyproject pin that create_module already applies).
        pyproject = (dest / "pyproject.toml").read_text(encoding="utf-8")
        assert "simple_module_core==0.0.27" in pyproject

    async def test_wildcard_when_unpinned(self, tmp_path):
        from simple_module_cli.scaffolding import create_module

        dest = tmp_path / "simple-module-my-feature"
        create_module(dest, name="MyFeature")  # framework_version=None
        pyproject = (dest / "pyproject.toml").read_text(encoding="utf-8")
        assert "==None" not in pyproject and "==*" not in pyproject
```

- [ ] **Step 2: Run to verify the tsconfig test fails**

Run: `uv run pytest framework/cli/tests/test_scaffolding_module_js.py -v`
Expected: `test_tsconfig_resolves_ui_from_node_modules` FAILS (template still has `packages/ui/src`); the two substitution tests may already pass (pyproject pinning exists).

- [ ] **Step 3: Fix the template and thread the substitution**

`templates/module/tsconfig.json.tpl` — replace the paths block:

```json
{
  "extends": "@simple-module-py/tsconfig/base.json",
  "compilerOptions": {
    "paths": {
      "@/*": ["./{{PACKAGE_NAME}}/*"],
      "@simple-module-py/ui/*": ["../../node_modules/@simple-module-py/ui/src/*"]
    }
  },
  "include": ["{{PACKAGE_NAME}}/**/*.ts", "{{PACKAGE_NAME}}/**/*.tsx"]
}
```

In `scaffolding.py`'s `create_module`, build the substitutions dict in a local variable and add the version key:

```python
    substitutions = {
        "{{MODULE_NAME}}": display_name,
        "{{MODULE_SLUG}}": slug,
        "{{PACKAGE_NAME}}": package_name,
        "{{PACKAGE_NAME_UPPER}}": package_name.upper(),
        # npm-side pin for @simple-module-py/* devDependencies; "*" when the
        # caller skips pinning (mirrors _should_pin_framework_version).
        "{{FRAMEWORK_VERSION}}": (
            framework_version if _should_pin_framework_version(framework_version) else "*"
        ),
    }
```

and pass `substitutions=substitutions` to `_apply_template_files`.

- [ ] **Step 4: Run tests, verify pass**

Run: `uv run pytest framework/cli/tests/test_scaffolding_module_js.py framework/cli/tests/test_scaffolding_module.py -v`
Expected: all PASS (including pre-existing scaffold tests).

- [ ] **Step 5: Commit**

```bash
git add framework/cli/simple_module_cli/templates/module/tsconfig.json.tpl framework/cli/simple_module_cli/scaffolding.py framework/cli/tests/test_scaffolding_module_js.py
git commit -m "fix(cli): module tsconfig resolves ui from node_modules, not monorepo path"
```

---

### Task 2: Standalone template overlay + `standalone` parameter replacing `include_ci`

Standalone repos need their own `node_modules` path, real devDependencies, and a `typecheck` script. Add an overlay directory `templates/module/_optional/standalone/` (the `_optional/` convention already exists — `_iter_template_files` skips it; `recipes.py` applies such roots explicitly) and replace `create_module`'s `include_ci` parameter with `standalone` (same truth table: standalone ⇒ keep `.github/` ⇒ apply overlay).

**Files:**
- Create: `framework/cli/simple_module_cli/templates/module/_optional/standalone/package.json.tpl`
- Create: `framework/cli/simple_module_cli/templates/module/_optional/standalone/tsconfig.json.tpl`
- Modify: `framework/cli/simple_module_cli/scaffolding.py` (`create_module` signature + overlay application)
- Modify: `framework/cli/simple_module_cli/cli.py` (`create-module` command: pass `standalone=`)
- Modify: `framework/cli/simple_module_cli/app_project.py:198` (`include_ci=False` → `standalone=False`)
- Modify: `framework/cli/tests/test_create_module_ci_skip.py` (rename param in calls)
- Test: extend `framework/cli/tests/test_scaffolding_module_js.py`

**Interfaces:**
- Consumes: `{{FRAMEWORK_VERSION}}` substitution from Task 1.
- Produces: `create_module(dest, name, template_root=None, *, framework_version=None, standalone=True)`. `standalone=True` ⇒ `.github/` kept + overlay applied; `standalone=False` ⇒ `.github/` removed + workspace JS configs kept. Tasks 4, 7 rely on this signature.

- [ ] **Step 1: Write the failing tests**

Append to `framework/cli/tests/test_scaffolding_module_js.py`:

```python
class TestStandaloneOverlay:
    async def test_standalone_tsconfig_uses_local_node_modules(self, tmp_path):
        from simple_module_cli.scaffolding import create_module

        dest = tmp_path / "simple-module-my-feature"
        create_module(dest, name="MyFeature", standalone=True)

        tsconfig = (dest / "tsconfig.json").read_text(encoding="utf-8")
        assert "./node_modules/@simple-module-py/ui/src/*" in tsconfig
        assert "../../node_modules" not in tsconfig

    async def test_standalone_package_json_has_devdeps_and_typecheck(self, tmp_path):
        from simple_module_cli.scaffolding import create_module

        dest = tmp_path / "simple-module-my-feature"
        create_module(dest, name="MyFeature", standalone=True, framework_version="0.0.27")

        pkg = (dest / "package.json").read_text(encoding="utf-8")
        assert '"typecheck": "tsc --noEmit"' in pkg
        assert '"@simple-module-py/ui": "0.0.27"' in pkg
        assert '"@simple-module-py/tsconfig": "0.0.27"' in pkg
        assert '"typescript"' in pkg

    async def test_in_repo_keeps_workspace_configs(self, tmp_path):
        from simple_module_cli.scaffolding import create_module

        dest = tmp_path / "simple-module-my-feature"
        create_module(dest, name="MyFeature", standalone=False)

        tsconfig = (dest / "tsconfig.json").read_text(encoding="utf-8")
        assert "../../node_modules/@simple-module-py/ui/src/*" in tsconfig
        pkg = (dest / "package.json").read_text(encoding="utf-8")
        assert "typecheck" not in pkg
        assert not (dest / ".github").exists()
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest framework/cli/tests/test_scaffolding_module_js.py -v`
Expected: the three new tests FAIL (`standalone` is an unexpected keyword argument).

- [ ] **Step 3: Create the overlay templates**

`templates/module/_optional/standalone/tsconfig.json.tpl`:

```json
{
  "extends": "@simple-module-py/tsconfig/base.json",
  "compilerOptions": {
    "paths": {
      "@/*": ["./{{PACKAGE_NAME}}/*"],
      "@simple-module-py/ui/*": ["./node_modules/@simple-module-py/ui/src/*"]
    }
  },
  "include": ["{{PACKAGE_NAME}}/**/*.ts", "{{PACKAGE_NAME}}/**/*.tsx"]
}
```

`templates/module/_optional/standalone/package.json.tpl` (peerDependencies stay the host-contract; devDependencies make `npm install && npm run typecheck` work in the repo itself):

```json
{
  "name": "@simple-module-py/{{MODULE_SLUG}}",
  "version": "0.1.0",
  "private": true,
  "description": "Frontend assets for the {{MODULE_NAME}} module",
  "scripts": {
    "typecheck": "tsc --noEmit"
  },
  "peerDependencies": {
    "react": "^19.0.0",
    "react-dom": "^19.0.0",
    "@inertiajs/react": "^2.0.0",
    "@simple-module-py/ui": "*"
  },
  "devDependencies": {
    "@inertiajs/react": "^2.0.0",
    "@simple-module-py/i18n": "{{FRAMEWORK_VERSION}}",
    "@simple-module-py/tsconfig": "{{FRAMEWORK_VERSION}}",
    "@simple-module-py/ui": "{{FRAMEWORK_VERSION}}",
    "@types/react": "^19.0.0",
    "@types/react-dom": "^19.0.0",
    "react": "^19.0.0",
    "react-dom": "^19.0.0",
    "typescript": "^5.7.0"
  },
  "dependencies": {}
}
```

- [ ] **Step 4: Rework `create_module`**

In `scaffolding.py`, change the signature and body:

```python
def create_module(
    dest: Path,
    name: str,
    template_root: Path | None = None,
    *,
    framework_version: str | None = None,
    standalone: bool = True,
) -> Path:
```

Docstring: keep the GH #195/#210 paragraphs, reword `include_ci` → `standalone`, and add: *"``standalone=True`` additionally overlays ``_optional/standalone/`` (npm devDependencies + a tsconfig that resolves ``@simple-module-py/ui`` from the repo's own ``node_modules``) so the module type-checks outside a workspace."*

Body (inside the existing `try`, after the base `_apply_template_files` call):

```python
        base_root = _resolve_template_root("module", template_root)
        _apply_template_files(
            base_root,
            dest,
            substitutions=substitutions,
            path_rewrites={_PACKAGE_PATH_TOKEN: package_name},
        )
        if standalone:
            # Overlay standalone-only JS configs over the workspace defaults.
            _apply_template_files(
                base_root / "_optional" / "standalone",
                dest,
                substitutions=substitutions,
                path_rewrites={_PACKAGE_PATH_TOKEN: package_name},
            )
        else:
            shutil.rmtree(dest / ".github", ignore_errors=True)
```

(Note: `_iter_template_files` skips `_optional/` in the base pass, but `base_root / "_optional" / "standalone"` as an explicit root iterates its contents — same pattern as `recipes.py`.)

Update callers:
- `cli.py` `create-module`: rename the local `include_ci` to `standalone_mode = standalone or not is_inside_existing_repo(target)`, pass `standalone=standalone_mode`, keep the "Skipped .github/ workflows" message keyed on `not standalone_mode`.
- `app_project.py:198`: `include_ci=False` → `standalone=False`.
- `framework/cli/tests/test_create_module_ci_skip.py`: update keyword arguments (`include_ci=` → `standalone=`) — behavior assertions stay identical.

- [ ] **Step 5: Run tests, verify pass**

Run: `uv run pytest framework/cli/tests -v 2>&1 | tail -30` — actually, per the exit-code rule: `uv run pytest framework/cli/tests > /tmp/t1.log; echo "exit=$?"; tail -30 /tmp/t1.log`
Expected: exit=0.

- [ ] **Step 6: Commit**

```bash
git add framework/cli/simple_module_cli framework/cli/tests
git commit -m "feat(cli): standalone module scaffold gets working npm/tsconfig setup"
```

---

### Task 3: Sample page + view endpoint in the module template

An empty `pages/` means `tsc --noEmit` fails with TS18003 ("no inputs") and `verify` proves nothing. Ship one real page + view route + menu item so a fresh module demonstrates the whole Inertia loop and gives typecheck/verify actual input. The menu item avoids the SM019 warning (views with no menu/permissions).

**Files:**
- Create: `framework/cli/simple_module_cli/templates/module/__PACKAGE__/pages/Index.tsx.tpl`
- Create: `framework/cli/simple_module_cli/templates/module/__PACKAGE__/endpoints/views.py.tpl`
- Delete: `framework/cli/simple_module_cli/templates/module/__PACKAGE__/pages/.gitkeep`
- Modify: `framework/cli/simple_module_cli/templates/module/__PACKAGE__/module.py.tpl`
- Test: extend `framework/cli/tests/test_scaffolding_module_js.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: every scaffolded module has `<pkg>/pages/Index.tsx` and `<pkg>/endpoints/views.py`; `meta` gains `view_prefix="/{{MODULE_SLUG}}"`. Tasks 4 and 7 (CI + e2e) rely on the page existing.

- [ ] **Step 1: Write the failing test**

```python
class TestSamplePage:
    async def test_scaffold_ships_index_page_and_view(self, tmp_path):
        from simple_module_cli.scaffolding import create_module

        dest = tmp_path / "simple-module-my-feature"
        create_module(dest, name="MyFeature")

        page = (dest / "my_feature" / "pages" / "Index.tsx").read_text(encoding="utf-8")
        assert "PageShell" in page
        views = (dest / "my_feature" / "endpoints" / "views.py").read_text(encoding="utf-8")
        assert '"MyFeature/Index"' in views
        module_py = (dest / "my_feature" / "module.py").read_text(encoding="utf-8")
        assert 'view_prefix="/my-feature"' in module_py
        assert "register_menu_items" in module_py
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest framework/cli/tests/test_scaffolding_module_js.py::TestSamplePage -v`
Expected: FAIL (no `Index.tsx`).

- [ ] **Step 3: Create the templates**

`templates/module/__PACKAGE__/pages/Index.tsx.tpl`:

```tsx
import { Head } from '@inertiajs/react';
import { PageShell } from '@simple-module-py/ui/components/PageShell';

export default function Index() {
  return (
    <PageShell title="{{MODULE_NAME}}" description="Scaffolded by smpy create-module — replace this page.">
      <Head title="{{MODULE_NAME}}" />
      <p className="text-sm text-muted-foreground">
        Edit <code>pages/Index.tsx</code> to build the {{MODULE_NAME}} UI.
      </p>
    </PageShell>
  );
}
```

(`PageShell` props: `title: string`, `description?`, `children` — see `packages/ui/src/components/PageShell.tsx:3`.)

`templates/module/__PACKAGE__/endpoints/views.py.tpl`:

```python
"""Inertia view endpoints for {{MODULE_NAME}} — mounted under ``/{{MODULE_SLUG}}``."""

from __future__ import annotations

from fastapi import APIRouter
from inertia import InertiaResponse
from simple_module_hosting.inertia_deps import InertiaDep

router = APIRouter()

_PAGE_INDEX = "{{MODULE_NAME}}/Index"


@router.get("/", response_model=None)
async def index(inertia: InertiaDep) -> InertiaResponse:
    return await inertia.render(_PAGE_INDEX, {})
```

`module.py.tpl` — three edits:

1. `meta` gains `view_prefix="/{{MODULE_SLUG}}",` (after `route_prefix`).
2. `register_routes` includes the view router:

```python
    def register_routes(self, api_router: APIRouter, view_router: APIRouter) -> None:
        from {{PACKAGE_NAME}}.endpoints.api import router as api
        from {{PACKAGE_NAME}}.endpoints.views import router as views

        api_router.include_router(api)
        view_router.include_router(views)
```

3. Add `register_menu_items` (mirror the import style of `modules/dashboard/dashboard/module.py` — `MenuItem`, `MenuRegistry`, `MenuSection` come from `simple_module_core`; verify the exact import line there before writing):

```python
    def register_menu_items(self, registry: MenuRegistry) -> None:
        registry.add(
            MenuItem(
                label="{{MODULE_NAME}}",
                url="/{{MODULE_SLUG}}",
                order=50,
                section=MenuSection.SIDEBAR,
            )
        )
```

Delete `pages/.gitkeep`.

- [ ] **Step 4: Run scaffold tests, verify pass**

Run: `uv run pytest framework/cli/tests > /tmp/t3.log; echo "exit=$?"; tail -20 /tmp/t3.log`
Expected: exit=0. If `test_creates_expected_module_files` or the module-template import test asserts `pages/.gitkeep`, update it to assert `pages/Index.tsx` instead.

- [ ] **Step 5: Commit**

```bash
git add framework/cli/simple_module_cli/templates/module framework/cli/tests
git commit -m "feat(cli): module scaffold ships a working sample page + view route"
```

---

### Task 4: Standalone CI workflow gets a frontend job; dev extra gains the CLI; `.gitignore` gains `.smpy/`

**Files:**
- Modify: `framework/cli/simple_module_cli/templates/module/.github/workflows/ci.yml`
- Modify: `framework/cli/simple_module_cli/templates/module/pyproject.toml.tpl` (dev extra)
- Modify: `framework/cli/simple_module_cli/templates/module/.gitignore`
- Modify: `framework/cli/simple_module_cli/cli.py` (`create-module` "Next steps" echo)
- Test: extend `framework/cli/tests/test_scaffolding_module_js.py`

**Interfaces:**
- Consumes: `npm run typecheck` (Task 2), sample page (Task 3), `smpy module verify` (Tasks 5–6; the workflow references it by name — fine, it merges before release).
- Produces: scaffolded standalone repos run typecheck + verify in CI.

- [ ] **Step 1: Write the failing test**

```python
class TestStandaloneCi:
    async def test_ci_has_frontend_job_and_dev_extra_has_cli(self, tmp_path):
        from simple_module_cli.scaffolding import create_module

        dest = tmp_path / "simple-module-my-feature"
        create_module(dest, name="MyFeature", standalone=True)

        ci = (dest / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        assert "npm run typecheck" in ci
        assert "smpy module verify" in ci
        pyproject = (dest / "pyproject.toml").read_text(encoding="utf-8")
        assert "simple_module_cli" in pyproject
        gitignore = (dest / ".gitignore").read_text(encoding="utf-8")
        assert ".smpy/" in gitignore
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest framework/cli/tests/test_scaffolding_module_js.py::TestStandaloneCi -v`
Expected: FAIL.

- [ ] **Step 3: Edit the templates**

Append to `ci.yml` (same indent style as the existing `test` job; keep action versions consistent with the file):

```yaml
  frontend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: '22'

      - name: Install uv
        uses: astral-sh/setup-uv@v3
        with:
          version: latest

      - name: Set up Python
        run: uv python install 3.12

      - name: Install project + dev deps
        run: uv sync --extra dev

      # npm install (not ci) so the job works before the first lockfile commit;
      # commit package-lock.json and switch to `npm ci` for reproducible builds.
      - name: Install JS deps
        run: npm install

      - name: Typecheck frontend
        run: npm run typecheck

      # Scaffolds a throwaway host under .smpy/verify-host/ and runs the real
      # Vite + Tailwind build against this module's pages and CSS.
      - name: Verify frontend builds against a scaffolded host
        run: uv run smpy module verify
```

`pyproject.toml.tpl` dev extra — add below `simple_module_test`:

```toml
    # `smpy module verify` / `smpy module build` for out-of-tree frontend work.
    "simple_module_cli>=0.1,<1.0",
```

(`pin_framework_deps` already rewrites `simple_module_*` in extras, so this gets pinned too.)

`.gitignore` — append:

```
# smpy module verify/build cache (throwaway scaffolded host)
.smpy/
```

`cli.py` `create-module` next-steps echo — after the `uv run pytest` line add:

```python
    typer.echo("  npm install")
    typer.echo("  npm run typecheck")
    typer.echo("  uv run smpy module verify")
```

- [ ] **Step 4: Run tests, verify pass**

Run: `uv run pytest framework/cli/tests > /tmp/t4.log; echo "exit=$?"; tail -20 /tmp/t4.log`
Expected: exit=0.

- [ ] **Step 5: Commit**

```bash
git add framework/cli/simple_module_cli framework/cli/tests
git commit -m "feat(cli): standalone module CI typechecks and verifies the frontend"
```

---

### Task 5: `smpy module` group — module introspection + cached verify-host bootstrap

**Files:**
- Create: `framework/cli/simple_module_cli/_module_host.py`
- Create: `framework/cli/simple_module_cli/module_cmd.py`
- Modify: `framework/cli/simple_module_cli/cli.py` (register the group)
- Test: `framework/cli/tests/test_module_cmd_verify.py` (new)

**Interfaces:**
- Consumes: `create_host`, `resolve_framework_version` from `scaffolding.py`.
- Produces (used by Tasks 6–8):
  - `ModuleInfo(root: Path, pypi_name: str, package_name: str)` (frozen dataclass)
  - `read_module_info(root: Path) -> ModuleInfo` — raises `typer.Exit(1)` with a message when `pyproject.toml` is missing or has no `[project.entry-points.simple_module]`
  - `ensure_verify_host(info: ModuleInfo, *, fresh: bool = False) -> Path` — returns `<root>/.smpy/verify-host`
  - `require_binary(name: str) -> str` — `shutil.which` or `typer.Exit(1)`
  - `module_app` — Typer group registered as `smpy module`

- [ ] **Step 1: Write the failing tests**

Create `framework/cli/tests/test_module_cmd_verify.py`:

```python
"""Tests for `smpy module` shared helpers + the verify command orchestration."""

from __future__ import annotations

import subprocess

import pytest
import typer

MODULE_PYPROJECT = """\
[project]
name = "simple_module_my_feature"
version = "0.1.0"

[project.entry-points.simple_module]
my_feature = "my_feature.module:MyFeatureModule"
"""


@pytest.fixture
def module_root(tmp_path):
    (tmp_path / "pyproject.toml").write_text(MODULE_PYPROJECT, encoding="utf-8")
    return tmp_path


class TestReadModuleInfo:
    async def test_reads_names(self, module_root):
        from simple_module_cli._module_host import read_module_info

        info = read_module_info(module_root)
        assert info.pypi_name == "simple_module_my_feature"
        assert info.package_name == "my_feature"
        assert info.root == module_root

    async def test_errors_without_pyproject(self, tmp_path):
        from simple_module_cli._module_host import read_module_info

        with pytest.raises(typer.Exit):
            read_module_info(tmp_path)

    async def test_errors_without_entry_point(self, tmp_path):
        from simple_module_cli._module_host import read_module_info

        (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\nversion='0'\n")
        with pytest.raises(typer.Exit):
            read_module_info(tmp_path)


class TestEnsureVerifyHost:
    async def test_scaffolds_host_and_wires_module_dep(self, module_root):
        from simple_module_cli._module_host import ensure_verify_host, read_module_info

        info = read_module_info(module_root)
        host = ensure_verify_host(info)

        assert host == module_root / ".smpy" / "verify-host"
        pyproject = (host / "pyproject.toml").read_text(encoding="utf-8")
        assert '"simple_module_my_feature"' in pyproject
        assert "[tool.uv.sources]" in pyproject
        assert 'path = "../.."' in pyproject
        assert (host / "client_app" / "package.json").is_file()

    async def test_reuses_existing_host(self, module_root):
        from simple_module_cli._module_host import ensure_verify_host, read_module_info

        info = read_module_info(module_root)
        host = ensure_verify_host(info)
        marker = host / "client_app" / "node_modules_marker"
        marker.write_text("keep me")
        ensure_verify_host(info)  # second call must not re-scaffold
        assert marker.read_text() == "keep me"

    async def test_fresh_rebuilds(self, module_root):
        from simple_module_cli._module_host import ensure_verify_host, read_module_info

        info = read_module_info(module_root)
        host = ensure_verify_host(info)
        marker = host / "stale"
        marker.write_text("x")
        ensure_verify_host(info, fresh=True)
        assert not marker.exists()
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest framework/cli/tests/test_module_cmd_verify.py -v`
Expected: FAIL — `No module named 'simple_module_cli._module_host'`.

- [ ] **Step 3: Implement `_module_host.py`**

```python
"""Shared plumbing for ``smpy module`` commands.

Out-of-tree module repos have no frontend toolchain of their own — the
commands borrow one by scaffolding a throwaway host (via the same templates
as ``smpy create-host``) into ``.smpy/verify-host/`` and caching it there.
"""

from __future__ import annotations

import shutil
import tomllib
from dataclasses import dataclass
from pathlib import Path

import typer

from simple_module_cli.scaffolding import create_host, resolve_framework_version

VERIFY_HOST_RELPATH = Path(".smpy") / "verify-host"


@dataclass(frozen=True)
class ModuleInfo:
    """Identity of the module under the cwd, read from its pyproject."""

    root: Path
    pypi_name: str  # [project].name, e.g. simple_module_my_feature
    package_name: str  # the simple_module entry-point key, e.g. my_feature


def read_module_info(root: Path) -> ModuleInfo:
    pyproject = root / "pyproject.toml"
    if not pyproject.is_file():
        typer.echo(f"error: no pyproject.toml in {root} — run from the module repo root.", err=True)
        raise typer.Exit(code=1)
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    entry_points = data.get("project", {}).get("entry-points", {}).get("simple_module", {})
    if not entry_points:
        typer.echo(
            "error: pyproject.toml declares no [project.entry-points.simple_module] — "
            "this does not look like a SimpleModule module.",
            err=True,
        )
        raise typer.Exit(code=1)
    return ModuleInfo(
        root=root,
        pypi_name=data["project"]["name"],
        package_name=next(iter(entry_points)),
    )


def require_binary(name: str) -> str:
    """Resolve ``name`` on PATH or exit with a clear message (npm on Windows is npm.cmd)."""
    path = shutil.which(name)
    if path is None:
        typer.echo(f"error: '{name}' not found on PATH — install it and retry.", err=True)
        raise typer.Exit(code=1)
    return path


def ensure_verify_host(info: ModuleInfo, *, fresh: bool = False) -> Path:
    """Scaffold (or reuse) the cached verify host; return its directory."""
    host_dir = info.root / VERIFY_HOST_RELPATH
    if fresh and host_dir.exists():
        shutil.rmtree(host_dir)
    if not (host_dir / "pyproject.toml").is_file():
        create_host(
            host_dir,
            name="verify_host",
            modules=[],
            framework_version=resolve_framework_version(),
        )
        _wire_module_dep(host_dir / "pyproject.toml", info.pypi_name)
    return host_dir


def _wire_module_dep(pyproject_path: Path, pypi_name: str) -> None:
    """Add the module as an editable path dependency of the verify host."""
    text = pyproject_path.read_text(encoding="utf-8")
    # Unpinned on purpose: [tool.uv.sources] overrides it with the local path.
    text = text.replace("dependencies = [\n", f'dependencies = [\n    "{pypi_name}",\n', 1)
    text += f'\n[tool.uv.sources]\n{pypi_name} = {{ path = "../..", editable = true }}\n'
    pyproject_path.write_text(text, encoding="utf-8")
```

- [ ] **Step 4: Implement `module_cmd.py` (group skeleton; verify lands in Task 6)**

```python
"""``smpy module`` — commands for developing a module out-of-tree (own repo)."""

from __future__ import annotations

import typer

module_app = typer.Typer(help="Develop a SimpleModule module outside a host repo.")
```

Register in `cli.py` next to the other groups (after the `skills` add_typer):

```python
from simple_module_cli.module_cmd import module_app
...
app.add_typer(module_app, name="module")
```

- [ ] **Step 5: Run tests, verify pass**

Run: `uv run pytest framework/cli/tests/test_module_cmd_verify.py -v`
Expected: PASS. Note: `ensure_verify_host` calls `resolve_framework_version()` which reads the installed dist version — works in the workspace venv; no mocking needed.

- [ ] **Step 6: Commit**

```bash
git add framework/cli/simple_module_cli framework/cli/tests/test_module_cmd_verify.py
git commit -m "feat(cli): smpy module group + cached verify-host bootstrap"
```

---

### Task 6: `smpy module verify`

**Files:**
- Modify: `framework/cli/simple_module_cli/module_cmd.py`
- Test: extend `framework/cli/tests/test_module_cmd_verify.py`

**Interfaces:**
- Consumes: `read_module_info`, `ensure_verify_host`, `require_binary` (Task 5).
- Produces: `run_verify(info: ModuleInfo, *, fresh: bool = False, runner=subprocess.run) -> None` and the `smpy module verify [--fresh]` command. Task 8's e2e calls `run_verify` directly.

- [ ] **Step 1: Write the failing tests**

Append to `test_module_cmd_verify.py`:

```python
class TestRunVerify:
    async def test_runs_steps_in_order_and_succeeds(self, module_root):
        from simple_module_cli._module_host import read_module_info
        from simple_module_cli.module_cmd import run_verify

        calls: list[tuple[str, str]] = []

        def fake_runner(cmd, cwd=None, **kwargs):
            calls.append((" ".join(str(c) for c in cmd), str(cwd)))
            return subprocess.CompletedProcess(cmd, 0)

        run_verify(read_module_info(module_root), runner=fake_runner)

        joined = [c for c, _ in calls]
        assert any("sync" in c for c in joined)
        assert any("npm" in c and "install" in c for c in joined)
        assert any("gen-pages" in c for c in joined)
        assert any("run build" in c for c in joined)
        # order: sync < install < gen-pages < build
        idx = {key: next(i for i, c in enumerate(joined) if key in c)
               for key in ("sync", "install", "gen-pages", "run build")}
        assert idx["sync"] < idx["install"] < idx["gen-pages"] < idx["run build"]
        # npm steps run in client_app, uv steps in the host root
        host = str(module_root / ".smpy" / "verify-host")
        assert calls[idx["sync"]][1] == host
        assert calls[idx["install"]][1] == f"{host}/client_app"

    async def test_failing_step_exits_nonzero_and_stops(self, module_root):
        from simple_module_cli._module_host import read_module_info
        from simple_module_cli.module_cmd import run_verify

        calls = []

        def failing_runner(cmd, cwd=None, **kwargs):
            calls.append(cmd)
            rc = 1 if any("install" in str(c) for c in cmd) else 0
            return subprocess.CompletedProcess(cmd, rc)

        with pytest.raises(typer.Exit) as excinfo:
            run_verify(read_module_info(module_root), runner=failing_runner)
        assert excinfo.value.exit_code == 1
        assert len(calls) == 2  # uv sync + npm install, nothing after the failure
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest framework/cli/tests/test_module_cmd_verify.py::TestRunVerify -v`
Expected: FAIL — `run_verify` not defined.

- [ ] **Step 3: Implement**

In `module_cmd.py`:

```python
import subprocess
from pathlib import Path

from simple_module_cli._module_host import (
    ensure_verify_host,
    read_module_info,
    require_binary,
)


def run_verify(info, *, fresh: bool = False, runner=subprocess.run) -> None:
    """Prove the module's TSX + CSS compile against a real scaffolded host.

    Output streams straight to the terminal (CI logs want the full Vite/tsc
    output); on failure we name the step and exit 1.
    """
    host = ensure_verify_host(info, fresh=fresh)
    client_app = host / "client_app"
    uv, npm = require_binary("uv"), require_binary("npm")
    steps: tuple[tuple[str, list[str], Path], ...] = (
        ("uv sync", [uv, "sync"], host),
        ("npm install", [npm, "install"], client_app),
        (
            "gen-pages",
            [uv, "run", "python", "-m", "simple_module_hosting", "gen-pages", "--host-dir=client_app"],
            host,
        ),
        ("frontend build (tsc + vite)", [npm, "run", "build"], client_app),
    )
    for label, cmd, cwd in steps:
        typer.echo(f"[verify] {label}")
        if runner(cmd, cwd=cwd).returncode != 0:
            typer.echo(f"[verify] FAILED at: {label}", err=True)
            raise typer.Exit(code=1)
    typer.echo("[verify] OK — module frontend builds against a scaffolded host")


@module_app.command("verify")
def verify_command(
    fresh: bool = typer.Option(False, "--fresh", help="Rebuild the cached .smpy/verify-host from scratch."),
) -> None:
    """Build this module's frontend inside a throwaway scaffolded host."""
    run_verify(read_module_info(Path.cwd()), fresh=fresh)
```

- [ ] **Step 4: Run tests, verify pass**

Run: `uv run pytest framework/cli/tests/test_module_cmd_verify.py -v`
Expected: PASS.

- [ ] **Step 5: Smoke the CLI surface**

Run: `uv run smpy module --help > /tmp/t6.log; echo "exit=$?"; cat /tmp/t6.log`
Expected: exit=0, `verify` listed.

- [ ] **Step 6: Commit**

```bash
git add framework/cli/simple_module_cli/module_cmd.py framework/cli/tests/test_module_cmd_verify.py
git commit -m "feat(cli): smpy module verify — build the frontend against a scaffolded host"
```

---

### Task 7: `smpy module build` — lib-mode bundle for `static_mounts()` assets

**Files:**
- Create: `framework/cli/simple_module_cli/_module_build.py`
- Modify: `framework/cli/simple_module_cli/module_cmd.py` (register the command)
- Test: `framework/cli/tests/test_module_cmd_build.py` (new)

**Interfaces:**
- Consumes: `ModuleInfo`, `ensure_verify_host`, `require_binary` (Task 5), `to_pascal_case` from `simple_module_cli.case`.
- Produces: `run_build(info: ModuleInfo, *, fresh: bool = False, runner=subprocess.run) -> None`; convention `<pkg>/assets_src/index.{ts,tsx,js}` → `<pkg>/static/dist/index.js` (+ CSS if imported).

- [ ] **Step 1: Write the failing tests**

Create `framework/cli/tests/test_module_cmd_build.py`:

```python
"""Tests for `smpy module build` — lib-mode bundling of static_mounts assets."""

from __future__ import annotations

import subprocess

import pytest
import typer

MODULE_PYPROJECT = """\
[project]
name = "simple_module_my_feature"
version = "0.1.0"

[project.entry-points.simple_module]
my_feature = "my_feature.module:MyFeatureModule"

[tool.hatch.build.targets.wheel.force-include]
"my_feature/static/dist" = "my_feature/static/dist"
"""


@pytest.fixture
def module_root(tmp_path):
    (tmp_path / "pyproject.toml").write_text(MODULE_PYPROJECT, encoding="utf-8")
    assets = tmp_path / "my_feature" / "assets_src"
    assets.mkdir(parents=True)
    (assets / "index.ts").write_text("export const hello = 'world'\n", encoding="utf-8")
    return tmp_path


def ok_runner(calls):
    def runner(cmd, cwd=None, **kwargs):
        calls.append(([str(c) for c in cmd], str(cwd)))
        return subprocess.CompletedProcess(cmd, 0)

    return runner


class TestRunBuild:
    async def test_errors_without_assets_src(self, tmp_path):
        from simple_module_cli._module_build import run_build
        from simple_module_cli._module_host import read_module_info

        (tmp_path / "pyproject.toml").write_text(MODULE_PYPROJECT, encoding="utf-8")
        with pytest.raises(typer.Exit):
            run_build(read_module_info(tmp_path), runner=ok_runner([]))

    async def test_generates_config_and_runs_vite(self, module_root):
        from simple_module_cli._module_build import run_build
        from simple_module_cli._module_host import read_module_info

        calls = []
        run_build(read_module_info(module_root), runner=ok_runner(calls))

        config = module_root / ".smpy" / "module-build.config.mjs"
        text = config.read_text(encoding="utf-8")
        assert "assets_src/index.ts" in text
        assert "static/dist" in text
        assert "iife" in text
        vite_calls = [c for c, _ in calls if "vite" in " ".join(c)]
        assert vite_calls and "--config" in vite_calls[0]

    async def test_warns_when_force_include_missing(self, module_root, capsys):
        from simple_module_cli._module_build import run_build
        from simple_module_cli._module_host import read_module_info

        stripped = MODULE_PYPROJECT.split("[tool.hatch")[0]
        (module_root / "pyproject.toml").write_text(stripped, encoding="utf-8")
        run_build(read_module_info(module_root), runner=ok_runner([]))
        assert "force-include" in capsys.readouterr().err
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest framework/cli/tests/test_module_cmd_build.py -v`
Expected: FAIL — no `_module_build` module.

- [ ] **Step 3: Implement `_module_build.py`**

```python
"""``smpy module build`` — bundle ``<pkg>/assets_src/`` into ``<pkg>/static/dist/``.

Only for assets served via :meth:`ModuleBase.static_mounts` (vendor JS,
widgets, images). Inertia pages do NOT need this — the consuming host's Vite
build compiles ``pages/*.tsx`` straight from the wheel.

The module repo carries no bundler of its own: we borrow the verify host's
node toolchain (``.smpy/verify-host/client_app``) and point Vite at a
generated lib-mode config.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import typer

from simple_module_cli._module_host import ModuleInfo, ensure_verify_host, require_binary
from simple_module_cli.case import to_pascal_case

_ENTRY_CANDIDATES = ("index.ts", "index.tsx", "index.js")


def run_build(info: ModuleInfo, *, fresh: bool = False, runner=subprocess.run) -> None:
    assets_src = info.root / info.package_name / "assets_src"
    entry = next((assets_src / n for n in _ENTRY_CANDIDATES if (assets_src / n).is_file()), None)
    if entry is None:
        typer.echo(
            f"error: no {assets_src.relative_to(info.root)}/index.(ts|tsx|js) found. "
            "`smpy module build` bundles static_mounts() assets only — Inertia pages "
            "are built by the consuming host and need no bundling.",
            err=True,
        )
        raise typer.Exit(code=1)

    host = ensure_verify_host(info, fresh=fresh)
    client_app = host / "client_app"
    npm = require_binary("npm")
    if not (client_app / "node_modules").is_dir():
        typer.echo("[build] npm install (first run)")
        if runner([npm, "install"], cwd=client_app).returncode != 0:
            typer.echo("[build] FAILED at: npm install", err=True)
            raise typer.Exit(code=1)

    out_dir = info.root / info.package_name / "static" / "dist"
    config_path = info.root / ".smpy" / "module-build.config.mjs"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        _vite_lib_config(entry, out_dir, global_name=to_pascal_case(info.package_name)),
        encoding="utf-8",
    )
    typer.echo(f"[build] vite build → {out_dir.relative_to(info.root)}")
    npx = require_binary("npx")
    if runner([npx, "vite", "build", "--config", str(config_path)], cwd=client_app).returncode != 0:
        typer.echo("[build] FAILED at: vite build", err=True)
        raise typer.Exit(code=1)

    _warn_missing_force_include(info)
    typer.echo("[build] OK")


def _vite_lib_config(entry: Path, out_dir: Path, *, global_name: str) -> str:
    return f"""\
import {{ defineConfig }} from 'vite'

export default defineConfig({{
  build: {{
    lib: {{
      entry: {entry.as_posix()!r},
      formats: ['iife'],
      name: {global_name!r},
      fileName: () => 'index.js',
    }},
    outDir: {out_dir.as_posix()!r},
    emptyOutDir: true,
  }},
}})
"""


def _warn_missing_force_include(info: ModuleInfo) -> None:
    """static/dist is gitignored — without force-include the wheel silently omits it."""
    pyproject = (info.root / "pyproject.toml").read_text(encoding="utf-8")
    if f"{info.package_name}/static/dist" not in pyproject:
        typer.echo(
            "warning: pyproject.toml has no force-include for "
            f'"{info.package_name}/static/dist" — the built bundle will NOT ship in the wheel. '
            "Add under [tool.hatch.build.targets.wheel.force-include]:\n"
            f'  "{info.package_name}/static/dist" = "{info.package_name}/static/dist"',
            err=True,
        )
```

Register in `module_cmd.py`:

```python
@module_app.command("build")
def build_command(
    fresh: bool = typer.Option(False, "--fresh", help="Rebuild the cached .smpy/verify-host from scratch."),
) -> None:
    """Bundle <pkg>/assets_src/ into <pkg>/static/dist/ for static_mounts()."""
    from simple_module_cli._module_build import run_build

    run_build(read_module_info(Path.cwd()), fresh=fresh)
```

- [ ] **Step 4: Run tests, verify pass**

Run: `uv run pytest framework/cli/tests/test_module_cmd_build.py framework/cli/tests/test_module_cmd_verify.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add framework/cli/simple_module_cli framework/cli/tests/test_module_cmd_build.py
git commit -m "feat(cli): smpy module build — bundle static_mounts assets via lib-mode vite"
```

---

### Task 8: End-to-end test (real npm + PyPI, `e2e` marker)

Proves the whole chain: scaffold a standalone module → `run_verify` → green. Uses the *published* framework packages (PyPI + npm at `resolve_framework_version()` — currently 0.0.27, released), while templates + CLI code under test are local. Excluded from default runs by the root `-m 'not e2e and not perf'`.

**Files:**
- Test: `framework/cli/tests/test_module_cmd_e2e.py` (new)

**Interfaces:**
- Consumes: `create_module` (Task 2/3 output), `read_module_info`, `run_verify`.

- [ ] **Step 1: Write the test**

```python
"""End-to-end: scaffold a standalone module and verify its frontend for real.

Needs network (PyPI + npm) and the published framework version matching
``resolve_framework_version()`` — i.e. run it on a released tree. Excluded
from default pytest runs via the ``e2e`` marker.
"""

from __future__ import annotations

import shutil

import pytest

pytestmark = pytest.mark.e2e


@pytest.mark.skipif(shutil.which("npm") is None, reason="npm not installed")
async def test_scaffolded_module_verifies_green(tmp_path):
    from simple_module_cli._module_host import read_module_info
    from simple_module_cli.module_cmd import run_verify
    from simple_module_cli.scaffolding import create_module, resolve_framework_version

    dest = tmp_path / "simple-module-e2e-feature"
    create_module(
        dest,
        name="E2eFeature",
        standalone=True,
        framework_version=resolve_framework_version(),
    )

    run_verify(read_module_info(dest))  # raises typer.Exit(1) on any failure

    client_app = dest / ".smpy" / "verify-host" / "client_app"
    dist = client_app / "static" / "dist"
    assert dist.is_dir() and any(dist.rglob("*.js")), "vite build produced no JS bundle"
```

Note for the implementer: check where the host template's `vite.config.ts` puts `build.outDir` (open `framework/cli/simple_module_cli/templates/host/client_app/vite.config.ts` and search `outDir`) and fix the final assertion's path to match — the build output location is whatever the host template says, not this plan.

- [ ] **Step 2: Run it once for real**

Run: `uv run pytest framework/cli/tests/test_module_cmd_e2e.py -m e2e -v > /tmp/t8.log 2>&1; echo "exit=$?"; tail -40 /tmp/t8.log`
Expected: exit=0 (takes minutes: uv resolve + npm install + vite build). If it fails, the log names the failing step — fix the underlying command wiring, not the test.

- [ ] **Step 3: Verify it's excluded by default**

Run: `uv run pytest framework/cli/tests/test_module_cmd_e2e.py > /tmp/t8b.log; echo "exit=$?"; tail -5 /tmp/t8b.log`
Expected: exit=0 with `deselected` (marker filter active).

- [ ] **Step 4: Commit**

```bash
git add framework/cli/tests/test_module_cmd_e2e.py
git commit -m "test(cli): e2e — scaffolded standalone module verifies green"
```

---

### Task 9: Documentation

**Files:**
- Modify: `docs/module-authoring.md`

- [ ] **Step 1: Rewrite the misleading `static/dist` paragraph**

In the "Frontend assets" section, replace the paragraph beginning "For production builds, ship a pre-bundled `my_module/static/dist`..." with:

```markdown
**Inertia pages never need pre-bundling.** The consuming host's Vite build
compiles `pages/*.tsx` straight out of the installed wheel (via the
`#module/<pkg>` aliases + `server.fs.allow`). `static/dist/` +
`static_mounts()` exist only for assets *outside* that pipeline — vendor JS,
standalone widgets, images. Build them with `smpy module build` (below) and
expose them via `ModuleBase.static_mounts()`:
```

(keep the existing code example that follows).

- [ ] **Step 2: Add a "Developing out-of-tree" section**

Insert after the "Styling" section:

```markdown
## Developing out-of-tree

A module in its own repo has no host around it — these are the three
commands that close the gap. All of them run from the module repo root.

### Type-checking

`smpy create-module` scaffolds a `package.json` whose devDependencies pin
`@simple-module-py/ui`, `@simple-module-py/tsconfig` and `@simple-module-py/i18n`
to the framework version that created the module (all three are published to
npm in lockstep with the PyPI packages), and a `tsconfig.json` that resolves
`@simple-module-py/ui/*` from your own `node_modules`. So:

```bash
npm install          # once; commit package-lock.json and use `npm ci` in CI
npm run typecheck    # tsc --noEmit over your pages
```

### `smpy module verify` — does my frontend actually build?

`tsc` alone cannot tell you whether your pages and `theme.css`/`styles.css`
survive a real host build (Vite import resolution, Tailwind scanning, the
`#module/<pkg>` alias plumbing). `verify` answers that by scaffolding a
throwaway host into `.smpy/verify-host/` (cached, gitignored), installing
your module into it as an editable path dependency, and running the host's
real `gen-pages` + `npm run build`:

```bash
uv run smpy module verify          # warm re-runs reuse the cached host
uv run smpy module verify --fresh  # nuke and rebuild the cached host
```

The scaffolded CI workflow runs it on every push. The verify host pins the
framework version you develop against, so a green verify ≈ your module
building inside a freshly scaffolded host of that version. It needs `uv`,
`npm`, and network access to PyPI + npm on first run.

### `smpy module build` — static_mounts() assets

If (and only if) your module ships assets outside the Inertia page pipeline,
put an entry file at `<pkg>/assets_src/index.ts` and run:

```bash
uv run smpy module build
```

It bundles `assets_src/` into `<pkg>/static/dist/` (IIFE, via the verify
host's Vite toolchain — your repo needs no bundler devDependency). The
scaffolded `pyproject.toml` already force-includes `static/dist` in the
wheel; the command warns if that block has been removed.
```

- [ ] **Step 3: Run the docs-adjacent lint**

Run: `uv run python scripts/check_readmes.py && uv run ruff format --check docs 2>/dev/null; make lint > /tmp/t9.log 2>&1; echo "exit=$?"; tail -20 /tmp/t9.log`
Expected: exit=0.

- [ ] **Step 4: Commit**

```bash
git add docs/module-authoring.md
git commit -m "docs: out-of-tree frontend development — typecheck, verify, build"
```

---

### Task 10: Full gate + wrap-up

- [ ] **Step 1: Full lint + test run**

Run: `make lint > /tmp/gate-lint.log 2>&1; echo "lint=$?"; uv run pytest > /tmp/gate-py.log 2>&1; echo "py=$?"; npm test > /tmp/gate-js.log 2>&1; echo "js=$?"`
Expected: all 0. Investigate any failure via the log files (never trust piped exit codes).

- [ ] **Step 2: Fix anything the gate surfaces, amend/commit**

- [ ] **Step 3: Push branch**

```bash
git push -u origin worktree-out-of-tree-frontend-dx
```

---

## Self-review notes (already applied)

- Spec coverage: scaffold fixes → Tasks 1–4; `verify` → Tasks 5–6; `build` → Task 7; testing → Tasks 1–8; docs → Task 9. The spec's "print the failing step's output" is satisfied by streaming subprocess output (no capture) + naming the failed step.
- The sample page (Task 3) is additive to the spec: without it, `npm run typecheck` fails on an empty scaffold (TS18003) and `verify` verifies nothing — it serves the spec's "green out of the box" requirement.
- Type consistency: `ModuleInfo` fields (`root`/`pypi_name`/`package_name`), `run_verify(info, *, fresh, runner)`, `run_build(info, *, fresh, runner)`, `ensure_verify_host(info, *, fresh)` are used with identical signatures across Tasks 5–8.
- `pin_framework_deps` pins the new `simple_module_cli` dev-extra entry automatically (it rewrites every `simple_module_*` requirement, extras included).
