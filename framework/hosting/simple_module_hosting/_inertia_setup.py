"""Configure fastapi-inertia with the Jinja2 template."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from inertia import InertiaConfig, inertia_dependency_factory

from simple_module_hosting.settings import Settings

logger = logging.getLogger(__name__)


def setup_inertia(
    app: FastAPI,
    settings: Settings,
    modules: list,
    project_root: Path,
) -> None:
    """Configure fastapi-inertia and attach the dependency factory to app.state.

    The host's own ``host/templates`` directory is first in the search path so
    it can override module-contributed templates. Each installed module
    contributes additional directories via ``ModuleBase.template_dirs()``.
    """
    from fastapi.templating import Jinja2Templates

    host_templates = project_root / "host" / "templates"
    directories: list[Path] = []

    if host_templates.is_dir():
        directories.append(host_templates)
    else:
        logger.warning("Host templates directory not found at %s", host_templates)

    for mod in modules:
        for path in mod.template_dirs():
            if Path(path).is_dir():
                directories.append(Path(path))
            else:
                logger.warning(
                    "Module '%s' declared template dir %s but it does not exist",
                    mod.meta.name,
                    path,
                )

    if not directories:
        logger.warning("No usable template directories — Inertia will fail to render views")
        return

    templates = Jinja2Templates(directory=directories)

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
