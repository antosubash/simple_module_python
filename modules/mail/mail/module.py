"""Mail module — the app's outgoing-mail transport, configured from the DB."""

from __future__ import annotations

from typing import TYPE_CHECKING

from simple_module_core.health import HealthCheck, HealthRegistry
from simple_module_core.mail import install_mail_resolver, install_mail_sender
from simple_module_core.module import ModuleBase, ModuleMeta

from mail import constants as c

if TYPE_CHECKING:
    from fastapi import FastAPI
    from simple_module_core.events import EventBus


class MailModule(ModuleBase):
    meta = ModuleMeta(
        name=c.MODULE_NAME,
        # ``Settings`` so register_module_settings can reach the registry.
        depends_on=[c.MODULE_SETTINGS],
    )

    def register_settings(self, app: FastAPI) -> None:
        from settings.registration import register_module_settings

        from mail.settings import MailSettings
        from mail.state import MailState

        register_module_settings(
            app, c.MODULE_PACKAGE, MailSettings, lambda s: MailState(settings=s)
        )

    def register_health_checks(self, registry: HealthRegistry) -> None:
        from mail.runtime import check_smtp

        registry.add(
            HealthCheck(
                name=c.CHECK_SMTP,
                check=check_smtp,
                # On demand only: this authenticates against the mail provider,
                # which must not happen on a readiness-probe timer.
                probe=False,
            )
        )

    def register_event_handlers(self, bus: EventBus, app: FastAPI | None = None) -> None:
        # Before the ``app is None`` return: the outbox worker builds modules
        # without an app and still has to send durable mail.
        from mail.runtime import resolve_sender_from_db

        install_mail_resolver(resolve_sender_from_db)
        if app is None:
            return

        from settings.contracts.events import SettingsReloaded

        from mail.sender import build_sender

        async def _reinstall(event: SettingsReloaded) -> None:
            if event.package != c.MODULE_PACKAGE:
                return
            install_mail_sender(build_sender(app.state.mail.settings))

        bus.subscribe(SettingsReloaded, _reinstall)

    async def on_startup(self, app: FastAPI) -> None:
        from mail.sender import build_sender

        install_mail_sender(build_sender(app.state.mail.settings))

    async def on_shutdown(self, app: FastAPI) -> None:
        install_mail_sender(None)
        install_mail_resolver(None)
