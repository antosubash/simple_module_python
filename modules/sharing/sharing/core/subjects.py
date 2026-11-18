"""Built-in subjects. User discovery keeps its existing audience and masking rules."""

from __future__ import annotations

import unicodedata
from collections.abc import Collection, Mapping

from simple_module_core.resources import ResourcePrincipal
from simple_module_core.tenancy import TenantRole, tenant_role
from simple_module_core.user_directory import resolve_user_labels
from simple_module_db.tenancy import current_tenant_id
from sqlalchemy import false

from sharing.contracts.schemas import ShareCandidate
from sharing.contracts.subjects import (
    SUBJECTS_KEY,
    SubjectContext,
    SubjectProvider,
    SubjectRegistry,
)
from sharing.core.constants import (
    CANDIDATES_MAX,
    PERM_DIRECTORY_SEARCH,
    SUBJECT_TENANT_ROLE,
    SUBJECT_USER,
)


async def _valid_user(ctx: SubjectContext, subject_id: str) -> str | None:
    user = (await ctx.directory.get_many(ctx.db, [subject_id])).get(subject_id)
    if user and user.is_active and user.id in await ctx.audience.visible([user.id]):
        return user.id
    return None


async def _user_candidates(ctx: SubjectContext, term: str, owner_id: str) -> list[ShareCandidate]:
    audience_ids = await ctx.audience.search_ids()
    found = await ctx.directory.search(
        ctx.db,
        term,
        limit=CANDIDATES_MAX,
        include_ids=audience_ids,
        exclude_ids=[uid for uid in (owner_id, ctx.principal.user_id) if uid],
        active_only=True,
        exact_email=audience_ids is None and not ctx.principal.has(PERM_DIRECTORY_SEARCH),
    )
    candidates = []
    for user in found:
        local, separator, domain = user.email.rpartition("@")
        email = f"{local[:1]}•••@{domain}" if separator else "•••"
        # Names may themselves contain an email; never echo those verbatim.
        label = user.label if "@" not in user.label else email
        candidates.append(ShareCandidate(id=user.id, display_name=label, email=email))
    return candidates


async def _user_labels(ctx: SubjectContext, ids: Collection[str]) -> Mapping[str, str]:
    return await resolve_user_labels(ctx.directory, ctx.db, await ctx.audience.visible(ids))


def _tenant_bound(principal: ResourcePrincipal) -> bool:
    return bool(principal.tenant_id and principal.tenant_id == current_tenant_id.get())


async def _role_visible(ctx: SubjectContext) -> bool:
    principal = ctx.principal
    return bool(
        _tenant_bound(principal)
        and any(tenant_role(role) in principal.roles for role in TenantRole)
        and principal.user_id
        and principal.user_id in await ctx.audience.visible([principal.user_id])
    )


async def _valid_role(ctx: SubjectContext, subject_id: str) -> str | None:
    if subject_id in {role.value for role in TenantRole} and await _role_visible(ctx):
        return subject_id
    return None


def _fold(text: str) -> str:
    """Case- and diacritic-insensitive form: ``Eigentümer`` and ``eigentumer`` match."""
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


async def _role_candidates(ctx: SubjectContext, term: str, owner_id: str) -> list[ShareCandidate]:
    if not await _role_visible(ctx):
        return []
    term = _fold(term)
    return [
        ShareCandidate(
            id=role.value, display_name=tenant_role(role), subject_type=SUBJECT_TENANT_ROLE
        )
        for role in TenantRole
        if term in role.value
        or (
            ctx.translate is not None
            and term in _fold(ctx.translate(f"sharing.subjects.{role.value}"))
        )
    ]


async def _role_labels(ctx: SubjectContext, ids: Collection[str]) -> Mapping[str, str]:
    if not await _role_visible(ctx):
        return {}
    return {role.value: tenant_role(role) for role in TenantRole if role.value in ids}


def _role_membership(principal: ResourcePrincipal, subject_id):
    if not _tenant_bound(principal):
        return false()
    return subject_id.in_(
        [role.value for role in TenantRole if tenant_role(role) in principal.roles]
    )


def default_subject_registry() -> SubjectRegistry:
    registry = SubjectRegistry()
    registry.register(
        SubjectProvider(
            name=SUBJECT_USER,
            label_key="sharing.subjects.user",
            validate=_valid_user,
            candidates=_user_candidates,
            labels=_user_labels,
            membership=lambda principal, subject_id: subject_id == principal.user_id,
        )
    )
    registry.register(
        SubjectProvider(
            name=SUBJECT_TENANT_ROLE,
            label_key="sharing.subjects.tenant_role",
            validate=_valid_role,
            candidates=_role_candidates,
            labels=_role_labels,
            membership=_role_membership,
        )
    )
    return registry


def subjects_for(principal: ResourcePrincipal) -> SubjectRegistry:
    return principal.context.get(SUBJECTS_KEY) or default_subject_registry()
