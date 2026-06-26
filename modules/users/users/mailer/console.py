"""Console mailer — logs tokenized links for local development."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from users.mailer import AppNameProvider

logger = logging.getLogger("users.mailer")


class ConsoleMailer:
    def __init__(self, base_url: str, app_name_provider: AppNameProvider | None = None) -> None:
        self._base = base_url.rstrip("/")
        from users.mailer import default_app_name

        self._app_name = app_name_provider or default_app_name

    async def send_verification(self, email: str, token: str) -> None:
        link = f"{self._base}/users/verify?token={token}"
        logger.info(
            "users.verify.email", extra={"to": email, "link": link, "app_name": self._app_name()}
        )

    async def send_password_reset(self, email: str, token: str) -> None:
        link = f"{self._base}/users/reset-password?token={token}"
        logger.info(
            "users.reset.email", extra={"to": email, "link": link, "app_name": self._app_name()}
        )

    async def send_invite(self, email: str, token: str, invited_by_name: str) -> None:
        link = f"{self._base}/users/invite/accept?token={token}"
        logger.info(
            "users.invite.email",
            extra={
                "to": email,
                "link": link,
                "invited_by": invited_by_name,
                "app_name": self._app_name(),
            },
        )
