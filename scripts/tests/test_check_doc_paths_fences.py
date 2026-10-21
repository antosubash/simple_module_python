"""Fence tracking in check_doc_paths follows CommonMark (same char, length >= opener)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "check_doc_paths", Path(__file__).resolve().parent.parent / "check_doc_paths.py"
)
mod = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(mod)

BAD = "`host/nope_missing.py`"


def _run(tmp_path, monkeypatch, body: str, capsys) -> tuple[int, str]:
    doc = tmp_path / "doc.md"
    doc.write_text(body, encoding="utf-8")
    monkeypatch.setattr(mod, "ROOT", tmp_path)
    monkeypatch.setattr(mod, "sources", lambda: [doc])
    monkeypatch.setattr(mod, "ALLOWLIST", tmp_path / "none.txt")
    monkeypatch.setattr(mod, "tracked_paths", set)
    rc = mod.main()
    return rc, capsys.readouterr().out


def test_inner_shorter_fence_does_not_close(tmp_path, monkeypatch, capsys):
    body = f"````md\n```py\nx\n```\n{BAD}\n````\n"
    rc, _ = _run(tmp_path, monkeypatch, body, capsys)
    assert rc == 0


def test_other_char_does_not_close(tmp_path, monkeypatch, capsys):
    body = f"```\n~~~\n{BAD}\n```\n"
    rc, _ = _run(tmp_path, monkeypatch, body, capsys)
    assert rc == 0


def test_text_after_closer_does_not_close(tmp_path, monkeypatch, capsys):
    body = f"```\n``` not a closer\n{BAD}\n```\n"
    rc, _ = _run(tmp_path, monkeypatch, body, capsys)
    assert rc == 0


def test_path_after_fence_is_checked(tmp_path, monkeypatch, capsys):
    body = f"````\n```\n````\n{BAD}\n"
    rc, out = _run(tmp_path, monkeypatch, body, capsys)
    assert rc == 1
    assert "nope_missing" in out
