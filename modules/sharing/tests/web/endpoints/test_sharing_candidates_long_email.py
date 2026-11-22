"""Candidate query validation allows a complete supported email address."""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

from _sharing_support import NOTE_TYPE, register_note_type
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sharing.core.service import SharingService
from sharing.web.deps import get_sharing_service
from sharing.web.endpoints.api import share_candidates
from simple_module_core.access.resources import ResourcePrincipal, ResourceTypeRegistry
from simple_module_hosting.resource_deps import resource_principal
from sqlalchemy import create_engine
from users.core.directory import UsersDirectory
from users.models import User


async def test_single_tenant_candidates_find_long_exact_email():
    email = "a" * 63 + "@" + "b" * 59 + ".com"
    assert len(email) == 127
    uid = uuid.uuid4()
    engine = create_engine("sqlite://")
    User.__table__.create(engine)
    try:
        with engine.connect() as connection:
            connection.execute(User.__table__.insert().values(id=uid, email=email))
            db = SimpleNamespace(execute=AsyncMock(side_effect=connection.execute))
            registry = ResourceTypeRegistry()
            register_note_type(registry)
            service = SharingService(db, registry, UsersDirectory())
            service._authorize = AsyncMock(return_value=SimpleNamespace(owner_id="owner"))

            async def get_service():
                return service

            async def get_principal():
                return ResourcePrincipal("owner")

            app = FastAPI()
            app.add_api_route("/candidates", share_candidates)
            app.dependency_overrides[get_sharing_service] = get_service
            app.dependency_overrides[resource_principal] = get_principal
            async with AsyncClient(transport=ASGITransport(app), base_url="http://test") as client:
                query = {"resource_type": NOTE_TYPE, "resource_id": "note"}
                response = await client.get("/candidates", params={**query, "q": email.upper()})
                assert response.status_code == 200, response.text
                assert [user["id"] for user in response.json()] == [str(uid)]
                response = await client.get("/candidates", params={**query, "q": email[:100]})
                assert response.status_code == 200, response.text
                assert response.json() == []
    finally:
        engine.dispose()
