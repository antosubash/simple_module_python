"""``RequiresResource`` — the object-level twin of ``RequiresPermission`` (GH #526).

Usage::

    def note_stmt(note_id: uuid.UUID):
        return select(Note).where(Note.id == note_id)


    @router.patch("/{note_id}")
    async def edit(note: Note = Depends(RequiresResource(NOTE_POLICY, ACTION_EDIT, note_stmt))): ...

``loader`` is an ordinary FastAPI dependency (it may take path and query
parameters) returning the *unfiltered* ``SELECT`` for the row. The row is
loaded only through ``policy.filter`` — never ``session.get`` on a raw id:

* not visible to the principal (``view``) → **404**, the same answer as a row
  that does not exist, so ids cannot be probed;
* visible but *action* not allowed → **403** :class:`PermissionDenied`.

API tokens: the dependency counts as a permission gate for ``token_guard``
only when ``permission=`` is given, and then also enforces that permission
(capped at the token's scopes) before loading. Without it a token is refused
on the route, as on any route that names no permission.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any

from fastapi import Depends, HTTPException, Request
from simple_module_core.permission_denied import PermissionDenied
from simple_module_core.resources import ResourcePolicy, ResourcePrincipal
from simple_module_db.deps import get_db
from simple_module_db.resource_policy import load_authorized

from simple_module_hosting.permissions import RequiresPermission, ensure_resolved_permissions
from simple_module_hosting.token_guard import GATE_PERMISSION, TOKEN_GATE_ATTR

RESOURCE_PERMISSION_PREFIX = "resource:"
"""``PermissionDenied.permission`` for an object-level refusal: ``resource:<action>``."""


async def resource_principal(request: Request) -> ResourcePrincipal:
    """The request's principal as a policy sees it; a dependency for list routes.

    Anonymous requests get ``user_id=None`` and no permissions, so a policy
    shows them public rows at most.
    """
    user = getattr(request.state, "user", None)
    if user is None:
        return ResourcePrincipal(user_id=None)
    held = await ensure_resolved_permissions(request)
    user = getattr(request.state, "user", None)  # resolution may demote a stale token
    if user is None:
        return ResourcePrincipal(user_id=None)
    user_id = getattr(user, "id", None)
    return ResourcePrincipal(
        user_id=str(user_id) if user_id is not None else None,
        permissions=frozenset(held),
    )


class RequiresResource:
    """Load the row named by *loader* if *principal* may *action* it; see module docs."""

    def __init__(
        self,
        policy: ResourcePolicy,
        action: str,
        loader: Callable[..., Any],
        *,
        permission: str | None = None,
    ) -> None:
        self.policy = policy
        self.action = action
        self.loader = loader
        self.permission = permission
        self._gate = RequiresPermission(permission) if permission else None
        if permission:
            setattr(self, TOKEN_GATE_ATTR, GATE_PERMISSION)
        # FastAPI reads the instance signature: request, the caller's loader
        # (with its own path params) and the request session.
        kw = inspect.Parameter.KEYWORD_ONLY
        self.__signature__ = inspect.Signature(
            [
                inspect.Parameter("request", kw, annotation=Request),
                inspect.Parameter("stmt", kw, default=Depends(loader)),
                inspect.Parameter("session", kw, default=Depends(get_db)),
            ]
        )

    async def __call__(self, *, request: Request, stmt: Any, session: Any) -> Any:
        if self._gate is not None:
            await self._gate(request)
        principal = await resource_principal(request)
        row, allowed = await load_authorized(session, self.policy, principal, self.action, stmt)
        if row is None:
            raise HTTPException(status_code=404, detail="Not found")
        if not allowed:
            raise PermissionDenied(f"{RESOURCE_PERMISSION_PREFIX}{self.action}")
        return row


__all__ = ["RESOURCE_PERMISSION_PREFIX", "RequiresResource", "resource_principal"]
