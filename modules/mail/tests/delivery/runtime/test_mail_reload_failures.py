"""Failed transport construction blocks delivery until an unchanged refresh recovers."""

from types import SimpleNamespace

import pytest
from mail.contracts import register_mail_transport
from mail.core import transports
from mail.core.settings import MailSettings
from mail.core.state import MailState
from mail.module import MailModule
from settings.contracts.events import SettingsReloaded
from settings.core.invalidation import reload_package
from simple_module_core.eventing.events import EventBus
from simple_module_core.eventing.invalidation import InvalidationBus
from simple_module_core.mailer import mail as core_mail
from simple_module_core.settings.module_settings import register_module_settings
from simple_module_core.settings.settings_base import DbBackedSettings
from simple_module_core.web.health import HealthStatus
from simple_module_test.mail import CapturedMail


class ProviderSettings(DbBackedSettings):
    from_address: str = "old@test"


@pytest.mark.parametrize("refresh_key", [None, "mail"])
@pytest.mark.parametrize("package", ["mail", "provider"])
async def test_failed_reload_blocks_delivery_and_unchanged_refresh_recovers(
    monkeypatch, refresh_key, package
):
    from mail.delivery.runtime import check_smtp

    monkeypatch.setattr(transports, "_transports", dict(transports._transports))
    monkeypatch.setattr(transports, "TRANSPORT_NAMES", list(transports.TRANSPORT_NAMES))
    available = True
    recovered = CapturedMail()

    def factory(options, log_bodies):
        if not available:
            raise RuntimeError("provider unavailable")
        return recovered

    register_mail_transport(
        "recovering", factory, settings_model=ProviderSettings, package="provider"
    )
    app = SimpleNamespace(
        state=SimpleNamespace(
            sm=SimpleNamespace(settings=SimpleNamespace(environment="testing")),
            mail=MailState(settings=MailSettings()),
        )
    )
    register_module_settings(app, "mail", MailSettings, lambda s: MailState(settings=s))
    register_module_settings(
        app, "provider", ProviderSettings, lambda s: SimpleNamespace(settings=s)
    )
    if package == "provider":
        app.state.mail.settings = MailSettings(backend="recovering")
    module = MailModule()
    events = EventBus()
    module.register_event_handlers(events, app)
    module.register_invalidations(InvalidationBus(), app)
    await module.on_startup(app)
    available = False

    class Overrides:
        async def get_overrides(self, package):
            if package == "mail":
                return {"backend": ("recovering", "string")}
            return {"from_address": ("new@test", "string")}

    changed = []

    async def record(event):
        changed.append(event)

    events.subscribe(SettingsReloaded, record)
    message = core_mail.MailMessage("to@test", "Subject", "Body")
    try:
        await reload_package(app, events, Overrides(), package)
        assert app.state.mail.settings.backend == "recovering"
        for sender in (
            core_mail.current_mail_sender(),
            await core_mail.resolve_mail_sender(object()),
        ):
            with pytest.raises(RuntimeError, match=r"Mail transport.*unavailable"):
                await sender.send(message)
        assert (await check_smtp()).status is HealthStatus.UNHEALTHY
        with pytest.raises(RuntimeError, match="provider unavailable"):
            await module._refresh.refresh(refresh_key)
        with pytest.raises(RuntimeError, match=r"Mail transport.*unavailable"):
            await core_mail.current_mail_sender().send(message)

        # No new SettingsReloaded event: the settings already contain this backend.
        available = True
        await reload_package(app, events, Overrides(), package)
        assert len(changed) == 1
        await module._refresh.refresh(refresh_key)
        await core_mail.current_mail_sender().send(message)
        assert recovered.messages == [message]
        assert (await check_smtp()).status is HealthStatus.HEALTHY
    finally:
        await module.on_shutdown(app)
