"""Generate eager frontend registration globs in module discovery order."""

from __future__ import annotations

import json
import os
from collections.abc import Sequence
from pathlib import Path

from simple_module_hosting.frontend.assets import ModuleAssets

# picomatch (Vite's glob engine) treats these as pattern syntax; a literal path
# containing one, e.g. ``plugin[12]/``, would otherwise match sibling folders.
_GLOB_SPECIAL = frozenset("*?[]{}()!+@")


def _escape_glob(path: str) -> str:
    return "".join(f"\\{ch}" if ch in _GLOB_SPECIAL else ch for ch in path)


def render_frontend_extensions(assets: Sequence[ModuleAssets], output_dir: Path) -> list[str]:
    imports = ["import type { ExtensionRegistry } from '@simple-module-py/ui/extensions';"]
    calls = []
    for asset in assets:
        entries = [
            path
            for suffix in ("ts", "tsx")
            if (path := asset.package_dir / "ui" / f"extensions.{suffix}").is_file()
        ]
        if len(entries) > 1:
            raise ValueError(f"{asset.name}: ship only one ui/extensions.ts or ui/extensions.tsx")
        if not entries:
            continue
        # Module projects check sources; host tsc must not follow real wheel paths.
        path = Path(os.path.relpath(entries[0], output_dir.resolve())).as_posix()
        if not path.startswith(("./", "../")):
            path = "./" + path
        symbol = f"moduleExtensions{len(calls)}"
        imports.append(
            f"const {symbol} = import.meta.glob<(registry: ExtensionRegistry) => void>("
            f"{json.dumps(_escape_glob(path))}, {{ eager: true, import: 'register' }});"
        )
        calls.append(
            f"  registry.runOnce({json.dumps(asset.name)}, () => "
            f"Object.values({symbol}).forEach(register => register(registry)));"
        )
    return [
        *imports,
        "",
        "export function registerModuleExtensions(registry: ExtensionRegistry): void {",
        *calls,
        "}",
        "",
    ]
