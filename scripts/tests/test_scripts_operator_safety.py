"""Regression coverage for container credentials and release rehearsal safety."""

import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
ENTRYPOINT = REPO_ROOT / "docker/entrypoint.sh"
PASSWORD_ENV = "SM_USERS_BOOTSTRAP_PASSWORD"


def _run_entrypoint(tmp_path: Path, **overrides: str) -> subprocess.CompletedProcess[str]:
    alembic = tmp_path / "alembic"
    alembic.write_text('#!/bin/sh\necho "migration-stub"\n')
    alembic.chmod(0o755)
    env = {key: value for key, value in os.environ.items() if not key.startswith("SM_")}
    env.update(
        PATH=f"{tmp_path}:{env['PATH']}",
        SM_SECRET_KEY="test-secret",
        SM_USERS_RESET_PASSWORD_TOKEN_SECRET="test-reset-secret",
        SM_USERS_VERIFICATION_TOKEN_SECRET="test-verification-secret",
    )
    env.update(overrides)
    return subprocess.run(
        [
            "sh",
            str(ENTRYPOINT),
            "sh",
            "-c",
            f'printf "%s\\n%s" "$SM_USERS_BOOTSTRAP_PASSWORD_GENERATED" "${PASSWORD_ENV}"',
        ],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.parametrize("password", [None, ""])
@pytest.mark.parametrize("environment", ["development", "production"])
def test_scripts_entrypoint_generates_and_marks_private_password(
    tmp_path: Path, password: str | None, environment: str
):
    overrides = {} if password is None else {PASSWORD_ENV: password}
    first = _run_entrypoint(tmp_path, SM_ENVIRONMENT=environment, **overrides)
    second = _run_entrypoint(tmp_path, SM_ENVIRONMENT=environment, **overrides)
    assert first.returncode == second.returncode == 0
    credential = first.stdout.splitlines()[-1]
    assert len(credential) >= 32
    assert credential != second.stdout.splitlines()[-1]
    assert credential not in first.stderr
    assert "admin@example.com" not in first.stderr
    assert first.stdout.splitlines()[-2] == "1"


def test_scripts_entrypoint_preserves_private_explicit_password(tmp_path: Path):
    password = "operator-provided-password"
    result = _run_entrypoint(tmp_path, **{PASSWORD_ENV: password})
    assert result.returncode == 0
    assert result.stdout.splitlines()[-1] == password
    assert result.stdout.splitlines()[-2] == ""
    assert password not in result.stderr


def test_scripts_entrypoint_rejects_public_password_in_production(tmp_path: Path):
    result = _run_entrypoint(tmp_path, SM_ENVIRONMENT="production", **{PASSWORD_ENV: "changeme"})
    assert result.returncode != 0
    assert "migration-stub" not in result.stdout
    assert PASSWORD_ENV in result.stderr


def test_scripts_release_rehearsal_uses_disposable_worktree():
    document = (REPO_ROOT / "docs/release.md").read_text()
    rehearsal = document.split("## Local pre-flight", 1)[1].split("## Troubleshooting", 1)[0]
    assert "git reset" not in rehearsal
    assert "git worktree add --detach" in rehearsal
    assert "git worktree remove --force" in rehearsal
    assert rehearsal.index("git worktree add") < rehearsal.index("scripts/bump_version.py")
    assert rehearsal.index("git worktree remove") > rehearsal.index("uv build")
