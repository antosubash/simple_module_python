"""Mail senders and the settings -> sender mapping."""

from __future__ import annotations

import contextlib
from email.message import EmailMessage

import aiosmtplib
from simple_module_core.mail import ConsoleMailSender, MailMessage, MailSender

from mail import constants as c
from mail.settings import MailSettings


class SmtpMailSender:
    """Delivers through an SMTP server with aiosmtplib."""

    delivers_email = True

    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        password: str,
        from_address: str,
        use_tls: bool,
    ) -> None:
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._from = from_address
        self._use_tls = use_tls

    async def send(self, message: MailMessage) -> None:
        email = EmailMessage()
        email["From"] = self._from
        email["To"] = message.to
        email["Subject"] = message.subject
        email.set_content(message.text)
        if message.html:
            email.add_alternative(message.html, subtype="html")

        await aiosmtplib.send(
            email,
            hostname=self._host,
            port=self._port,
            username=self._username or None,
            password=self._password or None,
            use_tls=self._use_tls,
        )

    async def verify_connection(self) -> None:
        """Open an SMTP session and authenticate, then hang up.

        Deliberately stops short of sending anything: an admin checking their
        config should not put a stray message in someone's inbox. Raises
        whatever aiosmtplib raises so the caller can show the real reason.
        """
        client = aiosmtplib.SMTP(hostname=self._host, port=self._port, use_tls=self._use_tls)
        await client.connect()
        try:
            if self._username:
                await client.login(self._username, self._password or "")
        finally:
            # A failure hanging up must not mask the login error being unwound.
            with contextlib.suppress(Exception):
                await client.quit()


def build_sender(settings: MailSettings, *, log_bodies: bool = True) -> MailSender:
    """``smtp`` -> :class:`SmtpMailSender`; ``console`` -> a logging sender.

    *log_bodies* is false outside development and testing: a console backend
    left in place in production must not write reset and invite tokens to the
    log, so there it logs only recipient and subject.
    """
    if settings.backend == c.BACKEND_SMTP:
        return SmtpMailSender(
            host=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_username,
            password=settings.smtp_password,
            from_address=settings.smtp_from,
            use_tls=settings.smtp_tls,
        )
    return ConsoleMailSender(include_body=log_bodies)
