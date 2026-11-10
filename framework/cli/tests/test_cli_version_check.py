"""`smpy new` warns when the running CLI is older than PyPI's latest (GH #899)."""

from __future__ import annotations

from pathlib import Path

import pytest
from simple_module_cli import _version_check
from simple_module_cli.cli import app
from typer.testing import CliRunner


def test_newer_release_reports_a_newer_stable_version(fake_pypi) -> None:
    fetcher = fake_pypi({"simple_module_cli": "0.0.44"})
    assert _version_check.newer_release("0.0.36", fetcher) == "0.0.44"


@pytest.mark.parametrize(
    "current", ["0.0.44", "0.0.45", "0.0.0", "0.0.40.dev0", "0.0.40rc1", "0.0.40+local"]
)
def test_no_newer_release_when_current_or_placeholder(fake_pypi, current: str) -> None:
    fetcher = fake_pypi({"simple_module_cli": "0.0.44"})
    assert _version_check.newer_release(current, fetcher) is None


@pytest.mark.parametrize("error", [OSError("offline"), TimeoutError(), ValueError("bad json")])
def test_any_lookup_failure_skips_the_check(error: Exception) -> None:
    def failing(url: str) -> dict:
        raise error

    assert _version_check.newer_release("0.0.36", failing) is None


def test_smpy_new_warns_and_still_scaffolds(tmp_path: Path, fake_pypi, monkeypatch) -> None:
    monkeypatch.setattr(
        _version_check, "_quick_fetcher", fake_pypi({"simple_module_cli": "99.0.0"})
    )
    target = tmp_path / "demo"
    result = CliRunner().invoke(
        app, ["new", "demo", "--yes", "--db", "sqlite", "--no-install", "--dest", str(target)]
    )
    assert result.exit_code == 0, result.output
    assert "simple_module_cli 99.0.0 is on PyPI" in result.output
    assert "uv tool upgrade simple_module_cli" in result.output
    assert (target / "host" / "pyproject.toml").is_file()


def test_smpy_new_is_silent_when_pypi_is_unreachable(tmp_path: Path) -> None:
    target = tmp_path / "demo"
    result = CliRunner().invoke(
        app, ["new", "demo", "--yes", "--db", "sqlite", "--no-install", "--dest", str(target)]
    )
    assert result.exit_code == 0, result.output
    assert "WARNING: this smpy" not in result.output
