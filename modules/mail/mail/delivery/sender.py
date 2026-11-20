"""Mail senders and the settings -> sender mapping."""

from __future__ import annotations

import contextlib
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from typing import Any

import aiosmtplib
from simple_module_core.mail import (
    MailMessage,
    MailSender,
    smtp_address_header,
    validate_mail_headers,
)

from mail.core import constants as c
from mail.core.settings import MailSettings
from mail.core.transports import get_mail_transport


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
        email["From"] = smtp_address_header(self._from)
        email["To"] = smtp_address_header(message.to)
        if message.reply_to is not None:
            email["Reply-To"] = smtp_address_header(message.reply_to)
        email["Subject"] = message.subject
        email["Date"] = formatdate(localtime=False, usegmt=True)
        from_header = email["From"]
        domain = None
        if not from_header.defects and len(from_header.addresses) == 1:
            domain = from_header.addresses[0].domain or None
        email["Message-ID"] = make_msgid(domain=domain)
        # Revalidate because a frozen dataclass can still contain a mutable dictionary.
        for name, value in validate_mail_headers(message.headers).items():
            email[name] = value
        email.set_content(message.text)
        if message.html:
            email.add_alternative(message.html, subtype="html")
        for attachment in message.attachments:
            maintype, subtype = attachment.content_type.split("/")
            email.add_attachment(
                attachment.content,
                maintype=maintype,
                subtype=subtype,
                filename=attachment.filename,
            )

        await aiosmtplib.send(
            email,
            # Never infer the SMTP envelope from custom or trace headers.
            sender=from_header.addresses[0].addr_spec,
            recipients=[address.addr_spec for address in email["To"].addresses],
            hostname=self._host,
            port=self._port,
            username=self._username or None,
            password=self._password or None,
            use_tls=self._use_tls,
            timeout=c.SMTP_TIMEOUT_SECONDS,
        )

    async def verify_connection(self) -> None:
        """Open an SMTP session and authenticate, then hang up.

        Deliberately stops short of sending anything: an admin checking their
        config should not put a stray message in someone's inbox. Raises
        whatever aiosmtplib raises so the caller can show the real reason.
        """
        client = aiosmtplib.SMTP(
            hostname=self._host,
            port=self._port,
            use_tls=self._use_tls,
            timeout=c.SMTP_TIMEOUT_SECONDS,
        )
        await client.connect()
        try:
            if self._username:
                await client.login(self._username, self._password or "")
        finally:
            # A failure hanging up must not mask the login error being unwound.
            with contextlib.suppress(Exception):
                await client.quit()


def build_sender(
    settings: MailSettings,
    *,
    log_bodies: bool = True,
    development: bool = True,
    options: Any = None,
) -> MailSender:
    """Build the selected registered transport with its module-owned options.

    *log_bodies* is false outside development and testing: a console backend
    left in place in production must not write reset and invite tokens to the
    log, so there it logs only recipient, subject and attachment metadata.
    """
    transport = get_mail_transport(settings.backend, development=development)
    return transport.factory(settings if options is None else options, log_bodies)
