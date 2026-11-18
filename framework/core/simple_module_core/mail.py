"""Outgoing mail: the message type, the sender protocol and the process's sender.

Modules send through :func:`current_mail_sender` (web code) or
:func:`resolve_mail_sender` (code that may run in the outbox worker) and never
need to know whether mail is configured: with nothing installed both return a
:class:`ConsoleMailSender`, which logs the message instead of delivering it.

The transport (SMTP and its settings) belongs to the ``mail`` module, which
installs a sender in a web process and a resolver everywhere. The state is
process-level rather than on ``app.state`` because the outbox worker builds
modules without an app (``register_event_handlers(bus, None)``), so a durable
handler has only its database session to go on (GH #496).
"""

from __future__ import annotations

import base64
import logging
import re
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from email import policy
from email.errors import HeaderParseError
from typing import Annotated, Any, Protocol, runtime_checkable

from pydantic import BeforeValidator, ConfigDict, field_serializer, field_validator
from sqlmodel import SQLModel

logger = logging.getLogger("simple_module.mail")

MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024
_MEDIA_TYPE = re.compile(
    r"[A-Za-z0-9][A-Za-z0-9!#$&^_.+-]{0,126}/[A-Za-z0-9][A-Za-z0-9!#$&^_.+-]{0,126}"
)


class MailAttachment(SQLModel):
    """An attached file; content is bytes in Python and base64 in durable JSON."""

    model_config = ConfigDict(frozen=True)  # ty: ignore[invalid-assignment]

    filename: str
    content_type: str
    content: bytes

    @field_validator("filename")
    @classmethod
    def validate_filename(cls, value: str) -> str:
        if (
            not value
            or value in {".", ".."}
            or any(c in value for c in "/\\")
            or any(ord(c) < 32 or ord(c) == 127 for c in value)
        ):
            raise ValueError(
                "attachment filename must be nonempty with no path separators or control characters"
            )
        return value

    @field_validator("content_type")
    @classmethod
    def validate_content_type(cls, value: str) -> str:
        if not _MEDIA_TYPE.fullmatch(value):
            raise ValueError(
                "attachment content_type must be a valid type/subtype without parameters"
            )
        if value.split("/", 1)[0].lower() in {"message", "multipart"}:
            raise ValueError(
                "attachment structured MIME types (message/*, multipart/*) are not supported"
            )
        return value

    @field_validator("content", mode="before")
    @classmethod
    def decode_content(cls, value: Any) -> Any:
        if isinstance(value, str):
            return base64.b64decode(value, validate=True)
        return value

    @field_serializer("content", when_used="json")
    def encode_content(self, value: bytes) -> str:
        return base64.b64encode(value).decode("ascii")


def _check_encoded_attachment_size(value: Any) -> Any:
    if not isinstance(value, (list, tuple)):
        return value
    encoded_length = padding = 0
    for item in value:
        if isinstance(item, dict) and isinstance(content := item.get("content"), str):
            encoded_length += len(content)
            padding += 2 if content.endswith("==") else int(content.endswith("="))
    # Four base64 characters encode three bytes, less each file's terminal padding.
    if encoded_length * 3 > (MAX_ATTACHMENT_BYTES + padding) * 4:
        raise ValueError(
            f"attachment total size must not exceed {MAX_ATTACHMENT_BYTES} bytes (10 MiB)"
        )
    return value


def _validate_reply_to(value: str) -> None:
    error = "reply_to must be one email address without control characters"
    if not value or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ValueError(error)
    try:
        header = policy.default.header_factory("To", value)
    except (ValueError, HeaderParseError) as exc:
        raise ValueError(error) from exc
    if (
        header.defects
        or len(header.addresses) != 1
        or any(group.display_name is not None for group in header.groups)
    ):
        raise ValueError(error)
    address = header.addresses[0]
    if not address.username or not address.domain:
        raise ValueError(error)


@dataclass(frozen=True)
class MailMessage:
    to: str
    subject: str
    text: str
    html: str | None = None
    attachments: Annotated[
        Sequence[MailAttachment], BeforeValidator(_check_encoded_attachment_size)
    ] = ()
    reply_to: str | None = None

    def __post_init__(self) -> None:
        if self.reply_to is not None:
            _validate_reply_to(self.reply_to)
        object.__setattr__(self, "attachments", tuple(self.attachments))
        if sum(len(item.content) for item in self.attachments) > MAX_ATTACHMENT_BYTES:
            raise ValueError(
                f"attachment total size must not exceed {MAX_ATTACHMENT_BYTES} bytes (10 MiB)"
            )


@runtime_checkable
class MailSender(Protocol):
    #: ``False`` for a sender that only logs: screens use it to hand the link
    #: back to the person instead of promising an inbox.
    delivers_email: bool

    async def send(self, message: MailMessage) -> None: ...


class ConsoleMailSender:
    """Logs each message instead of sending it.

    With ``include_body`` (the ``mail`` module's explicit ``console`` backend,
    for development) the body is logged, so a developer can follow a
    reset or invite link. The fallback used when no transport is installed
    passes ``include_body=False``: those bodies carry one-time tokens and must
    not end up in a production log just because mail was never configured.
    Attachments are logged only as filenames and byte counts in either mode.
    """

    delivers_email = False

    def __init__(self, *, include_body: bool = True) -> None:
        self.include_body = include_body

    async def send(self, message: MailMessage) -> None:
        extra = {
            "mail_to": message.to,
            "mail_subject": message.subject,
            "mail_reply_to": message.reply_to,
        }
        reply_to = f" (Reply-To: {message.reply_to})" if message.reply_to else ""
        for attachment in message.attachments:
            logger.log(
                logging.INFO if self.include_body else logging.WARNING,
                "Mail attachment (not sent): %s (%d bytes)",
                attachment.filename,
                len(attachment.content),
                extra=extra,
            )
        if self.include_body:
            logger.info(
                "Mail to %s%s (not sent, console sender): %s\n%s",
                message.to,
                reply_to,
                message.subject,
                message.text,
                extra=extra,
            )
        else:
            logger.warning(
                "Mail to %s%s not sent: no mail transport is installed (%s)",
                message.to,
                reply_to,
                message.subject,
                extra=extra,
            )


#: Builds a sender from the database (``AsyncSession``); used where no sender
#: is installed, i.e. in the outbox worker.
MailSenderResolver = Callable[[Any], Awaitable[MailSender]]

_sender: MailSender | None = None
_resolver: MailSenderResolver | None = None


def install_mail_sender(sender: MailSender | None) -> None:
    """Set (or with ``None`` clear) this process's sender."""
    global _sender
    _sender = sender


def install_mail_resolver(resolver: MailSenderResolver | None) -> None:
    """Set (or with ``None`` clear) the factory used when no sender is installed."""
    global _resolver
    _resolver = resolver


def reset_mail_sender() -> None:
    """Clear the process sender and resolver between isolated app/test runs."""
    install_mail_sender(None)
    install_mail_resolver(None)


def mail_transport_installed() -> bool:
    """Whether a transport (sender or resolver) is installed in this process.

    False means mail would only reach the fallback log. A durable handler uses
    it to fail, and be retried, rather than drop mail in a worker that was
    started without the ``mail`` module while the web process has it.
    """
    return _sender is not None or _resolver is not None


def current_mail_sender() -> MailSender:
    """The installed sender, else a console sender. Never raises."""
    return _sender if _sender is not None else ConsoleMailSender(include_body=False)


async def resolve_mail_sender(db: Any | None = None) -> MailSender:
    """The installed sender, else one built by the resolver from *db*, else console."""
    if _sender is None and _resolver is not None and db is not None:
        return await _resolver(db)
    return current_mail_sender()
