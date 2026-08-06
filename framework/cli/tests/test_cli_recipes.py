"""Tests for per-module post-scaffold recipes."""

from __future__ import annotations

from pathlib import Path

import pytest
from simple_module_cli.recipes import (
    RECIPES,
    BackgroundTasksRecipe,
    ScaffoldCtx,
)
from simple_module_cli.scaffolding import create_host


def _scaffold_minimal_host(target: Path) -> None:
    create_host(target, name="demo", modules=["Users"])


def _ctx() -> ScaffoldCtx:
    return ScaffoldCtx(name="demo", db="sqlite", tenancy=False, selected=("background_tasks",))


def test_background_tasks_recipe_registered() -> None:
    assert "background_tasks" in RECIPES
    assert isinstance(RECIPES["background_tasks"], BackgroundTasksRecipe)


def test_recipe_writes_run_worker_script(tmp_path: Path) -> None:
    _scaffold_minimal_host(tmp_path)
    BackgroundTasksRecipe().apply(tmp_path, _ctx())
    script = tmp_path / "scripts" / "run_worker.py"
    assert script.is_file()
    text = script.read_text()
    assert "from background_tasks.celery_app import build_celery" in text
    assert "celery = build_celery(BackgroundTasksSettings())" in text


def test_recipe_leaves_docker_assets_to_the_scaffold(tmp_path: Path) -> None:
    # Compose + Dockerfile are default scaffold output (docker_assets.py);
    # the recipe must not write or clobber them.
    _scaffold_minimal_host(tmp_path)
    BackgroundTasksRecipe().apply(tmp_path, _ctx())
    assert not (tmp_path / "docker-compose.yml").exists()
    assert not (tmp_path / "docker").exists()


def test_recipe_tolerates_pre_existing_compose(tmp_path: Path) -> None:
    # docker_assets.py runs after recipes in create_app_project, but the
    # recipe API is also public — a compose file on disk is not an error.
    _scaffold_minimal_host(tmp_path)
    (tmp_path / "docker-compose.yml").write_text("services: {}\n")
    BackgroundTasksRecipe().apply(tmp_path, _ctx())
    assert (tmp_path / "scripts" / "run_worker.py").is_file()


def test_recipe_appends_makefile_targets(tmp_path: Path) -> None:
    _scaffold_minimal_host(tmp_path)
    BackgroundTasksRecipe().apply(tmp_path, _ctx())
    makefile = (tmp_path / "Makefile").read_text()
    assert "worker:" in makefile
    assert "beat:" in makefile
    assert "worker-docker:" in makefile


def test_recipe_sets_broker_url_env_var(tmp_path: Path) -> None:
    _scaffold_minimal_host(tmp_path)
    BackgroundTasksRecipe().apply(tmp_path, _ctx())
    env_text = (tmp_path / ".env.example").read_text()
    assert "SM_BG_TASKS_BROKER_URL=redis://redis:6379/0" in env_text


def test_recipe_makefile_snippet_idempotent(tmp_path: Path) -> None:
    _scaffold_minimal_host(tmp_path)
    BackgroundTasksRecipe().apply(tmp_path, _ctx())
    first = (tmp_path / "Makefile").read_text()
    with pytest.raises(FileExistsError):
        BackgroundTasksRecipe().apply(tmp_path, _ctx())
    assert (tmp_path / "Makefile").read_text() == first


def test_recipe_errors_on_existing_run_worker(tmp_path: Path) -> None:
    _scaffold_minimal_host(tmp_path)
    (tmp_path / "scripts").mkdir(exist_ok=True)
    (tmp_path / "scripts" / "run_worker.py").write_text("# user-authored\n")
    with pytest.raises(FileExistsError):
        BackgroundTasksRecipe().apply(tmp_path, _ctx())
