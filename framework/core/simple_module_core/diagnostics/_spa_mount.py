"""SM031: a legacy SPA mount whose prefix overlaps a router, static mount or other SPA."""

from __future__ import annotations

from simple_module_core.diagnostics._types import Diagnostic, DiagnosticLevel
from simple_module_core.spa_mount import RESERVED_PREFIXES, prefixes_overlap

SPA_MOUNT_OVERLAP_CODE = "SM031"


def check_spa_mount_overlaps(modules: list) -> list[Diagnostic]:
    """SM031: a SPA mount prefix overlaps a router prefix or another mount."""
    owners: list[tuple[str, str]] = [(p, "framework") for p in RESERVED_PREFIXES]
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
