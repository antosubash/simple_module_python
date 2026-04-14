"""Configure fastapi-inertia with the Jinja2 template."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from inertia import InertiaConfig, inertia_dependency_factory

from simple_module_hosting.settings import Settings

logger = logging.getLogger(__name__)


def setup_inertia(app: FastAPI, settings: Settings, project_root: Path) -> None:
    """Configure fastapi-inertia and attach the dependency factory to app.state."""
    from fastapi.templating import Jinja2Templates

    templates_dir = project_root / "host" / "templates"

    if not templates_dir.is_dir():
        logger.warning("Templates directory not found at %s", templates_dir)
        return

    templates = Jinja2Templates(directory=templates_dir)

    inertia_config = InertiaConfig(
        environment=settings.environment,  # ty: ignore[invalid-argument-type]
        version="1.0",
        dev_url=settings.vite_dev_url if settings.is_development else "",
        templates=templates,
        root_template_filename="index.html",
        entrypoint_filename="main.tsx",
        root_directory=".",
        use_flash_errors=True,
    )

    inertia_dep = inertia_dependency_factory(inertia_config)
    app.state.inertia_config = inertia_config
    app.state.inertia_dependency = inertia_dep
