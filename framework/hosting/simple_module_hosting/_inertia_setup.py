"""Configure fastapi-inertia with the Jinja2 template."""

from __future__ import annotations

import hashlib
import json
import logging
import tempfile
from pathlib import Path

from fastapi import FastAPI
from inertia import InertiaConfig, inertia_dependency_factory

from simple_module_hosting.settings import Settings

logger = logging.getLogger(__name__)

_INERTIA_VERSION = "1.0"
_ROOT_TEMPLATE_FILENAME = "index.html"
_ENTRYPOINT_FILENAME = "main.tsx"
_ROOT_DIRECTORY = "."
# Built assets are served from the "/static" mount under "dist/", so production
# asset URLs are prefixed with "static/dist".
_ASSETS_PREFIX = "static/dist"
_VITE_MANIFEST_RELPATH = Path("static") / "dist" / ".vite" / "manifest.json"


def _prod_manifest_path(project_root: Path) -> str:
    """Return a manifest path fastapi-inertia can read in production.

    fastapi-inertia looks the entry up by ``f"{root_directory}/{entrypoint}"``
    (here ``"./main.tsx"``), but Vite keys its manifest by the entry's path
    relative to the Vite root (``"main.tsx"``) — so the raw Vite manifest would
    ``KeyError``. Read it, re-key the ``isEntry`` chunk under the key
    fastapi-inertia expects, and write the normalized copy beside the build
    output (falling back to a temp file if that dir is read-only). Returns ``""``
    when no built manifest exists, leaving production assets unconfigured rather
    than crashing at import time.
    """
    candidates = [
        project_root / "host" / _VITE_MANIFEST_RELPATH,
        project_root / _VITE_MANIFEST_RELPATH,
    ]
    vite_manifest = next((p for p in candidates if p.is_file()), None)
    if vite_manifest is None:
        logger.warning(
            "Production Vite manifest not found (looked in %s)", [str(c) for c in candidates]
        )
        return ""
    try:
        data = json.loads(vite_manifest.read_text())
        expected_key = f"{_ROOT_DIRECTORY}/{_ENTRYPOINT_FILENAME}"
        if expected_key not in data:
            entry = next((v for v in data.values() if v.get("isEntry")), None)
            if entry is None:
                # No entry to re-key: degrade gracefully (same as no-manifest)
                # rather than returning a path that KeyErrors at render time.
                logger.warning("No isEntry chunk in Vite manifest %s", vite_manifest)
                return ""
            data = {**data, expected_key: entry}
        out = vite_manifest.parent / "inertia-manifest.json"
        try:
            out.write_text(json.dumps(data))
        except OSError:
            # Build dir read-only (e.g. immutable container layer): fall back to
            # a temp file keyed by the source manifest path so multiple apps on
            # one host don't clobber each other's normalized manifests.
            digest = hashlib.sha1(str(vite_manifest).encode()).hexdigest()[:12]
            out = Path(tempfile.gettempdir()) / f"sm-inertia-manifest-{digest}.json"
            out.write_text(json.dumps(data))
        return str(out)
    except Exception:
        logger.exception("Failed to prepare production Inertia manifest from %s", vite_manifest)
        return ""


def setup_inertia(
    app: FastAPI,
    settings: Settings,
    modules: list,
    project_root: Path,
) -> InertiaConfig | None:
    """Configure fastapi-inertia and attach the dependency factory to app.state.

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
        # Production reads built assets from the Vite manifest; dev serves them
        # from the Vite dev server, so these only matter when not use_dev_server.
        manifest_json_path="" if use_dev_server else _prod_manifest_path(project_root),
        assets_prefix="" if use_dev_server else _ASSETS_PREFIX,
        templates=templates,
        root_template_filename=_ROOT_TEMPLATE_FILENAME,
        entrypoint_filename=_ENTRYPOINT_FILENAME,
        root_directory=_ROOT_DIRECTORY,
        use_flash_errors=True,
    )

    inertia_dep = inertia_dependency_factory(inertia_config)
    app.state.inertia_dependency = inertia_dep
    return inertia_config
