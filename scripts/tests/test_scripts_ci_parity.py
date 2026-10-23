"""Lint/CI parity catches omitted checks, including its own gate."""

import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts/check_ci_parity.py"


def run_check(tmp_path, makefile, workflow):
    (tmp_path / "Makefile").write_text(makefile)
    workflow_path = tmp_path / ".github/workflows/pr.yml"
    workflow_path.parent.mkdir(parents=True)
    workflow_path.write_text(workflow)
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(tmp_path)],
        text=True,
        capture_output=True,
        check=False,
    )


@pytest.mark.parametrize(
    "run",
    ["make ci-one ci-two", "|\n          make ci-one\n          make ci-two"],
)
def test_scripts_parity_accepts_all_prerequisites(tmp_path, run):
    result = run_check(
        tmp_path,
        "lint: ci-one \\\n ci-two # comment\n",
        f"jobs:\n  lint:\n    steps:\n      - run: {run}\n",
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "step",
    [
        "# make ci-two\n      - run: make ci-one",
        "- name: make ci-two\n        run: make ci-one",
        "- run: make ci-one ci-two-extra",
        '- run: echo "make ci-two"',
    ],
)
def test_scripts_parity_rejects_checks_not_executed(tmp_path, step):
    result = run_check(
        tmp_path, "lint: ci-one ci-two\n", f"jobs:\n  lint:\n    steps:\n      {step}\n"
    )
    assert result.returncode == 1
    assert "ci-two" in result.stderr


def test_scripts_parity_rejects_missing_lint_target(tmp_path):
    result = run_check(tmp_path, "other: ci-one\n", "jobs: {}\n")
    assert result.returncode == 1
    assert "lint" in result.stderr


def test_scripts_repository_lint_is_covered():
    result = subprocess.run(
        [sys.executable, str(SCRIPT)], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr


def test_scripts_parity_honors_explicit_local_only_allowlist(tmp_path, monkeypatch):
    from scripts import check_ci_parity

    (tmp_path / "Makefile").write_text("lint: ci-one ci-local\n")
    workflow = tmp_path / ".github/workflows/pr.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text("jobs:\n  lint:\n    steps:\n      - run: make ci-one\n")
    monkeypatch.setattr(check_ci_parity, "LOCAL_ONLY_CHECKS", {"ci-local": "local tooling"})
    assert check_ci_parity.check_parity(tmp_path) == []


def test_scripts_parity_catches_its_own_missing_step(tmp_path):
    result = run_check(
        tmp_path,
        "lint: ci-check-ci-parity\n",
        "jobs:\n  lint:\n    steps:\n      - run: make ci-python-lint\n",
    )
    assert result.returncode == 1
    assert "ci-check-ci-parity" in result.stderr
