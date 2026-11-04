"""Doctor compatibility hooks use boot's scoped, filtered DB sessions (#815)."""

import pytest
import sqlalchemy as sa
from simple_module_core.data_compatibility import collect_data_compatibility
from simple_module_core.module import ModuleBase, ModuleMeta
from simple_module_db.base import create_module_base
from simple_module_db.data_compatibility import database_compatibility_diagnostics
from simple_module_db.listeners import register_listeners
from simple_module_db.mixins import MultiTenantMixin, SoftDeleteMixin
from simple_module_db.session import init_db
from simple_module_db.tenancy import all_tenants, tenant_context
from sqlmodel import Field

Base = create_module_base("db_doctor_session_review")


class DoctorRow(Base, MultiTenantMixin, SoftDeleteMixin, table=True):  # ty: ignore[unsupported-base]
    __tablename__ = "db_doctor_session_review_row"
    id: int = Field(primary_key=True)


@pytest.fixture
async def doctor_database(tmp_path):
    url = f"sqlite+aiosqlite:///{tmp_path / 'doctor.db'}"
    state = init_db(url)
    state.tenant_strict = True
    register_listeners(state)
    try:
        async with state.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.execute(sa.text("CREATE TABLE alembic_version (version_num VARCHAR(32))"))
            await conn.execute(sa.text("INSERT INTO alembic_version VALUES ('review')"))
            await conn.execute(
                sa.insert(DoctorRow),
                [
                    {"id": 1, "tenant_id": "a", "is_deleted": False},
                    {"id": 2, "tenant_id": "a", "is_deleted": True},
                    {"id": 3, "tenant_id": "b", "is_deleted": False},
                ],
            )
        yield state, url
    finally:
        await state.engine.dispose()


@pytest.mark.parametrize(
    "scope,include_deleted,expected",
    [("a", False, [1]), ("a", True, [1, 2]), ("all", False, [1, 3]), ("all", True, [1, 2, 3])],
)
async def test_db_doctor_and_boot_apply_same_filters(
    doctor_database, scope, include_deleted, expected
):
    state, url = doctor_database
    seen = []

    class Check(ModuleBase):
        meta = ModuleMeta(name="DoctorSessionReview")

        async def check_data_compatibility(self, db):
            context = all_tenants() if scope == "all" else tenant_context(scope)
            with context:
                result = await db.execute(
                    sa.select(DoctorRow.id)
                    .order_by(DoctorRow.id)
                    .execution_options(include_deleted=include_deleted)
                )
                seen.append(list(result.scalars()))
            return []

    module = Check()
    async with state.session_factory() as db:
        await collect_data_compatibility([module], db)
    assert await database_compatibility_diagnostics([module], url) == []
    assert seen == [expected, expected]


async def test_db_doctor_fails_closed_without_tenant_context(doctor_database):
    _, url = doctor_database

    class Check(ModuleBase):
        meta = ModuleMeta(name="DoctorTenantReview")

        async def check_data_compatibility(self, db):
            await db.execute(sa.select(DoctorRow))
            return []

    findings = await database_compatibility_diagnostics([Check()], url)
    assert len(findings) == 1
    assert findings[0].level == "error"
    assert "MissingTenantError" in findings[0].message
