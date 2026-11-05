"""Delegated permission edits are bounded by platform-level access (#687)."""

from fastapi import HTTPException, Request, status
from simple_module_core.permissions import ADMIN_ROLE, PermissionRegistry, grants
from simple_module_core.user_directory import DirectoryUser
from simple_module_hosting.permissions import resolve_principal_permissions

from permissions.constants import PERM_MANAGE


class PermissionWriteRefused(HTTPException):
    """A 403 with a reason that view routes turn into a form error."""

    def __init__(self, reason: str) -> None:
        super().__init__(status_code=status.HTTP_403_FORBIDDEN, detail=reason)


_PLATFORM_ONLY = "Global permission edits require platform-level access."
_MORE_PRIVILEGED_ACCOUNT = "You cannot manage a more privileged account."


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

    A delegated actor needs platform-level ``permissions.manage`` and may
    change a user or role only if its platform-level access already holds
    everything the target holds: otherwise it could strip access from (or
    reshape) principals stronger than itself. ``role`` is ``(name, keys)``.
    """
    if request is None:
        return
    actor = getattr(request.state, "user", None)
    if actor is not None and ADMIN_ROLE in actor.roles and not actor.is_scoped:
        return
    if actor is None:
        # No principal: skip the grant sources, which expect a real user.
        raise _refuse(_PLATFORM_ONLY)
    held = await resolve_principal_permissions(request, actor, registry, include_tenant_roles=False)
    if not grants(held, PERM_MANAGE):
        raise _refuse(_PLATFORM_ONLY)
    if target is not None:
        # Unknown provider roles cannot prove that the target is within reach.
        if target.roles is None or ADMIN_ROLE in target.roles:
            raise _refuse(_MORE_PRIVILEGED_ACCOUNT)
        target_permissions = await resolve_principal_permissions(
            request, target, registry, include_tenant_roles=False
        )
        if any(not grants(held, key) for key in target_permissions):
            raise _refuse(_MORE_PRIVILEGED_ACCOUNT)
    if role is not None:
        name, role_keys = role
        if name == ADMIN_ROLE or any(not grants(held, key) for key in role_keys):
            raise _refuse("You cannot manage a more privileged role.")
    if any(not grants(held, key) for key in added):
        raise _refuse("You cannot assign permissions you do not hold.")
