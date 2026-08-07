"""Tests for the default Docker assets every ``smpy new`` app receives."""

from __future__ import annotations

from pathlib import Path

import pytest
from simple_module_cli.app_project import create_app_project


def _create(
    target: Path,
    selected: list[str] | None = None,
    *,
    db: str = "sqlite",
    flat: bool = False,
) -> None:
    create_app_project(
        target,
        name="demo-app",
        db=db,
        tenancy=False,
        selected=selected,
        flat=flat,
    )


def test_default_app_ships_docker_assets(tmp_path: Path) -> None:
    target = tmp_path / "demo"
    _create(target)
    assert (target / "docker-compose.yml").is_file()
    assert (target / "docker" / "host.Dockerfile").is_file()
    assert (target / ".dockerignore").is_file()
    assert not (target / "docker" / "worker.Dockerfile").exists()


def test_sqlite_scaffold_compose_stays_on_sqlite(tmp_path: Path) -> None:
    # Migrations are dialect-frozen at autogenerate time (sa.false() renders
    # as DEFAULT 0 on SQLite, which Postgres rejects), so a sqlite scaffold
    # must not point its containers at a Postgres service.
    target = tmp_path / "demo"
    _create(target)
    compose = (target / "docker-compose.yml").read_text()
    assert "sqlite+aiosqlite:////app/data/app.db" in compose
    assert "postgresql+asyncpg" not in compose
    assert "image: postgres" not in compose
    assert "appdata:/app/data" in compose
    assert "redis:" not in compose
    assert "worker:" not in compose


def test_postgres_scaffold_compose_ships_postgres(tmp_path: Path) -> None:
    target = tmp_path / "demo"
    _create(target, db="postgres")
    compose = (target / "docker-compose.yml").read_text()
    assert 'POSTGRES_DB: "demo-app"' in compose
    assert "postgresql+asyncpg://postgres:postgres@postgres:5432/demo-app" in compose
    assert "pgdata:" in compose
    assert "sqlite" not in compose


def test_compose_containers_run_production_env(tmp_path: Path) -> None:
    # Development mode emits asset tags pointing at the (absent) Vite dev
    # server, so containers must boot in production mode.
    target = tmp_path / "demo"
    _create(target)
    compose = (target / "docker-compose.yml").read_text()
    assert "SM_ENVIRONMENT: production" in compose


def test_background_tasks_adds_worker_services_on_same_image(tmp_path: Path) -> None:
    target = tmp_path / "demo"
    _create(target, selected=["users", "background_tasks"])
    compose = (target / "docker-compose.yml").read_text()
    for service in ("redis:", "worker:", "beat:"):
        assert service in compose
    assert "scripts.run_worker:celery" in compose
    assert "redisdata:" in compose
    # worker/beat build the app image — no separate worker Dockerfile.
    assert "worker.Dockerfile" not in compose
    assert not (target / "docker" / "worker.Dockerfile").exists()


def test_app_service_gets_broker_urls_with_background_tasks(tmp_path: Path) -> None:
    # BackgroundTasksSettings fails production boot on a localhost broker,
    # so the *app* container needs the compose-network broker too.
    yaml = pytest.importorskip("yaml")
    target = tmp_path / "demo"
    _create(target, selected=["users", "background_tasks"])
    data = yaml.safe_load((target / "docker-compose.yml").read_text())
    app_env = data["services"]["app"]["environment"]
    assert app_env["SM_BG_TASKS_BROKER_URL"] == "redis://redis:6379/0"
    assert app_env["SM_BG_TASKS_RESULT_BACKEND"] == "redis://redis:6379/1"
    # ...and a plain app must not carry background-tasks config.
    plain = tmp_path / "plain"
    _create(plain)
    plain_env = yaml.safe_load((plain / "docker-compose.yml").read_text())["services"]["app"][
        "environment"
    ]
    assert "SM_BG_TASKS_BROKER_URL" not in plain_env


def test_compose_parses_as_yaml_in_every_shape(tmp_path: Path) -> None:
    yaml = pytest.importorskip("yaml")
    shapes = {
        "sqlite-plain": ({}, {"app"}, "appdata"),
        "sqlite-tasks": (
            {"selected": ["users", "background_tasks"]},
            {"app", "redis", "worker", "beat"},
            "appdata",
        ),
        "pg-plain": ({"db": "postgres"}, {"postgres", "app"}, "pgdata"),
        "pg-tasks": (
            {"db": "postgres", "selected": ["users", "background_tasks"]},
            {"postgres", "app", "redis", "worker", "beat"},
            "pgdata",
        ),
    }
    for name, (kwargs, services, volume) in shapes.items():
        target = tmp_path / name
        _create(target, **kwargs)
        data = yaml.safe_load((target / "docker-compose.yml").read_text())
        assert set(data["services"]) == services, name
        assert volume in data["volumes"], name


def test_dockerfile_runs_gen_pages_before_frontend_build(tmp_path: Path) -> None:
    # The Vite build imports modules.generated.{ts,css}, which gen-pages
    # emits from the installed Python modules — order is load-bearing.
    target = tmp_path / "demo"
    _create(target)
    dockerfile = (target / "docker" / "host.Dockerfile").read_text()
    assert "gen-pages" in dockerfile
    assert dockerfile.index("gen-pages") < dockerfile.index("npm run build")
    # Plural `heads` — singular errors once a second module ships its own
    # migration branch label.
    assert "alembic upgrade heads" in dockerfile


def test_flat_mode_gets_flat_dockerfile_variant(tmp_path: Path) -> None:
    target = tmp_path / "demo"
    _create(target, flat=True)
    dockerfile = (target / "docker" / "host.Dockerfile").read_text()
    assert "flat-layout" in dockerfile
    assert "cd host" not in dockerfile
    assert (target / "docker-compose.yml").is_file()
    assert (target / ".dockerignore").is_file()


def test_makefile_gets_docker_targets(tmp_path: Path) -> None:
    target = tmp_path / "demo"
    _create(target)
    makefile = (target / "Makefile").read_text()
    assert "docker-build:" in makefile
    assert "docker-up:" in makefile
    assert "docker-down:" in makefile
