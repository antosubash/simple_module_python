"""Resolver and health check: the parts that work without an app."""

from __future__ import annotations

from typing import Any

from settings.hydrate import hydrate_settings
from settings.service import SettingService
from settings.store import SettingsStore
from simple_module_core.health import HealthCheckResult, HealthStatus
from simple_module_core.mail import MailSender, current_mail_sender

from mail import constants as c
from mail.sender import build_sender
from mail.settings import MailSettings


async def resolve_sender_from_db(db: Any) -> MailSender:
    """Build a sender from the stored settings; used where none is installed.

    The outbox worker builds modules without an app, so it has only a session.
    """
    store = SettingsStore(SettingService(db))
    settings = await hydrate_settings(MailSettings, store, c.MODULE_PACKAGE, lenient=True)
    return build_sender(settings)


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
