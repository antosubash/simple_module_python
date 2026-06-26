"""Mailer interface and factory — pick console/smtp from settings."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol, runtime_checkable

from users.settings import UsersSettings

#: Returns the live application name (e.g. from the branding module) so emails
#: are branded with the deployment's name rather than the framework default.
AppNameProvider = Callable[[], str]

#: Fallback app name when no provider is supplied (e.g. branding not installed).
DEFAULT_APP_NAME = "SimpleModule"


def default_app_name() -> str:
    return DEFAULT_APP_NAME


@runtime_checkable
class Mailer(Protocol):
    async def send_verification(self, email: str, token: str) -> None: ...
    async def send_password_reset(self, email: str, token: str) -> None: ...
    async def send_invite(self, email: str, token: str, invited_by_name: str) -> None: ...


def build_mailer(
    settings: UsersSettings,
    app_name_provider: AppNameProvider | None = None,
) -> Mailer:
    provider = app_name_provider or default_app_name
    if settings.mailer == "smtp":
        from users.mailer.smtp import SmtpMailer

        return SmtpMailer(
            host=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_username,
            password=settings.smtp_password,
            from_address=settings.smtp_from,
            use_tls=settings.smtp_tls,
            base_url=settings.base_url,
            app_name_provider=provider,
        )

    from users.mailer.console import ConsoleMailer

    return ConsoleMailer(base_url=settings.base_url, app_name_provider=provider)
