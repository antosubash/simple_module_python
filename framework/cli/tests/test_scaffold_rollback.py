"""Scaffold rollback on partial failure.

Before the rollback added to ``create_module``, a mid-pipeline error left
the user with a non-empty destination directory — the next ``smpy new``
invocation against the same path would then refuse to overwrite, but the
files already written wouldn't form a valid Python package either.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from simple_module_cli import scaffolding


def test_create_module_rolls_back_on_template_failure(tmp_path, monkeypatch):
    """An exception during ``_apply_template_files`` must clear ``dest``."""
    dest = tmp_path / "broken_module"

    def boom(*_args, **_kwargs):
        # Simulate a mid-write error after the dest directory exists but
        # before all files have been laid down.
        dest.mkdir(exist_ok=True)
        (dest / "half_written.py").write_text("# truncated", encoding="utf-8")
        raise RuntimeError("simulated template engine failure")

    monkeypatch.setattr(scaffolding, "_apply_template_files", boom)

    with pytest.raises(RuntimeError, match="simulated template engine failure"):
        scaffolding.create_module(dest, "my_thing")

    assert not dest.exists(), (
        "Partial scaffold left on disk — rollback didn't fire. Subsequent "
        "smpy new attempts at this path would refuse to overwrite."
    )


def test_rollback_does_not_delete_pre_existing_directory(tmp_path, monkeypatch):
    """A pre-existing (empty) destination must stay on disk on rollback.

    We can't tell from inside ``create_module`` whether ``dest`` was made
    by us or by the caller, but the directory's *prior existence* is a
    reliable signal: if the caller mkdir'd it, leaving their dir alone is
    the conservative choice. (The half-written scaffold contents inside
    are an unavoidable consequence — preventing those needs a transactional
    file system, which we don't have.)
    """
    dest = tmp_path / "owned_by_caller"
    dest.mkdir()

    def boom(*_args, **_kwargs):
        raise RuntimeError("simulated failure before any files written")

    monkeypatch.setattr(scaffolding, "_apply_template_files", boom)

    with pytest.raises(RuntimeError):
        scaffolding.create_module(dest, "thing")

    # The dir survives — we didn't make it.
    assert dest.exists()


def test_successful_scaffold_keeps_dest():
    """Sanity check: the rollback path only fires on failure."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp) / "real_module"
        scaffolding.create_module(dest, "real_module")
        assert dest.exists()
        # The template materialises at least the package directory.
        assert any(dest.iterdir())
