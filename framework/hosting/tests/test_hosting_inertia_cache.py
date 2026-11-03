"""Cache safety through the real hosting middleware pipeline."""

import httpx

_INERTIA = {"X-Inertia": "true"}
_OK = 200


def _vary_fields(response: httpx.Response) -> set[str]:
    return {part.strip().lower() for part in response.headers.get("vary", "").split(",")}


class TestAgainstTheRealApp:
    async def test_a_rendered_view_never_returns_a_storable_payload(
        self, authenticated_client: httpx.AsyncClient
    ) -> None:
        """End to end, through the whole middleware pipeline."""
        resp = await authenticated_client.get("/dashboard/", headers=_INERTIA)

        assert resp.status_code == _OK
        assert resp.headers["content-type"].startswith("application/json")
        assert resp.headers["cache-control"] == "private, no-store"
        assert "x-inertia" in _vary_fields(resp)
