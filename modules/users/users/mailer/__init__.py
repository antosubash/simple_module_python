"""Mailer interface and factory — built-in templated mailer."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from inspect import Parameter, signature
from pathlib import Path
from typing import Protocol, TypedDict, runtime_checkable

from simple_module_hosting.pipeline.public_urls import public_origin, trusted_request_origin
from starlette.requests import Request

from users.core.settings import UsersSettings
from users.mailer.templated import TemplatedMailer

#: Returns the live application name (e.g. from the branding module) so emails
#: are branded with the deployment's name rather than the framework default.
AppNameProvider = Callable[[], str]

#: Fallback app name when no provider is supplied (e.g. branding not installed).
DEFAULT_APP_NAME = "SimpleModule"


def default_app_name() -> str:
    return DEFAULT_APP_NAME


class MailLinkOptions(TypedDict, total=False):
    link_origin: str


_SEND_METHODS = ("send_verification", "send_password_reset", "send_invite")


def _accepts_link_origin(mailer: TemplatedMailer) -> bool:
    """A subclass overriding a send method with the original signature opts out."""
    for name in _SEND_METHODS:
        params = signature(getattr(mailer, name)).parameters
        if "link_origin" not in params and not any(
            p.kind is Parameter.VAR_KEYWORD for p in params.values()
        ):
            return False
    return True


def request_mail_options(mailer: object, request: Request | None) -> MailLinkOptions:
    # A configured origin always wins, so the request origin is only offered
    # without one, and only to mailers whose send methods take the keyword.
    if (
        isinstance(mailer, TemplatedMailer)
        and not mailer.has_configured_origin
        and request is not None
        and _accepts_link_origin(mailer)
        and (origin := trusted_request_origin(request)) is not None
    ):
        return {"link_origin": origin}
    return {}


@runtime_checkable
class Mailer(Protocol):
    """The send interface a third-party mailer implements.

    The built-in ``TemplatedMailer`` also accepts a keyword-only
    ``link_origin``; callers pass it only after ``request_mail_options``
    confirms the concrete mailer takes it, so this protocol keeps the original
    signatures and existing implementations still type-check.
    """

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


def mailer_delivers(
    mailer: object | None,
    *,
    link_origin: str | None = None,
    log_missing_origin: bool = False,
) -> bool:
    """Whether *mailer* actually puts mail in front of a person.

    Four screens branch on this — the reset-sent card, add-people, resend
    invite and bulk invite — and each had its own copy of the same two-part
    guard. It is one question with one answer: no mailer at all delivers
    nothing, and a console sender only writes the link to the log, so both
    have to hand the link back instead of promising an inbox. Takes the mailer
    rather than the settings because ``delivers_email`` is the mailer's own
    claim; a third-party mailer that never set the flag is taken at its word.
    """
    if (
        isinstance(mailer, TemplatedMailer)
        and type(mailer).delivers_email is TemplatedMailer.delivers_email
    ):
        return mailer.delivers_with_origin(link_origin, log_missing_origin=log_missing_origin)
    return bool(mailer is not None and getattr(mailer, "delivers_email", True))


def build_mailer(
    settings: UsersSettings,
    app_name_provider: AppNameProvider | None = None,
    *,
    template_dirs: Sequence[str | Path] = (),
    base_url_provider: Callable[[], str] | None = None,
) -> Mailer:
    return TemplatedMailer(
        base_url=base_url_provider or public_origin(None, settings.base_url),
        app_name_provider=app_name_provider,
        template_dirs=template_dirs,
    )
