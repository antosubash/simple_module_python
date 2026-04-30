"""Configure fastapi-inertia with the Jinja2 template."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from inertia import InertiaConfig, inertia_dependency_factory

from simple_module_hosting.settings import Settings

logger = logging.getLogger(__name__)

_INERTIA_VERSION = "1.0"
_ROOT_TEMPLATE_FILENAME = "index.html"
_ENTRYPOINT_FILENAME = "main.tsx"
_ROOT_DIRECTORY = "."


def setup_inertia(
    app: FastAPI,
    settings: Settings,
    modules: list,
    project_root: Path,
) -> InertiaConfig | None:
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
        return None

    templates = Jinja2Templates(directory=directories)

    # fastapi-inertia only switches to the asset manifest when environment
    # equals the literal string "production". Anything else (staging, qa,
    # ...) would render a /main.tsx <script> tag served by the SPA fallback
    # as text/html, breaking module loading. Normalize:
    #   * `development`/`testing` → keep the dev-server path (Vite serves
    #     /main.tsx directly).
    #   * Anything else (staging, production, qa, ...) → use the production
    #     manifest so built assets are referenced.
    from simple_module_core.environments import NON_PROD_ENVIRONMENTS

    use_dev_server = settings.environment in NON_PROD_ENVIRONMENTS
    inertia_environment = "development" if use_dev_server else "production"

    inertia_config = InertiaConfig(
        environment=inertia_environment,
        version=_INERTIA_VERSION,
        dev_url=settings.vite_dev_url if use_dev_server else "",
        templates=templates,
        root_template_filename=_ROOT_TEMPLATE_FILENAME,
        entrypoint_filename=_ENTRYPOINT_FILENAME,
        root_directory=_ROOT_DIRECTORY,
        use_flash_errors=True,
    )

    inertia_dep = inertia_dependency_factory(inertia_config)
    app.state.inertia_dependency = inertia_dep
    return inertia_config
