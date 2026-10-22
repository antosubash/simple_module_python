"""SM032: a legacy SPA mount whose prefix overlaps a router, static mount or other SPA."""

from __future__ import annotations

from collections.abc import Iterable

from simple_module_core.diagnostics._types import Diagnostic, DiagnosticLevel
from simple_module_core.spa_mount import RESERVED_PREFIXES, prefixes_overlap

SPA_MOUNT_OVERLAP_CODE = "SM032"


def check_spa_mount_overlaps(modules: list, route_paths: Iterable[str] = ()) -> list[Diagnostic]:
    """SM032: a SPA mount prefix overlaps a router prefix, a registered route or another mount.

    ``route_paths`` are the paths actually registered on the app (the host
    supplies them after wiring); meta prefixes alone miss host routes such as
    ``/docs`` or ``/openapi.json``.
    """
    owners: list[tuple[str, str]] = [(p, "framework") for p in RESERVED_PREFIXES]
    owners.extend((path.split("{", 1)[0].rstrip("/"), "a registered route") for path in route_paths)
    for mod in modules:
        for prefix in (mod.meta.route_prefix, mod.meta.view_prefix, mod.meta.admin_view_prefix):
            if prefix:
                owners.append((prefix, mod.meta.name))
        owners.extend((p, mod.meta.name) for p in mod.static_mounts())

    found: list[Diagnostic] = []
    seen: list[tuple[str, str]] = []
    for mod in modules:
        for mount in mod.spa_mounts():
            for prefix, owner in [*owners, *seen]:
                if prefixes_overlap(mount.prefix, prefix):
                    found.append(
                        Diagnostic(
                            level=DiagnosticLevel.ERROR,
                            code=SPA_MOUNT_OVERLAP_CODE,
                            message=(
                                f"SPA mount {mount.prefix!r} overlaps {prefix!r} (owned by {owner})"
                            ),
                            module_name=mod.meta.name,
                            suggestion="Pick a prefix no router, static mount or SPA uses",
                        )
                    )
            seen.append((mount.prefix, mod.meta.name))
    return found
