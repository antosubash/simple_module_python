"""A field typed as a secret is masked on every read path (GH #487 review).

Json fields now store the real credential, so ``token: SecretStr | None`` and
``tokens: dict[str, SecretStr]`` — names the secret-name rule does not match —
must be hidden by their *type*: in the module editor and its API, in the raw
row listing, and a PUT echoing the mask must leave the stored secret alone.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from settings._module_settings import SECRET_MASK
from settings._secrets import annotation_holds_secret
from settings.registration import register_module_settings
from settings.service import SettingService
from settings.store import SettingsStore

PACKAGE = "typedsecret"
URL = f"/api/settings/modules/{PACKAGE}"


class _TypedSecretCfg(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SM_TEST_TYPED_SECRET_", extra="ignore")

    token: SecretStr | None = None
    tokens: dict[str, SecretStr] = {}
    label: str = "visible"


@dataclass
class _Services:
    settings: _TypedSecretCfg


@pytest.fixture
def registered(app):
    register_module_settings(app, PACKAGE, _TypedSecretCfg, lambda s: _Services(settings=s))
    return app


async def _stored(app) -> dict[str, tuple[str, str]]:
    async with app.state.sm.db.session_factory() as db:
        return await SettingsStore(SettingService(db)).get_overrides(PACKAGE)


def _fields(payload: dict) -> dict[str, dict]:
    (view,) = [m for m in payload["modules"] if m["package"] == PACKAGE]
    return {f["name"]: f for f in view["fields"]}


def test_annotation_walk_finds_secrets_in_unions_and_containers():
    assert annotation_holds_secret(SecretStr | None)
    assert annotation_holds_secret(dict[str, SecretStr])
    assert annotation_holds_secret(list[SecretStr | None])
    assert not annotation_holds_secret(str | None)
    assert not annotation_holds_secret(dict[str, int])


async def test_typed_secrets_are_stored_in_clear_but_never_read_back(
    registered, authenticated_client
):
    resp = await authenticated_client.put(
        URL, json={"token": "hunter2", "tokens": {"a": "s3cret"}, "label": "shown"}
    )
    assert resp.status_code == 200, resp.text
    stored = await _stored(registered)
    assert "hunter2" in stored["token"][0]
    assert "s3cret" in stored["tokens"][0]

    fields = _fields((await authenticated_client.get("/api/settings/modules")).json())
    for name in ("token", "tokens"):
        assert fields[name]["is_secret"] is True
        assert fields[name]["value"] == SECRET_MASK
    assert fields["label"]["value"] == "shown"
    assert fields["label"]["is_secret"] is False

    rows = (await authenticated_client.get("/api/settings/")).text
    assert "hunter2" not in rows
    assert "s3cret" not in rows


async def test_echoing_the_mask_keeps_the_stored_secret(registered, authenticated_client):
    await authenticated_client.put(URL, json={"token": "hunter2", "tokens": {"a": "s3cret"}})
    before = await _stored(registered)

    resp = await authenticated_client.put(
        URL, json={"token": SECRET_MASK, "tokens": SECRET_MASK, "label": "edited"}
    )
    assert resp.status_code == 200, resp.text
    after = await _stored(registered)
    assert after["token"] == before["token"]
    assert after["tokens"] == before["tokens"]
    assert registered.state.typedsecret.settings.token.get_secret_value() == "hunter2"
