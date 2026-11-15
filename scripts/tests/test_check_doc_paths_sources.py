"""check_doc_paths scans the root agent guides, not only docs/ and skills/."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "check_doc_paths", Path(__file__).resolve().parent.parent / "check_doc_paths.py"
)
mod = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(mod)


def test_root_guides_are_scanned(tmp_path, monkeypatch):
    for name in ("AGENTS.md", "CLAUDE.md", "README.md"):
        (tmp_path / name).write_text("# x\n", encoding="utf-8")
    (tmp_path / "docs").mkdir()
    (tmp_path / "skills").mkdir()
    monkeypatch.setattr(mod, "ROOT", tmp_path)

    names = {p.name for p in mod.sources()}

    assert {"AGENTS.md", "CLAUDE.md", "README.md"} <= names
