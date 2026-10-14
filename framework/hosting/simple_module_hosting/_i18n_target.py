"""Where generated i18n key files are written: monorepo checkout or published npm package."""

from __future__ import annotations

import re
from pathlib import Path

RESOURCE_KEY_RE = re.compile(r"^\s+'([^']+)': '',$", re.MULTILINE)

_PUBLISHED_PKG = Path("node_modules") / "@simple-module-py" / "i18n" / "src"


def resolve_i18n_types_dir(project_root: Path) -> tuple[Path | None, bool]:
    """Where the generated key files go, and whether that is a published package.

    The monorepo's ``packages/i18n/src`` wins. A scaffolded app has no such
    checkout — ``@simple-module-py/i18n`` is an npm dependency — so walk up from
    ``project_root`` to the nearest ``node_modules`` holding it (npm workspaces
    hoist it to the workspace root, above the host; a flat host installs into
    ``client_app/``). ``(None, False)`` when
    neither exists, the normal shape of a wheel-installed prod app.
    """
    local = project_root / "packages" / "i18n" / "src"
    if local.is_dir():
        return local, False
    root = project_root.resolve()
    # A flat host (``smpy new --flat``) keeps its npm install in client_app/.
    for base in (root, root / "client_app", *root.parents):
        published = base / _PUBLISHED_PKG
        if published.is_dir():
            return published, True
    return None, False


def read_resource_keys(resources_path: Path) -> frozenset[str]:
    """Keys listed in an existing ``generated-resources.ts`` (empty if unreadable)."""
    try:
        return frozenset(RESOURCE_KEY_RE.findall(resources_path.read_text(encoding="utf-8")))
    except OSError:
        return frozenset()
