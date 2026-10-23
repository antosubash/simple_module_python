"""A single-tenant install keeps serving public files with the tenants plugin installed."""

import io

import pytest
from file_storage import constants
from PIL import Image
from simple_module_hosting.settings import Settings


@pytest.fixture
def settings(settings: Settings) -> Settings:
    return settings.model_copy(update={"multi_tenant": False})


async def test_file_storage_public_serves_fallback_tenant_files(authenticated_client, client):
    content = io.BytesIO()
    Image.new("RGB", (20, 20)).save(content, format="PNG")
    response = await authenticated_client.post(
        f"{constants.ROUTE_PREFIX_API}{constants.PATH_UPLOAD}",
        files={"file": ("image.png", content.getvalue(), "image/png")},
        data={"public": "true"},
    )
    assert response.status_code == 201, response.text
    file = response.json()
    # The fallback tenant has no registry row; that must not 404 the file.
    for url in (
        file["public_url"],
        f"{constants.ROUTE_PREFIX_API}/public/{file['id']}",
        f"{constants.ROUTE_PREFIX_API}/public/{file['id']}/thumbnail?w=64",
    ):
        assert (await client.get(url)).status_code == 200, url
