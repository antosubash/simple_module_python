"""Grant, revoke and list shares (GH #526).

Every grant is checked three ways: the resource type is registered, the
granter passes the owning module's policy for ``share`` on that row, and the
subject is validated by its registered provider. Rows are tenant-scoped by
``MultiTenantMixin``; revoking hard-deletes.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
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

from sharing.contracts.schemas import ShareCandidate, ShareGrant
from sharing.contracts.subjects import SubjectContext, SubjectRegistry
from sharing.core.audience import Audience, OpenAudience
from sharing.core.constants import (
    CANDIDATES_MAX,
    CANDIDATES_MIN_QUERY,
    ERR_BAD_ROLE,
    ERR_EXPIRED,
    ERR_FORBIDDEN,
    ERR_NOT_FOUND,
    ERR_SELF,
    ERR_UNKNOWN_GRANTEE,
    ERR_UNKNOWN_SUBJECT,
    ERR_UNKNOWN_TYPE,
    PERM_MANAGE,
    SUBJECT_USER,
)
from sharing.core.policy import resolve_roles, row_id
from sharing.core.subjects import subjects_for
from sharing.models import ResourceShare


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
        subjects: SubjectRegistry | None = None,
        *,
        translate: Callable[[str], str] | None = None,
    ) -> None:
        self.db = db
        self.registry = registry
        self.directory = directory
        self.audience = audience or OpenAudience()
        self.subjects = subjects
        self.translate = translate

    def context(self, principal: ResourcePrincipal) -> SubjectContext:
        return SubjectContext(self.db, self.directory, self.audience, principal, self.translate)

    def subject_registry(self, principal: ResourcePrincipal) -> SubjectRegistry:
        return self.subjects if self.subjects is not None else subjects_for(principal)

    def _subject(self, principal: ResourcePrincipal, name: str):
        provider = self.subject_registry(principal).get(name)
        if provider is None:
            raise SharingError(422, ERR_UNKNOWN_SUBJECT)
        return provider

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
        if data.role not in resolve_roles(resource_type.share_roles):
            raise SharingError(422, ERR_BAD_ROLE)
        if data.expires_at is not None and _aware(data.expires_at) <= utcnow():
            raise SharingError(422, ERR_EXPIRED)
        row = await self._authorize(principal, resource_type, data.resource_id)
        provider = self._subject(principal, data.subject_type)
        subject_id = await provider.validate(self.context(principal), data.subject_id)
        if subject_id is None:
            raise SharingError(422, ERR_UNKNOWN_GRANTEE)
        if data.subject_type == SUBJECT_USER and subject_id == principal.user_id:
            raise SharingError(422, ERR_SELF)
        resource_id = row_id(row)
        share = await self._existing(data.resource_type, resource_id, subject_id, data.subject_type)
        if share is None:
            share = ResourceShare(
                resource_type=data.resource_type,
                resource_id=resource_id,
                subject_type=data.subject_type,
                subject_id=subject_id,
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
                share = await self._existing(
                    data.resource_type, resource_id, subject_id, data.subject_type
                )
                if share is None:
                    raise
        share.role = data.role
        share.expires_at = data.expires_at
        share.granted_by = principal.user_id or ""
        await self.db.flush()
        return share

    async def _existing(
        self, rtype: str, rid: str, subject_id: str, subject_type: str = SUBJECT_USER
    ) -> ResourceShare | None:
        stmt = select(ResourceShare).where(
            ResourceShare.resource_type == rtype,
            ResourceShare.resource_id == rid,
            ResourceShare.subject_type == subject_type,
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
        if not principal.has(PERM_MANAGE) and not (
            share.subject_type == SUBJECT_USER and share.subject_id == principal.user_id
        ):
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

    async def candidates(
        self,
        principal: ResourcePrincipal,
        rtype: str,
        resource_id: str,
        query: str,
        subject_type: str = SUBJECT_USER,
    ) -> list[ShareCandidate]:
        resource_type = self._type(rtype)
        row = await self._authorize(principal, resource_type, resource_id)
        provider = self._subject(principal, subject_type)
        term = query.strip()
        if len(term) < CANDIDATES_MIN_QUERY:
            return []
        owner_col = getattr(resource_type.policy, "owner_col", None)
        owner_id = str(getattr(row, getattr(owner_col, "key", "owner_id"), ""))
        found = await provider.candidates(self.context(principal), term, owner_id)
        return [
            candidate.model_copy(update={"subject_type": subject_type})
            for candidate in found[:CANDIDATES_MAX]
        ]


__all__ = ["SharingError", "SharingService"]
