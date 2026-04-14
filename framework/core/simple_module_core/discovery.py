"""Module discovery via Python entry_points and dependency ordering."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from importlib.metadata import entry_points

from simple_module_core.exceptions import CircularDependencyError, InvalidModuleError
from simple_module_core.module import ModuleBase, ModuleMeta

logger = logging.getLogger(__name__)

ENTRY_POINT_GROUP = "simple_module"


def discover_modules(*, strict: bool = False) -> list[ModuleBase]:
    """Discover all installed modules via ``[project.entry-points.simple_module]``.

    Parameters
    ----------
    strict:
        When ``True``, any invalid module (failed to load, not a
        ``ModuleBase`` subclass, missing/invalid ``meta``) raises
        :class:`InvalidModuleError` immediately. Callers in production
        should pass ``strict=True`` so a broken deployment fails loudly
        at boot rather than silently losing a feature.

        When ``False`` (the default — preserves dev ergonomics), invalid
        modules are logged and skipped.

    Returns instantiated module objects (unsorted).
    """
    eps = entry_points(group=ENTRY_POINT_GROUP)
    modules: list[ModuleBase] = []

    for ep in eps:
        try:
            module_cls = ep.load()
        except Exception as exc:
            msg = f"Failed to load module entry point '{ep.name}': {exc}"
            if strict:
                raise InvalidModuleError(msg) from exc
            logger.exception("%s", msg)
            continue

        try:
            instance = module_cls()
        except Exception as exc:
            msg = f"Failed to instantiate module '{ep.name}' ({module_cls!r}): {exc}"
            if strict:
                raise InvalidModuleError(msg) from exc
            logger.exception("%s", msg)
            continue

        if not isinstance(instance, ModuleBase):
            msg = (
                f"Entry point '{ep.name}' loaded {module_cls!r} which is not a "
                "ModuleBase subclass"
            )
            if strict:
                raise InvalidModuleError(msg)
            logger.warning("%s — skipping", msg)
            continue

        meta = getattr(instance, "meta", None)
        if not isinstance(meta, ModuleMeta):
            msg = (
                f"Module {module_cls.__qualname__!r} (entry point '{ep.name}') "
                "is missing 'meta = ModuleMeta(...)'"
            )
            if strict:
                raise InvalidModuleError(msg)
            logger.error("%s — skipping", msg)
            continue

        modules.append(instance)
        logger.info("Discovered module: %s (v%s)", meta.name, meta.version)

    return modules


def topological_sort(modules: Sequence[ModuleBase]) -> list[ModuleBase]:
    """Sort modules so dependencies come before dependents.

    Raises ``CircularDependencyError`` if a cycle is detected.
    """
    by_name: dict[str, ModuleBase] = {m.meta.name: m for m in modules}

    # Kahn's algorithm
    in_degree: dict[str, int] = {name: 0 for name in by_name}
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
            return path[idx:] + [node]
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
