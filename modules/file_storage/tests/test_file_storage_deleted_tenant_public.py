"""Public originals and thumbnails deny orphan files before teardown delivery."""

import io

import pytest
from file_storage import constants
from PIL import Image
from sqlalchemy import delete
from tenants.models import Invitation, Membership, Tenant


@pytest.mark.parametrize("directory", [True, False], ids=["with-directory", "without-directory"])
async def test_file_storage_public_checks_deleted_tenant(
    app, authenticated_client, client, admin_tenant_id, directory, monkeypatch
):
    content = io.BytesIO()
    Image.new("RGB", (20, 20)).save(content, format="PNG")
    response = await authenticated_client.post(
        f"{constants.ROUTE_PREFIX_API}{constants.PATH_UPLOAD}",
        files={"file": ("image.png", content.getvalue(), "image/png")},
        data={"public": "true"},
    )
    assert response.status_code == 201, response.text
    file = response.json()
    urls = [
        file["public_url"],
        f"{constants.ROUTE_PREFIX_API}/public/{file['id']}",
        f"{constants.ROUTE_PREFIX_API}/public/{file['id']}/thumbnail?w=64",
    ]
    for url in urls:
        assert (await client.get(url)).status_code == 200

    # Bypass the deletion publisher to leave the rows/bytes in place: the
    # immediate guard must work even while the outbox worker is unavailable.
    async with app.state.sm.db.session_factory() as db:
        for model in (Membership, Invitation):
            await db.execute(delete(model).where(model.tenant_id == admin_tenant_id))
        await db.execute(delete(Tenant).where(Tenant.id == admin_tenant_id))
        await db.commit()

    if not directory:
        # Hosts without a tenant registry retain the single-tenant contract.
        monkeypatch.delattr(app.state, "tenant_exists")
    for url in urls:
        response = await client.get(url, headers={"If-None-Match": '"cached"'})
        assert response.status_code == (404 if directory else 200), response.text
