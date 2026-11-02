"""Owner-scoped callers see their own usage and no tenant quota; downloads are sandboxed."""

from __future__ import annotations

from file_storage import constants
from file_storage_uploads_helpers import API, INERTIA, upload_text

VIEW = f"{constants.ROUTE_PREFIX_VIEW}/"


async def _props(client) -> dict:
    resp = await client.get(VIEW, headers=INERTIA)
    assert resp.status_code == 200, resp.text
    return resp.json()["props"]


class TestUsageScope:
    async def test_member_sees_own_usage_and_no_quota(self, tenant_client):
        async with (
            tenant_client("member") as a,
            tenant_client("member", tenant_id=a.tenant_id) as b,
            tenant_client("member", tenant_id=a.tenant_id) as empty,
        ):
            a.client._transport.app.state.file_storage.settings.quota_bytes = 1024**3
            await upload_text(a.client, "a.txt")  # 2 bytes
            await b.client.post(
                f"{API}/upload", files={"file": ("b.txt", b"x" * 100, "text/plain")}
            )

            assert (await _props(a.client))["used_bytes"] == 2
            assert (await _props(b.client))["used_bytes"] == 100
            assert (await _props(empty.client))["used_bytes"] == 0
            for who in (a, b, empty):
                assert (await _props(who.client))["quota_bytes"] is None

    async def test_manager_keeps_tenant_wide_usage_and_quota(self, tenant_client):
        async with (
            tenant_client("member") as a,
            tenant_client("admin", tenant_id=a.tenant_id) as boss,
        ):
            boss.client._transport.app.state.file_storage.settings.quota_bytes = 1024**3
            await upload_text(a.client, "a.txt")

            props = await _props(boss.client)
            assert props["used_bytes"] == 2
            assert props["quota_bytes"] == 1024**3
