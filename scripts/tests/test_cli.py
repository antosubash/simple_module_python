"""Tests for the main() CLI entry point of the new_module script."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from new_module import main


class TestMainCLI:
    """Tests for the main() entry point."""

    def test_main_invokes_full_pipeline(
        self, workspace: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ):
        monkeypatch.setattr(sys, "argv", ["new_module.py", "orders"])
        main()

        assert (workspace / "modules" / "orders" / "pyproject.toml").exists()
        assert (workspace / "modules" / "orders" / "orders" / "module.py").exists()
        assert '"orders"' in (workspace / "host" / "pyproject.toml").read_text()
        assert "Scaffolding module 'orders'" in capsys.readouterr().out

    def test_main_exits_on_invalid_name(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(sys, "argv", ["new_module.py", "Invalid-Name"])
        with pytest.raises(SystemExit):
            main()
