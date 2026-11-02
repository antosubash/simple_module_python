"""Release dispatches must be serialized, current, and safe to finalize (#628)."""

import os
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/release.yml"


def workflow():
    return yaml.safe_load(WORKFLOW.read_text())


def git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


@pytest.fixture
def release_repos(tmp_path: Path):
    remote = tmp_path / "origin.git"
    git(tmp_path, "init", "--bare", "--initial-branch=main", str(remote))
    author = tmp_path / "author"
    git(tmp_path, "clone", str(remote), str(author))
    git(author, "config", "user.name", "Test")
    git(author, "config", "user.email", "test@example.com")
    (author / "version").write_text("1.0.0\n")
    git(author, "add", ".")
    git(author, "commit", "-m", "initial")
    git(author, "push", "origin", "main")
    runner = tmp_path / "runner"
    git(tmp_path, "clone", str(remote), str(runner))
    sha = git(runner, "rev-parse", "HEAD")
    git(runner, "checkout", "--detach", sha)
    return remote, author, runner, sha


def shell(repo: Path, script: str, **env: str):
    return subprocess.run(
        ["/bin/bash", "--noprofile", "--norc", "-euo", "pipefail", "-c", script],
        cwd=repo,
        env={**os.environ, **env},
        capture_output=True,
        text=True,
    )


def test_release_serialization_and_publish_gate():
    config = workflow()
    assert config.get("concurrency") == {"group": "release", "cancel-in-progress": False}
    jobs = config["jobs"]
    assert set(jobs["release-guard"]["needs"]) >= {"build", "preflight"}
    for name in ("publish-pypi", "publish-npm"):
        assert "release-guard" in jobs[name]["needs"]
    assert "resolve" in jobs["checks"]["needs"]
    assert "resolve" in jobs["preflight"]["needs"]


@pytest.mark.parametrize("job", ["resolve", "release-guard"])
@pytest.mark.parametrize("source", ["main", "feature", "tag", "stale", "offline"])
def test_release_source_guard(release_repos, job: str, source: str):
    remote, author, runner, sha = release_repos
    # Run the workflow's actual command with its shared script in the runner checkout.
    scripts = runner / "scripts"
    scripts.mkdir()
    for path in (ROOT / "scripts").glob("check_release_ref.sh"):
        (scripts / path.name).write_text(path.read_text())
    steps = workflow()["jobs"].get(job, {}).get("steps", [])
    guard = next((s for s in steps if s.get("name") == "Verify release source"), None)
    assert guard is not None, f"{job} must validate the source before proceeding"
    if source == "stale":
        (author / "merged").write_text("merged before publishing\n")
        git(author, "add", ".")
        git(author, "commit", "-m", "merged PR")
        git(author, "push", "origin", "main")
    if source == "offline":
        git(runner, "remote", "set-url", "origin", str(remote / "missing"))
    ref = {"feature": "refs/heads/feature", "tag": "refs/tags/v1.0.0"}.get(
        source, "refs/heads/main"
    )
    result = shell(runner, guard["run"], GITHUB_REF=ref, GITHUB_SHA=sha)
    assert (result.returncode == 0) == (source == "main"), result.stdout + result.stderr


@pytest.mark.parametrize("advance", ["none", "unrelated", "conflict", "tag-exists", "push-race"])
def test_finalize_preserves_main_and_only_tags_on_success(release_repos, advance: str):
    remote, author, runner, dispatch_sha = release_repos
    (runner / "version").write_text("1.0.1\n")
    if advance in ("unrelated", "conflict"):
        (author / ("version" if advance == "conflict" else "merged")).write_text("PR change\n")
        git(author, "add", ".")
        git(author, "commit", "-m", "merged PR")
        git(author, "push", "origin", "main")
    if advance == "tag-exists":
        git(author, "tag", "v1.0.1")
        git(author, "push", "origin", "v1.0.1")
    if advance == "push-race":
        # Advance main after finalize's fetch/merge, just as its push starts.
        hook = runner / ".git/hooks/pre-push"
        hook.write_text(
            "#!/bin/sh\n"
            f'git -C "{author}" commit --allow-empty -m "racing PR"\n'
            f'git -C "{author}" push origin main\n'
        )
        hook.chmod(0o755)
    main_before = git(remote, "rev-parse", "main")
    step = next(
        s for s in workflow()["jobs"]["finalize"]["steps"] if s.get("name") == "Commit, tag, push"
    )
    result = shell(runner, step["run"], VERSION="1.0.1")
    if advance in ("conflict", "tag-exists", "push-race"):
        assert result.returncode != 0
        assert git(remote, "rev-parse", "main") == git(author, "rev-parse", "HEAD")
        assert git(remote, "show", "main:version") != "1.0.1"
        assert bool(git(remote, "tag", "-l", "v1.0.1")) == (advance == "tag-exists")
    else:
        assert result.returncode == 0, result.stdout + result.stderr
        # The tag is the published source: the release commit on the dispatch SHA.
        assert git(remote, "rev-parse", "v1.0.1^") == dispatch_sha
        assert git(remote, "merge-base", "--is-ancestor", "v1.0.1", "main") == ""
        if advance == "none":
            assert git(remote, "rev-parse", "main") == git(remote, "rev-parse", "v1.0.1")
        assert git(remote, "show", "main:version") == "1.0.1"
        assert git(remote, "merge-base", "--is-ancestor", main_before, "main") == ""
        if advance == "unrelated":
            assert git(remote, "show", "main:merged") == "PR change"
