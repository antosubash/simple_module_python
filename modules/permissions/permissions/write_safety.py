"""Delegated grant writes are bounded by the actor's effective access (#687)."""

from fastapi import HTTPException, Request, status
from simple_module_core.permissions import ADMIN_ROLE, PermissionRegistry, grants
from simple_module_core.user_directory import DirectoryUser
from simple_module_hosting.permissions import (
    ensure_resolved_permissions,
    resolve_principal_permissions,
)


class PermissionWriteRefused(HTTPException):
    """A 403 with a reason but no ``required_permission``: the actor holds
    ``permissions.manage``, so nothing may claim it is missing. View routes turn
    it into a form error so the edit screen can show the reason."""

    def __init__(self, reason: str) -> None:
        super().__init__(status_code=status.HTTP_403_FORBIDDEN, detail=reason)


def _refuse(reason: str) -> PermissionWriteRefused:
    return PermissionWriteRefused(reason)


async def check_permission_write(
    request: Request | None,
    registry: PermissionRegistry,
    added: set[str],
    target: DirectoryUser | None = None,
    *,
    role: tuple[str, set[str]] | None = None,
) -> None:
    """Trusted in-process calls and unscoped admins may assign any registered key.

    A delegated actor may change a user or role only if it already holds
    everything the target holds: otherwise it could strip access from (or
    reshape) principals stronger than itself. ``role`` is ``(name, keys)``.
    """
    if request is None:
        return
    actor = getattr(request.state, "user", None)
    if actor is not None and ADMIN_ROLE in actor.roles and not actor.is_scoped:
        return
    held = await ensure_resolved_permissions(request)
    if target is not None:
        # Unknown provider roles cannot prove that the target is within reach.
        if target.roles is None or ADMIN_ROLE in target.roles:
            raise _refuse("You cannot manage a more privileged account.")
        target_permissions = await resolve_principal_permissions(request, target, registry)
        if any(not grants(held, key) for key in target_permissions):
            raise _refuse("You cannot manage a more privileged account.")
    if role is not None:
        name, role_keys = role
        if name == ADMIN_ROLE or any(not grants(held, key) for key in role_keys):
            raise _refuse("You cannot manage a more privileged role.")
    if any(not grants(held, key) for key in added):
        raise _refuse("You cannot assign permissions you do not hold.")
