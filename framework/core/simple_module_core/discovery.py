"""Module discovery via Python entry_points and dependency ordering."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from importlib.metadata import entry_points

from simple_module_core.dotenv import env_str, load_dotenv_into_environ
from simple_module_core.exceptions import CircularDependencyError, InvalidModuleError
from simple_module_core.module import ModuleBase, ModuleMeta

logger = logging.getLogger(__name__)

ENTRY_POINT_GROUP = "simple_module"

DEFAULT_AUTH_PROVIDER = "users"
"""Auth provider activated when several are installed — see select_auth_provider."""


def get_module_package_name(module: ModuleBase) -> str:
    """Return the top-level Python package a module instance belongs to.

    Used by Alembic env.py, the frontend manifest generator, and diagnostics
    to locate a module's files (models, pages, templates) on disk.
    """
    return type(module).__module__.split(".")[0]


def discover_modules(
    enabled: Sequence[str] | None = None,
    *,
    strict: bool = False,
) -> list[ModuleBase]:
    """Discover all installed modules via ``[project.entry-points.simple_module]``.

    Returns instantiated module objects (unsorted). Raises
    :class:`FrameworkVersionError` if any discovered module's
    ``requires_framework`` spec rejects the current framework API version.

    Parameters
    ----------
    enabled:
        Optional allowlist of module names (case-insensitive matched against
        ``ModuleMeta.name``). When ``None`` (default), every installed module
        is loaded. When a list, only modules whose name appears in it are
        loaded. Names that don't match any installed module log a warning.
        An empty list loads nothing.
    strict:
        When ``True``, any invalid module (failed to load, not a
        ``ModuleBase`` subclass, missing/invalid ``meta``) raises
        :class:`InvalidModuleError` immediately. Callers in production
        should pass ``strict=True`` so a broken deployment fails loudly
        at boot rather than silently losing a feature.

        When ``False`` (the default — preserves dev ergonomics), invalid
        modules are logged and skipped.
    """
    # Imported here to avoid a circular import at module load time.
    from simple_module_core.versioning import check_framework_compatibility

    def fail(msg: str, exc: BaseException | None = None) -> None:
        if strict:
            raise InvalidModuleError(msg) from exc
        if exc is not None:
            logger.exception("%s — skipping", msg)
        else:
            logger.error("%s — skipping", msg)

    eps = entry_points(group=ENTRY_POINT_GROUP)
    modules: list[ModuleBase] = []
    allowlist_lower = {name.lower() for name in enabled} if enabled is not None else None

    for ep in eps:
        try:
            module_cls = ep.load()
        except Exception as exc:
            fail(f"Failed to load module entry point '{ep.name}': {exc}", exc)
            continue

        try:
            instance = module_cls()
        except Exception as exc:
            fail(
                f"Failed to instantiate module '{ep.name}' ({module_cls!r}): {exc}",
                exc,
            )
            continue

        if not isinstance(instance, ModuleBase):
            fail(
                f"Entry point '{ep.name}' loaded {module_cls!r} which is not a ModuleBase subclass"
            )
            continue

        meta = getattr(instance, "meta", None)
        if not isinstance(meta, ModuleMeta):
            fail(
                f"Module {module_cls.__qualname__!r} (entry point '{ep.name}') "
                "is missing 'meta = ModuleMeta(...)'"
            )
            continue

        if allowlist_lower is not None and meta.name.lower() not in allowlist_lower:
            logger.info(
                "Module '%s' is installed but not in modules_enabled — skipping",
                meta.name,
            )
            continue

        modules.append(instance)
        logger.info("Discovered module: %s (v%s)", meta.name, meta.version)

    # Warn about allowlist entries that didn't resolve to an installed module.
    if allowlist_lower is not None:
        loaded = {m.meta.name.lower() for m in modules}
        missing = allowlist_lower - loaded
        for name in missing:
            logger.warning(
                "modules_enabled references '%s' which is not installed — ignoring",
                name,
            )

    check_framework_compatibility(modules)
    return modules


def resolve_auth_provider() -> str:
    """Return the configured auth provider name, honoring ``.env``.

    For tools that run outside the host process (``make doctor``, ``smpy host
    gen-pages``) and so have no ``BootstrapSettings`` to read from. The host
    passes ``settings.auth_provider`` to :func:`select_auth_provider` instead.
    """
    load_dotenv_into_environ()
    return env_str("SM_AUTH_PROVIDER", DEFAULT_AUTH_PROVIDER)


def select_auth_provider(
    modules: Sequence[ModuleBase],
    preferred: str = DEFAULT_AUTH_PROVIDER,
    *,
    strict: bool = False,
) -> list[ModuleBase]:
    """Drop every auth provider except ``preferred`` when several are installed.

    ``users`` and ``keycloak`` both claim ``app.state.auth.auth_provider``, so
    only one can be active — that's what SM020 reports. A dev workspace has
    both installed (``uv sync --all-packages`` installs every member), which
    would otherwise fail the boot on a fresh clone. Selecting one here keeps
    the alternative provider installed and testable but inert.

    Nothing is dropped when fewer than two providers are present — a host that
    installs only ``keycloak`` keeps it whatever ``preferred`` says.

    A ``preferred`` that names none of the installed providers is a
    misconfiguration (typically a typo). Leaving every provider mounted means
    two modules write ``app.state.auth.auth_provider`` and the topological
    order silently decides the winner, so this always warns, and with
    ``strict`` raises :class:`InvalidModuleError`. Callers in production
    should pass ``strict=True``: SM020 would catch this, but diagnostics run
    in development only, so nothing else reports it in a deployed app.
    """
    providers = [m for m in modules if getattr(m, "_is_auth_provider", False)]
    if len(providers) < 2:
        return list(modules)

    installed = ", ".join(m.meta.name for m in providers)
    keep = next((m for m in providers if m.meta.name.lower() == preferred.lower()), None)
    if keep is None:
        msg = (
            f"SM_AUTH_PROVIDER={preferred!r} matches none of the installed auth "
            f"providers ({installed}); all of them stay mounted and the last one "
            "registered wins"
        )
        if strict:
            raise InvalidModuleError(msg)
        logger.warning("%s — set it to one of the names above", msg)
        return list(modules)

    logger.info(
        "Auth provider '%s' active (SM_AUTH_PROVIDER); skipping also-installed: %s",
        keep.meta.name,
        ", ".join(m.meta.name for m in providers if m is not keep),
    )
    return [m for m in modules if m is keep or not getattr(m, "_is_auth_provider", False)]


def topological_sort(modules: Sequence[ModuleBase]) -> list[ModuleBase]:
    """Sort modules so dependencies come before dependents.

    Raises ``CircularDependencyError`` if a cycle is detected.
    """
    by_name: dict[str, ModuleBase] = {m.meta.name: m for m in modules}

    # Kahn's algorithm
    in_degree: dict[str, int] = dict.fromkeys(by_name, 0)
    dependents: dict[str, list[str]] = {name: [] for name in by_name}

    for mod in modules:
        for dep_name in mod.meta.depends_on:
            if dep_name not in by_name:
                logger.warning(
                    "Module '%s' depends on '%s' which is not installed — ignoring",
                    mod.meta.name,
                    dep_name,
                )
                continue
            in_degree[mod.meta.name] += 1
            dependents[dep_name].append(mod.meta.name)

    queue: list[str] = [name for name, deg in in_degree.items() if deg == 0]
    result: list[str] = []

    while queue:
        # Sort queue for deterministic ordering
        queue.sort()
        current = queue.pop(0)
        result.append(current)
        for dependent in dependents[current]:
            in_degree[dependent] -= 1
            if in_degree[dependent] == 0:
                queue.append(dependent)

    if len(result) != len(by_name):
        # Find the cycle for a helpful error message
        remaining = set(by_name.keys()) - set(result)
        cycle = _find_cycle(remaining, {n: m.meta.depends_on for n, m in by_name.items()})
        raise CircularDependencyError(cycle)

    return [by_name[name] for name in result]


def _find_cycle(nodes: set[str], deps: dict[str, list[str]]) -> list[str]:
    """Find one cycle in the dependency graph for error reporting."""
    visited: set[str] = set()
    path: list[str] = []

    def dfs(node: str) -> list[str] | None:
        if node in visited:
            idx = path.index(node) if node in path else 0
            return [*path[idx:], node]
        visited.add(node)
        path.append(node)
        for dep in deps.get(node, []):
            if dep in nodes:
                result = dfs(dep)
                if result:
                    return result
        path.pop()
        return None

    for node in nodes:
        visited.clear()
        path.clear()
        cycle = dfs(node)
        if cycle:
            return cycle

    return list(nodes)  # fallback
