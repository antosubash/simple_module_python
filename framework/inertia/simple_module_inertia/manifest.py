"""Locate the entry's JS and CSS for the current environment.

Vite keys its manifest by the entry's path relative to the Vite root
(``"main.tsx"``); upstream looked it up as ``f"{root_directory}/{entrypoint}"``
and ``KeyError``'d, which is why hosting used to rewrite the manifest file.
Try Vite's key first, upstream's shape second, the first ``isEntry`` chunk
last — and say which manifest was searched when none of them hit.
"""

from __future__ import annotations

import json
import posixpath
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from simple_module_inertia.config import InertiaConfig


@dataclass
class InertiaFiles:
    js: str
    css: list[str] = field(default_factory=list)


@lru_cache
def read_manifest(path: str) -> dict[str, Any]:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _find_entry(manifest: dict[str, Any], config: InertiaConfig) -> dict[str, Any] | None:
    keys = (
        config.entrypoint_filename,
        f"{config.root_directory}/{config.entrypoint_filename}",
    )
    for key in keys:
        if key in manifest:
            return manifest[key]
    return next((chunk for chunk in manifest.values() if chunk.get("isEntry")), None)


def _public(prefix: str, file: str) -> str:
    return posixpath.join("/", prefix, file) if prefix else posixpath.join("/", file)


def entry_assets(config: InertiaConfig) -> InertiaFiles:
    if config.environment == "production" or config.ssr_enabled:
        if not config.manifest_json_path:
            raise LookupError(
                "Production rendering needs InertiaConfig.manifest_json_path to point at "
                "the built Vite manifest; it is empty"
            )
        manifest = read_manifest(config.manifest_json_path)
        entry = _find_entry(manifest, config)
        if entry is None:
            raise LookupError(
                f"No entry chunk for {config.entrypoint_filename!r} in {config.manifest_json_path}"
            )
        return InertiaFiles(
            js=_public(config.assets_prefix, entry["file"]),
            css=[_public(config.assets_prefix, f) for f in entry.get("css") or []],
        )
    root = config.root_directory.strip("/")
    path = (
        config.entrypoint_filename
        if root in ("", ".")
        else f"{root}/{config.entrypoint_filename}"
    )
    return InertiaFiles(js=f"{config.dev_url.rstrip('/')}/{path}")
