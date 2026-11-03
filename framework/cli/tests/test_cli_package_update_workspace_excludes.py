"""Package updates respect uv workspace exclusions (GH #767)."""

import tomllib
from pathlib import Path

import pytest
from simple_module_cli.package_update import run_update


@pytest.mark.parametrize("exclude", ["modules/archive", "modules/arch*"])
def test_package_update_leaves_excluded_manifest_unchanged(
    tmp_path: Path,
    write_pyproject,
    fake_pypi,
    exclude: str,
) -> None:
    root = tmp_path / "pyproject.toml"
    root.write_text(
        '[project]\nname="host"\nversion="0"\ndependencies=[]\n'
        '[tool.uv.workspace]\nmembers=["modules/*"]\n'
        f'exclude=["{exclude}"]\n'
    )
    manifests = {}
    for name in ("active", "archive"):
        directory = tmp_path / "modules" / name
        directory.mkdir(parents=True)
        manifest = directory / "pyproject.toml"
        write_pyproject(manifest, "simple_module_core==0.0.42")
        manifests[name] = manifest
    original = manifests["archive"].read_bytes()

    run_update(tmp_path, fetcher=fake_pypi({"simple_module_core": "0.0.43"}))

    assert manifests["archive"].read_bytes() == original
    assert tomllib.loads(manifests["active"].read_text())["project"]["dependencies"] == [
        "simple_module_core==0.0.43"
    ]
