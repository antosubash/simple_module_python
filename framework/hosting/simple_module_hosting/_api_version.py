"""Default ``HostSettings.api_version``: the host project's own version."""

from __future__ import annotations


def default_api_version() -> str:
    """The host project's version, else ``0.0.0``.

    This repo's host is the installed ``simple-module-host`` distribution. A
    scaffolded host is ``package = false`` (never installed), so there is no
    distribution to ask: read ``[project].version`` from its ``pyproject.toml``
    under ``SM_PROJECT_ROOT`` (or the cwd) instead.
    """
    import tomllib
    from importlib.metadata import PackageNotFoundError, version

    from simple_module_core.dotenv import find_env_file

    try:
        return version("simple-module-host")
    except PackageNotFoundError:
        pass
    # Same project-root convention as .env (SM_PROJECT_ROOT, else a bounded walk
    # up from the cwd), so a CLI run from host/ finds the same project as the app.
    root = find_env_file().parent
    for candidate in (root / "host" / "pyproject.toml", root / "pyproject.toml"):
        try:
            project = tomllib.loads(candidate.read_text(encoding="utf-8")).get("project")
        except (OSError, ValueError):  # missing/unreadable, bad UTF-8, bad TOML
            continue
        if not isinstance(project, dict):
            continue
        # The first file declaring a [project] is the host's: a dynamic version
        # must not fall through to an unrelated (workspace-root) project's.
        found = project.get("version")
        return found if isinstance(found, str) and found else "0.0.0"
    return "0.0.0"
