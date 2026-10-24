"""Grant, revoke and list shares (GH #526).

Every grant is checked three ways: the resource type is registered, the
granter passes the owning module's policy for ``share`` on that row, and the
grantee is someone the user directory knows. Rows are tenant-scoped by
``MultiTenantMixin``; revoking hard-deletes.
"""

from __future__ import annotations

import uuid
from typing import Any

from simple_module_core.datetimes import aware as _aware
from simple_module_core.datetimes import utcnow
from simple_module_core.resources import (
    ACTION_SHARE,
    ResourcePrincipal,
    ResourceType,
    ResourceTypeRegistry,
)
from simple_module_core.user_directory import UserDirectory
from simple_module_db.resource_policy import load_authorized
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from sharing.audience import Audience, OpenAudience
from sharing.constants import (
    ERR_BAD_ROLE,
    ERR_EXPIRED,
    ERR_FORBIDDEN,
    ERR_NOT_FOUND,
    ERR_SELF,
    ERR_UNKNOWN_GRANTEE,
    ERR_UNKNOWN_TYPE,
    PERM_MANAGE,
    SUBJECT_USER,
)
from sharing.contracts.schemas import ShareGrant
from sharing.models import ResourceShare
from sharing.policy import row_id


class SharingError(Exception):
    """A refused share operation, with the HTTP status it maps to."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class SharingService:
    def __init__(
        self,
        db: AsyncSession,
        registry: ResourceTypeRegistry,
        directory: UserDirectory,
        audience: Audience | OpenAudience | None = None,
    ) -> None:
        self.db = db
        self.registry = registry
        self.directory = directory
        self.audience = audience or OpenAudience()

    def _type(self, name: str) -> ResourceType:
        resource_type = self.registry.get(name)
        if resource_type is None:
            raise SharingError(422, ERR_UNKNOWN_TYPE)
        return resource_type

    async def _authorize(
        self, principal: ResourcePrincipal, resource_type: ResourceType, resource_id: str
    ) -> Any:
        """The resource row if *principal* may share it: 404 if invisible, 403 if not."""
        try:
            stmt = resource_type.select_by_id(resource_id)
        except ValueError:
            raise SharingError(404, ERR_NOT_FOUND) from None
        row, allowed = await load_authorized(
            self.db, resource_type.policy, principal, ACTION_SHARE, stmt
        )
        if row is None:
            raise SharingError(404, ERR_NOT_FOUND)
        if not allowed:
            raise SharingError(403, ERR_FORBIDDEN)
        return row

    async def grant(self, principal: ResourcePrincipal, data: ShareGrant) -> ResourceShare:
        resource_type = self._type(data.resource_type)
        if data.role not in resource_type.shareable_actions:
            raise SharingError(422, ERR_BAD_ROLE)
        if data.expires_at is not None and _aware(data.expires_at) <= utcnow():
            raise SharingError(422, ERR_EXPIRED)
        row = await self._authorize(principal, resource_type, data.resource_id)
        grantee = (await self.directory.get_many(self.db, [data.subject_id])).get(data.subject_id)
        # One error for "no such user" and "not in your tenant": no enumeration.
        if grantee is None or grantee.id not in await self.audience.visible([grantee.id]):
            raise SharingError(422, ERR_UNKNOWN_GRANTEE)
        if grantee.id == principal.user_id:
            raise SharingError(422, ERR_SELF)
        resource_id = row_id(row)
        share = await self._existing(data.resource_type, resource_id, grantee.id)
        if share is None:
            share = ResourceShare(
                resource_type=data.resource_type,
                resource_id=resource_id,
                subject_type=SUBJECT_USER,
                subject_id=grantee.id,
                role=data.role,
                granted_by=principal.user_id or "",
                expires_at=data.expires_at,
            )
            try:
                async with self.db.begin_nested():
                    self.db.add(share)
                    await self.db.flush()
            except IntegrityError:
                # Another grant may have won the unique-key race.
                share = await self._existing(data.resource_type, resource_id, grantee.id)
                if share is None:
                    raise
        share.role = data.role
        share.expires_at = data.expires_at
        share.granted_by = principal.user_id or ""
        await self.db.flush()
        return share

    async def _existing(self, rtype: str, rid: str, subject_id: str) -> ResourceShare | None:
        stmt = select(ResourceShare).where(
            ResourceShare.resource_type == rtype,
            ResourceShare.resource_id == rid,
            ResourceShare.subject_type == SUBJECT_USER,
            ResourceShare.subject_id == subject_id,
        )
        return (await self.db.execute(stmt)).scalars().first()

    async def revoke(self, principal: ResourcePrincipal, share_id: uuid.UUID) -> None:
        """Delete a share: an admin, its grantee (leaving), or whoever may share the row."""
        share = (
            (await self.db.execute(select(ResourceShare).where(ResourceShare.id == share_id)))
            .scalars()
            .first()
        )
        if share is None:
            raise SharingError(404, ERR_NOT_FOUND)
        if not principal.has(PERM_MANAGE) and share.subject_id != principal.user_id:
            resource_type = self.registry.get(share.resource_type)
            if resource_type is None:
                raise SharingError(404, ERR_NOT_FOUND)
            await self._authorize(principal, resource_type, share.resource_id)
        await self.db.delete(share)
        await self.db.flush()

    async def for_resource(
        self, principal: ResourcePrincipal, rtype: str, resource_id: str
    ) -> list[ResourceShare]:
        """Every share on one row (expired included), for whoever may share it."""
        row = await self._authorize(principal, self._type(rtype), resource_id)
        stmt = (
            select(ResourceShare)
            .where(
                ResourceShare.resource_type == rtype,
                ResourceShare.resource_id == row_id(row),
            )
            .order_by(ResourceShare.created_at)
        )
        return list((await self.db.execute(stmt)).scalars())


__all__ = ["SharingError", "SharingService"]
