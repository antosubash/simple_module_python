"""Per-module post-scaffold recipes.

A recipe is invoked by ``smpy new`` after the base host scaffold lands. It
performs module-specific actions (write helper scripts, append Make
targets, drop a docker-compose stack). The framework layer is kept free
of devex concerns — recipes know about Makefiles and compose, framework
scaffolding does not.
"""

from __future__ import annotations

import importlib.resources
import shutil
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from simple_module_cli._env import set_env_key

__all__ = [
    "RECIPES",
    "BackgroundTasksRecipe",
    "Recipe",
    "ScaffoldCtx",
]

_BG_BROKER_ENV_KEY = "SM_BG_TASKS_BROKER_URL"
_BG_BROKER_DEFAULT = "redis://redis:6379/0"
_MAKEFILE_MARKER = "# --- background_tasks --"


@dataclass(frozen=True)
class ScaffoldCtx:
    name: str
    db: str
    tenancy: bool
    selected: Sequence[str]


class Recipe(Protocol):
    def apply(self, target: Path, ctx: ScaffoldCtx) -> None: ...


def _optional_template_root(name: str) -> Path:
    """Resolve ``templates/host/_optional/<name>/`` from package data."""
    base = importlib.resources.files("simple_module_cli")
    return Path(str(base / "templates" / "host" / "_optional" / name))


class BackgroundTasksRecipe:
    """Lays down run_worker.py + broker env keys + Make targets.

    The compose services (redis/worker/beat) and the shared app image come
    from the default Docker assets every scaffold gets — see
    :mod:`simple_module_cli.docker_assets`.
    """

    def apply(self, target: Path, ctx: ScaffoldCtx) -> None:
        templates = _optional_template_root("background_tasks")

        run_worker_dest = target / "scripts" / "run_worker.py"
        if run_worker_dest.exists():
            raise FileExistsError(
                f"{run_worker_dest} already exists — refusing to clobber. "
                "Remove the file or run `smpy new` against an empty directory."
            )

        run_worker_dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(templates / "run_worker.py", run_worker_dest)

        env_path = target / ".env.example"
        env_text = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
        env_path.write_text(
            set_env_key(env_text, _BG_BROKER_ENV_KEY, _BG_BROKER_DEFAULT),
            encoding="utf-8",
        )

        makefile_path = target / "Makefile"
        snippet = (templates / "Makefile.snippet").read_text(encoding="utf-8")
        existing = makefile_path.read_text(encoding="utf-8") if makefile_path.exists() else ""
        if _MAKEFILE_MARKER not in existing:
            sep = "" if existing.endswith("\n") or not existing else "\n"
            makefile_path.write_text(existing + sep + snippet, encoding="utf-8")


RECIPES: dict[str, Recipe] = {
    "background_tasks": BackgroundTasksRecipe(),
}
