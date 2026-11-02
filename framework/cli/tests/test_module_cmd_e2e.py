"""End-to-end: scaffold a standalone module and verify its frontend for real.

Python framework packages are wired into the verify host from the local tree
via ``[tool.uv.sources]`` (so the e2e tests THIS checkout, not the last
release); the npm packages (`@simple-module-py/*`) still come from the
registry at the released version. Needs network + npm. Excluded from default
pytest runs via the ``e2e`` marker.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

pytestmark = pytest.mark.e2e

_REPO_ROOT = Path(__file__).resolve().parents[3]

# Everything the verify-host resolves from PyPI that this repo also owns —
# point it at the local tree instead so the e2e exercises HEAD.
_LOCAL_SOURCES = {
    "simple_module_core": _REPO_ROOT / "framework" / "core",
    "simple_module_db": _REPO_ROOT / "framework" / "db",
    "simple_module_hosting": _REPO_ROOT / "framework" / "hosting",
    "simple_module_settings": _REPO_ROOT / "modules" / "settings",
}


@pytest.mark.skipif(shutil.which("npm") is None, reason="npm not installed")
async def test_scaffolded_module_verifies_green(tmp_path):
    from simple_module_cli._module_host import ensure_verify_host, read_module_info
    from simple_module_cli.module_cmd import run_verify
    from simple_module_cli.scaffolding import create_module, resolve_framework_version

    dest = tmp_path / "simple-module-e2e-feature"
    create_module(
        dest,
        name="E2eFeature",
        standalone=True,
        framework_version=resolve_framework_version(),
    )

    info = read_module_info(dest)
    host = ensure_verify_host(info)
    # The scaffolded host pyproject ends with the [tool.uv.sources] table that
    # wires the module itself; appending more keys extends the same table.
    host_pyproject = host / "pyproject.toml"
    extra_sources = "".join(
        f'{name} = {{ path = "{path.as_posix()}", editable = true }}\n'
        for name, path in _LOCAL_SOURCES.items()
    )
    host_pyproject.write_text(
        host_pyproject.read_text(encoding="utf-8") + extra_sources, encoding="utf-8"
    )

    run_verify(info)  # reuses the patched host; raises typer.Exit(1) on any failure

    # The host template's vite.config.ts sets build.outDir to '../static/dist'
    # relative to client_app, i.e. <host>/static/dist.
    dist = host / "static" / "dist"
    assert dist.is_dir() and any(dist.rglob("*.js")), "vite build produced no JS bundle"
