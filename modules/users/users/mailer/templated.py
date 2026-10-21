"""Built-in mailer: renders the bundled templates and hands them to the mail sender.

Transport (SMTP, console, ...) belongs to the ``mail`` module. The sender is
looked up at send time so a settings change there takes effect without a
restart, and ``delivers_email`` reads it live for the same reason.
"""

from __future__ import annotations

import importlib.resources
from typing import TYPE_CHECKING, Any

import jinja2
from simple_module_core.mail import MailMessage, current_mail_sender

if TYPE_CHECKING:
    from users.mailer import AppNameProvider

_TPL_VERIFY = "verify_email.txt"
_TPL_RESET = "reset_password.txt"
_TPL_INVITE = "invite.txt"


# The bundled templates directory; plain text, so no autoescape.
_template_env = jinja2.Environment(
    loader=jinja2.FileSystemLoader(str(importlib.resources.files(__package__) / "templates")),
    autoescape=False,
)


class TemplatedMailer:
    def __init__(self, base_url: str, app_name_provider: AppNameProvider | None = None) -> None:
        self._base = base_url.rstrip("/")
        from users.mailer import default_app_name

        self._app_name = app_name_provider or default_app_name

    @property
    def delivers_email(self) -> bool:
        """Whether the installed sender puts mail in front of a person."""
        return current_mail_sender().delivers_email

    async def send_verification(self, email: str, token: str) -> None:
        app = self._app_name()
        link = f"{self._base}/users/verify?token={token}"
        await self._send(email, f"Verify your email for {app}", _TPL_VERIFY, link=link)

    async def send_password_reset(self, email: str, token: str) -> None:
        app = self._app_name()
        link = f"{self._base}/users/reset-password?token={token}"
        await self._send(email, f"Reset your {app} password", _TPL_RESET, link=link)

    async def send_invite(
        self,
        email: str,
        token: str,
        invited_by_name: str,
        message: str | None = None,
    ) -> None:
        app = self._app_name()
        link = f"{self._base}/users/invite/accept?token={token}"
        await self._send(
            email,
            f"{invited_by_name} invited you to {app}",
            _TPL_INVITE,
            link=link,
            invited_by_name=invited_by_name,
            # Stripped here rather than in the template: a message of nothing
            # but whitespace should leave no quoted block behind.
            message=(message or "").strip() or None,
        )

    async def _send(self, to: str, subject: str, template_name: str, **context: Any) -> None:
        body = _template_env.get_template(template_name).render(
            app_name=self._app_name(), **context
        )
        await current_mail_sender().send(MailMessage(to=to, subject=subject, text=body))
