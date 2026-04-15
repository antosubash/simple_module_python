"""SMTP mailer — sends emails via aiosmtplib with Jinja2 templates."""

from __future__ import annotations

import importlib.resources
from email.message import EmailMessage

import aiosmtplib
import jinja2


def _load_template_env() -> jinja2.Environment:
    """Build a Jinja2 Environment pointed at the bundled templates directory."""
    templates_path = importlib.resources.files(__package__) / "templates"
    return jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(templates_path)),
        autoescape=False,
    )


_template_env: jinja2.Environment | None = None


def _get_template_env() -> jinja2.Environment:
    global _template_env
    if _template_env is None:
        _template_env = _load_template_env()
    return _template_env


class SmtpMailer:
    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        password: str,
        from_address: str,
        use_tls: bool,
        base_url: str,
    ) -> None:
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._from = from_address
        self._use_tls = use_tls
        self._base = base_url.rstrip("/")

    async def send_verification(self, email: str, token: str) -> None:
        link = f"{self._base}/users/verify?token={token}"
        template = _get_template_env().get_template("verify_email.txt")
        body = template.render(link=link)
        await self._send(email, "Verify your email address", body)

    async def send_password_reset(self, email: str, token: str) -> None:
        link = f"{self._base}/users/reset-password?token={token}"
        template = _get_template_env().get_template("reset_password.txt")
        body = template.render(link=link)
        await self._send(email, "Reset your password", body)

    async def send_invite(self, email: str, token: str, invited_by_name: str) -> None:
        link = f"{self._base}/users/invite/accept?token={token}"
        template = _get_template_env().get_template("invite.txt")
        body = template.render(link=link, invited_by_name=invited_by_name)
        await self._send(email, f"You've been invited by {invited_by_name}", body)

    async def _send(self, to: str, subject: str, body: str) -> None:
        message = EmailMessage()
        message["From"] = self._from
        message["To"] = to
        message["Subject"] = subject
        message.set_content(body)

        await aiosmtplib.send(
            message,
            hostname=self._host,
            port=self._port,
            username=self._username or None,
            password=self._password or None,
            use_tls=self._use_tls,
        )
