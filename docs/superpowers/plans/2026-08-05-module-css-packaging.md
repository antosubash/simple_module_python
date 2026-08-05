# Module CSS Packaging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a pip-installed module ship real CSS (design tokens and component
styles) that lands in the host's Tailwind build automatically, with a defined
cascade position and no hand-edited paths.

**Architecture:** A module may ship `<pkg>/theme.css` and `<pkg>/styles.css`,
auto-detected like `pages/`. `smpy gen-pages` emits `@import` lines into
`host/client_app/modules.generated.css` — `theme.css` unlayered (so `@theme`
tokens register) and `styles.css` as `layer(components)` (so module rules can
never beat a utility). Paths are per-module Vite aliases (`#module/<pkg>`) fed
by a new additive `modules.assets.json`, so no generated file contains a
`../../../.venv/...` path.

**Tech Stack:** Python 3.12, FastAPI, Hatch wheels, Vite 8, `@tailwindcss/vite`
4.2.4, Tailwind CSS v4, pytest.

## Global Constraints

- **300-line cap** on `.py`/`.ts`/`.tsx`, enforced by `scripts/check_file_size.py`.
  `manifest.py` is already at 275 lines, so new asset logic goes in a new
  `framework/hosting/simple_module_hosting/assets.py`.
- **SQLModel is the project-wide model standard.** Not relevant here (no models),
  but do not introduce Pydantic `BaseModel` for the asset record — use a
  `dataclass`.
- **No new Python dependencies.** In particular, no CSS parser for the SM022 /
  SM023 lints.
- **`modules.manifest.json` keeps its exact current shape** (`{name: pages_dir}`).
  Downstream apps (`smpy_gis`, `smpy_saas`, `laco_wiki_python`,
  `smpy_pagebuilder`) hold their own copy of `vite.config.ts` and must keep
  building untouched.
- **Alias segment is the lowercase Python package name** (`#module/blog_posts`),
  not `ModuleMeta.name` (`BlogPosts`).
- Diagnostic codes: **SM022**, **SM023**. Existing set stops at SM021.
- Run `make ci-python-lint` rather than `make lint` — `make lint` fails
  repo-wide on a pre-existing invalid `preset` key in `biome.json`.

---

### Task 1: Verify the two load-bearing resolver claims

The spec flags two assumptions as untested. Both change the design if wrong, so
they are checked before any code is written.

**Files:**
- Create (throwaway): `$CLAUDE_JOB_DIR/tmp/css-spike/`

- [ ] **Step 1: Build a minimal Tailwind 4.2.4 spike**

Create a scratch Vite project that imports a CSS file from outside its root via
a `resolve.alias`, and `@source`s a directory by absolute path. Put a class in
the aliased CSS and a utility class in a `.tsx` under the absolute `@source`
dir.

- [ ] **Step 2: Run the build and inspect output CSS**

Confirm two things independently:
1. The aliased `@import` resolved (the module CSS rule appears in output).
2. The absolute `@source` scanned (the utility from that dir appears in output).

- [ ] **Step 3: Record the result**

If the absolute `@source` fails, the `@source` section switches to alias
specifiers too, and Task 3's emission changes accordingly. If the alias
`@import` fails, stop — the design needs revisiting.

- [ ] **Step 4: Note whether `fs.allow` was needed**

Run the dev server against a file outside the root without `fs.allow` and see
whether the CSS still resolves. `@import` is inlined at transform time, so it
may not need whitelisting.

---

### Task 2: Asset discovery — `compute_module_assets`

**Files:**
- Create: `framework/hosting/simple_module_hosting/assets.py`
- Test: `framework/cli/tests/test_module_css_assets.py`

**Interfaces:**
- Consumes: `simple_module_core.get_module_package_name`, `ModuleBase`.
- Produces:
  - `@dataclass(frozen=True) ModuleAssets` with fields
    `name: str`, `package_name: str`, `package_dir: Path`,
    `pages_dir: Path | None`, `theme_css: Path | None`, `styles_css: Path | None`.
  - `compute_module_assets(modules: Sequence[ModuleBase]) -> list[ModuleAssets]`
    — preserves input (discovery) order; includes a module if it has **any** of
    pages/theme/styles.

- [ ] **Step 1: Write the failing test**

```python
"""Tests for module CSS asset discovery and emission."""

from __future__ import annotations


class TestComputeModuleAssets:
    async def test_detects_theme_and_styles(self, tmp_path, monkeypatch):
        """A module shipping theme.css/styles.css has them detected."""
        import sys

        from simple_module_core import ModuleBase, ModuleMeta
        from simple_module_hosting.assets import compute_module_assets

        pkg = tmp_path / "styled_mod"
        (pkg / "pages").mkdir(parents=True)
        (pkg / "theme.css").write_text("@theme { --color-x: red; }\n")
        (pkg / "styles.css").write_text(".x { color: red; }\n")
        (pkg / "__init__.py").write_text("")
        monkeypatch.syspath_prepend(str(tmp_path))
        sys.modules.pop("styled_mod", None)

        module_src = "from simple_module_core import ModuleBase, ModuleMeta\n"
        (pkg / "module.py").write_text(module_src)

        class StyledMod(ModuleBase):
            meta = ModuleMeta(name="Styled")

        # Force the package association the helper resolves against.
        StyledMod.__module__ = "styled_mod.module"

        result = compute_module_assets([StyledMod()])
        assert len(result) == 1
        entry = result[0]
        assert entry.package_name == "styled_mod"
        assert entry.theme_css is not None and entry.theme_css.name == "theme.css"
        assert entry.styles_css is not None and entry.styles_css.name == "styles.css"
        assert entry.pages_dir is not None

    async def test_css_only_module_is_included(self, tmp_path, monkeypatch):
        """A module with CSS but no pages/ still appears (the manifest gap)."""
        import sys

        from simple_module_core import ModuleBase, ModuleMeta
        from simple_module_hosting.assets import compute_module_assets

        pkg = tmp_path / "cssonly_mod"
        pkg.mkdir(parents=True)
        (pkg / "__init__.py").write_text("")
        (pkg / "styles.css").write_text(".y { color: blue; }\n")
        monkeypatch.syspath_prepend(str(tmp_path))
        sys.modules.pop("cssonly_mod", None)

        class CssOnly(ModuleBase):
            meta = ModuleMeta(name="CssOnly")

        CssOnly.__module__ = "cssonly_mod.module"

        result = compute_module_assets([CssOnly()])
        assert [e.name for e in result] == ["CssOnly"]
        assert result[0].pages_dir is None
        assert result[0].styles_css is not None

    async def test_preserves_discovery_order(self):
        """Order follows discover_modules(), not alphabetical."""
        from simple_module_core import discover_modules
        from simple_module_hosting.assets import compute_module_assets

        modules = discover_modules()
        result = compute_module_assets(modules)
        names = [e.name for e in result]
        assert names != sorted(names) or len(names) <= 1
        discovery_order = [m.meta.name for m in modules]
        assert names == [n for n in discovery_order if n in set(names)]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest framework/cli/tests/test_module_css_assets.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'simple_module_hosting.assets'`

- [ ] **Step 3: Write the implementation**

```python
"""Per-module frontend asset discovery (pages + CSS).

Separate from ``manifest.py`` because that file is already at the repo's
300-line cap. ``manifest.py`` imports from here.
"""

from __future__ import annotations

import importlib.resources
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from simple_module_core import ModuleBase, get_module_package_name

logger = logging.getLogger(__name__)

THEME_CSS = "theme.css"
STYLES_CSS = "styles.css"


@dataclass(frozen=True)
class ModuleAssets:
    """Frontend assets a single module contributes."""

    name: str
    package_name: str
    package_dir: Path
    pages_dir: Path | None
    theme_css: Path | None
    styles_css: Path | None


def compute_module_assets(modules: Sequence[ModuleBase]) -> list[ModuleAssets]:
    """Return per-module frontend assets, preserving discovery order.

    Discovery order matters: ``discover_modules()`` topologically sorts by
    ``depends_on``, so emitting CSS in this order lets a dependent module
    override its dependency. A module is included only if it contributes at
    least one asset.
    """
    result: list[ModuleAssets] = []
    for mod in modules:
        pkg_name = get_module_package_name(mod)
        try:
            pkg_root = Path(str(importlib.resources.files(pkg_name)))
        except ModuleNotFoundError:
            logger.debug(
                "Module '%s': package %s not importable — skipping", mod.meta.name, pkg_name
            )
            continue
        pages_dir = pkg_root / "pages"
        theme = pkg_root / THEME_CSS
        styles = pkg_root / STYLES_CSS
        entry = ModuleAssets(
            name=mod.meta.name,
            package_name=pkg_name,
            package_dir=pkg_root.resolve(),
            pages_dir=pages_dir.resolve() if pages_dir.is_dir() else None,
            theme_css=theme.resolve() if theme.is_file() else None,
            styles_css=styles.resolve() if styles.is_file() else None,
        )
        if entry.pages_dir or entry.theme_css or entry.styles_css:
            result.append(entry)
    return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest framework/cli/tests/test_module_css_assets.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add framework/hosting/simple_module_hosting/assets.py framework/cli/tests/test_module_css_assets.py
git commit -m "feat(hosting): discover per-module theme.css/styles.css assets"
```

---

### Task 3: Emit CSS imports and `modules.assets.json`

**Files:**
- Modify: `framework/hosting/simple_module_hosting/assets.py` (add emitters)
- Modify: `framework/hosting/simple_module_hosting/manifest.py` (CSS section + assets file)
- Test: `framework/cli/tests/test_module_css_assets.py`

**Interfaces:**
- Consumes: `ModuleAssets`, `compute_module_assets` from Task 2.
- Produces:
  - `ALIAS_PREFIX = "#module"`
  - `render_modules_css(assets, *, in_repo: Callable[[Path], bool]) -> str`
  - `render_assets_json(assets) -> str`
  - `write_module_pages_manifest` returns an extra `"assets"` key.

- [ ] **Step 1: Write the failing test**

```python
class TestCssEmission:
    async def test_emits_alias_imports_with_no_relative_paths(self, tmp_path):
        """Generated CSS references modules by alias, never by ../.. path."""
        from simple_module_core import discover_modules
        from simple_module_hosting.manifest import write_module_pages_manifest

        modules = discover_modules()
        written = write_module_pages_manifest(modules, tmp_path)
        css = written["css"].read_text(encoding="utf-8")

        import_lines = [ln for ln in css.splitlines() if ln.startswith("@import")]
        for line in import_lines:
            assert "../" not in line, f"generated @import must not use relative paths: {line}"
            assert '"#module/' in line, f"@import must use the alias prefix: {line}"

    async def test_styles_layered_theme_unlayered(self, tmp_path):
        """theme.css imports unlayered; styles.css imports into layer(components)."""
        from simple_module_hosting.assets import ModuleAssets, render_modules_css

        assets = [
            ModuleAssets(
                name="Gis",
                package_name="gis",
                package_dir=tmp_path / "gis",
                pages_dir=None,
                theme_css=tmp_path / "gis" / "theme.css",
                styles_css=tmp_path / "gis" / "styles.css",
            )
        ]
        css = render_modules_css(assets, in_repo=lambda _p: False)

        assert '@import "#module/gis/theme.css";' in css
        assert '@import "#module/gis/styles.css" layer(components);' in css
        # theme must precede styles so tokens exist before rules consume them
        assert css.index("theme.css") < css.index("styles.css")

    async def test_source_skips_in_repo_but_import_does_not(self, tmp_path):
        """@source is wheel-only; @import is emitted for every module."""
        from simple_module_hosting.assets import ModuleAssets, render_modules_css

        assets = [
            ModuleAssets(
                name="Local",
                package_name="local",
                package_dir=tmp_path / "local",
                pages_dir=tmp_path / "local" / "pages",
                theme_css=None,
                styles_css=tmp_path / "local" / "styles.css",
            )
        ]
        css = render_modules_css(assets, in_repo=lambda _p: True)

        assert "@source" not in css, "in-repo pages are covered by the static glob"
        assert '@import "#module/local/styles.css" layer(components);' in css

    async def test_writes_assets_json(self, tmp_path):
        """modules.assets.json is emitted alongside the existing three files."""
        import json

        from simple_module_core import discover_modules
        from simple_module_hosting.manifest import write_module_pages_manifest

        written = write_module_pages_manifest(discover_modules(), tmp_path)
        assets_path = tmp_path / "modules.assets.json"
        assert assets_path.is_file()
        assert written["assets"] == assets_path

        data = json.loads(assets_path.read_text(encoding="utf-8"))
        entry = data["Dashboard"]
        assert entry["package_name"] == "dashboard"
        assert entry["package"].endswith("dashboard")
        assert set(entry) == {"package_name", "package", "pages", "theme", "styles"}

    async def test_manifest_json_shape_unchanged(self, tmp_path):
        """modules.manifest.json stays {name: pages_dir} for downstream vite configs."""
        import json

        from simple_module_core import discover_modules
        from simple_module_hosting.manifest import write_module_pages_manifest

        write_module_pages_manifest(discover_modules(), tmp_path)
        data = json.loads((tmp_path / "modules.manifest.json").read_text(encoding="utf-8"))
        assert all(isinstance(v, str) for v in data.values())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest framework/cli/tests/test_module_css_assets.py -v`
Expected: FAIL — `render_modules_css` / `render_assets_json` undefined, and
`written` has no `"assets"` key.

- [ ] **Step 3: Implement the emitters in `assets.py`**

```python
ALIAS_PREFIX = "#module"

_CSS_HEADER = """\
/* AUTO-GENERATED by simple_module_hosting.assets — do not edit by hand.
 * Regenerate with: smpy gen-pages
 *
 * Emission order is module discovery order (topological by depends_on),
 * so a dependent module's CSS can override its dependency's.
 */
"""


def render_modules_css(
    assets: Sequence[ModuleAssets],
    *,
    in_repo: Callable[[Path], bool],
) -> str:
    """Render ``modules.generated.css``.

    Three sections. ``@source`` is emitted only for wheel-installed modules
    (in-repo pages are already covered by the static glob in the host's
    styles.css), but ``@import`` is emitted for every module — there is no
    static-glob equivalent for CSS.

    ``theme.css`` is imported unlayered so its ``@theme`` blocks register as
    design tokens; ``styles.css`` is imported into ``layer(components)`` so a
    module rule can never outrank a Tailwind utility.
    """
    source_lines = [
        f'@source "{e.pages_dir.as_posix()}/**/*.{{ts,tsx}}";'
        for e in assets
        if e.pages_dir and not in_repo(e.pages_dir)
    ]
    theme_lines = [
        f'@import "{ALIAS_PREFIX}/{e.package_name}/{THEME_CSS}";'
        for e in assets
        if e.theme_css
    ]
    style_lines = [
        f'@import "{ALIAS_PREFIX}/{e.package_name}/{STYLES_CSS}" layer(components);'
        for e in assets
        if e.styles_css
    ]

    out = [_CSS_HEADER]
    for heading, lines in (
        ("/* ── @source: class scanning (wheel-installed modules) ── */", source_lines),
        ("/* ── theme: unlayered, registers @theme tokens ── */", theme_lines),
        ("/* ── styles: layer(components), always loses to utilities ── */", style_lines),
    ):
        if lines:
            out.append("")
            out.append(heading)
            out.extend(lines)
    out.append("")
    return "\n".join(out)


def render_assets_json(assets: Sequence[ModuleAssets]) -> str:
    """Render ``modules.assets.json`` — the richer companion to the pages manifest."""
    payload = {
        e.name: {
            "package_name": e.package_name,
            "package": e.package_dir.as_posix(),
            "pages": e.pages_dir.as_posix() if e.pages_dir else None,
            "theme": e.theme_css.as_posix() if e.theme_css else None,
            "styles": e.styles_css.as_posix() if e.styles_css else None,
        }
        for e in assets
    }
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"
```

Add `import json` and `from collections.abc import Callable, Sequence` at the
top of `assets.py`.

- [ ] **Step 4: Rewire `manifest.py`**

Replace the CSS-emission block in `write_module_pages_manifest` with calls to
the new renderers, add the `modules.assets.json` write, and include `"assets"`
in the returned dict. Delete the now-unused `_GENERATED_CSS_HEADER`. Keep
`_is_in_repo_module` and pass it as the `in_repo` callable:

```python
    assets = compute_module_assets(modules)
    css_text = render_modules_css(
        assets, in_repo=lambda p: _is_in_repo_module(p, repo_root)
    )
    assets_path = output_dir / "modules.assets.json"
    wrote_assets = _write_if_changed(assets_path, render_assets_json(assets))
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest framework/cli/tests/test_module_css_assets.py framework/cli/tests/test_module_pages_manifest.py -v`
Expected: PASS (both files — the existing manifest tests must not regress)

- [ ] **Step 6: Check the file-size cap**

Run: `uv run python scripts/check_file_size.py`
Expected: PASS — `manifest.py` must still be under 300 lines.

- [ ] **Step 7: Commit**

```bash
git add framework/hosting/simple_module_hosting/ framework/cli/tests/test_module_css_assets.py
git commit -m "feat(hosting): emit aliased module CSS imports and modules.assets.json"
```

---

### Task 4: Wire Vite aliases and widen the host `@source` glob

**Files:**
- Modify: `host/client_app/vite.config.ts`
- Modify: `host/client_app/styles.css`
- Modify: `framework/cli/simple_module_cli/templates/host/client_app/vite.config.ts`
- Modify: `framework/cli/simple_module_cli/templates/host/client_app/styles.css`

**Interfaces:**
- Consumes: `modules.assets.json` from Task 3.
- Produces: a `#module/<package_name>` alias per module, resolvable from CSS
  and TSX alike.

- [ ] **Step 1: Read `modules.assets.json` in `vite.config.ts`**

Add alongside the existing manifest read, leaving that read intact:

```ts
// Aliases let generated CSS reference module files as
// "#module/<pkg>/styles.css" instead of a brittle
// ../../../.venv/lib/python3.12/site-packages/<pkg>/styles.css path.
// @tailwindcss/vite resolves CSS @import through Vite's resolver
// (createResolver({...config.resolve, ...})), so resolve.alias applies.
type ModuleAsset = { package_name: string; package: string };
const moduleAliases: { find: string; replacement: string }[] = [];
const assetsPath = path.resolve(__dirname, 'modules.assets.json');
if (fs.existsSync(assetsPath)) {
  const assets = JSON.parse(fs.readFileSync(assetsPath, 'utf-8')) as Record<string, ModuleAsset>;
  for (const entry of Object.values(assets)) {
    moduleAliases.push({
      find: `#module/${entry.package_name}`,
      replacement: entry.package,
    });
    if (!moduleFsAllow.includes(entry.package)) moduleFsAllow.push(entry.package);
  }
  // Longest find first so "#module/gis" can't shadow "#module/gis_extra".
  moduleAliases.sort((a, b) => b.find.length - a.find.length);
}
```

- [ ] **Step 2: Register the aliases**

In the existing `resolve:` block, add `alias: moduleAliases,` beside
`tsconfigPaths` and `dedupe`.

- [ ] **Step 3: Widen the in-repo `@source` glob**

In both `styles.css` files, change
`@source "../../modules/*/*/pages/**/*.{ts,tsx}";` to
`@source "../../modules/*/*/**/*.{ts,tsx}";` so `.ts`/`.tsx` outside `pages/`
is scanned. The `{ts,tsx}` filter keeps `.py` out.

- [ ] **Step 4: Mirror steps 1-2 into the scaffold template**

Apply the same edits to
`framework/cli/simple_module_cli/templates/host/client_app/vite.config.ts` so
new `smpy new` apps get aliases from the start.

- [ ] **Step 5: Verify the templates still typecheck and the app builds**

Run: `npx tsc --noEmit -p host/client_app/tsconfig.json`
Expected: PASS

Run: `npm run build`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add host/client_app framework/cli/simple_module_cli/templates/host/client_app
git commit -m "feat(client): resolve module CSS through per-module Vite aliases"
```

---

### Task 5: Prove it end-to-end with a real module

A green unit suite can coexist with Tailwind emitting nothing, so this is the
task that actually proves the feature.

**Files:**
- Create: `modules/dashboard/dashboard/styles.css`
- Test: `framework/cli/tests/test_module_css_build.py`

- [ ] **Step 1: Add a real stylesheet to an in-repo module**

```css
/* Dashboard module styles. Imported into layer(components) by
 * modules.generated.css, so these rules always lose to Tailwind utilities. */
@layer components {
  .dashboard-stat-grid {
    display: grid;
    gap: var(--spacing, 0.25rem);
  }
}
```

- [ ] **Step 2: Write the failing build test**

```python
"""Proves module-shipped CSS survives a real Tailwind build."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.slow
class TestModuleCssReachesBundle:
    def test_module_class_is_emitted_by_vite_build(self):
        """A class defined only in a module's styles.css appears in built CSS."""
        subprocess.run(
            ["uv", "run", "smpy", "gen-pages", "--host-dir", "host/client_app"],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["npm", "run", "build"], cwd=REPO_ROOT, check=True, capture_output=True
        )
        built = list((REPO_ROOT / "host" / "static" / "dist" / "assets").glob("*.css"))
        assert built, "no CSS emitted by the build"
        combined = "\n".join(p.read_text(encoding="utf-8") for p in built)
        assert "dashboard-stat-grid" in combined
```

- [ ] **Step 3: Run it and watch it fail, then pass**

Run: `uv run pytest framework/cli/tests/test_module_css_build.py -v`

Before Tasks 3-4 land this fails on the missing class. After they land it
passes. If it fails *after*, the alias did not resolve — re-check Task 1's
findings before changing the emitter.

- [ ] **Step 4: Commit**

```bash
git add modules/dashboard/dashboard/styles.css framework/cli/tests/test_module_css_build.py
git commit -m "test(client): assert module-shipped CSS reaches the built bundle"
```

---

### Task 6: SM022 / SM023 diagnostics

**Files:**
- Create: `framework/core/simple_module_core/diagnostics/_css.py`
- Modify: `framework/core/simple_module_core/diagnostics/_module.py:32-39`
- Test: `framework/core/tests/test_css_diagnostics.py`

**Interfaces:**
- Consumes: `Diagnostic`, `DiagnosticLevel`, `ModuleBase`, and the `src_dir`
  already computed by `ModuleDiagnostics.run`.
- Produces: `check_module_css(mod: ModuleBase, src_dir: Path) -> list[Diagnostic]`,
  called exactly like the existing `check_js_workspace_files(mod, src_dir)`.

- [ ] **Step 1: Write the failing test**

```python
"""SM022/SM023 — module CSS placed in the wrong file."""

from __future__ import annotations


class TestModuleCssDiagnostics:
    def _mod(self):
        from simple_module_core import ModuleBase, ModuleMeta

        class Styled(ModuleBase):
            meta = ModuleMeta(name="Styled")

        return Styled()

    def test_sm022_theme_at_rule_in_styles_css(self, tmp_path):
        """@theme inside styles.css is inert under layer(components)."""
        from simple_module_core.diagnostics._css import check_module_css

        (tmp_path / "styles.css").write_text("@theme {\n  --color-x: red;\n}\n")
        diags = check_module_css(self._mod(), tmp_path)
        assert [d.code for d in diags] == ["SM022"]

    def test_sm023_plain_rule_in_theme_css(self, tmp_path):
        """An unlayered rule in theme.css outranks every Tailwind utility."""
        from simple_module_core.diagnostics._css import check_module_css

        (tmp_path / "theme.css").write_text(".card {\n  padding: 0;\n}\n")
        diags = check_module_css(self._mod(), tmp_path)
        assert [d.code for d in diags] == ["SM023"]

    def test_root_block_allowed_in_theme_css(self, tmp_path):
        """:root custom-property blocks are legitimate in theme.css."""
        from simple_module_core.diagnostics._css import check_module_css

        (tmp_path / "theme.css").write_text(
            "@theme {\n  --a: 1;\n}\n:root {\n  --b: 2;\n}\n"
        )
        assert check_module_css(self._mod(), tmp_path) == []

    def test_nested_at_rule_not_flagged(self, tmp_path):
        """Only top-level constructs count — brace depth is tracked."""
        from simple_module_core.diagnostics._css import check_module_css

        (tmp_path / "styles.css").write_text(
            "@layer components {\n  .x { color: red; }\n}\n"
        )
        assert check_module_css(self._mod(), tmp_path) == []

    def test_comments_stripped_before_scanning(self, tmp_path):
        """A commented-out @theme is not a finding."""
        from simple_module_core.diagnostics._css import check_module_css

        (tmp_path / "styles.css").write_text("/* @theme { --x: 1; } */\n.y { color: red; }\n")
        assert check_module_css(self._mod(), tmp_path) == []

    def test_clean_module_has_no_findings(self, tmp_path):
        from simple_module_core.diagnostics._css import check_module_css

        (tmp_path / "theme.css").write_text("@theme {\n  --color-x: red;\n}\n")
        (tmp_path / "styles.css").write_text("@layer components {\n  .x { color: red; }\n}\n")
        assert check_module_css(self._mod(), tmp_path) == []

    def test_missing_files_are_not_findings(self, tmp_path):
        from simple_module_core.diagnostics._css import check_module_css

        assert check_module_css(self._mod(), tmp_path) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest framework/core/tests/test_css_diagnostics.py -v`
Expected: FAIL — no module `simple_module_core.diagnostics._css`

- [ ] **Step 3: Implement `_css.py`**

A line-oriented scan tracking brace depth, comments stripped first. No CSS
parser dependency — this catches the ordinary mistake, not pathological input.

`THEME_ONLY_AT_RULES = {"@theme", "@custom-variant", "@utility"}` are the
constructs that must live in `theme.css`; `theme.css` may additionally hold
`@font-face`, `@import`, `@charset` and `:root` blocks.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest framework/core/tests/test_css_diagnostics.py -v`
Expected: PASS

- [ ] **Step 5: Wire into `ModuleDiagnostics.run`**

Add `diagnostics.extend(check_module_css(mod, src_dir))` to the file-based
check loop, and the import at the top of `_module.py`.

- [ ] **Step 6: Verify the whole diagnostic suite and `make doctor`**

Run: `uv run pytest framework/core/tests/ -v`
Run: `make doctor`
Expected: PASS, and `make doctor` reports no new findings for in-repo modules.

- [ ] **Step 7: Commit**

```bash
git add framework/core/simple_module_core/diagnostics framework/core/tests/test_css_diagnostics.py
git commit -m "feat(doctor): add SM022/SM023 for misplaced module CSS"
```

---

### Task 7: Documentation

**Files:**
- Modify: `docs/module-authoring.md`
- Modify: `CLAUDE.md`
- Modify: `framework/cli/simple_module_cli/templates/module/README.md.tpl`

- [ ] **Step 1: Add a "Styling" section to `docs/module-authoring.md`**

Cover: the two-file convention; that `@theme` goes in `theme.css` and component
rules in `styles.css`; why (unlayered CSS beats every layered rule, and a
layered `@theme` is inert); the cascade order DS theme < module theme < app
overrides; and that no packaging change is needed because Hatch already ships
files under the package dir.

- [ ] **Step 2: Update `CLAUDE.md`**

Add `theme.css` / `styles.css` to the module-layout tree, and add SM022/SM023
to the diagnostic-code list.

- [ ] **Step 3: Mention the convention in the scaffold README template**

One short paragraph — the scaffold deliberately does *not* create empty CSS
files, so the README is where authors learn the convention exists.

- [ ] **Step 4: Run the full check**

Run: `make ci-python-lint`
Run: `make test-py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add docs CLAUDE.md framework/cli/simple_module_cli/templates/module/README.md.tpl
git commit -m "docs: document the module theme.css/styles.css convention"
```

---

## Self-Review

**Spec coverage:** §1 authoring surface → Task 2. §2 emission → Task 3. §3
cascade → Tasks 3 (layering) + 4 (glob widening). §4 alias/manifest → Tasks 3
(`modules.assets.json`) + 4 (Vite wiring). §5 diagnostics → Task 6. §6 tests →
Tasks 2, 3, 5, 6. §7 docs → Task 7. "To verify during implementation" → Task 1.
No gaps.

**Type consistency:** `ModuleAssets` field names (`package_name`, `package_dir`,
`pages_dir`, `theme_css`, `styles_css`) are used identically in Tasks 2 and 3.
The JSON keys (`package_name`, `package`, `pages`, `theme`, `styles`) match
between `render_assets_json` in Task 3 and the `ModuleAsset` TS type in Task 4.
`check_module_css(mod, src_dir)` matches the existing
`check_js_workspace_files(mod, src_dir)` signature it sits beside.

**Ordering note:** Task 5's build test only passes once Tasks 3 and 4 have both
landed, which is why it is sequenced after them.
