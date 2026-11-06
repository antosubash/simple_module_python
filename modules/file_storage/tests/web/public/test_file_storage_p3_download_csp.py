"""Authenticated downloads carry the sandbox CSP."""

from __future__ import annotations

from _file_storage_uploads_support import API, upload_text
from file_storage.core import constants


class TestDownloadSandbox:
    async def test_streamed_download_is_sandboxed(self, tenant_client):
        async with tenant_client("member") as a:
            file_id = await upload_text(a.client, "a.txt")
            resp = await a.client.get(f"{API}/files/{file_id}/download")

            assert resp.status_code == 200
            assert constants.PUBLIC_CSP in resp.headers.get_list("content-security-policy")
            assert resp.headers["x-content-type-options"] == "nosniff"
            assert "attachment" in resp.headers["content-disposition"]

    async def test_thumbnail_keeps_the_sandbox_csp(self, tenant_client):
        async with tenant_client("member") as a:
            import io

            from PIL import Image

            buf = io.BytesIO()
            Image.new("RGB", (4, 4)).save(buf, "PNG")
            resp = await a.client.post(
                f"{API}/upload", files={"file": ("p.png", buf.getvalue(), "image/png")}
            )
            file_id = resp.json()["id"]
            thumb = await a.client.get(f"{API}/files/{file_id}/thumbnail")
            assert thumb.status_code == 200
            assert constants.PUBLIC_CSP in thumb.headers.get_list("content-security-policy")
