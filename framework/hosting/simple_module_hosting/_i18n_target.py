"""Locate app-owned generated i18n files without mutating npm installations."""

from __future__ import annotations

import re
from pathlib import Path

RESOURCE_KEY_RE = re.compile(r"^\s+'([^']+)': '',$", re.MULTILINE)

_PUBLISHED_PKG = Path("node_modules") / "@simple-module-py" / "i18n" / "src"


def resolve_i18n_types_dir(project_root: Path) -> tuple[Path | None, bool]:
    """Return the compatibility workspace target or the app's own aggregate.

    The boolean identifies the app-owned target (formerly the published target).
    An npm install is still required, but never used as an output directory.
    """
    local = project_root / "packages/i18n/src"
    if local.is_dir():
        return local, False
    root = project_root.resolve()
    client = next((p for p in (root / "host/client_app", root / "client_app") if p.is_dir()), None)
    for base in (root, root / "client_app", *root.parents):
        if (base / _PUBLISHED_PKG).is_dir():
            return (client / "i18n" if client else root / "i18n"), True
    return None, False


def app_i18n_dir(project_root: Path) -> Path | None:
    for client in (project_root / "host/client_app", project_root / "client_app"):
        if client.is_dir():
            return client / "i18n"
    return None


def read_resource_keys(resources_path: Path) -> frozenset[str]:
    """Keys listed in an existing ``generated-resources.ts`` (empty if unreadable)."""
    try:
        return frozenset(RESOURCE_KEY_RE.findall(resources_path.read_text(encoding="utf-8")))
    except OSError:
        return frozenset()


def app_i18n_import(client: Path) -> str:
    return (
        "import './i18n/keys.generated';\n" if (client / "i18n/keys.generated.ts").is_file() else ""
    )


def attach_app_i18n(client: Path) -> None:
    """Older app resolvers import this manifest; register their custom keys too."""
    from simple_module_hosting._generated_files import _write_if_changed

    manifest = client / "modules.generated.ts"
    if manifest.is_file():
        source = manifest.read_text(encoding="utf-8")
        statement = app_i18n_import(client)
        if statement and statement not in source:
            _write_if_changed(manifest, statement + source)
