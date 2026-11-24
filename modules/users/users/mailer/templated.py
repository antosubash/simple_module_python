"""Built-in mailer: renders host or bundled templates and hands them to the mail sender.

Transport (SMTP, console, ...) belongs to the ``mail`` module. The sender is
looked up at send time so a settings change there takes effect without a
restart, and ``delivers_email`` reads it live for the same reason.
"""

from __future__ import annotations

import importlib.resources
import logging
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

import jinja2
import jinja2.sandbox
from simple_module_core.mailer.mail import MailMessage, current_mail_sender

from users.core.constants import MAIL_TEMPLATE_INVITE, MAIL_TEMPLATE_RESET, MAIL_TEMPLATE_VERIFY

if TYPE_CHECKING:
    from users.mailer import AppNameProvider

logger = logging.getLogger(__name__)
_MISSING_ORIGIN = (
    "Account email skipped: configure host.public_base_url / SM_PUBLIC_BASE_URL "
    "(or users.base_url) for absolute links"
)


class TemplatedMailer:
    def __init__(
        self,
        base_url: str | Callable[[], str],
        app_name_provider: AppNameProvider | None = None,
        *,
        template_dirs: Sequence[str | Path] = (),
    ) -> None:
        self._base_url = base_url
        from users.mailer import default_app_name

        self._app_name = app_name_provider or default_app_name
        # An admin edits this setting in the UI; a bad entry must not stop the
        # app from booting, so it is skipped with a warning instead.
        directories = []
        for directory in map(Path, template_dirs):
            if directory.is_absolute() and directory.is_dir():
                directories.append(directory)
            else:
                logger.warning(
                    "Ignoring mail template path %s: not an existing absolute directory",
                    directory,
                )
        # Sandboxed: the setting is editable from the admin UI, so a template
        # dropped into a writable directory (an upload folder) must not be able
        # to run arbitrary Python.
        self._template_env = jinja2.sandbox.SandboxedEnvironment(
            loader=jinja2.FileSystemLoader(
                [*directories, str(importlib.resources.files(__package__) / "templates")]
            ),
            autoescape=jinja2.select_autoescape(enabled_extensions=("html",), default=False),
        )

    @property
    def _base(self) -> str:
        origin = self._base_url() if callable(self._base_url) else self._base_url
        return origin.rstrip("/")

    @property
    def delivers_email(self) -> bool:
        """Whether the installed sender puts mail in front of a person."""
        return self.delivers_with_origin()

    def delivers_with_origin(
        self, link_origin: str | None = None, *, log_missing_origin: bool = False
    ) -> bool:
        if not (self._base or link_origin):
            if log_missing_origin:
                logger.error(_MISSING_ORIGIN)
            return False
        return current_mail_sender().delivers_email

    async def send_verification(
        self, email: str, token: str, *, link_origin: str | None = None
    ) -> None:
        app = self._app_name()
        link = f"/users/verify?token={token}"
        await self._send(
            email,
            f"Verify your email for {app}",
            MAIL_TEMPLATE_VERIFY,
            app_name=app,
            link=link,
            link_origin=link_origin,
        )

    async def send_password_reset(
        self, email: str, token: str, *, link_origin: str | None = None
    ) -> None:
        app = self._app_name()
        link = f"/users/reset-password?token={token}"
        await self._send(
            email,
            f"Reset your {app} password",
            MAIL_TEMPLATE_RESET,
            app_name=app,
            link=link,
            link_origin=link_origin,
        )

    async def send_invite(
        self,
        email: str,
        token: str,
        invited_by_name: str,
        message: str | None = None,
        *,
        link_origin: str | None = None,
    ) -> None:
        app = self._app_name()
        link = f"/users/invite/accept?token={token}"
        await self._send(
            email,
            f"{invited_by_name} invited you to {app}",
            MAIL_TEMPLATE_INVITE,
            app_name=app,
            link=link,
            link_origin=link_origin,
            invited_by_name=invited_by_name,
            # Stripped here rather than in the template: a message of nothing
            # but whitespace should leave no quoted block behind.
            message=(message or "").strip() or None,
        )

    async def _send(
        self,
        to: str,
        subject: str,
        template_name: str,
        *,
        link: str,
        link_origin: str | None,
        **context: Any,
    ) -> None:
        base = self._base or link_origin
        if not base:
            logger.error(_MISSING_ORIGIN)
            return
        context["link"] = f"{base}{link}"
        body = self._template_env.get_template(template_name).render(**context)
        html_name = str(Path(template_name).with_suffix(".html"))
        try:
            html_template = self._template_env.get_template(html_name)
        except jinja2.TemplateNotFound as exc:
            if exc.name != html_name:
                raise
            html_template = None
        html = html_template.render(**context) if html_template is not None else None
        await current_mail_sender().send(MailMessage(to=to, subject=subject, text=body, html=html))
