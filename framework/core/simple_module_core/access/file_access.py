"""Module-owned file policies, usable without installing file_storage (#999)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from simple_module_core.access.resources import ResourcePolicy

ACTION_PUBLISH = "publish"
_STATE_KEY = "file_access_policies"
_OWNER_TAG = re.compile(r"^[a-z][a-z0-9_.-]{0,127}$")


@dataclass(frozen=True)
class FileAccessPolicy:
    policy: ResourcePolicy
    publishable: bool = True


class FileAccessPolicyRegistry:
    """Per-app declarations. Unknown owner tags must fail closed."""

    def __init__(self) -> None:
        self._policies: dict[str, FileAccessPolicy] = {}

    def register(
        self, owner_module: str, policy: ResourcePolicy, *, publishable: bool = True
    ) -> None:
        validate_owner_module(owner_module)
        if owner_module in self._policies:
            raise ValueError(f"File access policy {owner_module!r} is registered twice")
        if not isinstance(policy, ResourcePolicy):
            raise TypeError("File access policies must implement ResourcePolicy")
        self._policies[owner_module] = FileAccessPolicy(policy, publishable)

    def get(self, owner_module: str) -> FileAccessPolicy | None:
        return self._policies.get(owner_module)

    def items(self) -> tuple[tuple[str, FileAccessPolicy], ...]:
        return tuple(self._policies.items())


def validate_owner_module(owner_module: str) -> None:
    if not _OWNER_TAG.fullmatch(owner_module):
        raise ValueError("File owner tag must be a lowercase identifier of at most 128 characters")


def file_access_policies(app: Any) -> FileAccessPolicyRegistry:
    """Get/create the app registry, including during register_settings."""
    registry = getattr(app.state, _STATE_KEY, None)
    if registry is None:
        registry = FileAccessPolicyRegistry()
        setattr(app.state, _STATE_KEY, registry)
    return registry


def register_file_access_policy(
    app: Any, owner_module: str, policy: ResourcePolicy, *, publishable: bool = True
) -> None:
    """Register once from a module's register_settings(app) hook.

    The policy filters SELECTs over StoredFile, using view, publish, edit
    (unpublish), and delete actions. It controls tagged files even for admins.
    """
    file_access_policies(app).register(owner_module, policy, publishable=publishable)
