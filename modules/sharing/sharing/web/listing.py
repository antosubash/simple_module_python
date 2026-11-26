"""The admin share listing, shared by the admin page and the admin API."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Request
from simple_module_core.access.resources import ResourcePrincipal
from simple_module_db import PageParams, TenantIsolationError, paginate
from sqlmodel import col, select

from sharing.contracts.schemas import ShareOut
from sharing.core.service import SharingService
from sharing.models import ResourceShare
from sharing.web.present import present_shares


@dataclass(frozen=True)
class AdminShareListing:
    shares: list[ShareOut]
    total: int
    page: int
    pages: int
    tenant_required: bool


async def list_admin_shares(
    request: Request, service: SharingService, params: PageParams, who: ResourcePrincipal
) -> AdminShareListing:
    """One page of the tenant's shares, newest first.

    Strict tenancy with no active tenant (a platform admin before picking one)
    has nothing to list: an empty first page with ``tenant_required`` set.
    """
    from simple_module_core.access.user_directory import get_user_directory

    stmt = select(ResourceShare).order_by(
        col(ResourceShare.created_at).desc(), col(ResourceShare.id)
    )
    try:
        page = await paginate(service.db, stmt, params)
        shares = await present_shares(
            get_user_directory(request.app),
            service.db,
            page.items,
            service.audience,
            who,
            service.subject_registry(who),
        )
    except TenantIsolationError:
        return AdminShareListing([], 0, 1, 1, True)
    return AdminShareListing(shares, page.total, page.page, page.pages, False)
