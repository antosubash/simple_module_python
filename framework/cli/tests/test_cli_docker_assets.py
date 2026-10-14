"""Tests for the default Docker assets every ``smpy new`` app receives."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest
from simple_module_cli._env import env_values
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
    # snake_case: a kebab DB name needs quoting in every psql call (GH #443).
    assert 'POSTGRES_DB: "demo_app"' in compose
    assert "@postgres:5432/demo_app" in compose
    assert "pgdata:" in compose
    assert "sqlite" not in compose


def test_postgres_compose_has_no_default_password_or_public_port(tmp_path: Path) -> None:
    # GH #444: the containers run in production mode, so the DB must not be
    # reachable from the network with a well-known superuser password.
    target = tmp_path / "demo"
    _create(target, db="postgres", selected=["users", "background_tasks"])
    compose = (target / "docker-compose.yml").read_text()
    assert "postgres:postgres" not in compose
    assert "POSTGRES_PASSWORD: postgres" not in compose
    assert '"5432:5432"' not in compose
    assert '"6379:6379"' not in compose
    assert '"127.0.0.1:5432:5432"' in compose
    assert compose.count("${POSTGRES_PASSWORD:?") == 4  # postgres, app, worker, beat


def test_postgres_scaffold_env_matches_compose_password(tmp_path: Path) -> None:
    target = tmp_path / "demo"
    _create(target, db="postgres")
    env = env_values((target / ".env").read_text())
    password = env["POSTGRES_PASSWORD"]
    assert len(password) >= 20
    assert (
        env["SM_DATABASE_URL"]
        == f"postgresql+asyncpg://postgres:{password}@localhost:5432/demo_app"
    )
    example = (target / ".env.example").read_text()
    assert password not in example
    assert "POSTGRES_PASSWORD=\n" in example


def test_postgres_password_must_be_url_safe_is_documented_and_enforced(tmp_path: Path) -> None:
    # GH #472: compose cannot URL-encode, so the raw password lands in the URL.
    target = tmp_path / "demo"
    _create(target, db="postgres")
    example = (target / ".env.example").read_text()
    assert "URL-safe" in example
    assert example.index("URL-safe") < example.index("POSTGRES_PASSWORD=")
    makefile = (target / "Makefile").read_text()
    assert makefile.index("URL-safe") < makefile.index("docker compose up")


@pytest.mark.skipif(shutil.which("make") is None, reason="needs make")
@pytest.mark.parametrize(
    ("env_body", "ok"),
    [
        ("POSTGRES_PASSWORD=abc-_.~123\n", True),
        ('POSTGRES_PASSWORD="abc123"\n', True),
        ("POSTGRES_PASSWORD='abc123'\n", True),
        ("POSTGRES_PASSWORD=abc123\r\n", True),
        ("POSTGRES_PASSWORD=abc123 # local only\n", True),
        ("POSTGRES_PASSWORD=\n", True),
        ("# POSTGRES_PASSWORD=a/b\nPOSTGRES_PASSWORD=ok\n", True),
        ("POSTGRES_PASSWORD=a/b@c\n", False),
        ('POSTGRES_PASSWORD="a:b"\n', False),
        ("POSTGRES_PASSWORD=ok\nPOSTGRES_PASSWORD=p#ss word\n", False),
    ],
)
def test_docker_up_guard_reads_password_like_compose(
    tmp_path: Path, env_body: str, ok: bool
) -> None:
    target = tmp_path / "demo"
    _create(target, db="postgres")
    (target / ".env").write_bytes(env_body.encode())
    # Stub `docker` so a passing guard does not start anything.
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    stub = bin_dir / "docker"
    stub.write_text("#!/bin/sh\nexit 0\n")
    stub.chmod(0o755)
    env = {**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"}
    result = subprocess.run(
        ["make", "docker-up"], cwd=target, env=env, capture_output=True, text=True, check=False
    )
    assert (result.returncode == 0) is ok, result.stderr


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
