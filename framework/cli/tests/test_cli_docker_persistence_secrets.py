"""Docker scaffolds keep secrets out and filesystem uploads on a volume."""

import re
from pathlib import Path

import pytest
import yaml
from simple_module_cli.app_project import create_app_project

ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize("source", ["repo", "scaffold"])
def test_cli_dockerignore_excludes_secret_variants(tmp_path, source):
    target = ROOT
    if source == "scaffold":
        target = tmp_path / "demo"
        create_app_project(target, name="demo", db="sqlite", tenancy=False)
    patterns = (target / ".dockerignore").read_text().splitlines()
    for path in (
        ".env",
        ".env.production",
        "host/.env.local",
        "deploy/tls/server.pem",
        "keys/signing.key",
        "credentials.json",
        "config/credentials-prod.json",
        "secrets/token",
        "host/secrets/token",
    ):
        assert _ignored(patterns, path), path
    for path in (".env.example", "host/.env.example", "modules/users/users/credentials.py"):
        assert not _ignored(patterns, path), path


def _ignored(patterns: list[str], path: str) -> bool:
    """Approximate Docker's matcher: last matching rule wins, ``!`` re-includes."""
    ignored = False
    for raw in patterns:
        rule = raw.strip()
        if not rule or rule.startswith("#"):
            continue
        negate = rule.startswith("!")
        rule = rule.lstrip("!").strip("/")
        regex = re.escape(rule).replace(r"\*\*/", "(?:.*/)?").replace(r"\*", "[^/]*")
        if re.fullmatch(regex + "(?:/.*)?", path):
            ignored = not negate
    return ignored


@pytest.mark.parametrize("db", ["sqlite", "postgres"])
@pytest.mark.parametrize("flat", [False, True])
@pytest.mark.parametrize("tasks", [False, True])
def test_cli_docker_uploads_share_persistent_appdata(tmp_path, db, flat, tasks):
    target = tmp_path / "demo"
    create_app_project(
        target,
        name="demo",
        db=db,
        tenancy=False,
        flat=flat,
        selected=["users", "file_storage", *(["background_tasks"] if tasks else [])],
    )
    compose = yaml.safe_load((target / "docker-compose.yml").read_text())
    assert "appdata" in compose["volumes"]
    for name in ("app", "worker", "beat") if tasks else ("app",):
        assert "appdata:/app/data" in compose["services"][name]["volumes"]
    dockerfile = (target / "docker/host.Dockerfile").read_text()
    assert "mkdir -p /app/data/uploads" in dockerfile
    assert "ln -s /app/data/uploads /app/uploads" in dockerfile
    if not flat:
        assert "ln -s /app/data/uploads /app/host/uploads" in dockerfile
    ignored = (target / ".dockerignore").read_text().splitlines()
    assert {"uploads/", "host/uploads/"} <= set(ignored)


def test_cli_repo_docker_uploads_use_existing_data_volume():
    dockerfile = (ROOT / "Dockerfile").read_text()
    assert "mkdir -p /app/data/uploads" in dockerfile
    assert "ln -s /app/data/uploads /app/uploads" in dockerfile
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
    assert "appdata:/app/data" in compose["services"]["app"]["volumes"]
    makefile = (ROOT / "Makefile").read_text()
    run_target = makefile.split("docker-app: docker-build", 1)[1].split("docker-compose-app:")[0]
    assert "-v simple-module-python-data:/app/data" in run_target


def test_cli_worker_image_keeps_uploads_on_data_volume():
    from simple_module_cli import docker_cmd

    template = (
        Path(docker_cmd.__file__).parent / "templates" / "docker" / "worker.Dockerfile.tpl"
    ).read_text()
    assert "ln -s /app/data/uploads /app/uploads" in template
