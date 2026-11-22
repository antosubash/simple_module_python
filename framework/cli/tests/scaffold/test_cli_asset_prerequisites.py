"""Missing frontend prerequisites may skip locally but must fail on CI."""

import pytest


@pytest.mark.parametrize("ci", [None, "true"])
def test_cli_missing_asset_prerequisite_fails_on_ci(monkeypatch, require_cli_asset, ci):
    if ci:
        monkeypatch.setenv("CI", ci)
    else:
        monkeypatch.delenv("CI", raising=False)
    outcome = pytest.fail.Exception if ci else pytest.skip.Exception
    with pytest.raises(outcome, match="missing tool"):
        require_cli_asset(False, "missing tool")


def test_cli_available_asset_prerequisite_runs_on_ci(monkeypatch, require_cli_asset):
    monkeypatch.setenv("CI", "true")
    require_cli_asset(True, "missing tool")
