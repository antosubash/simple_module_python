"""Mail editor saves exercise the shared validation and persistence pipeline."""

from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from mail.core.settings import MailSettings
from settings.module_settings.reload import apply_changes_and_reload
from settings.web.endpoints.module_api import _settings_errors
from simple_module_core.eventing.events import EventBus
from simple_module_core.settings.module_settings import register_module_settings
from simple_module_core.settings.settings_hydrate import build_settings


class _Store:
    def __init__(self):
        self.rows = {}

    async def lock_package(self, package):
        pass

    async def get_overrides(self, package):
        return dict(self.rows)

    async def set_override(self, package, field, raw, value_type):
        self.rows[field] = (raw, value_type)

    async def clear_override(self, package, field):
        self.rows.pop(field, None)

    def on_commit(self, callback):
        pass


@pytest.fixture
def target():
    app = FastAPI()
    register_module_settings(app, "mail", MailSettings, lambda cfg: SimpleNamespace(settings=cfg))
    return app, _Store()


@pytest.mark.parametrize("value", ["", "   ", "invalid", "a@test, b@test", "x" * 1200])
async def test_invalid_sender_save_returns_field_422_without_writing(target, value):
    app, store = target
    store.rows["smtp_from"] = ("existing@example.com", "string")
    with pytest.raises(HTTPException) as exc, _settings_errors(None):
        await apply_changes_and_reload(
            app, EventBus(), store, package="mail", changes={"smtp_from": value}
        )
    assert exc.value.status_code == 422
    assert exc.value.detail[0]["loc"] == ["smtp_from"]
    assert "smtp_from" in exc.value.detail[0]["msg"]
    assert store.rows == {"smtp_from": ("existing@example.com", "string")}


async def test_sender_save_persists_trimmed_mailbox(target):
    app, store = target
    cfg = await apply_changes_and_reload(
        app,
        EventBus(),
        store,
        package="mail",
        changes={"smtp_from": "  Example Team <sender@example.com>  "},
    )
    assert cfg.smtp_from == "Example Team <sender@example.com>"
    assert store.rows == {"smtp_from": ("Example Team <sender@example.com>", "string")}
    assert build_settings(MailSettings, store.rows).smtp_from == cfg.smtp_from


async def test_saving_default_sender_clears_override(target):
    app, store = target
    store.rows["smtp_from"] = ("existing@example.com", "string")
    cfg = await apply_changes_and_reload(
        app, EventBus(), store, package="mail", changes={"smtp_from": "  no-reply@localhost  "}
    )
    assert cfg.smtp_from == "no-reply@localhost"
    assert store.rows == {}
