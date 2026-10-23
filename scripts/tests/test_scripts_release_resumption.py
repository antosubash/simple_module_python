"""Release publishing must gate new projects and tolerate partial releases (#599)."""

import io
import json
import os
import subprocess
import tarfile
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/release.yml"


def test_every_publish_job_needs_preflight() -> None:
    jobs = yaml.safe_load(WORKFLOW.read_text())["jobs"]
    assert "preflight" in jobs
    assert any(
        "python -m scripts.release_preflight" in step.get("run", "")
        for step in jobs["preflight"]["steps"]
    )
    for name, job in jobs.items():
        if name.startswith("publish-"):
            needs = job["needs"]
            assert "preflight" in ([needs] if isinstance(needs, str) else needs)
    assert set(jobs["finalize"]["needs"]) >= {"publish-pypi", "publish-npm"}


def test_pypi_skips_existing_distributions() -> None:
    jobs = yaml.safe_load(WORKFLOW.read_text())["jobs"]
    publish = next(
        step
        for step in jobs["publish-pypi"]["steps"]
        if step.get("uses", "").startswith("pypa/gh-action-pypi-publish@")
    )
    assert str(publish["with"].get("skip-existing")).lower() == "true"


def test_postgres_runs_for_concurrency_sensitive_modules() -> None:
    workflow = yaml.load(
        (ROOT / ".github/workflows/postgres-tests.yml").read_text(), Loader=yaml.BaseLoader
    )
    assert set(workflow["on"]["pull_request"]["paths"]) >= {
        "modules/users/**",
        "modules/background_tasks/**",
        "modules/file_storage/**",
    }


@pytest.mark.parametrize("status", [200, 404, 403, 429, 500, "network"])
def test_npm_only_publishes_missing_exact_version(tmp_path: Path, status: int | str) -> None:
    jobs = yaml.safe_load(WORKFLOW.read_text())["jobs"]
    step = next(
        step for step in jobs["publish-npm"]["steps"] if step.get("name") == "Publish tarball"
    )
    script = step["run"].replace("${{ matrix.package }}", "ui")
    dist = tmp_path / "dist-npm"
    dist.mkdir()
    metadata = json.dumps({"name": "@simple-module-py/ui", "version": "1.2.3"}).encode()
    with tarfile.open(dist / "simple-module-py-ui-1.2.3.tgz", "w:gz") as archive:
        info = tarfile.TarInfo("package/package.json")
        info.size = len(metadata)
        archive.addfile(info, io.BytesIO(metadata))
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    # Only the registry and publishing boundaries are replaced; run the real shell step.
    curl = bin_dir / "curl"
    curl.write_text(
        "#!/bin/bash\n"
        '[[ "$*" == *"https://registry.npmjs.org/@simple-module-py%2Fui/1.2.3"* ]] || exit 90\n'
        + ("exit 7\n" if status == "network" else f"printf '{status}'\n")
    )
    npm = bin_dir / "npm"
    npm.write_text('#!/bin/bash\nprintf "%s\\n" "$*" > published\n')
    curl.chmod(0o755)
    npm.chmod(0o755)
    result = subprocess.run(
        ["bash", "-euo", "pipefail", "-c", script],
        cwd=tmp_path,
        env={**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}"},
        capture_output=True,
        text=True,
    )
    assert (result.returncode == 0) == (status in (200, 404)), result.stderr
    assert (tmp_path / "published").exists() == (status == 404)
    if status == 404:
        assert (
            "publish --access public ./dist-npm/simple-module-py-ui-1.2.3.tgz"
            in (tmp_path / "published").read_text()
        )


def test_preflight_reports_every_new_matrix_package(capsys: pytest.CaptureFixture[str]) -> None:
    from scripts.release_preflight import main

    packages = yaml.safe_load(WORKFLOW.read_text())["jobs"]["publish-pypi"]["strategy"]["matrix"][
        "package"
    ]
    missing = {packages[0], packages[-1]}

    def registry(url: str, *, timeout: int):
        name = url.split("/")[-2]
        assert timeout > 0
        assert url == f"https://pypi.org/pypi/{name}/json"
        assert name in packages
        if name in missing:
            raise HTTPError(url, 404, "Not Found", None, None)
        return io.BytesIO(b"{}")

    with patch("scripts.release_preflight.urlopen", side_effect=registry):
        assert main() == 1
    output = capsys.readouterr().out
    assert all(name in output for name in missing)
    assert "docs/release.md" in output
    assert "pending publisher" in output


def test_preflight_accepts_existing_projects() -> None:
    from scripts.release_preflight import main

    with patch("scripts.release_preflight.urlopen", side_effect=lambda *a, **kw: io.BytesIO(b"{}")):
        assert main() == 0


@pytest.mark.parametrize(
    "error", [HTTPError("url", 503, "Unavailable", None, None), URLError("offline")]
)
def test_preflight_fails_closed_on_registry_errors(error: URLError) -> None:
    from scripts.release_preflight import main

    with patch("scripts.release_preflight.urlopen", side_effect=error):
        assert main() == 1
