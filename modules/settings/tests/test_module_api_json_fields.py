"""Round-trips through the generic editor for ``json``-typed fields (GH #487).

A dict field saved from the editor used to be stored as a JSON *string*, and
an ``int | None`` rendered as the literal text ``null``. Both are checked by
re-hydrating from the store, since that is where the wrong type surfaced.
"""

from __future__ import annotations

from background_tasks.settings import BackgroundTasksSettings
from settings.service import SettingService
from settings.store import SettingsStore
from simple_module_core.settings_hydrate import hydrate_settings, input_type_for_field

_PKG = "background_tasks"


async def _rehydrated(app) -> BackgroundTasksSettings:
    async with app.state.sm.db.session_factory() as db:
        return await hydrate_settings(
            BackgroundTasksSettings, SettingsStore(SettingService(db)), _PKG
        )


async def test_dict_field_round_trips_as_a_dict(authenticated_client, app):
    routes = {"reports.*": "heavy"}
    resp = await authenticated_client.put(
        f"/api/settings/modules/{_PKG}", json={"task_routes_override": routes}
    )
    assert resp.status_code == 200, resp.text
    assert app.state.background_tasks.settings.task_routes_override == routes
    assert (await _rehydrated(app)).task_routes_override == routes


async def test_dict_sent_as_text_is_stored_as_the_validated_dict(authenticated_client, app):
    """The validator ``json.loads`` the text; the store must keep its result."""
    resp = await authenticated_client.put(
        f"/api/settings/modules/{_PKG}",
        json={"task_routes_override": '{"reports.*": "heavy"}'},
    )
    assert resp.status_code == 200, resp.text
    async with app.state.sm.db.session_factory() as db:
        overrides = await SettingsStore(SettingService(db)).get_overrides(_PKG)
    assert overrides["task_routes_override"] == ('{"reports.*": "heavy"}', "json")
    assert (await _rehydrated(app)).task_routes_override == {"reports.*": "heavy"}


async def test_optional_int_round_trips_a_number_and_none(authenticated_client, app):
    resp = await authenticated_client.put(
        f"/api/settings/modules/{_PKG}", json={"worker_concurrency": 4}
    )
    assert resp.status_code == 200, resp.text
    assert (await _rehydrated(app)).worker_concurrency == 4

    resp = await authenticated_client.put(
        f"/api/settings/modules/{_PKG}", json={"worker_concurrency": None}
    )
    assert resp.status_code == 200, resp.text
    assert (await _rehydrated(app)).worker_concurrency is None


async def test_editor_props_describe_the_input(authenticated_client):
    resp = await authenticated_client.get("/api/settings/modules")
    fields = {
        f["name"]: f for m in resp.json()["modules"] if m["package"] == _PKG for f in m["fields"]
    }
    assert (
        fields["worker_concurrency"]["input_type"],
        fields["worker_concurrency"]["nullable"],
    ) == (
        "int",
        True,
    )
    assert fields["worker_concurrency"]["value"] is None
    assert fields["task_routes_override"]["input_type"] == "json"
    assert fields["task_reject_on_worker_lost"]["input_type"] == "bool"
    assert fields["retention_days"]["nullable"] is False


def test_input_type_unwraps_optional_scalars_only():
    from file_storage.settings import FileStorageSettings

    assert input_type_for_field(BackgroundTasksSettings, "worker_concurrency") == ("int", True)
    assert input_type_for_field(BackgroundTasksSettings, "task_reject_on_worker_lost") == (
        "bool",
        True,
    )
    assert input_type_for_field(BackgroundTasksSettings, "task_routes_override") == ("json", False)
    assert input_type_for_field(FileStorageSettings, "allowed_content_types") == ("json", True)
    assert input_type_for_field(BackgroundTasksSettings, "retention_days") == ("int", False)


async def test_oversized_stored_value_is_reported_on_its_field(authenticated_client):
    """The 4000-char column limit names ``value``; the editor needs the field."""
    routes = {f"task_{i}.*": "heavy" for i in range(400)}
    resp = await authenticated_client.put(
        f"/api/settings/modules/{_PKG}", json={"task_routes_override": routes}
    )
    assert resp.status_code == 422, resp.text
    locs = [tuple(e["loc"]) for e in resp.json()["detail"]]
    assert locs == [("task_routes_override",)]


async def test_rejected_value_is_not_echoed_back(authenticated_client):
    """A 422 names the field, never the value: it may carry a credential."""
    secret = "s3cr3t-broker-pw"
    resp = await authenticated_client.put(
        f"/api/settings/modules/{_PKG}",
        json={"broker_url": f"evil.module://user:{secret}@redis:6379/0"},
    )
    assert resp.status_code == 422, resp.text
    assert secret not in resp.text
    assert all("input" not in err for err in resp.json()["detail"])


def test_optional_bare_containers_and_models_get_the_json_input():
    from pydantic import BaseModel
    from pydantic_settings import BaseSettings

    class _Shape(BaseModel):
        name: str = ""

    class _Cfg(BaseSettings):
        mapping: dict | None = None
        items: list | None = None
        shape: _Shape | None = None

    for name in ("mapping", "items", "shape"):
        assert input_type_for_field(_Cfg, name) == ("json", True), name
