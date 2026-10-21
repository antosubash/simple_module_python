"""Worker image generation and validation through the public CLI."""

import pytest
from simple_module_cli.cli import app
from simple_module_cli.docker_assets import _read, _template_root
from typer.testing import CliRunner


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    fragment = _read(_template_root() / "compose-tasks-postgres.yml.tpl")
    (tmp_path / "compose.yml").write_text("services:\n" + fragment.replace("{{PG_DB}}", "demo"))
    return tmp_path


def invoke(*args):
    return CliRunner().invoke(app, ["docker", "add-worker", *args])


def test_generated_worker(project):
    result = invoke(
        "geo",
        "--queues",
        "geo,heavy",
        "--modules",
        "geo.tasks,other.tasks",
        "--apt",
        "libgdal-dev",
        "--extras",
        "gdal",
        "--extras",
        "images",
    )
    assert result.exit_code == 0, result.output
    docker = (project / "docker/worker-geo.Dockerfile").read_text()
    assert "FROM python:3.12-slim-bookworm AS builder" in docker
    assert "FROM python:3.12-slim-bookworm AS runtime" in docker
    assert "uv sync --all-packages --no-dev --extra gdal --extra images" in docker
    assert docker.count("libgdal-dev") == 2
    assert "USER app" in docker and "--uid 10001" in docker
    assert "HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3" in docker
    assert "inspect ping" in docker
    assert "node" not in docker.lower() and "npm" not in docker and "{{" not in docker
    service = (project / "compose.worker-geo.yml").read_text()
    assert "  worker-geo:" in service
    assert 'SM_BG_TASKS_WORKER_QUEUES: "geo,heavy"' in service
    assert 'SM_BG_TASKS_WORKER_INCLUDE_MODULES: "geo.tasks,other.tasks"' in service
    assert '      - "-Q"\n      - "geo,heavy"' in service
    assert "dockerfile: docker/worker-geo.Dockerfile" in service
    assert "postgres:\n        condition: service_healthy" in service
    assert "@postgres:5432/demo" in service
    assert service.count("    command:") == 1
    assert "  beat:" not in service
    assert "  redis:" not in service.splitlines()


def test_rerun_force_and_multiple_workers(project):
    assert invoke("geo", "--queues", "geo").exit_code == 0
    before = (project / "compose.yml").read_text()
    docker = project / "docker/worker-geo.Dockerfile"
    docker.write_text("custom")
    result = invoke("geo", "--queues", "geo")
    assert result.exit_code != 0 and "--force" in result.output
    assert docker.read_text() == "custom"
    assert (project / "compose.yml").read_text() == before
    assert invoke("geo", "--queues", "geo", "--force").exit_code == 0
    assert (project / "compose.yml").read_text() == before
    assert invoke("other", "--queues", "other").exit_code == 0
    content = (project / "compose.yml").read_text()
    assert content.count("include:") == 1
    assert content.count("  - compose.worker-geo.yml") == 1
    assert content.count("  - compose.worker-other.yml") == 1


@pytest.mark.parametrize("option", ["--queues", "--modules", "--apt", "--extras", "--base"])
@pytest.mark.parametrize("bad", ["foo;id", "foo\nRUN id", "foo bar", "foo$(id)", "foo`id`"])
def test_reject_unsafe_options(project, option, bad):
    args = ["geo", "--queues", "geo", option, bad]
    result = invoke(*args)
    assert result.exit_code != 0
    assert "Invalid" in result.output
    assert not (project / "docker").exists()
    assert not (project / "compose.yml").read_text().startswith("include:")


@pytest.mark.parametrize("name", ["Upper", "../geo", "x;id", "a b", "a\nb", "a" * 42])
def test_reject_bad_names(project, name):
    assert invoke(name, "--queues", "geo").exit_code != 0
    assert not (project / "docker").exists()


def test_existing_include_and_custom_base(project):
    compose = project / "compose.yml"
    compose.write_text("include:\n  - other.yml\n" + compose.read_text())
    assert (
        invoke(
            "geo", "--queues", "geo", "--base", "registry.example:5000/team/python:3.12"
        ).exit_code
        == 0
    )
    assert compose.read_text().count("include:") == 1
    assert "  - other.yml" in compose.read_text()
    assert (
        "FROM registry.example:5000/team/python:3.12"
        in (project / "docker/worker-geo.Dockerfile").read_text()
    )


def test_scaffold_filename_and_sqlite(project):
    (project / "compose.yml").unlink()
    fragment = _read(_template_root() / "compose-tasks-sqlite.yml.tpl")
    (project / "docker-compose.yml").write_text("services:\n" + fragment)
    assert invoke("geo", "--queues", "geo").exit_code == 0
    service = (project / "compose.worker-geo.yml").read_text()
    assert "appdata:/app/data" in service
    assert "postgres:" not in service
    assert "include:" in (project / "docker-compose.yml").read_text()


def test_missing_worker_does_not_write(project):
    (project / "compose.yml").write_text("services: {}\n")
    assert invoke("geo", "--queues", "geo").exit_code != 0
    assert not (project / "docker").exists()


@pytest.mark.parametrize(
    ("option", "bad"),
    [
        ("--queues", "a,,b"),
        ("--queues", "a.b"),
        ("--modules", "a..b"),
        ("--extras", "--dev"),
        ("--apt", "-evil"),
        ("--base", "python:3.12#evil"),
    ],
)
def test_reject_malformed_values(project, option, bad):
    assert invoke("geo", "--queues", "geo", option, bad).exit_code != 0
    assert not (project / "docker").exists()


def test_unmanaged_include_refused_before_writing(project):
    compose = project / "compose.yml"
    original = "include: [other.yml]\n" + compose.read_text()
    compose.write_text(original)
    result = invoke("geo", "--queues", "geo")
    assert result.exit_code != 0 and "block list" in result.output
    assert compose.read_text() == original
    assert not (project / "docker").exists()
