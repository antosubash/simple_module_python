"""The admin settings endpoint accepts ``task_routes_override`` as the UI sends it."""

from __future__ import annotations

import pytest
from background_tasks.celery_app import describe_routes

URL = "/api/settings/modules/background_tasks"
ROUTES = '{"background_tasks.demo_echo": "heavy"}'


async def test_json_string_from_the_settings_textbox_takes_effect(authenticated_client, app):
    resp = await authenticated_client.put(URL, json={"task_routes_override": ROUTES})
    assert resp.status_code == 200, resp.text
    settings = app.state.background_tasks.settings
    assert settings.task_routes_override == {"background_tasks.demo_echo": "heavy"}
    effective = {r["pattern"]: r["queue"] for r in describe_routes(settings)}
    assert effective["background_tasks.demo_echo"] == "heavy"


@pytest.mark.parametrize(
    "bad",
    ["{nope", "[1]", '{"x": {"queue": "q", "serializer": "pickle"}}', '{"x": 5}'],
)
async def test_invalid_override_is_rejected_with_422(authenticated_client, app, bad):
    original = app.state.background_tasks.settings
    resp = await authenticated_client.put(URL, json={"task_routes_override": bad})
    assert resp.status_code == 422
    assert "task_routes_override" in resp.text
    assert app.state.background_tasks.settings is original
