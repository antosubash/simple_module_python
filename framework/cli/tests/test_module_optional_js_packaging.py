"""Config-free module wheels include optional dependency-only manifests."""

from __future__ import annotations

import json
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
from simple_module_cli.scaffolding import create_module


@pytest.mark.parametrize("extra_deps", [False, True])
def test_scaffold_sdist_rebuild_ships_optional_js_manifest(tmp_path: Path, extra_deps: bool):
    module = create_module(tmp_path / "orders", name="orders")
    if extra_deps:
        (module / "orders" / "package.json").write_text(
            json.dumps({"dependencies": {"maplibre-gl": "^5.0.0"}})
        )
    out = tmp_path / "dist"
    result = subprocess.run(
        ["uv", "build", "--python", sys.executable, "--out-dir", str(out)],
        cwd=module,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    (wheel,) = out.glob("*.whl")
    with zipfile.ZipFile(wheel) as archive:
        assert "orders/pages/Browse.tsx" in archive.namelist()
        assert ("orders/package.json" in archive.namelist()) == extra_deps
        if extra_deps:
            assert json.loads(archive.read("orders/package.json")) == {
                "dependencies": {"maplibre-gl": "^5.0.0"}
            }
