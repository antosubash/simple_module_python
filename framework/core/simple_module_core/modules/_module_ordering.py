"""Dependency ordering and duplicate protection for discovered modules."""

from __future__ import annotations

import logging
from collections.abc import Sequence

from simple_module_core.modules.module import ModuleBase
from simple_module_core.runtime.exceptions import (
    CircularDependencyError,
    InvalidModuleError,
    MissingDependencyError,
)

logger = logging.getLogger("simple_module_core.modules.discovery")


def missing_dependencies(modules: Sequence[ModuleBase]) -> list[tuple[str, str]]:
    """Every ``(module, dependency)`` pair whose dependency is not in *modules*."""
    names = {m.meta.name for m in modules}
    return [
        (mod.meta.name, dep) for mod in modules for dep in mod.meta.depends_on if dep not in names
    ]


def _ordering_deps(mod: ModuleBase, loaded: dict[str, ModuleBase]) -> list[str]:
    """The loaded modules *mod* must sort after: required and optional alike."""
    wanted = [*mod.meta.depends_on, *mod.meta.optional_depends_on]
    return [dep for dep in dict.fromkeys(wanted) if dep in loaded]


def topological_sort(modules: Sequence[ModuleBase], *, strict: bool = False) -> list[ModuleBase]:
    """Sort modules so dependencies come before dependents.

    ``optional_depends_on`` orders the same way when present and is never
    missing. A ``depends_on`` entry naming a module that is not loaded is
    logged and ignored; with ``strict`` every such pair is collected and
    raised at once as :class:`MissingDependencyError`. The host passes
    ``strict`` outside development: a module whose dependency is absent would
    otherwise boot and fail later, or silently query another module's empty
    tables (GH #501).

    Raises ``CircularDependencyError`` if a cycle is detected.
    """
    by_name: dict[str, ModuleBase] = {}
    for mod in modules:
        if mod.meta.name in by_name:
            first = type(by_name[mod.meta.name])
            later = type(mod)
            message = (
                f"SM008 Duplicate module name '{mod.meta.name}': "
                f"{first.__module__}.{first.__qualname__} and "
                f"{later.__module__}.{later.__qualname__}"
            )
            if strict:
                raise InvalidModuleError(message)
            logger.warning("%s — skipping later module", message)
            continue
        by_name[mod.meta.name] = mod

    missing = missing_dependencies(list(by_name.values()))
    if missing and strict:
        raise MissingDependencyError(missing)
    for name, dep in missing:
        logger.warning("Module '%s' depends on '%s' which is not installed — ignoring", name, dep)

    # Kahn's algorithm
    in_degree: dict[str, int] = dict.fromkeys(by_name, 0)
    dependents: dict[str, list[str]] = {name: [] for name in by_name}

    edges = {m.meta.name: _ordering_deps(m, by_name) for m in by_name.values()}
    for name, deps in edges.items():
        for dep_name in deps:
            in_degree[name] += 1
            dependents[dep_name].append(name)

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
        cycle = _find_cycle(remaining, edges)
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
