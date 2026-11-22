"""Mail senders and the settings -> sender mapping."""

from __future__ import annotations

import contextlib
from email import policy
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


class _SmtpPolicy(policy.EmailPolicy):
    """Keep UTF-8 header lines within SMTP's byte limit."""

    def fold_binary(self, name: str, value: Any) -> bytes:
        folded = super().fold_binary(name, value)
        if self.utf8 and any(len(line) > 998 for line in folded.split(b"\r\n")):
            # The stdlib counts characters; UTF-8 needs up to four bytes each.
            return policy.EmailPolicy.fold_binary(self.clone(max_line_length=998 // 4), name, value)
        return folded


def _tls_kwargs(port: int, use_tls: bool) -> dict[str, bool]:
    """Use implicit TLS on 465 and STARTTLS on submission ports."""
    return {"use_tls": use_tls and port == 465, "start_tls": use_tls and port != 465}


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

        # Never infer the SMTP envelope from custom or trace headers.
        sender = from_header.addresses[0].addr_spec
        recipients = [address.addr_spec for address in email["To"].addresses]
        utf8_required = not (sender.isascii() and all(address.isascii() for address in recipients))
        # Typeshed's EmailPolicy constructor self type excludes subclasses.
        wire_policy = _SmtpPolicy(  # ty: ignore[invalid-argument-type]
            utf8=utf8_required, linesep="\r\n"
        )
        # Avoid encoded words in long RFC 2369 URLs; bytes bypass aiosmtplib's refolding.
        wire = email.as_bytes(policy=wire_policy.clone(max_line_length=998, cte_type="7bit"))
        tls = _tls_kwargs(self._port, self._use_tls)
        await aiosmtplib.send(
            wire,
            sender=sender,
            recipients=recipients,
            mail_options=["SMTPUTF8"] if utf8_required else [],
            hostname=self._host,
            port=self._port,
            username=self._username or None,
            password=self._password or None,
            use_tls=tls["use_tls"],
            start_tls=tls["start_tls"],
            timeout=c.SMTP_TIMEOUT_SECONDS,
        )

    async def verify_connection(self) -> None:
        """Open an SMTP session and authenticate, then hang up.

        Deliberately stops short of sending anything: an admin checking their
        config should not put a stray message in someone's inbox. Raises
        whatever aiosmtplib raises so the caller can show the real reason.
        """
        tls = _tls_kwargs(self._port, self._use_tls)
        client = aiosmtplib.SMTP(
            hostname=self._host,
            port=self._port,
            use_tls=tls["use_tls"],
            start_tls=tls["start_tls"],
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
