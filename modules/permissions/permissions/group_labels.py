"""Registry groups as the permission editors show them, in the request's locale."""

from __future__ import annotations

from collections.abc import Callable

from simple_module_core.permissions import PermissionGroup, PermissionRegistry

from permissions.contracts.schemas import PermissionGroupOut


def _label(group: PermissionGroup, translate: Callable[[str], str] | None) -> str:
    # Translator.t() echoes an unknown key back; keep the literal name then.
    if not group.label_key or translate is None:
        return group.name
    translated = translate(group.label_key)
    return group.name if translated == group.label_key else translated


def localized_groups(
    registry: PermissionRegistry, translate: Callable[[str], str] | None = None
) -> list[PermissionGroupOut]:
    return [
        PermissionGroupOut(
            name=g.name,
            label=_label(g, translate),
            permissions=sorted(g.permissions),
            labels=registry.source_labels(g.name),
        )
        for g in registry.groups
    ]
