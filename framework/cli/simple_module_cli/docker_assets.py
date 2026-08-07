"""Default Docker assets for ``smpy new`` scaffolds.

Every new app ships a container story out of the box: a multi-stage
``docker/host.Dockerfile``, a ``docker-compose.yml`` matched to the
scaffold's DB choice (app on a SQLite volume, or postgres + app; plus
redis/worker/beat when ``background_tasks`` is selected), a
``.dockerignore``, and ``docker-*`` Make targets. This runs for every
scaffold — unlike per-module recipes — because the compose service set
depends on the *whole* module selection, which only the scaffolder knows.

worker/beat reuse the app image with a different command: the workspace
venv already contains everything (``uv sync --all-packages``), so a
separate worker Dockerfile would only duplicate build logic.
"""

from __future__ import annotations

import importlib.resources
import shutil
from pathlib import Path

from simple_module_cli.case import to_kebab_case
from simple_module_cli.recipes import ScaffoldCtx

__all__ = ["scaffold_docker_assets"]

_MAKEFILE_MARKER = "# --- docker --"
_PG_DB_TOKEN = "{{PG_DB}}"
_APP_EXTRA_ENV_TOKEN = "{{APP_EXTRA_ENV}}"

# BackgroundTasksSettings refuses a localhost broker when
# SM_ENVIRONMENT=production, so the app container needs the compose-network
# broker URLs too — not just worker/beat.
_APP_BROKER_ENV = (
    "      SM_BG_TASKS_BROKER_URL: redis://redis:6379/0\n"
    "      SM_BG_TASKS_RESULT_BACKEND: redis://redis:6379/1\n"
)


def _template_root() -> Path:
    base = importlib.resources.files("simple_module_cli")
    return Path(str(base / "templates" / "docker"))


def scaffold_docker_assets(target: Path, ctx: ScaffoldCtx, *, flat: bool = False) -> None:
    """Emit compose + Dockerfile + .dockerignore + Make targets at ``target``.

    The compose file is assembled from fragments: a per-DB base (app alone
    on SQLite, or postgres + app), per-DB worker services when
    ``background_tasks`` is selected, and a computed ``volumes:`` block —
    appending fragments keeps the templates plain YAML instead of merge
    logic.
    """
    templates = _template_root()
    compose_dest = target / "docker-compose.yml"
    dockerfile_dest = target / "docker" / "host.Dockerfile"
    for path in (compose_dest, dockerfile_dest):
        if path.exists():
            raise FileExistsError(
                f"{path} already exists — refusing to clobber. "
                "Remove the file or run `smpy new` against an empty directory."
            )

    dockerfile_dest.parent.mkdir(parents=True, exist_ok=True)
    src_name = "host-flat.Dockerfile" if flat else "host.Dockerfile"
    shutil.copy2(templates / src_name, dockerfile_dest)

    # The compose stack must match the scaffold's DB choice: a migration
    # history is dialect-frozen at autogenerate time (e.g. sa.false()
    # compiles to DEFAULT 0 on SQLite, which Postgres rejects), so pointing
    # a sqlite-scaffolded app at a Postgres container fails on first boot.
    db = "postgres" if ctx.db == "postgres" else "sqlite"
    pg_db = to_kebab_case(ctx.name)
    with_tasks = "background_tasks" in ctx.selected
    compose = (
        _read(templates / f"compose-base-{db}.yml.tpl")
        .replace(_PG_DB_TOKEN, pg_db)
        .replace(_APP_EXTRA_ENV_TOKEN, _APP_BROKER_ENV if with_tasks else "")
    )
    volumes = ["pgdata"] if db == "postgres" else ["appdata"]
    if with_tasks:
        compose += _read(templates / f"compose-tasks-{db}.yml.tpl").replace(_PG_DB_TOKEN, pg_db)
        volumes.append("redisdata")
    compose += "\nvolumes:\n" + "".join(f"  {name}:\n" for name in volumes)
    compose_dest.write_text(compose, encoding="utf-8")

    ignore_dest = target / ".dockerignore"
    if not ignore_dest.exists():
        shutil.copy2(templates / "dockerignore", ignore_dest)

    makefile_path = target / "Makefile"
    existing = makefile_path.read_text(encoding="utf-8") if makefile_path.exists() else ""
    if _MAKEFILE_MARKER not in existing:
        snippet = _read(templates / "Makefile.snippet")
        sep = "" if existing.endswith("\n") or not existing else "\n"
        makefile_path.write_text(existing + sep + snippet, encoding="utf-8")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")
