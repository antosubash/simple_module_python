"""Shared fixtures and test models for the database test suite."""

from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest
from _models import _tenant_session, _TenantBase
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture
async def tenant_session() -> AsyncGenerator[AsyncSession, None]:
    """Session backed by in-memory SQLite with tenant listeners registered."""
    async for session in _tenant_session(_TenantBase.metadata, strict=False):
        yield session


@pytest.fixture
async def strict_session() -> AsyncGenerator[AsyncSession, None]:
    """Like ``tenant_session``, with fail-closed isolation (``multi_tenant`` on)."""
    async for session in _tenant_session(_TenantBase.metadata, strict=True):
        yield session


@pytest.fixture
async def acme_default_session() -> AsyncGenerator[AsyncSession, None]:
    """Single-tenant install with ``default_tenant="acme"``."""
    async for session in _tenant_session(_TenantBase.metadata, strict=False, default_tenant="acme"):
        yield session
