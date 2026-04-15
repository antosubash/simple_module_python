"""Mailer interface and factory — pick console/smtp from settings."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from users.settings import UsersSettings


@runtime_checkable
class Mailer(Protocol):
    async def send_verification(self, email: str, token: str) -> None: ...
    async def send_password_reset(self, email: str, token: str) -> None: ...
    async def send_invite(self, email: str, token: str, invited_by_name: str) -> None: ...


def build_mailer(settings: UsersSettings) -> Mailer:
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
        )

    from users.mailer.console import ConsoleMailer

    return ConsoleMailer(base_url=settings.base_url)
