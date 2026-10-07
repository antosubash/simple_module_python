"""Reap a branding image once nothing references it — after the write commits.

Every upload mints a new ``file_storage`` id, so the file a setting stops
pointing at would otherwise sit in the store forever. Deleting it in the
request, though, deletes the *bytes* immediately while the settings write is
still uncommitted: a late rollback would leave the setting pointing at a file
that is gone. So the reap is queued with ``register_on_commit`` and runs only
once the new value is durable, in a session of its own.

A file is reaped only when no image field of the same owner still references
it — the tenant's own overrides for a tenant file, the SYSTEM values for a
platform file — re-checked at reap time, so a value copied to another field
(logo and dark logo sharing one upload) keeps the file alive.

Best effort throughout: the rebrand already succeeded, so a failure is logged
and leaves an orphan for a janitor, never a broken setting.
"""

from __future__ import annotations

import logging
import uuid
from contextlib import nullcontext
from typing import TYPE_CHECKING

from simple_module_db import tenant_context
from simple_module_db.callbacks import register_on_commit

from branding.constants import PACKAGE, TENANT_IMAGE_FIELDS

if TYPE_CHECKING:
    from fastapi import FastAPI
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

_IMAGE_KEYS = frozenset(f"{PACKAGE}.{name}" for name in TENANT_IMAGE_FIELDS)


async def referenced_ids(db: AsyncSession, tenant_id: str | None) -> set[str]:
    """File ids the owner's image fields hold (``None`` = the system's)."""
    from settings.contracts.schemas import SettingScope
    from settings.service import SettingService

    scope, scope_id = (SettingScope.TENANT, tenant_id) if tenant_id else (SettingScope.SYSTEM, "")
    rows = await SettingService(db).list_by_scope_unmasked(scope, scope_id)
    return {row.value for row in rows if row.key in _IMAGE_KEYS and row.value}


def schedule_reap(app: FastAPI, db: AsyncSession, file_id: str, *, tenant_id: str | None) -> None:
    """Reap ``file_id`` after ``db`` commits, if it is still unreferenced then.

    ``tenant_id`` is the file's owner; ``None`` means a platform file.
    """
    if not file_id:
        return
    register_on_commit(db, lambda: reap(app, file_id, tenant_id=tenant_id))


async def reap(app: FastAPI, file_id: str, *, tenant_id: str | None) -> None:
    from file_storage.service import FileStorageService

    try:
        parsed = uuid.UUID(file_id)
    except ValueError:
        logger.warning("Branding image %r is not a file id; nothing to reap.", file_id)
        return
    try:
        with tenant_context(tenant_id) if tenant_id else nullcontext():
            async with app.state.sm.db.session_factory() as db:
                if file_id in await referenced_ids(db, tenant_id):
                    return
                services = app.state.file_storage
                storage = FileStorageService(db, services.backend, services.settings)
                # Soft-delete and commit first, drop the bytes after: a failed
                # commit must never leave a live row with no object. A failure
                # after the commit only orphans an object, which is acceptable.
                row = await storage.delete(parsed, platform=tenant_id is None, drop_object=False)
                await db.commit()
                await storage.drop_object(row)
    except Exception:
        # Deliberately broad: a cleanup failure is never a reason to fail (or,
        # running after commit, to misreport) a rebrand that succeeded.
        logger.warning("Could not delete replaced branding image %s.", file_id, exc_info=True)


__all__ = ["reap", "referenced_ids", "schedule_reap"]
