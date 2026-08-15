"""Per-module frontend asset discovery and CSS emission.

Split out from :mod:`simple_module_hosting.manifest`, which is already at the
repo's 300-line cap. ``manifest.py`` imports from here.

A module may ship two optional stylesheets beside its ``pages/`` directory:

* ``theme.css`` — ``@theme`` tokens, ``@custom-variant``, ``@font-face``.
  Imported *unlayered*, because a ``@theme`` block inside a cascade layer is
  inert and registers no design tokens.
* ``styles.css`` — component rules, keyframes, vendor CSS. Imported into
  ``layer(components)``, because unlayered CSS outranks every Tailwind
  utility: a module shipping a bare ``.card { padding: 0 }`` would otherwise
  silently beat ``p-4``.

Both are referenced by **absolute** filesystem path, exactly as the ``@source``
lines in the same file already are.

This used to emit a per-module Vite alias (``#module/<pkg>/styles.css``) to
avoid a relative path like ``../../../.venv/lib/python3.12/site-packages/<pkg>``
— but that objection only ever applied to *relative* paths, and the alias made
this generated file depend on the host resolving it. ``vite.config.ts`` is
scaffold output: it is written once into an app and then owned and edited
there, so it is versioned independently of these Python packages. A host
scaffolded before the alias existed never receives it, and a Python-only
dependency bump would emit specifiers that host cannot resolve, failing the
build with ``Can't resolve '#module/<pkg>/styles.css'`` — naming something that
appears nowhere in the app's own sources (GH issue #253).

Absolute paths keep the generated CSS self-contained: it resolves under any
``vite.config.ts``, old or new, with no alias configured at all.
"""

from __future__ import annotations

import importlib.resources
import json
import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from simple_module_core import ModuleBase, get_module_package_name

logger = logging.getLogger(__name__)

THEME_CSS = "theme.css"
STYLES_CSS = "styles.css"
PACKAGE_JSON = "package.json"
PAGES_DIR = "pages"
COMPONENTS_DIR = "components"


@dataclass(frozen=True)
class ModuleAssets:
    """Frontend assets a single module contributes."""

    name: str
    package_name: str
    package_dir: Path
    pages_dir: Path | None
    theme_css: Path | None
    styles_css: Path | None
    npm_name: str | None = None
    components_dir: Path | None = None


def find_npm_name(pkg_root: Path) -> str | None:
    """Return the module's npm package name, or ``None`` if it ships no JS.

    Two install layouts put ``package.json`` in different places:

    * **wheel** — Hatch force-includes the module-root ``package.json`` *into*
      the Python package, so it lands at ``site-packages/<pkg>/package.json``.
    * **editable / workspace** — it stays at the source-tree module root,
      ``modules/<name>/package.json``, one level above the Python package.

    The parent candidate is accepted only when that directory also holds a
    ``pyproject.toml``. Without that guard a wheel-installed module would
    happily read ``site-packages/package.json`` — some unrelated file that
    happens to sit there — and alias the module onto a stranger's name.
    """
    candidates = [pkg_root / PACKAGE_JSON]
    parent = pkg_root.parent
    if (parent / "pyproject.toml").is_file():
        candidates.append(parent / PACKAGE_JSON)
    for candidate in candidates:
        if not candidate.is_file():
            continue
        try:
            name = json.loads(candidate.read_text(encoding="utf-8")).get("name")
        except (OSError, ValueError):
            logger.debug("Module package.json at %s is unreadable — ignoring", candidate)
            continue
        if isinstance(name, str) and name:
            return name
    return None


def compute_module_assets(modules: Sequence[ModuleBase]) -> list[ModuleAssets]:
    """Return per-module frontend assets, preserving discovery order.

    Discovery order matters. ``discover_modules()`` topologically sorts by
    ``ModuleMeta.depends_on``, which is the order the host invokes
    ``register_*`` hooks in; emitting CSS in that same order means a module
    that depends on another can override its dependency's styles.

    A module is included only if it contributes at least one asset.
    """
    result: list[ModuleAssets] = []
    for mod in modules:
        pkg_name = get_module_package_name(mod)
        try:
            pkg_root = Path(str(importlib.resources.files(pkg_name)))
        except (ModuleNotFoundError, TypeError):
            logger.debug(
                "Module '%s': package %s not importable — skipping", mod.meta.name, pkg_name
            )
            continue
        pages_dir = pkg_root / PAGES_DIR
        components_dir = pkg_root / COMPONENTS_DIR
        theme = pkg_root / THEME_CSS
        styles = pkg_root / STYLES_CSS
        entry = ModuleAssets(
            name=mod.meta.name,
            package_name=pkg_name,
            package_dir=pkg_root.resolve(),
            pages_dir=pages_dir.resolve() if pages_dir.is_dir() else None,
            theme_css=theme.resolve() if theme.is_file() else None,
            styles_css=styles.resolve() if styles.is_file() else None,
            npm_name=find_npm_name(pkg_root),
            components_dir=components_dir.resolve() if components_dir.is_dir() else None,
        )
        if entry.pages_dir or entry.theme_css or entry.styles_css or entry.components_dir:
            result.append(entry)
    return result


_CSS_HEADER = """\
/* AUTO-GENERATED by simple_module_hosting.assets — do not edit by hand.
 * Regenerate with: smpy gen-pages
 *
 * Emission order is module discovery order (topological by depends_on), so a
 * dependent module's CSS can override its dependency's.
 *
 * theme.css is imported unlayered so its @theme blocks register as design
 * tokens; styles.css is imported into layer(components) so a module rule can
 * never outrank a Tailwind utility.
 */"""


def render_modules_css(
    assets: Sequence[ModuleAssets],
    *,
    in_repo: Callable[[Path], bool],
) -> str:
    """Render the contents of ``modules.generated.css``.

    ``@source`` is emitted only for wheel-installed modules — in-repo module
    pages are already covered by the static ``@source`` glob in the host's
    ``styles.css``, so emitting an absolute one too would just duplicate it.
    ``@import`` is emitted for *every* module, in-repo and wheel alike, because
    there is no static-glob equivalent for CSS.

    Both ``pages/`` and ``components/`` are scanned. A wheel module's widgets
    live under ``components/``, and leaving them out meant every host had to
    hand-write a ``@source`` pointing into ``.venv`` — which cannot be written
    portably: POSIX venvs nest under ``lib/python3.x/site-packages`` while
    Windows uses ``Lib/site-packages``. Tailwind accepts a glob that matches
    nothing without complaint, so the hand-written POSIX path silently dropped
    every widget class on Windows. Emitting the resolved absolute path here
    works on both. See GH #258.

    Every path is absolute, so nothing here depends on the host's
    ``vite.config.ts`` — see the module docstring for why that matters.
    """
    source_lines = [
        f'@source "{d.as_posix()}/**/*.{{ts,tsx}}";'
        for e in assets
        for d in (e.pages_dir, e.components_dir)
        if d and not in_repo(d)
    ]
    theme_lines = [f'@import "{e.theme_css.as_posix()}";' for e in assets if e.theme_css]
    style_lines = [
        f'@import "{e.styles_css.as_posix()}" layer(components);' for e in assets if e.styles_css
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
    """Render ``modules.assets.json`` — the richer companion to the pages manifest.

    Kept separate from ``modules.manifest.json`` rather than replacing it:
    ``vite.config.ts`` is scaffolded *into* each app, so changing the existing
    manifest's value shape would break every downstream app at once. This file
    is purely additive, and also covers CSS-only modules that never appear in
    the pages manifest because they ship no ``pages/``.

    ``npm_name`` is what lets one module import another's TS/TSX by package
    name. The host aliases it onto ``package`` — the module's *Python package
    directory* — and that target is forced, not chosen: a wheel contains only
    ``site-packages/<pkg>/**``, so the source-tree module root simply does not
    exist once installed. Anchoring the npm name there is the only mapping
    that can mean the same thing in both layouts. See ``find_npm_name``.
    """
    payload = {
        e.name: {
            "package_name": e.package_name,
            "package": e.package_dir.as_posix(),
            "pages": e.pages_dir.as_posix() if e.pages_dir else None,
            "components": e.components_dir.as_posix() if e.components_dir else None,
            "theme": e.theme_css.as_posix() if e.theme_css else None,
            "styles": e.styles_css.as_posix() if e.styles_css else None,
            "npm_name": e.npm_name,
        }
        for e in assets
    }
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"
