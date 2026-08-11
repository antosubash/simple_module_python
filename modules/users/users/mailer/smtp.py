"""SMTP mailer — sends emails via aiosmtplib with Jinja2 templates."""

from __future__ import annotations

import importlib.resources
from email.message import EmailMessage
from typing import TYPE_CHECKING

import aiosmtplib
import jinja2

if TYPE_CHECKING:
    from users.mailer import AppNameProvider


def _load_template_env() -> jinja2.Environment:
    """Build a Jinja2 Environment pointed at the bundled templates directory."""
    templates_path = importlib.resources.files(__package__) / "templates"
    return jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(templates_path)),
        autoescape=False,
    )


# Resolve the template directory at import time — deterministic, async-safe,
# and the filesystem path is known by then anyway.
_template_env: jinja2.Environment = _load_template_env()


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
        app_name_provider: AppNameProvider | None = None,
    ) -> None:
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._from = from_address
        self._use_tls = use_tls
        self._base = base_url.rstrip("/")
        from users.mailer import default_app_name

        self._app_name = app_name_provider or default_app_name

    async def send_verification(self, email: str, token: str) -> None:
        app = self._app_name()
        link = f"{self._base}/users/verify?token={token}"
        template = _template_env.get_template("verify_email.txt")
        body = template.render(link=link, app_name=app)
        await self._send(email, f"Verify your email for {app}", body)

    async def send_password_reset(self, email: str, token: str) -> None:
        app = self._app_name()
        link = f"{self._base}/users/reset-password?token={token}"
        template = _template_env.get_template("reset_password.txt")
        body = template.render(link=link, app_name=app)
        await self._send(email, f"Reset your {app} password", body)

    async def send_invite(self, email: str, token: str, invited_by_name: str) -> None:
        app = self._app_name()
        link = f"{self._base}/users/invite/accept?token={token}"
        template = _template_env.get_template("invite.txt")
        body = template.render(link=link, invited_by_name=invited_by_name, app_name=app)
        await self._send(email, f"{invited_by_name} invited you to {app}", body)

    async def verify_connection(self) -> None:
        """Open an SMTP session and authenticate, then hang up.

        Deliberately stops short of sending anything: an admin checking their
        mailer config should not put a stray message in someone's inbox. This
        catches the failures that actually happen — wrong host or port, TLS
        mismatch, bad credentials — and raises whatever aiosmtplib raises so
        the caller can show the real reason.
        """
        client = aiosmtplib.SMTP(hostname=self._host, port=self._port, use_tls=self._use_tls)
        await client.connect()
        try:
            if self._username:
                await client.login(self._username, self._password or "")
        finally:
            # noop() before quit keeps a server that dislikes an abrupt close
            # from logging this probe as an error.
            try:
                await client.quit()
            except Exception:
                pass

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
