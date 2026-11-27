"""check_doc_paths scans the root agent guides, not only docs/ and skills/."""

from __future__ import annotations

from scripts import check_doc_paths as mod


def test_root_guides_are_scanned(tmp_path, monkeypatch):
    for name in ("AGENTS.md", "CLAUDE.md", "README.md"):
        (tmp_path / name).write_text("# x\n", encoding="utf-8")
    (tmp_path / "docs").mkdir()
    (tmp_path / "skills").mkdir()
    monkeypatch.setattr(mod, "ROOT", tmp_path)

    names = {p.name for p in mod.sources()}

    assert {"AGENTS.md", "CLAUDE.md", "README.md"} <= names


def test_agent_rules_are_scanned(tmp_path, monkeypatch):
    rules_dir = tmp_path / ".agents" / "rules"
    rules_dir.mkdir(parents=True)
    rule_file = rules_dir / "architecture.md"
    rule_file.write_text(
        "---\ntrigger: model_decision\ndescription: test\n---\n\n# Arch\n", encoding="utf-8"
    )
    (tmp_path / "docs").mkdir()
    (tmp_path / "skills").mkdir()
    monkeypatch.setattr(mod, "ROOT", tmp_path)

    assert rule_file in mod.sources()
