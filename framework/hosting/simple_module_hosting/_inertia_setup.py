"""Configure simple_module_inertia with the Jinja2 template."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from simple_module_inertia import InertiaConfig, inertia_dependency_factory
from starlette.requests import Request

from simple_module_hosting._favicon import default_favicon_data_uri
from simple_module_hosting.settings import Settings

logger = logging.getLogger(__name__)

_INERTIA_VERSION = "1.0"
_ROOT_TEMPLATE_FILENAME = "index.html"
_ENTRYPOINT_FILENAME = "main.tsx"
_ROOT_DIRECTORY = "."

# Fallback app name when the (optional) branding module isn't installed. Mirrors
# branding's own default so the unbranded title is identical everywhere.
_DEFAULT_APP_NAME = "SimpleModule"

# Built assets are served from the "/static" mount under "dist/", so production
# asset URLs are prefixed with "static/dist". The manifest is read where Vite
# writes it; the adapter looks the entry up by Vite's own key.
_ASSETS_PREFIX = "static/dist"
_VITE_MANIFEST_RELPATH = Path("static") / "dist" / ".vite" / "manifest.json"


def branding_head(request: Request) -> dict:
    """Branding metadata for the root template's ``<head>``.

    Reads the optional branding module's settings off ``app.state`` by name
    (duck-typed, never imported) so the ``<title>``, ``theme-color`` and
    favicon are already branded *before* React hydrates — otherwise the browser
    paints the default favicon and only swaps on hydration, a visible flicker on
    every full page load. Degrades to the framework default when branding isn't
    installed.

    The favicon URL is read from the module rather than assembled here: branding
    owns its route shape, and framework code must not reach into a plugin
    (SM009). ``BrandingHead`` still applies it client-side too, so a favicon
    changed at runtime updates without a reload. When nothing has been uploaded
    — the state every install starts in — it falls back to a generated mark
    rather than ``None``, because omitting the tag sends the browser to
    ``/favicon.ico``, which this app does not serve.
    """
    services = getattr(request.app.state, "branding", None)
    settings = getattr(services, "settings", None)
    app_name = getattr(settings, "app_name", "") or _DEFAULT_APP_NAME
    accent = getattr(settings, "primary_color", "") or ""
    favicon_url = getattr(services, "favicon_url", None) or default_favicon_data_uri(
        app_name, accent
    )
    return {
        "app_name": app_name,
        "theme_color": accent or None,
        "favicon_url": favicon_url,
    }


def _prod_manifest_path(project_root: Path) -> str:
    """The Vite manifest to read in production, or ``""`` when none is built."""
    candidates = [
        project_root / "host" / _VITE_MANIFEST_RELPATH,
        project_root / _VITE_MANIFEST_RELPATH,
    ]
    found = next((p for p in candidates if p.is_file()), None)
    if found is None:
        logger.warning(
            "Production Vite manifest not found (looked in %s)", [str(c) for c in candidates]
        )
        return ""
    return str(found)


def setup_inertia(
    app: FastAPI,
    settings: Settings,
    modules: list,
    project_root: Path,
) -> InertiaConfig | None:
    """Configure the Inertia adapter and attach the dependency factory to app.state.

    Two host layouts are supported: ``host/templates`` (the framework's
    own host package) and ``templates`` at the project root (what
    ``smpy new`` produces). The first one found wins so it can override
    module-contributed templates.
    """
    from fastapi.templating import Jinja2Templates

    candidate_dirs = [
        project_root / "host" / "templates",
        project_root / "templates",
    ]
    directories: list[Path] = []

    host_templates = next((p for p in candidate_dirs if p.is_dir()), None)
    if host_templates is not None:
        directories.append(host_templates)
    else:
        logger.warning(
            "Host templates directory not found (looked in %s)",
            ", ".join(str(p) for p in candidate_dirs),
        )

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
    # Expose branding metadata to the root template (pre-hydration head tags).
    templates.env.globals["branding_head"] = branding_head

    # The adapter only switches to the asset manifest when environment equals
    # the literal "production"; normalise anything non-dev (staging, qa, ...)
    # to that so built assets are referenced rather than a Vite dev url.
    from simple_module_core.environments import NON_PROD_ENVIRONMENTS

    use_dev_server = settings.environment in NON_PROD_ENVIRONMENTS
    inertia_environment = "development" if use_dev_server else "production"

    inertia_config = InertiaConfig(
        environment=inertia_environment,
        version=_INERTIA_VERSION,
        dev_url=settings.vite_dev_url if use_dev_server else "",
        manifest_json_path="" if use_dev_server else _prod_manifest_path(project_root),
        assets_prefix="" if use_dev_server else _ASSETS_PREFIX,
        templates=templates,
        root_template_filename=_ROOT_TEMPLATE_FILENAME,
        entrypoint_filename=_ENTRYPOINT_FILENAME,
        root_directory=_ROOT_DIRECTORY,
        use_flash_errors=True,
    )
    app.state.inertia_dependency = inertia_dependency_factory(inertia_config)
    return inertia_config
