"""Settings API mutations need ``settings.view`` too, like the pages they back (#1178).

The admin view router is gated on ``settings.view``, so a session could never
create, edit or delete a setting without it. The API equivalents now ask for
the same: a token scoped to the mutation grant alone gets ``403``.
"""

from __future__ import annotations

from _api_tokens_support import admin_session, bearer_client, pat_for  # ty: ignore[import-not-found]
from settings.core.constants import Permissions
from simple_module_core.settings.module_settings import module_settings_registry

_BASE = "/api/settings"
_MODULE = "mail"


async def _pat(app, scopes: list[str]) -> str:
    return await pat_for(app, await admin_session(app), scopes)


async def _create(app, key: str) -> int:
    token = await _pat(app, [Permissions.VIEW, Permissions.CREATE])
    async with bearer_client(app, token) as bc:
        resp = await bc.post(f"{_BASE}/", json={"key": key, "value": "v"})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _status(app, scopes: list[str], method: str, url: str, **kwargs) -> int:
    async with bearer_client(app, await _pat(app, scopes)) as bc:
        return (await bc.request(method, url, **kwargs)).status_code


async def test_create_needs_view(app):
    body = {"json": {"key": "probe.create", "value": "v"}}
    assert await _status(app, [Permissions.CREATE], "POST", f"{_BASE}/", **body) == 403
    await _create(app, "probe.create")


async def test_update_needs_view(app):
    url = f"{_BASE}/{await _create(app, 'probe.update')}"
    body = {"json": {"value": "w"}}
    assert await _status(app, [Permissions.EDIT], "PUT", url, **body) == 403
    assert await _status(app, [Permissions.VIEW, Permissions.EDIT], "PUT", url, **body) == 200


async def test_delete_needs_view(app):
    url = f"{_BASE}/{await _create(app, 'probe.delete')}"
    assert await _status(app, [Permissions.DELETE], "DELETE", url) == 403
    assert await _status(app, [Permissions.VIEW, Permissions.DELETE], "DELETE", url) == 204


async def test_module_update_needs_view(app):
    url = f"{_BASE}/modules/{_MODULE}"
    assert await _status(app, [Permissions.EDIT], "PUT", url, json={}) == 403
    assert await _status(app, [Permissions.VIEW, Permissions.EDIT], "PUT", url, json={}) == 200


async def test_module_clear_needs_view(app):
    field = next(iter(module_settings_registry(app).get(_MODULE).model_fields))
    url = f"{_BASE}/modules/{_MODULE}/{field}"
    assert await _status(app, [Permissions.DELETE], "DELETE", url) == 403
    assert await _status(app, [Permissions.VIEW, Permissions.DELETE], "DELETE", url) == 204
