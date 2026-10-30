"""Plan lockstep npm updates without installing packages or writing files."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote

from simple_module_cli.package_update_deps import Change, Skip
from simple_module_cli.pypi import Fetcher

_SECTIONS = ("dependencies", "devDependencies", "optionalDependencies", "peerDependencies")
_PREFIX = "@simple-module-py/"
_REGISTRY = "https://registry.npmjs.org/"
_SEMVER = re.compile(
    r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
)


def _version_key(version: str) -> tuple | None:
    match = _SEMVER.fullmatch(version)
    if not match:
        return None
    major, minor, patch, pre = match.groups()
    identifiers = (pre or "").split(".") if pre else []
    if any(part.isdigit() and len(part) > 1 and part.startswith("0") for part in identifiers):
        return None
    suffix = tuple((0, int(p)) if p.isdigit() else (1, p) for p in identifiers)
    return (int(major), int(minor), int(patch), pre is None, suffix)


@dataclass
class Manifest:
    path: Path
    original: str
    doc: dict[str, Any]

    @property
    def packages(self) -> set[str]:
        return {
            name
            for section in _SECTIONS
            for name in self.doc.get(section, {})
            if name.startswith(_PREFIX)
        }


def load_manifests(directories: list[Path]) -> list[Manifest]:
    manifests = []
    paths = dict.fromkeys(
        path.resolve()
        for directory in directories
        for path in (directory / "package.json", directory / "client_app/package.json")
        if path.is_file()
    )
    for path in paths:
        original = path.read_bytes().decode("utf-8")
        doc = json.loads(original)
        if not isinstance(doc, dict):
            raise ValueError(f"{path}: expected a JSON object")
        for section in _SECTIONS:
            if section in doc and not isinstance(doc[section], dict):
                raise ValueError(f"{path}: {section} must be an object")
        manifests.append(Manifest(path, original, doc))
    return manifests


def _render(manifest: Manifest) -> str:
    match = re.search(r"(?:\r?\n)([ \t]+)\S", manifest.original)
    indent = match[1] if match else None
    newline = "\r\n" if "\r\n" in manifest.original else "\n"
    rendered = json.dumps(manifest.doc, indent=indent, ensure_ascii=False)
    if newline != "\n":
        rendered = rendered.replace("\n", newline)
    return rendered + (newline if manifest.original.endswith("\n") else "")


def plan_npm(
    manifests: list[Manifest], target: str | None, fetcher: Fetcher, *, blocked: str | None = None
) -> tuple[list[Change], list[Skip], list[tuple[Path, str]]]:
    changes: list[Change] = []
    skips: list[Skip] = []
    pending: list[tuple[Path, str]] = []
    available: dict[str, bool] = {}
    target_key = _version_key(target) if target else None
    for manifest in manifests:
        changed = False
        for section in _SECTIONS:
            for name, pin in manifest.doc.get(section, {}).items():
                if not name.startswith(_PREFIX):
                    continue
                style = pin[:1] if isinstance(pin, str) and pin[:1] in ("^", "~") else ""
                current = _version_key(pin[len(style) :]) if isinstance(pin, str) else None
                reason = None
                if current is None:
                    reason = f"unsupported npm reference {pin!r}"
                elif target_key is None:
                    reason = blocked or f"no npm-compatible simple_module_core target ({target})"
                elif current >= target_key:
                    continue
                else:
                    if name not in available:
                        try:
                            data = fetcher(_REGISTRY + quote(name, safe="@"))
                            available[name] = target in data.get("versions", {})
                        except (OSError, ValueError):  # HTTP/URL/timeout, bad JSON
                            available[name] = False
                    if not available[name]:
                        reason = f"npm release {target} unavailable"
                if reason:
                    skips.append(Skip(manifest.path, name, reason))
                    continue
                new = style + str(target)
                manifest.doc[section][name] = new
                changes.append(Change(manifest.path, name, pin, new))
                changed = True
        if changed:
            pending.append((manifest.path, _render(manifest)))
    return changes, skips, pending
