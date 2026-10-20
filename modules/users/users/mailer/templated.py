"""Built-in mailer: renders the bundled templates and hands them to the mail sender.

Transport (SMTP, console, ...) belongs to the ``mail`` module. The sender is
looked up at send time so a settings change there takes effect without a
restart, and ``delivers_email`` reads it live for the same reason.
"""

from __future__ import annotations

import importlib.resources
from typing import TYPE_CHECKING

import jinja2
from simple_module_core.mail import MailMessage, current_mail_sender

if TYPE_CHECKING:
    from users.mailer import AppNameProvider

_TPL_VERIFY = "verify_email.txt"
_TPL_RESET = "reset_password.txt"
_TPL_INVITE = "invite.txt"


def _load_template_env() -> jinja2.Environment:
    """Build a Jinja2 Environment pointed at the bundled templates directory."""
    templates_path = importlib.resources.files(__package__) / "templates"
    return jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(templates_path)),
        autoescape=False,
    )


_template_env: jinja2.Environment = _load_template_env()


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
        body = _template_env.get_template(_TPL_VERIFY).render(link=link, app_name=app)
        await self._send(email, f"Verify your email for {app}", body)

    async def send_password_reset(self, email: str, token: str) -> None:
        app = self._app_name()
        link = f"{self._base}/users/reset-password?token={token}"
        body = _template_env.get_template(_TPL_RESET).render(link=link, app_name=app)
        await self._send(email, f"Reset your {app} password", body)

    async def send_invite(
        self,
        email: str,
        token: str,
        invited_by_name: str,
        message: str | None = None,
    ) -> None:
        app = self._app_name()
        link = f"{self._base}/users/invite/accept?token={token}"
        body = _template_env.get_template(_TPL_INVITE).render(
            link=link,
            invited_by_name=invited_by_name,
            app_name=app,
            # Stripped here rather than in the template: a message of nothing
            # but whitespace should leave no quoted block behind.
            message=(message or "").strip() or None,
        )
        await self._send(email, f"{invited_by_name} invited you to {app}", body)

    async def _send(self, to: str, subject: str, body: str) -> None:
        await current_mail_sender().send(MailMessage(to=to, subject=subject, text=body))
