"""Tenant search treats SQL wildcard characters as literals (#1078)."""

import pytest
from tenants.core.service import TenantService
from tenants.models import Tenant


@pytest.mark.parametrize(
    "query, expected", [("100%", "percent"), ("_", "underscore"), ("\\", "slash")]
)
async def test_literal_search(db_session, query, expected):
    db_session.add_all(
        [
            Tenant(slug="percent", name="100% Ready"),
            Tenant(slug="underscore", name="under_score"),
            Tenant(slug="slash", name=r"back\slash"),
            Tenant(slug="ordinary", name="1000 Ready"),
        ]
    )
    await db_session.flush()
    assert [row.slug for row in await TenantService(db_session).list_all(search=query)] == [
        expected
    ]
