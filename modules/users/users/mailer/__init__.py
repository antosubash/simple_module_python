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
    # *message* is the optional note the inviter typed on the batch form.
    # Keyword-defaulted so a third-party mailer written against the older
    # three-argument signature keeps satisfying this protocol.
    async def send_invite(
        self,
        email: str,
        token: str,
        invited_by_name: str,
        message: str | None = None,
    ) -> None: ...


def mailer_delivers(mailer: object | None) -> bool:
    """Whether *mailer* actually puts mail in front of a person.

    Four screens branch on this — the reset-sent card, add-people, resend
    invite and bulk invite — and each had its own copy of the same two-part
    guard. It is one question with one answer: no mailer at all delivers
    nothing, and the console mailer only writes the link to the log, so both
    have to hand the link back instead of promising an inbox. Takes the mailer
    rather than the settings because ``delivers_email`` is the mailer's own
    claim; a third-party mailer that never set the flag is taken at its word.
    """
    return bool(mailer is not None and getattr(mailer, "delivers_email", True))


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
