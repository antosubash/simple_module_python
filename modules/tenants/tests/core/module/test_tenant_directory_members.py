"""Directory searches can obtain all members without losing the tenant boundary."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

from simple_module_core.tenancy import tenant_member_ids
from sqlalchemy import create_engine
from tenants.models import Membership, Tenant
from tenants.module import _tenant_members


async def test_all_members_and_existing_subset_lookup_stay_in_tenant():
    engine = create_engine("sqlite://")
    Tenant.__table__.create(engine)
    Membership.__table__.create(engine)
    try:
        with engine.connect() as connection:
            for tenant, user in [("blue", "owner"), ("blue", "friend"), ("red", "foreign")]:
                connection.execute(
                    Membership.__table__.insert().values(tenant_id=tenant, user_id=user)
                )
            db = SimpleNamespace(execute=AsyncMock(side_effect=connection.execute))
            app = SimpleNamespace(state=SimpleNamespace(tenant_members=_tenant_members()))
            assert await tenant_member_ids(app, db, "blue", None) == {"owner", "friend"}
            assert await tenant_member_ids(app, db, "blue", ["friend", "foreign"]) == {"friend"}
            assert await tenant_member_ids(app, db, "blue", []) == set()
            assert await tenant_member_ids(app, db, "missing", None) == set()
    finally:
        engine.dispose()
