"""Module-owned state attached to ``app.state.mail``."""

from __future__ import annotations

from dataclasses import dataclass

from mail.core.settings import MailSettings


@dataclass
class MailState:
    """``settings`` is reassigned in place on a hot reload, so stay mutable."""

    settings: MailSettings
