"""Regression test: ``simple_module_cli`` must build cleanly via ``uv build``.

The release workflow runs ``uv build --all-packages`` which builds the sdist
first and then re-builds the wheel from the unpacked sdist. Any
``force-include`` that points outside the package (e.g. ``../../skills``)
breaks that rebuild because the sdist's parent directory has no such files.

This test catches that class of regression at unit-test time so it can never
slip past PR checks again.
"""

from __future__ import annotations

import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

CLI_PROJECT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def built_artifacts(tmp_path_factory) -> tuple[Path, Path]:
    """Build sdist + wheel via ``uv build`` exactly as the release workflow does."""
    if shutil.which("uv") is None:
        pytest.skip("uv not available on PATH")
    out = tmp_path_factory.mktemp("dist")
    subprocess.run(
        ["uv", "build", "--package", "simple_module_cli", "--out-dir", str(out)],
        check=True,
        capture_output=True,
    )
    sdist = next(out.glob("simple_module_cli-*.tar.gz"), None)
    wheel = next(out.glob("simple_module_cli-*-py3-none-any.whl"), None)
    assert sdist is not None, f"sdist not produced; got: {list(out.iterdir())}"
    assert wheel is not None, f"wheel not produced; got: {list(out.iterdir())}"
    return sdist, wheel


def test_wheel_contains_bundled_skills(built_artifacts: tuple[Path, Path]) -> None:
    """The wheel must ship the agent skill packs that ``smpy skills`` depends on.

    Regression: ``[tool.hatch.build.targets.wheel.force-include]`` with
    ``../../skills`` made the wheel re-build from sdist crash with
    ``FileNotFoundError: Forced include not found``.
    """
    _, wheel = built_artifacts
    with zipfile.ZipFile(wheel) as zf:
        names = zf.namelist()
    skill_files = [n for n in names if n.startswith("simple_module_cli/skills/")]
    assert skill_files, (
        f"wheel {wheel.name} does not ship simple_module_cli/skills/* "
        f"(top-level entries: {sorted({n.split('/', 1)[0] for n in names})})"
    )
    skill_dirs = {n.split("/")[2] for n in skill_files if n.count("/") >= 2 and n.split("/")[2]}
    assert "simple-module-creating" in skill_dirs, (
        f"expected the simple-module-creating skill in the wheel; got dirs: {sorted(skill_dirs)}"
    )


def test_wheel_contains_templates(built_artifacts: tuple[Path, Path]) -> None:
    """``smpy new`` reads from ``simple_module_cli/templates`` — must ship in the wheel."""
    _, wheel = built_artifacts
    with zipfile.ZipFile(wheel) as zf:
        names = zf.namelist()
    template_files = [n for n in names if n.startswith("simple_module_cli/templates/")]
    assert template_files, "wheel does not ship simple_module_cli/templates/*"


def test_sdist_is_self_contained(built_artifacts: tuple[Path, Path]) -> None:
    """The sdist must include skills + templates; without them the sdist→wheel
    rebuild that ``uv build --all-packages`` performs would fail.
    """
    sdist, _ = built_artifacts
    import tarfile

    with tarfile.open(sdist) as tf:
        names = tf.getnames()
    assert any("simple_module_cli/skills/" in n for n in names), (
        "sdist does not include simple_module_cli/skills/* — "
        "wheel rebuild from sdist will fail in CI"
    )
    assert any("simple_module_cli/templates/" in n for n in names), (
        "sdist does not include simple_module_cli/templates/*"
    )
