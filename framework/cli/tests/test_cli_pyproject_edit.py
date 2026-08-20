"""Tests for host pyproject.toml editing (deps + [tool.uv.sources])."""

from __future__ import annotations

from pathlib import Path

from simple_module_cli.git_source import RefInfo
from simple_module_cli.pyproject_edit import (
    dep_constraint,
    git_sources,
    has_git_sources,
    load_pyproject,
    save_pyproject,
    write_dependency,
    write_git_source,
    write_path_source,
)

BASE = (
    "# host config\n"
    '[project]\nname = "myhost"\nversion = "0.1.0"\n'
    "dependencies = [\n"
    '    "fastapi>=0.110",  # keep\n'
    '    "simple_module_core>=0.1,<1.0",\n'
    "]\n"
)


def _doc(tmp_path: Path, text: str = BASE):
    p = tmp_path / "pyproject.toml"
    p.write_text(text, encoding="utf-8")
    return p, load_pyproject(p)


def test_write_dependency_adds_and_replaces(tmp_path: Path) -> None:
    p, doc = _doc(tmp_path)
    assert write_dependency(doc, "simple_module_blog", ">=0.2.0,<1.0") is True
    assert write_dependency(doc, "simple_module_blog", ">=0.2.0,<1.0") is False
    assert write_dependency(doc, "simple_module_blog", ">=0.3.0,<1.0") is True
    save_pyproject(p, doc)
    out = p.read_text(encoding="utf-8")
    assert "simple_module_blog>=0.3.0,<1.0" in out
    assert out.count("simple_module_blog") == 1
    assert "# keep" in out  # tomlkit round-trip preserves comments


def test_write_git_source_variants(tmp_path: Path) -> None:
    p, doc = _doc(tmp_path)
    write_git_source(
        doc,
        "simple_module_blog",
        url="https://github.com/x/repo",
        ref_info=RefInfo("tag", "v0.2.0"),
        subdirectory="modules/blog",
    )
    save_pyproject(p, doc)
    text = p.read_text(encoding="utf-8")
    assert "[tool.uv.sources]" in text
    assert 'git = "https://github.com/x/repo"' in text
    assert 'tag = "v0.2.0"' in text
    assert 'subdirectory = "modules/blog"' in text

    _, doc2 = _doc(tmp_path, p.read_text(encoding="utf-8"))
    assert has_git_sources(doc2) is True
    assert "simple_module_blog" in git_sources(doc2)


def test_branch_and_rev_and_default_keys(tmp_path: Path) -> None:
    p, doc = _doc(tmp_path)
    write_git_source(doc, "a", url="u", ref_info=RefInfo("branch", "main"), subdirectory=None)
    write_git_source(doc, "b", url="u", ref_info=RefInfo("rev", "abc123"), subdirectory=None)
    write_git_source(doc, "c", url="u", ref_info=RefInfo("default", None), subdirectory=None)
    save_pyproject(p, doc)
    text = p.read_text(encoding="utf-8")
    assert 'branch = "main"' in text
    assert 'rev = "abc123"' in text
    # default ref → bare git source, no pin key
    assert text.count("tag =") == 0


def test_write_path_source(tmp_path: Path) -> None:
    p, doc = _doc(tmp_path)
    write_path_source(doc, "simple_module_local", path="../local_mod")
    save_pyproject(p, doc)
    text = p.read_text(encoding="utf-8")
    assert 'path = "../local_mod"' in text
    assert "editable = true" in text


def test_dep_constraint_and_no_git_sources(tmp_path: Path) -> None:
    _, doc = _doc(tmp_path)
    assert dep_constraint(doc, "simple_module_core") == ">=0.1,<1.0"
    assert dep_constraint(doc, "absent") is None
    assert has_git_sources(doc) is False
