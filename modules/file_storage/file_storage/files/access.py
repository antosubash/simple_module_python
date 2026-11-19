"""Compose module file policies with legacy uploader/manage access (#999)."""

from __future__ import annotations

from typing import Any

from simple_module_core.file_access import ACTION_PUBLISH, FileAccessPolicyRegistry
from simple_module_core.permission_denied import PermissionDenied
from simple_module_core.resources import ACTION_VIEW, ResourcePrincipal
from simple_module_db.resource_policy import OwnedResourcePolicy, load_authorized
from sqlalchemy import and_, or_, select
from sqlmodel import col

from file_storage.core import constants
from file_storage.models import StoredFile


class FileAccess:
    """A request-bound ResourcePolicy; its SQL filters are authoritative."""

    def __init__(
        self,
        registry: FileAccessPolicyRegistry,
        principal: ResourcePrincipal,
        *,
        public: bool = False,
    ) -> None:
        self.registry = registry
        self.principal = principal
        self.public = public
        self.legacy = OwnedResourcePolicy(
            StoredFile.created_by, bypass_perm=constants.Permission.MANAGE
        )

    def filter(self, principal: ResourcePrincipal, action: str, stmt: Any) -> Any:
        legacy = col(StoredFile.owner_module).is_(None)
        if not self.public:
            owned = self.legacy.predicate(principal, action)
            if owned is not None:
                legacy = and_(legacy, owned)
        clauses = [legacy]
        for tag, entry in self.registry.items():
            if (action == ACTION_PUBLISH or self.public) and not entry.publishable:
                continue
            allowed = entry.policy.filter(principal, action, select(StoredFile.id))
            clauses.append(and_(col(StoredFile.owner_module) == tag, StoredFile.id.in_(allowed)))
        return stmt.where(or_(*clauses))

    def can(self, principal: ResourcePrincipal, action: str, obj: Any) -> bool:
        # Let load_authorized fall back to the action's SQL, including EXISTS policies.
        return False

    def apply(self, stmt: Any, action: str = ACTION_VIEW) -> Any:
        return self.filter(self.principal, action, stmt)

    async def load(self, db: Any, stmt: Any, action: str) -> StoredFile | None:
        row, allowed = await load_authorized(db, self, self.principal, action, stmt)
        if row is not None and not allowed:
            raise PermissionDenied(f"resource:{action}")
        return row
