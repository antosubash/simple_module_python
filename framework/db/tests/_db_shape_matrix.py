"""Combined tenant/soft-delete probes shared by the statement families (#597)."""

import pytest
from _models import _tenant_session
from simple_module_db.base import create_module_base
from simple_module_db.mixins import MultiTenantMixin, SoftDeleteMixin
from simple_module_db.tenancy import tenant_context
from sqlmodel import Field

Base = create_module_base("shape_matrix")


class MatrixRow(Base, MultiTenantMixin, SoftDeleteMixin, table=True):  # ty: ignore[unsupported-base]
    __tablename__ = "shape_matrix_row"
    id: int = Field(primary_key=True)
    name: str = "original"


class MatrixAnchor(Base, table=True):  # ty: ignore[unsupported-base]
    __tablename__ = "shape_matrix_anchor"
    id: int = Field(primary_key=True)


row, anchor = MatrixRow.__table__, MatrixAnchor.__table__


async def seed(session):
    session.add_all([MatrixAnchor(id=i) for i in range(1, 6)])
    for tenant, ids in (("A", (1, 2)), ("B", (3, 4))):
        with tenant_context(tenant):
            session.add_all([MatrixRow(id=ids[0]), MatrixRow(id=ids[1], is_deleted=True)])
            await session.flush()
    await session.commit()


@pytest.fixture(params=[False, True], ids=["tenant-off", "tenant-on"])
async def matrix_session(request):
    async for session in _tenant_session(Base.metadata, strict=request.param, seed=seed):
        yield session


def visible_ids(tenant, include_deleted):
    ids = {"A": [1, 2], "B": [3, 4], None: [1, 2, 3, 4]}[tenant]
    return ids if include_deleted else [i for i in ids if i % 2]
