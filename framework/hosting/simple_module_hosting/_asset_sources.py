"""Tailwind source discovery across conventional and module-owned domain areas."""

import os
from pathlib import Path


def source_dirs(base: Path) -> list[Path]:
    """Directories directly containing TS/TSX, pruning caches and package metadata."""
    found = []
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [
            name
            for name in dirnames
            if name not in {"__pycache__", "node_modules"}
            and not name.startswith(".")
            and not name.endswith((".dist-info", ".egg-info"))
        ]
        if any(Path(name).suffix in {".ts", ".tsx"} for name in filenames):
            found.append(Path(dirpath))
    return sorted(found)


def module_source_dirs(package: Path, conventional: tuple[Path | None, ...]) -> list[Path]:
    """Keep conventional bases and add domain areas containing frontend code.

    Each source-bearing descendant needs its own base because uv's venv ignore
    file can hide descendants from Tailwind's scanner (#419).
    """
    sources = source_dirs(package)
    roots = [directory for directory in conventional if directory]
    for source in sources:
        relative = source.relative_to(package)
        root = package / relative.parts[0] if relative.parts else package
        if root not in roots:
            roots.append(root)
    return list(
        dict.fromkeys(
            path
            for root in roots
            for path in [root, *(source for source in sources if source.is_relative_to(root))]
        )
    )
