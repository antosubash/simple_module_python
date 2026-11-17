"""Worker image generation and validation through the public CLI."""

import re

import pytest
import yaml
from background_tasks.core.settings import BackgroundTasksSettings
from background_tasks.worker.task_routing import ModuleTaskConfig, select_packages
from simple_module_cli.cli import app
from simple_module_cli.docker_assets import _read, _template_root
from typer.testing import CliRunner


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    fragment = _read(_template_root() / "compose-tasks-postgres.yml.tpl")
    (tmp_path / "compose.yml").write_text("services:\n" + fragment.replace("{{PG_DB}}", "demo"))
    return tmp_path


_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def invoke(*args):
    # Wide and colourless: CI forces Rich colour, which splits option names
    # with escape codes and wraps the error box.
    runner = CliRunner(env={"COLUMNS": "200", "NO_COLOR": "1", "TERM": "dumb"})
    return runner.invoke(app, ["docker", "add-worker", *args])


def plain(output: str) -> str:
    return " ".join(_ANSI.sub("", output).split())


def test_generated_worker(project, monkeypatch):
    compose = project / "compose.yml"
    compose.write_text(
        compose.read_text().replace(
            "    environment:\n",
            "    environment:\n"
            "    # Worker queue override\n"
            '      SM_BG_TASKS_WORKER_QUEUES: "old"\n'
            '      "SM_BG_TASKS_INCLUDE_MODULES": "old"\n',
            1,
        )
    )
    result = invoke(
        "geo",
        "--queues",
        "geo,heavy",
        "--modules",
        "geo,other",
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
    assert service.count("SM_BG_TASKS_WORKER_QUEUES") == 1
    assert service.count("SM_BG_TASKS_INCLUDE_MODULES") == 1
    assert 'SM_BG_TASKS_WORKER_QUEUES: "geo,heavy"' in service
    assert 'SM_BG_TASKS_INCLUDE_MODULES: "geo,other"' in service
    assert "    # Worker queue override\n" in service
    env = yaml.safe_load(service)["services"]["worker-geo"]["environment"]
    for key in ("SM_BG_TASKS_WORKER_QUEUES", "SM_BG_TASKS_INCLUDE_MODULES"):
        monkeypatch.setenv(key, env[key])
    monkeypatch.delenv("SM_BG_TASKS_EXCLUDE_MODULES", raising=False)
    configs = {"other": ModuleTaskConfig(package="other", queues=frozenset({"other"}))}
    assert select_packages(["other"], configs, BackgroundTasksSettings()) == ["other"]
    assert '      - "-Q"\n      - "geo,heavy"' in service
    assert "dockerfile: docker/worker-geo.Dockerfile" in service
    assert "postgres:\n        condition: service_healthy" in service
    assert "@postgres:5432/demo" in service
    assert service.count("    command:") == 1
    assert "  beat:" not in service
    assert "  redis:" not in service.splitlines()


def test_rerun_force_and_multiple_workers(project):
    assert invoke("geo", "--queues", "geo").exit_code == 0
    assert "SM_BG_TASKS_INCLUDE_MODULES" not in (project / "compose.worker-geo.yml").read_text()
    before = (project / "compose.yml").read_text()
    docker = project / "docker/worker-geo.Dockerfile"
    docker.write_text("custom")
    result = invoke("geo", "--queues", "geo")
    assert result.exit_code != 0 and "--force" in plain(result.output)
    assert docker.read_text() == "custom"
    assert (project / "compose.yml").read_text() == before
    assert invoke("geo", "--queues", "geo", "--force").exit_code == 0
    assert (project / "compose.yml").read_text() == before
    assert invoke("other", "--queues", "other").exit_code == 0
    content = (project / "compose.yml").read_text()
    assert content.count("include:") == 1
    assert content.count("  - compose.worker-geo.yml") == 1
    assert content.count("  - compose.worker-other.yml") == 1


def test_omitting_modules_preserves_base_worker_include(project):
    compose = project / "compose.yml"
    entry = '      SM_BG_TASKS_INCLUDE_MODULES: "other"\n'
    compose.write_text(
        compose.read_text().replace("    environment:\n", "    environment:\n" + entry, 1)
    )
    assert invoke("geo", "--queues", "geo").exit_code == 0
    service = (project / "compose.worker-geo.yml").read_text()
    assert service.count("SM_BG_TASKS_INCLUDE_MODULES") == 1
    assert entry in service


def test_worker_preserves_multiline_environment_value_with_blank_line(project):
    compose = project / "compose.yml"
    compose.write_text(
        compose.read_text().replace(
            "    environment:\n",
            "    environment:\n"
            "      MESSAGE: |\n"
            "        first\n  \n        last\n"
            "      SM_BG_TASKS_WORKER_QUEUES: old\n",
            1,
        )
    )
    result = invoke("geo", "--queues", "geo")
    assert result.exit_code == 0, result.output
    service = (project / "compose.worker-geo.yml").read_text()
    env = yaml.safe_load(service)["services"]["worker-geo"]["environment"]
    assert env["MESSAGE"] == "first\n\nlast\n"
    assert env["SM_BG_TASKS_WORKER_QUEUES"] == "geo"


@pytest.mark.parametrize(
    "entries",
    [
        "      - SM_BG_TASKS_WORKER_QUEUES=old\n",
        "      SM_BG_TASKS_WORKER_QUEUES: |\n        old\n\n        other\n",
        "      SM_BG_TASKS_WORKER_QUEUES: old,\n        other\n",
        "      SM_BG_TASKS_WORKER_QUEUES: &queues old\n",
        "      OTHER: &queues old\n      SM_BG_TASKS_WORKER_QUEUES: *queues\n",
        "      SM_BG_TASKS_INCLUDE_MODULES: &modules old\n",
        "      &env\n      SM_BG_TASKS_WORKER_QUEUES: old\n",
    ],
)
def test_worker_refuses_unsupported_environment_before_writing(project, entries):
    compose = project / "compose.yml"
    original = re.sub(
        r"    environment:\n(?:      [^\n]*\n)+",
        "    environment:\n" + entries,
        compose.read_text(),
        count=1,
    )
    compose.write_text(original)

    result = invoke("geo", "--queues", "geo", "--modules", "geo")

    assert result.exit_code == 2, result.output
    assert "environment" in plain(result.output)
    assert compose.read_text() == original
    assert not (project / "docker").exists()
    assert not (project / "compose.worker-geo.yml").exists()


def test_modules_rejects_task_module_paths(project):
    result = invoke("geo", "--queues", "geo", "--modules", "geo.tasks")
    assert result.exit_code != 0
    assert "top-level Python package names" in plain(result.output)
    assert not (project / "compose.worker-geo.yml").exists()


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


@pytest.mark.parametrize("key", ["SM_BG_TASKS_WORKER_QUEUES", "SM_BG_TASKS_INCLUDE_MODULES"])
def test_bare_inherited_environment_keys_are_accepted(project, key):
    compose = project / "compose.yml"
    compose.write_text(
        compose.read_text().replace("    environment:\n", f"    environment:\n      {key}:\n", 1)
    )
    result = invoke("geo", "--queues", "geo")
    assert result.exit_code == 0, plain(result.output)
    service = yaml.safe_load((project / "compose.worker-geo.yml").read_text())
    env = next(iter(service["services"].values()))["environment"]
    assert env["SM_BG_TASKS_WORKER_QUEUES"] == "geo"
