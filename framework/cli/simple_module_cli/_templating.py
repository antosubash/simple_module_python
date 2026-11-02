"""Package-data template engine shared by the scaffolders.

Extracted from :mod:`simple_module_cli.scaffolding` (which keeps the public
``create_workspace`` / ``create_host`` / ``create_module`` entry points) so
each file has one job: this one renders template trees, that one decides what
to render.
"""

from __future__ import annotations

import importlib.resources
import shutil
from collections.abc import Mapping
from pathlib import Path

_TEMPLATES_PACKAGE = "simple_module_cli.templates"
_PACKAGE_PATH_TOKEN = "__PACKAGE__"


def _iter_template_files(template_root: Path):
    """Yield every file under ``template_root``. Skips ``_optional/`` paths."""
    for path in template_root.rglob("*"):
        if not path.is_file():
            continue
        if "_optional" in path.relative_to(template_root).parts:
            continue
        yield path


def _require_empty_dest(dest: Path, *, preserve_existing: frozenset[str] = frozenset()) -> None:
    """Refuse a non-empty destination unless every top-level entry is allowed.

    ``preserve_existing`` is matched against the *name* of each top-level entry,
    so callers can permit common pre-existing files (``.git``, ``README.md``,
    ...) without silently overwriting unrelated user content.
    """
    if dest.exists():
        unexpected = sorted(p.name for p in dest.iterdir() if p.name not in preserve_existing)
        if unexpected:
            raise FileExistsError(
                f"Destination {dest} exists and contains files that would collide "
                f"with the scaffold: {', '.join(unexpected)}. "
                "Move them aside or choose another path."
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
    preserve_existing: frozenset[str] = frozenset(),
) -> list[Path]:
    """Write template files into ``dest``; return paths skipped to preserve the user's copy."""
    preserved: list[Path] = []
    for src in _iter_template_files(src_root):
        rel_str = str(src.relative_to(src_root))
        for old, new in (path_rewrites or {}).items():
            rel_str = rel_str.replace(old, new)
        rel_str = rel_str.removesuffix(".tpl")
        target = dest / rel_str
        top = Path(rel_str).parts[0] if rel_str else ""
        if top in preserve_existing and target.exists():
            preserved.append(target)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        if src.suffix == ".tpl":
            text = src.read_text(encoding="utf-8")
            for placeholder, value in substitutions.items():
                text = text.replace(placeholder, value)
            target.write_text(text, encoding="utf-8")
        else:
            shutil.copy2(src, target)
    return preserved
