"""Tests for scripts/check_readmes.py."""

from __future__ import annotations

from pathlib import Path

from scripts.check_readmes import check_readme, main


def test_missing_readme_reported(tmp_pkg_dir: Path) -> None:
    errors = check_readme(tmp_pkg_dir)
    assert any("README.md" in e and "not found" in e for e in errors)


def test_tiny_readme_reported(tmp_pkg_dir: Path, writer) -> None:
    writer(tmp_pkg_dir / "README.md", "# tiny\n")
    errors = check_readme(tmp_pkg_dir)
    assert any("too short" in e.lower() for e in errors)


def test_missing_sections_reported(tmp_pkg_dir: Path, writer) -> None:
    writer(
        tmp_pkg_dir / "README.md",
        "# pkg\n\n" + ("Lorem ipsum " * 80),
    )
    errors = check_readme(tmp_pkg_dir)
    joined = "\n".join(errors)
    assert "Install" in joined
    assert "Usage" in joined


def test_valid_readme_passes(tmp_pkg_dir: Path, writer) -> None:
    writer(
        tmp_pkg_dir / "README.md",
        "# simple_module_foo\n\n"
        + ("Lorem ipsum dolor sit amet. " * 40)
        + "\n\n## Install\n\n`pip install x`\n\n## Usage\n\n`x()`\n",
    )
    assert check_readme(tmp_pkg_dir) == []


def test_main_fails_on_missing(tmp_path: Path, monkeypatch, writer) -> None:
    writer(
        tmp_path / "framework/core/pyproject.toml",
        '[project]\nname = "simple_module_core"\n',
    )
    monkeypatch.chdir(tmp_path)
    assert main([]) != 0
