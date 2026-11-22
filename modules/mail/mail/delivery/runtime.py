"""Resolver and health check: the parts that work without an app."""

from __future__ import annotations

import os
from typing import Any

from settings.core.service import SettingService
from settings.module_settings.store import SettingsStore
from simple_module_core.mailer.mail import (
    MailMessage,
    MailSender,
    current_mail_sender,
    install_default_mail_sender,
)
from simple_module_core.settings.environments import NON_PROD_ENVIRONMENTS
from simple_module_core.settings.settings_hydrate import hydrate_settings
from simple_module_core.web.health import HealthCheckResult, HealthStatus

from mail.core import constants as c
from mail.core.settings import MailSettings
from mail.core.transports import get_mail_transport
from mail.delivery.sender import build_sender


async def resolve_sender_from_db(db: Any) -> MailSender:
    """Build a sender from the stored settings; used where none is installed.

    The outbox worker builds modules without an app, so it has only a session.
    """
    store = SettingsStore(SettingService(db))
    settings = await hydrate_settings(MailSettings, store, c.MODULE_PACKAGE, lenient=True)
    development = os.environ.get("SM_ENVIRONMENT", "development") == "development"
    transport = get_mail_transport(settings.backend, development=development)
    options = None
    if transport.settings_model is not None and transport.package is not None:
        options = await hydrate_settings(
            transport.settings_model, store, transport.package, lenient=True
        )
    return build_sender(
        settings, options=options, log_bodies=_worker_is_non_prod(), development=development
    )


def _worker_is_non_prod() -> bool:
    # No app (and so no host settings) in the worker: read the process's
    # environment the way background_tasks' own checks do.
    return os.environ.get("SM_ENVIRONMENT", "development") in NON_PROD_ENVIRONMENTS


class _UnavailableMailSender:
    # Keep callers on the send path so durable delivery fails and retries.
    delivers_email = True

    async def send(self, message: MailMessage) -> None:
        await self.verify_connection()

    async def verify_connection(self) -> None:
        raise RuntimeError("Mail transport is unavailable: configured sender construction failed")


def install_app_sender(app: Any) -> None:
    """Install a sender built from *app*'s current mail settings.

    Bodies are logged only in development or testing (host ``environment``).
    """
    log_bodies = app.state.sm.settings.environment in NON_PROD_ENVIRONMENTS
    development = app.state.sm.settings.environment == "development"
    settings = app.state.mail.settings
    try:
        transport = get_mail_transport(settings.backend, development=development)
        options = None
        if transport.package is not None:
            options = getattr(app.state, transport.package).settings
        sender = build_sender(
            settings, options=options, log_bodies=log_bodies, development=development
        )
    except Exception:
        app.state.mail.sender_failed = True
        install_default_mail_sender(_UnavailableMailSender())
        raise
    app.state.mail.sender_failed = False
    install_default_mail_sender(sender)


async def check_smtp() -> HealthCheckResult:
    """Verify the installed sender, re-read on every run.

    Settings can change after boot, so a check pinned to the boot-time sender
    would keep testing credentials the admin has replaced.
    """
    sender = current_mail_sender()
    verify = getattr(sender, "verify_connection", None)
    if verify is None:
        return HealthCheckResult(
            status=HealthStatus.HEALTHY,
            detail=f"{type(sender).__name__} needs no connection",
        )
    try:
        await verify()
    except Exception as exc:
        # The reason matters more than the traceback.
        return HealthCheckResult(status=HealthStatus.UNHEALTHY, detail=str(exc))
    return HealthCheckResult(status=HealthStatus.HEALTHY, detail="SMTP reachable")
