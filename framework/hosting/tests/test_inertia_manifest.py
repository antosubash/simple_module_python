"""Tests for production Inertia manifest normalization (_prod_manifest_path).

fastapi-inertia looks the entry up by ``f"{root_directory}/{entrypoint}"`` =
``"./main.tsx"``, but Vite keys its manifest by the entry's source path
(``"main.tsx"``). _prod_manifest_path bridges the two so production page
rendering doesn't KeyError. Regression guard for that bug.
"""

from __future__ import annotations

import json
from pathlib import Path

from simple_module_hosting._inertia_setup import _prod_manifest_path


def _write_vite_manifest(project_root: Path) -> Path:
    manifest_dir = project_root / "host" / "static" / "dist" / ".vite"
    manifest_dir.mkdir(parents=True)
    manifest = {
        "main.tsx": {
            "file": "assets/main-ABC123.js",
            "css": ["assets/main-DEF456.css"],
            "isEntry": True,
        },
        "pages/Foo.tsx": {"file": "assets/Foo-XYZ.js"},
    }
    path = manifest_dir / "manifest.json"
    path.write_text(json.dumps(manifest))
    return path


def test_rekeys_entry_for_fastapi_inertia(tmp_path: Path):
    _write_vite_manifest(tmp_path)
    result = _prod_manifest_path(tmp_path)

    assert result, "expected a manifest path, got empty string"
    data = json.loads(Path(result).read_text())
    # fastapi-inertia will look up f"{root_directory}/{entrypoint}" == "./main.tsx"
    assert "./main.tsx" in data
    assert data["./main.tsx"]["file"] == "assets/main-ABC123.js"
    assert data["./main.tsx"]["css"] == ["assets/main-DEF456.css"]
    # original keys are preserved (other chunks still resolvable)
    assert "pages/Foo.tsx" in data


def test_returns_empty_when_no_built_manifest(tmp_path: Path):
    # No host/static/dist/.vite/manifest.json present.
    assert _prod_manifest_path(tmp_path) == ""


def test_scaffolded_layout_without_host_dir(tmp_path: Path):
    # smpy-new apps keep static/ at the project root (no host/ subdir).
    manifest_dir = tmp_path / "static" / "dist" / ".vite"
    manifest_dir.mkdir(parents=True)
    (manifest_dir / "manifest.json").write_text(
        json.dumps({"main.tsx": {"file": "assets/main-A.js", "isEntry": True}})
    )
    result = _prod_manifest_path(tmp_path)
    assert result
    data = json.loads(Path(result).read_text())
    assert data["./main.tsx"]["file"] == "assets/main-A.js"
