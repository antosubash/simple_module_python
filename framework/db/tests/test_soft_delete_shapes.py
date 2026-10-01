"""#332 (soft-delete half): trashed rows stay hidden in joins, subqueries and counts."""

from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest
from simple_module_db import SoftDeleteMixin, create_module_base
from simple_module_db.listeners import register_listeners
from simple_module_db.session import init_db
from simple_module_test.database import database_url_for_tests, init_db_kwargs, reset_schema
from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import Field

_URL = database_url_for_tests()
_Base = create_module_base("sdshapes")


class _Folder(_Base, table=True):  # ty: ignore[unsupported-base]
    __tablename__ = "sdshapes_folder"
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(max_length=20)


class _File(_Base, SoftDeleteMixin, table=True):  # ty: ignore[unsupported-base]
    __tablename__ = "sdshapes_file"
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(max_length=20)
    folder_id: int | None = Field(default=None, foreign_key="sdshapes_folder.id")


@pytest.fixture
async def db() -> AsyncGenerator[AsyncSession, None]:
    state = init_db(_URL, **init_db_kwargs(_URL))
    register_listeners(state)
    await reset_schema(state.engine)
    async with state.engine.begin() as conn:
        await conn.run_sync(_Base.metadata.create_all)
    async with state.session_factory() as session:
        session.add_all([_Folder(id=1, name="live"), _Folder(id=2, name="trash")])
        await session.flush()
        kept = _File(name="kept", folder_id=1)
        gone = _File(name="gone", folder_id=2)
        session.add_all([kept, gone])
        await session.flush()
        await session.delete(gone)  # soft delete
        await session.flush()
        yield session
    await state.engine.dispose()


def _shapes():
    f = _File.__table__
    return {
        "join target": select(_Folder.name).join(_File).order_by(_Folder.name),
        "orm exists": select(_Folder.name).where(
            select(_File.id).where(_File.folder_id == _Folder.id).exists()
        ),
        "bare core exists": select(_Folder.name).where(
            exists().where(_File.folder_id == _Folder.id)
        ),
        "in_ subquery": select(_Folder.name).where(_Folder.id.in_(select(_File.folder_id))),
        "count select_from": select(func.count()).select_from(_File),
        "count of subquery": select(func.count()).select_from(select(_File).subquery()),
        "core table": select(f.c.name),
    }


_EXPECTED = {
    "join target": [("live",)],
    "orm exists": [("live",)],
    "bare core exists": [("live",)],
    "in_ subquery": [("live",)],
    "count select_from": [(1,)],
    "count of subquery": [(1,)],
    "core table": [("kept",)],
}


@pytest.mark.parametrize("shape", list(_EXPECTED))
async def test_trashed_rows_stay_hidden(db: AsyncSession, shape: str):
    rows = (await db.execute(_shapes()[shape])).all()
    assert [tuple(r) for r in rows] == _EXPECTED[shape]


async def test_include_deleted_still_reveals_them(db: AsyncSession):
    stmt = select(func.count()).select_from(_File).execution_options(include_deleted=True)
    assert (await db.execute(stmt)).scalar_one() == 2
